"""
backend_server.py — FastAPI backend handling all tool business logic.

The voice agent POSTs here for:
  - Booking creation (fire-and-forget)
  - Availability checks (sync — agent needs slot data)
  - Business hours (sync — agent needs status)
  - Post-call processing (fire-and-forget: sentiment, DB, notifications, webhooks)
  - Transcript streaming (fire-and-forget)
  - Active call upserts (fire-and-forget)

Runs on port 8001 alongside the agent (port 8081) and ui_server (port 8000).
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timedelta

import pytz
from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import JSONResponse

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend-server")

app = FastAPI(title="Voice Agent Backend")


# ══════════════════════════════════════════════════════════════════════════════
# TOOL ENDPOINTS — Called by agent tool functions
# ══════════════════════════════════════════════════════════════════════════════


@app.get("/api/tools/availability")
async def tool_check_availability(date: str):
    """Check available appointment slots for a given date. Synchronous — agent waits."""
    from calendar_tools import get_available_slots

    logger.info(f"[AVAILABILITY] Checking slots for {date}")
    try:
        slots = get_available_slots(date)
        if not slots:
            return {"slots": [], "message": f"No available slots on {date}."}
        slot_strings = [s.get("start_time", str(s))[-8:][:5] for s in slots[:6]]
        return {"slots": slots, "formatted": ", ".join(slot_strings), "date": date}
    except Exception as e:
        logger.error(f"[AVAILABILITY] Failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "message": "Failed to check availability."},
        )


@app.get("/api/tools/business-hours")
async def tool_business_hours():
    """Check if the business is currently open. Synchronous — agent waits."""
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    hours = {
        0: ("Monday", "10:00", "19:00"),
        1: ("Tuesday", "10:00", "19:00"),
        2: ("Wednesday", "10:00", "19:00"),
        3: ("Thursday", "10:00", "19:00"),
        4: ("Friday", "10:00", "19:00"),
        5: ("Saturday", "10:00", "17:00"),
        6: ("Sunday", None, None),
    }
    day_name, open_t, close_t = hours[now.weekday()]
    current_time = now.strftime("%H:%M")

    if open_t is None:
        return {
            "status": "closed",
            "message": "We are closed on Sundays. Next opening: Monday 10:00 AM IST.",
        }
    if open_t <= current_time <= close_t:
        return {
            "status": "open",
            "message": f"We are OPEN. Today ({day_name}): {open_t}–{close_t} IST.",
        }
    return {
        "status": "closed",
        "message": f"We are CLOSED. Today ({day_name}): {open_t}–{close_t} IST.",
    }


@app.post("/api/tools/book-site-visit", status_code=202)
async def tool_book_site_visit(request: Request, background_tasks: BackgroundTasks):
    """
    Fire-and-forget: Accept site visit request, send WhatsApp/Telegram in background.
    No calendar booking API is used.
    """
    data = await request.json()
    logger.info(f"[SITE-VISIT] Received: {data.get('caller_name')} at {data.get('visit_time')}")
    background_tasks.add_task(_process_site_visit, data)
    return {"accepted": True, "message": "Site visit request is being processed."}


async def _process_site_visit(data: dict):
    """Background task: send site visit notifications."""
    from notify import notify_site_visit_requested

    visit_time = data.get("visit_time", "")
    caller_name = data.get("caller_name", "Unknown")
    caller_phone = data.get("caller_phone", "unknown")
    property_preferences = data.get("property_preferences", "")
    notes = data.get("notes", "")
    tts_voice = data.get("tts_voice", "")

    try:
        notify_site_visit_requested(
            caller_name=caller_name,
            caller_phone=caller_phone,
            site_visit_time=visit_time,
            property_preferences=property_preferences,
            notes=notes,
            tts_voice=tts_voice,
            ai_summary="",
        )
        logger.info(f"[SITE-VISIT] Confirmed notification sent for {caller_name}")
    except Exception as e:
        logger.error(f"[SITE-VISIT] Error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# INTERNAL ENDPOINTS — Called by agent for housekeeping
# ══════════════════════════════════════════════════════════════════════════════


@app.post("/api/internal/call-completed", status_code=202)
async def internal_call_completed(request: Request, background_tasks: BackgroundTasks):
    """
    Fire-and-forget: Agent sends all post-call data here.
    Backend handles sentiment analysis, DB writes, notifications, webhooks.
    """
    data = await request.json()
    logger.info(f"[CALL-COMPLETED] Processing for {data.get('phone')}")
    background_tasks.add_task(_process_call_completed, data)
    return {"accepted": True}


async def _process_call_completed(data: dict):
    """Background task: full post-call processing pipeline."""
    from notify import notify_booking_confirmed, notify_call_no_booking
    from db import save_call_log

    phone = data.get("phone", "unknown")
    caller_name = data.get("caller_name", "")
    duration = data.get("duration", 0)
    transcript = data.get("transcript", "")
    booking_intent = data.get("booking_intent")
    property_preferences = data.get("property_preferences", "")
    interrupt_count = data.get("interrupt_count", 0)
    tts_voice = data.get("tts_voice", "")
    room_name = data.get("room_name", "")

    # ── Sentiment analysis ────────────────────────────────────────────────
    sentiment = "unknown"
    if transcript and transcript != "unavailable":
        try:
            import openai as _oai

            _client = _oai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
            resp = await _client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=5,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Classify this call as one word: positive, neutral, "
                            f"negative, or frustrated.\n\n{transcript[:800]}"
                        ),
                    }
                ],
            )
            sentiment = resp.choices[0].message.content.strip().lower()
            logger.info(f"[SENTIMENT] {sentiment}")
        except Exception as e:
            logger.warning(f"[SENTIMENT] Failed: {e}")

    # ── Cost estimation ───────────────────────────────────────────────────
    def estimate_cost(dur: int, chars: int) -> float:
        return round(
            (dur / 60) * 0.002
            + (dur / 60) * 0.006
            + (chars / 1000) * 0.003
            + (chars / 4000) * 0.0001,
            5,
        )

    estimated_cost = estimate_cost(duration, len(transcript))
    logger.info(f"[COST] Estimated: ${estimated_cost}")

    # ── Analytics timestamps ──────────────────────────────────────────────
    ist = pytz.timezone("Asia/Kolkata")
    try:
        call_dt = datetime.now(ist)  # best approximation from backend
    except Exception:
        call_dt = datetime.now(ist)

    # ── Booking status ────────────────────────────────────────────────────
    booking_status_msg = "No booking"
    was_booked = False

    if booking_intent:
        # Booking was already processed by /api/tools/save-booking
        # Just record the status
        booking_status_msg = (
            f"Booking Intent: {booking_intent.get('caller_name')} at "
            f"{booking_intent.get('start_time')}"
        )
        was_booked = True
    else:
        notify_call_no_booking(
            caller_name=caller_name,
            caller_phone=phone,
            call_summary="Caller did not schedule during this call.",
            tts_voice=tts_voice,
            duration_seconds=duration,
        )

    # ── n8n webhook ───────────────────────────────────────────────────────
    _n8n_url = os.getenv("N8N_WEBHOOK_URL")
    if _n8n_url:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    _n8n_url,
                    json={
                        "event": "call_completed",
                        "phone": phone,
                        "caller_name": caller_name,
                        "duration": duration,
                        "booked": was_booked,
                        "sentiment": sentiment,
                        "summary": booking_status_msg,
                        "interrupt_count": interrupt_count,
                        "property_preferences": property_preferences,
                    },
                )
            logger.info("[N8N] Webhook triggered")
        except Exception as e:
            logger.warning(f"[N8N] Webhook failed: {e}")

    # ── Save to Supabase ──────────────────────────────────────────────────
    save_call_log(
        phone=phone,
        duration=duration,
        transcript=transcript,
        summary=booking_status_msg,
        caller_name=caller_name,
        sentiment=sentiment,
        estimated_cost_usd=estimated_cost,
        call_date=call_dt.date().isoformat(),
        call_hour=call_dt.hour,
        call_day_of_week=call_dt.strftime("%A"),
        was_booked=was_booked,
        interrupt_count=interrupt_count,
        property_preferences=property_preferences,
        site_visit_time=booking_intent.get('visit_time') if booking_intent else "",
    )


@app.post("/api/internal/transcript", status_code=202)
async def internal_transcript(request: Request, background_tasks: BackgroundTasks):
    """Fire-and-forget: Stream a single transcript line to Supabase."""
    data = await request.json()
    background_tasks.add_task(_save_transcript, data)
    return {"accepted": True}


async def _save_transcript(data: dict):
    """Background task: write transcript line to Supabase."""
    try:
        import db

        sb = db.get_supabase()
        if sb:
            sb.table("call_transcripts").insert(
                {
                    "call_room_id": data.get("room_id", ""),
                    "phone": data.get("phone", ""),
                    "role": data.get("role", "user"),
                    "content": data.get("content", ""),
                }
            ).execute()
    except Exception as e:
        logger.debug(f"[TRANSCRIPT] Write failed: {e}")


@app.post("/api/internal/active-call", status_code=202)
async def internal_active_call(request: Request, background_tasks: BackgroundTasks):
    """Fire-and-forget: Upsert active call status in Supabase."""
    data = await request.json()
    background_tasks.add_task(_upsert_active_call, data)
    return {"accepted": True}


async def _upsert_active_call(data: dict):
    """Background task: upsert active_calls table."""
    try:
        import db

        sb = db.get_supabase()
        if sb:
            sb.table("active_calls").upsert(
                {
                    "room_id": data.get("room_id", ""),
                    "phone": data.get("phone", ""),
                    "caller_name": data.get("caller_name", ""),
                    "status": data.get("status", "active"),
                    "last_updated": datetime.utcnow().isoformat(),
                }
            ).execute()
    except Exception as e:
        logger.debug(f"[ACTIVE-CALL] {e}")


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH
# ══════════════════════════════════════════════════════════════════════════════


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "voice-agent-backend",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
