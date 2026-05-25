"""
backend_server.py — Unified FastAPI backend for all voice agents.

Serves:
  - Real Estate Agent endpoints (/api/re/*)
  - Doctor Agent endpoints (/api/doc/*)
  - Shared internal endpoints (/api/internal/*)
  - Call dispatch (/api/dispatch-call)
  - System health check (/api/system-check — SSE)

Runs on port 7860 (HF Spaces default) or 8001 locally.
"""

import os
import json
import random
import logging
import asyncio
from datetime import datetime, timedelta

import pytz
from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

# Pre-load all shared modules at startup for speed
import db
import notify
import calendar_tools

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backend-server")

app = FastAPI(title="Voice Agent Backend")

# CORS — allow frontend on Vercel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════════════════════
# REAL ESTATE ENDPOINTS — /api/re/*
# ══════════════════════════════════════════════════════════════════════════════


@app.get("/api/re/business-hours")
async def re_business_hours():
    """Real estate business hours. Mon-Sat 10AM-7PM, Sun closed."""
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    hours = {
        0: ("Monday",    "10:00", "19:00"),
        1: ("Tuesday",   "10:00", "19:00"),
        2: ("Wednesday", "10:00", "19:00"),
        3: ("Thursday",  "10:00", "19:00"),
        4: ("Friday",    "10:00", "19:00"),
        5: ("Saturday",  "10:00", "17:00"),
        6: ("Sunday",    None,    None),
    }
    day_name, open_t, close_t = hours[now.weekday()]
    current_time = now.strftime("%H:%M")
    if open_t is None:
        return {"status": "closed", "message": "We are closed on Sundays. Next opening: Monday 10:00 AM IST."}
    if open_t <= current_time <= close_t:
        return {"status": "open", "message": f"We are OPEN. Today ({day_name}): {open_t}–{close_t} IST."}
    return {"status": "closed", "message": f"We are CLOSED. Today ({day_name}): {open_t}–{close_t} IST."}


@app.post("/api/re/book-site-visit", status_code=202)
async def re_book_site_visit(request: Request, background_tasks: BackgroundTasks):
    """Fire-and-forget: Accept site visit request, send WhatsApp/Telegram in background."""
    data = await request.json()
    logger.info(f"[RE/SITE-VISIT] Received: {data.get('caller_name')} at {data.get('visit_time')}")
    background_tasks.add_task(_process_site_visit, data)
    return {"accepted": True, "message": "Site visit request is being processed."}


async def _process_site_visit(data: dict):
    visit_time = data.get("visit_time", "")
    caller_name = data.get("caller_name", "Unknown")
    caller_phone = data.get("caller_phone", "unknown")
    property_preferences = data.get("property_preferences", "")
    notes = data.get("notes", "")
    tts_voice = data.get("tts_voice", "")
    try:
        notify.notify_site_visit_requested(
            caller_name=caller_name,
            caller_phone=caller_phone,
            site_visit_time=visit_time,
            property_preferences=property_preferences,
            notes=notes,
            tts_voice=tts_voice,
        )
        logger.info(f"[RE/SITE-VISIT] Notification sent for {caller_name}")
    except Exception as e:
        logger.error(f"[RE/SITE-VISIT] Error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# DOCTOR ENDPOINTS — /api/doc/*
# ══════════════════════════════════════════════════════════════════════════════


@app.get("/api/doc/availability")
async def doc_check_availability(date: str):
    """Check available appointment slots for Dr. Nehra. Sync — agent waits."""
    logger.info(f"[DOC/AVAILABILITY] Checking slots for {date}")
    try:
        # Use doctor-specific Cal.com credentials
        _orig_key = os.environ.get("CAL_API_KEY", "")
        _orig_eid = os.environ.get("CAL_EVENT_TYPE_ID", "")
        os.environ["CAL_API_KEY"] = os.environ.get("DOC_CAL_API_KEY", _orig_key)
        os.environ["CAL_EVENT_TYPE_ID"] = os.environ.get("DOC_CAL_EVENT_TYPE_ID", _orig_eid)

        slots = calendar_tools.get_available_slots(date)

        # Restore original
        os.environ["CAL_API_KEY"] = _orig_key
        os.environ["CAL_EVENT_TYPE_ID"] = _orig_eid

        if not slots:
            return {"slots": [], "formatted": "No slots available", "date": date}
        logger.info(f"[DOC/AVAILABILITY] {len(slots)} slots for {date}. First: {slots[0] if slots else 'none'}")
        slot_labels = [s.get("label", "") for s in slots[:8]]
        return {"slots": slots, "formatted": ", ".join(slot_labels), "date": date}
    except Exception as e:
        logger.error(f"[DOC/AVAILABILITY] Failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/doc/book-appointment")
async def doc_book_appointment(request: Request, background_tasks: BackgroundTasks):
    """Sync: Book appointment via Cal.com, send notifications in background."""
    data = await request.json()
    logger.info(f"[DOC/BOOK] Received: {data.get('caller_name')} at {data.get('start_time')}")

    start_time = data.get("start_time", "")
    caller_name = data.get("caller_name", "Unknown")
    caller_phone = data.get("caller_phone", "unknown")
    dental_concern = data.get("dental_concern", "")
    notes = data.get("notes", "")

    # Use doctor-specific Cal.com credentials
    _orig_key = os.environ.get("CAL_API_KEY", "")
    _orig_eid = os.environ.get("CAL_EVENT_TYPE_ID", "")
    os.environ["CAL_API_KEY"] = os.environ.get("DOC_CAL_API_KEY", _orig_key)
    os.environ["CAL_EVENT_TYPE_ID"] = os.environ.get("DOC_CAL_EVENT_TYPE_ID", _orig_eid)

    try:
        result = await calendar_tools.async_create_booking(
            start_time=start_time,
            caller_name=caller_name,
            caller_phone=caller_phone,
            notes=f"Dental concern: {dental_concern}. {notes}",
        )
    finally:
        os.environ["CAL_API_KEY"] = _orig_key
        os.environ["CAL_EVENT_TYPE_ID"] = _orig_eid

    if result.get("success"):
        # Fire notifications in background — don't block response
        background_tasks.add_task(
            notify.notify_appointment_confirmed,
            caller_name=caller_name,
            caller_phone=caller_phone,
            appointment_time=start_time,
            dental_concern=dental_concern,
            booking_id=result.get("booking_id", ""),
            notes=notes,
        )
        return {"success": True, "booking_id": result.get("booking_id"), "message": "Appointment confirmed"}
    else:
        return {"success": False, "message": result.get("message", "Booking failed")}


@app.get("/api/doc/business-hours")
async def doc_business_hours():
    """Dr. Nehra's clinic hours. Mon-Sat 9AM-6PM, Sun closed."""
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    hours = {
        0: ("Monday",    "09:00", "18:00"),
        1: ("Tuesday",   "09:00", "18:00"),
        2: ("Wednesday", "09:00", "18:00"),
        3: ("Thursday",  "09:00", "18:00"),
        4: ("Friday",    "09:00", "18:00"),
        5: ("Saturday",  "09:00", "18:00"),
        6: ("Sunday",    None,    None),
    }
    day_name, open_t, close_t = hours[now.weekday()]
    current_time = now.strftime("%H:%M")
    if open_t is None:
        return {"status": "closed", "message": "Dr. Nehra's clinic is closed on Sundays. Next opening: Monday 9:00 AM."}
    if open_t <= current_time <= close_t:
        return {"status": "open", "message": f"Clinic is OPEN. Today ({day_name}): {open_t}–{close_t}."}
    return {"status": "closed", "message": f"Clinic is CLOSED. Today ({day_name}): {open_t}–{close_t}."}


# ══════════════════════════════════════════════════════════════════════════════
# CALL DISPATCH — Frontend triggers outbound calls
# ══════════════════════════════════════════════════════════════════════════════


@app.post("/api/dispatch-call")
async def dispatch_call(request: Request):
    """Create a LiveKit room and dispatch the requested agent to call a phone number."""
    data = await request.json()
    agent_type = data.get("agent_type", "")  # "real-estate-agent" or "doctor-nehra"
    phone_number = data.get("phone_number", "")

    if not agent_type or not phone_number:
        return JSONResponse(status_code=400, content={"error": "agent_type and phone_number required"})
    if not phone_number.startswith("+"):
        return JSONResponse(status_code=400, content={"error": "Phone number must start with +"})

    url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not (url and api_key and api_secret):
        return JSONResponse(status_code=500, content={"error": "LiveKit credentials not configured"})

    try:
        from livekit import api as lk_api
        lk = lk_api.LiveKitAPI(url=url, api_key=api_key, api_secret=api_secret)

        room_name = f"call-{agent_type}-{phone_number.replace('+', '')}-{random.randint(1000, 9999)}"
        dispatch_request = lk_api.CreateAgentDispatchRequest(
            agent_name=agent_type,
            room=room_name,
            metadata=json.dumps({"phone_number": phone_number}),
        )
        dispatch = await lk.agent_dispatch.create_dispatch(dispatch_request)
        await lk.aclose()

        logger.info(f"[DISPATCH] {agent_type} → {phone_number} in room {room_name}")
        return {"success": True, "room": room_name, "dispatch_id": dispatch.id}
    except Exception as e:
        logger.error(f"[DISPATCH] Failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# INTERNAL ENDPOINTS — Shared by both agents
# ══════════════════════════════════════════════════════════════════════════════


@app.post("/api/internal/call-completed", status_code=202)
async def internal_call_completed(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    logger.info(f"[CALL-COMPLETED] Processing for {data.get('phone')} (agent: {data.get('agent_type')})")
    background_tasks.add_task(_process_call_completed, data)
    return {"accepted": True}


async def _process_call_completed(data: dict):
    """Post-call pipeline: Azure LLM transcript analysis → booking → notifications → DB save."""
    phone = data.get("phone", "unknown")
    caller_name = data.get("caller_name", "")
    duration = data.get("duration", 0)
    transcript = data.get("transcript", "")
    agent_type = data.get("agent_type", "real_estate")
    booking_intent = data.get("booking_intent")  # may come from normal mode
    interrupt_count = data.get("interrupt_count", 0)
    tts_voice = data.get("tts_voice", "")

    # Agent-specific fields
    property_preferences = data.get("property_preferences", "")
    dental_concern = data.get("dental_concern", "")

    # ── Azure GPT-4o-mini: Extract booking + sentiment from transcript ────
    sentiment = "unknown"
    extracted_booking = None
    extracted_summary = ""

    if transcript and transcript != "unavailable" and not booking_intent:
        try:
            import openai as _oai

            _azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
            _azure_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
            _azure_deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
            _azure_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-01-preview")

            if _azure_endpoint and _azure_key:
                _client = _oai.AsyncAzureOpenAI(
                    azure_endpoint=_azure_endpoint,
                    api_key=_azure_key,
                    api_version=_azure_version,
                )
                model_name = _azure_deployment
            else:
                # Fallback to regular OpenAI if Azure not configured
                _client = _oai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
                model_name = "gpt-4o-mini"

            if agent_type == "doctor":
                extraction_prompt = (
                    "Analyze this dental clinic call transcript. Return ONLY valid JSON:\n"
                    "{\n"
                    '  "sentiment": "positive" | "neutral" | "negative" | "frustrated",\n'
                    '  "summary": "one-line summary of the call",\n'
                    '  "booking": null or {\n'
                    '    "patient_name": "...",\n'
                    '    "phone": "...",\n'
                    '    "start_time": "ISO 8601 datetime with +05:30 timezone e.g. 2026-05-26T09:00:00+05:30",\n'
                    '    "dental_concern": "...",\n'
                    '    "notes": "any extra notes"\n'
                    "  }\n"
                    "}\n\n"
                    "RULES:\n"
                    "- Only set booking if the patient CONFIRMED an appointment (said yes to a specific time).\n"
                    "- If they just asked about availability but didn't confirm, set booking to null.\n"
                    f"- The caller's phone number is: {phone}\n"
                    f"- Today's date is: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d')}\n\n"
                    f"TRANSCRIPT:\n{transcript[:2000]}"
                )
            else:
                extraction_prompt = (
                    "Analyze this real estate call transcript. Return ONLY valid JSON:\n"
                    "{\n"
                    '  "sentiment": "positive" | "neutral" | "negative" | "frustrated",\n'
                    '  "summary": "one-line summary of the call",\n'
                    '  "site_visit": null or {\n'
                    '    "visitor_name": "...",\n'
                    '    "phone": "...",\n'
                    '    "visit_time": "ISO 8601 datetime with +05:30 timezone",\n'
                    '    "property_preferences": "...",\n'
                    '    "notes": "any extra notes"\n'
                    "  }\n"
                    "}\n\n"
                    "RULES:\n"
                    "- Only set site_visit if the caller CONFIRMED a visit.\n"
                    f"- The caller's phone number is: {phone}\n"
                    f"- Today's date is: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d')}\n\n"
                    f"TRANSCRIPT:\n{transcript[:2000]}"
                )

            resp = await _client.chat.completions.create(
                model=model_name,
                max_tokens=300,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": extraction_prompt}],
            )

            raw_json = resp.choices[0].message.content.strip()
            logger.info(f"[POST-CALL] Azure LLM extraction: {raw_json[:500]}")

            extracted = json.loads(raw_json)
            sentiment = extracted.get("sentiment", "unknown")
            extracted_summary = extracted.get("summary", "")

            if agent_type == "doctor" and extracted.get("booking"):
                extracted_booking = extracted["booking"]
                caller_name = extracted_booking.get("patient_name", caller_name)
                dental_concern = extracted_booking.get("dental_concern", dental_concern)
                logger.info(f"[POST-CALL] Booking extracted: {extracted_booking}")
            elif agent_type != "doctor" and extracted.get("site_visit"):
                extracted_booking = extracted["site_visit"]
                caller_name = extracted_booking.get("visitor_name", caller_name)
                property_preferences = extracted_booking.get("property_preferences", property_preferences)
                logger.info(f"[POST-CALL] Site visit extracted: {extracted_booking}")

        except json.JSONDecodeError as e:
            logger.warning(f"[POST-CALL] JSON parse failed: {e}")
        except Exception as e:
            logger.warning(f"[POST-CALL] Azure extraction failed: {e}")

    elif transcript and transcript != "unavailable" and booking_intent:
        # Normal mode — booking already done by tools, just do sentiment
        try:
            import openai as _oai
            _azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
            _azure_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
            if _azure_endpoint and _azure_key:
                _client = _oai.AsyncAzureOpenAI(
                    azure_endpoint=_azure_endpoint,
                    api_key=_azure_key,
                    api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-01-preview"),
                )
                model_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
            else:
                _client = _oai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
                model_name = "gpt-4o-mini"
            resp = await _client.chat.completions.create(
                model=model_name, max_tokens=5,
                messages=[{"role": "user", "content": f"Classify this call as one word: positive, neutral, negative, or frustrated.\n\n{transcript[:800]}"}],
            )
            sentiment = resp.choices[0].message.content.strip().lower()
        except Exception as e:
            logger.warning(f"[SENTIMENT] Failed: {e}")

    # ── Execute Cal.com booking if extracted from transcript ───────────────
    if extracted_booking and not booking_intent:
        if agent_type == "doctor":
            start_time = extracted_booking.get("start_time", "")
            if start_time:
                logger.info(f"[POST-CALL] Booking via Cal.com: {caller_name} at {start_time}")
                # Use doctor Cal.com creds
                _orig_key = os.environ.get("CAL_API_KEY", "")
                _orig_eid = os.environ.get("CAL_EVENT_TYPE_ID", "")
                os.environ["CAL_API_KEY"] = os.environ.get("DOC_CAL_API_KEY", _orig_key)
                os.environ["CAL_EVENT_TYPE_ID"] = os.environ.get("DOC_CAL_EVENT_TYPE_ID", _orig_eid)
                try:
                    result = await calendar_tools.async_create_booking(
                        start_time=start_time,
                        caller_name=caller_name,
                        caller_phone=phone,
                        notes=f"Dental concern: {dental_concern}. {extracted_booking.get('notes', '')}",
                    )
                    if result.get("success"):
                        booking_intent = {
                            "start_time": start_time,
                            "caller_name": caller_name,
                            "caller_phone": phone,
                            "booking_id": result.get("booking_id", ""),
                        }
                        logger.info(f"[POST-CALL] ✅ Cal.com booking confirmed: {result.get('booking_id')}")
                        # Send WhatsApp confirmation
                        notify.notify_appointment_confirmed(
                            caller_name=caller_name, caller_phone=phone,
                            appointment_time=start_time,
                            dental_concern=dental_concern,
                            booking_id=result.get("booking_id", ""),
                        )
                    else:
                        logger.error(f"[POST-CALL] ❌ Cal.com booking failed: {result.get('message')}")
                        # Notify about failed booking
                        notify.notify_doctor_call_no_booking(
                            caller_name=caller_name, caller_phone=phone,
                            call_summary=f"Booking attempted but failed: {result.get('message')}. Time: {start_time}",
                            duration_seconds=duration,
                        )
                finally:
                    os.environ["CAL_API_KEY"] = _orig_key
                    os.environ["CAL_EVENT_TYPE_ID"] = _orig_eid
            else:
                logger.warning("[POST-CALL] Booking extracted but no start_time found")

    # ── Cost estimation ───────────────────────────────────────────────────
    def estimate_cost(dur: int, chars: int) -> float:
        return round(
            (dur / 60) * 0.002 + (dur / 60) * 0.006
            + (chars / 1000) * 0.003 + (chars / 4000) * 0.0001, 5
        )

    estimated_cost = estimate_cost(duration, len(transcript))

    # ── Timestamps ────────────────────────────────────────────────────────
    ist = pytz.timezone("Asia/Kolkata")
    call_dt = datetime.now(ist)

    # ── Booking status + notifications ────────────────────────────────────
    was_booked = bool(booking_intent)

    if not was_booked:
        if agent_type == "doctor":
            notify.notify_doctor_call_no_booking(
                caller_name=caller_name, caller_phone=phone,
                call_summary=extracted_summary or "Patient did not book during this call.",
                duration_seconds=duration,
            )
        else:
            notify.notify_call_no_booking(
                caller_name=caller_name, caller_phone=phone,
                call_summary=extracted_summary or "Caller did not schedule during this call.",
                tts_voice=tts_voice, duration_seconds=duration,
            )

    # ── n8n webhook ───────────────────────────────────────────────────────
    _n8n_url = os.getenv("N8N_WEBHOOK_URL")
    if _n8n_url:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(_n8n_url, json={
                    "event": "call_completed", "agent_type": agent_type,
                    "phone": phone, "caller_name": caller_name,
                    "duration": duration, "booked": was_booked,
                    "sentiment": sentiment, "interrupt_count": interrupt_count,
                })
        except Exception as e:
            logger.warning(f"[N8N] Webhook failed: {e}")

    # ── Save to Supabase (agent-specific table) ──────────────────────────
    if agent_type == "doctor":
        db.save_doctor_call(
            phone=phone, duration=duration, transcript=transcript,
            summary=extracted_summary or (f"Booking: {booking_intent}" if was_booked else "No appointment"),
            caller_name=caller_name, sentiment=sentiment,
            estimated_cost_usd=estimated_cost,
            call_date=call_dt.date().isoformat(),
            call_hour=call_dt.hour,
            call_day_of_week=call_dt.strftime("%A"),
            was_booked=was_booked, interrupt_count=interrupt_count,
            dental_concern=dental_concern,
            appointment_time=booking_intent.get("start_time") if booking_intent else "",
            booking_id=booking_intent.get("booking_id", "") if booking_intent else "",
        )
    else:
        db.save_real_estate_call(
            phone=phone, duration=duration, transcript=transcript,
            summary=extracted_summary or (f"Site visit: {booking_intent}" if was_booked else "No booking"),
            caller_name=caller_name, sentiment=sentiment,
            estimated_cost_usd=estimated_cost,
            call_date=call_dt.date().isoformat(),
            call_hour=call_dt.hour,
            call_day_of_week=call_dt.strftime("%A"),
            was_booked=was_booked, interrupt_count=interrupt_count,
            property_preferences=property_preferences,
            site_visit_time=booking_intent.get("visit_time") if booking_intent else "",
        )


@app.post("/api/internal/transcript", status_code=202)
async def internal_transcript(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    background_tasks.add_task(_save_transcript, data)
    return {"accepted": True}


async def _save_transcript(data: dict):
    try:
        sb = db.get_supabase()
        if sb:
            sb.table("call_transcripts").insert({
                "call_room_id": data.get("room_id", ""),
                "phone": data.get("phone", ""),
                "role": data.get("role", "user"),
                "content": data.get("content", ""),
            }).execute()
    except Exception as e:
        logger.debug(f"[TRANSCRIPT] Write failed: {e}")


@app.post("/api/internal/active-call", status_code=202)
async def internal_active_call(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    background_tasks.add_task(_upsert_active_call, data)
    return {"accepted": True}


async def _upsert_active_call(data: dict):
    try:
        sb = db.get_supabase()
        if sb:
            sb.table("active_calls").upsert({
                "room_id": data.get("room_id", ""),
                "phone": data.get("phone", ""),
                "caller_name": data.get("caller_name", ""),
                "status": data.get("status", "active"),
                "last_updated": datetime.utcnow().isoformat(),
            }).execute()
    except Exception as e:
        logger.debug(f"[ACTIVE-CALL] {e}")


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM CHECK — SSE endpoint for frontend health verification
# ══════════════════════════════════════════════════════════════════════════════


@app.get("/api/system-check")
async def system_check():
    """SSE endpoint that streams system component status checks."""
    async def event_stream():
        import httpx

        # 1. Backend (always OK if we got here)
        yield _sse_event("backend", "ok", "✅ Backend server running")
        await asyncio.sleep(0.3)

        # 2. Supabase
        yield _sse_event("supabase", "checking", "Checking database connection...")
        try:
            sb = db.get_supabase()
            if sb:
                sb.table("real_estate_calls").select("id").limit(1).execute()
                yield _sse_event("supabase", "ok", "✅ Supabase connected")
            else:
                yield _sse_event("supabase", "warn", "⚠️ Supabase not configured")
        except Exception as e:
            yield _sse_event("supabase", "error", f"❌ Supabase error: {str(e)[:60]}")
        await asyncio.sleep(0.3)

        # 3. LiveKit
        yield _sse_event("livekit", "checking", "Checking LiveKit connection...")
        try:
            url = os.getenv("LIVEKIT_URL", "")
            api_key = os.getenv("LIVEKIT_API_KEY", "")
            api_secret = os.getenv("LIVEKIT_API_SECRET", "")
            if url and api_key and api_secret:
                from livekit import api as lk_api
                lk = lk_api.LiveKitAPI(url=url, api_key=api_key, api_secret=api_secret)
                rooms = await lk.room.list_rooms(lk_api.ListRoomsRequest())
                await lk.aclose()
                yield _sse_event("livekit", "ok", f"✅ LiveKit connected ({len(rooms.rooms)} active rooms)")
            else:
                yield _sse_event("livekit", "warn", "⚠️ LiveKit credentials not set")
        except Exception as e:
            yield _sse_event("livekit", "error", f"❌ LiveKit error: {str(e)[:60]}")
        await asyncio.sleep(0.3)

        # 4. Cal.com (Doctor)
        yield _sse_event("calcom", "checking", "Checking Cal.com (Doctor)...")
        doc_cal_key = os.getenv("DOC_CAL_API_KEY", "")
        if doc_cal_key:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        "https://api.cal.com/v2/me",
                        headers={"Authorization": f"Bearer {doc_cal_key}", "cal-api-version": "2024-08-13"},
                    )
                    if resp.status_code == 200:
                        yield _sse_event("calcom", "ok", "✅ Cal.com (Doctor) connected")
                    else:
                        yield _sse_event("calcom", "warn", f"⚠️ Cal.com returned {resp.status_code}")
            except Exception as e:
                yield _sse_event("calcom", "error", f"❌ Cal.com error: {str(e)[:60]}")
        else:
            yield _sse_event("calcom", "warn", "⚠️ DOC_CAL_API_KEY not set")
        await asyncio.sleep(0.3)

        # 5. Twilio/WhatsApp
        yield _sse_event("twilio", "checking", "Checking Twilio/WhatsApp...")
        if os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN"):
            yield _sse_event("twilio", "ok", "✅ Twilio credentials configured")
        else:
            yield _sse_event("twilio", "warn", "⚠️ Twilio not configured (WhatsApp disabled)")
        await asyncio.sleep(0.3)

        # 6. Done
        yield _sse_event("done", "ok", "All checks completed")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse_event(step: str, status: str, message: str) -> str:
    data = json.dumps({"step": step, "status": status, "message": message})
    return f"data: {data}\n\n"


# ══════════════════════════════════════════════════════════════════════════════
# WEB CHAT — Single-user lock + SSE availability
# ══════════════════════════════════════════════════════════════════════════════

_web_chat_lock = {"active": False, "room_name": None, "started_at": None}
_sse_clients: list[asyncio.Queue] = []


def _broadcast_status(status: str):
    msg = {"status": status}
    for q in _sse_clients:
        try:
            q.put_nowait(msg)
        except Exception:
            pass


async def _auto_release_lock(room_name: str, timeout: int = 180):
    """Safety net: auto-release lock after timeout seconds."""
    await asyncio.sleep(timeout)
    if _web_chat_lock["active"] and _web_chat_lock["room_name"] == room_name:
        logger.info(f"[WEB-CHAT] Auto-releasing lock for {room_name}")
        _web_chat_lock["active"] = False
        _web_chat_lock["room_name"] = None
        _broadcast_status("available")


@app.get("/api/web-chat/status")
async def web_chat_status():
    """SSE stream — real-time web chat availability."""
    async def stream():
        queue: asyncio.Queue = asyncio.Queue()
        _sse_clients.append(queue)
        try:
            status = "busy" if _web_chat_lock["active"] else "available"
            yield f"data: {json.dumps({'status': status})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'status': 'heartbeat'})}\n\n"
        finally:
            _sse_clients.remove(queue)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/web-chat/start")
async def start_web_chat(request: Request):
    """Create LiveKit room, generate browser token, dispatch agent."""
    if _web_chat_lock["active"]:
        return JSONResponse(status_code=409, content={
            "error": "busy",
            "message": "Agent is in another conversation. Please wait.",
        })

    data = await request.json()
    agent_type = data.get("agent_type", "")
    if not agent_type:
        return JSONResponse(status_code=400, content={"error": "agent_type required"})

    url = os.getenv("LIVEKIT_URL", "")
    api_key = os.getenv("LIVEKIT_API_KEY", "")
    api_secret = os.getenv("LIVEKIT_API_SECRET", "")

    if not (url and api_key and api_secret):
        return JSONResponse(status_code=500, content={"error": "LiveKit credentials not configured"})

    room_name = f"web-{agent_type}-{random.randint(10000, 99999)}"

    try:
        from livekit import api as lk_api

        # Generate browser participant token
        token = (
            lk_api.AccessToken(api_key, api_secret)
            .with_identity("web-user")
            .with_name("Web Visitor")
            .with_grants(lk_api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            ))
            .to_jwt()
        )

        # Dispatch agent to room
        lk = lk_api.LiveKitAPI(url=url, api_key=api_key, api_secret=api_secret)
        await lk.agent_dispatch.create_dispatch(
            lk_api.CreateAgentDispatchRequest(
                agent_name=agent_type,
                room=room_name,
                metadata=json.dumps({"phone_number": "web-user", "channel": "web"}),
            )
        )
        await lk.aclose()

        # Acquire lock
        _web_chat_lock["active"] = True
        _web_chat_lock["room_name"] = room_name
        _web_chat_lock["started_at"] = datetime.utcnow().isoformat()
        _broadcast_status("busy")

        # Auto-release after 3 min safety net
        asyncio.create_task(_auto_release_lock(room_name, timeout=180))

        logger.info(f"[WEB-CHAT] Started: {agent_type} in {room_name}")
        return {"token": token, "room_name": room_name, "livekit_url": url}

    except Exception as e:
        logger.error(f"[WEB-CHAT] Failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/web-chat/end")
async def end_web_chat(request: Request):
    """Release lock and return post-chat summary."""
    data = await request.json()
    room_name = data.get("room_name", "")

    if _web_chat_lock["room_name"] == room_name:
        _web_chat_lock["active"] = False
        _web_chat_lock["room_name"] = None
        _broadcast_status("available")
        logger.info(f"[WEB-CHAT] Ended: {room_name}")

    return {
        "summary": "Chat completed",
        "call_benefits": [
            "📱 WhatsApp confirmation with booking details",
            "🔔 Follow-up reminders",
            "👤 Direct connection to our team",
            "⚡ Priority scheduling and support",
        ],
        "contact_url": "https://devbhangale.vercel.app",
    }


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN DATA ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════


@app.get("/api/admin/stats")
async def admin_stats():
    """Aggregated stats for both agents."""
    re_logs = db.fetch_call_logs("real_estate_calls", limit=500)
    doc_logs = db.fetch_call_logs("doctor_calls", limit=500)

    def calc(logs: list) -> dict:
        total = len(logs)
        booked = sum(1 for r in logs if r.get("was_booked"))
        durations = [r["duration_seconds"] for r in logs if r.get("duration_seconds")]
        avg_dur = round(sum(durations) / len(durations)) if durations else 0
        rate = round((booked / total) * 100) if total else 0
        return {"total": total, "booked": booked, "avg_duration": avg_dur, "booking_rate": rate}

    return {
        "real_estate": calc(re_logs),
        "doctor": calc(doc_logs),
        "combined": calc(re_logs + doc_logs),
    }


@app.get("/api/admin/calls")
async def admin_calls(agent: str = "real_estate", limit: int = 50):
    """Fetch call logs for a specific agent."""
    table = "real_estate_calls" if agent == "real_estate" else "doctor_calls"
    return db.fetch_call_logs(table, limit=limit)


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH
# ══════════════════════════════════════════════════════════════════════════════


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "voice-agent-backend",
        "agents": ["real-estate-agent", "doctor-nehra"],
        "web_chat_active": _web_chat_lock["active"],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7860")))

