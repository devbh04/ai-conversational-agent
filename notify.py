import os
import logging
import requests
import httpx
from datetime import datetime

logger = logging.getLogger("notify")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_URL       = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"


# ─── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(message: str) -> bool:
    """Fire a single POST to Telegram. Supports Markdown formatting."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("[TELEGRAM] Token or Chat ID not set — skipping.")
        return False
    try:
        resp = requests.post(
            TELEGRAM_URL,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=5,
        )
        resp.raise_for_status()
        logger.info("[TELEGRAM] Message sent.")
        return True
    except Exception as e:
        logger.error(f"[TELEGRAM] Failed: {e}")
        return False


# ─── WhatsApp via Twilio (#16) ────────────────────────────────────────────────

def send_whatsapp(to_phone: str, message: str) -> bool:
    """
    Send a WhatsApp message via Twilio.
    Requires env vars: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER
    The Twilio sandbox number is whatsapp:+14155238886 (for testing).
    Production: use your approved Twilio WhatsApp sender number.
    """
    account_sid  = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token   = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_number  = os.environ.get("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

    if not account_sid or not auth_token:
        logger.debug("[WHATSAPP] Twilio credentials not set — skipping.")
        return False

    # Normalise destination number
    to_wa = f"whatsapp:{to_phone}" if not to_phone.startswith("whatsapp:") else to_phone

    try:
        resp = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
            auth=(account_sid, auth_token),
            data={"From": from_number, "To": to_wa, "Body": message},
            timeout=8.0,
        )
        resp.raise_for_status()
        logger.info(f"[WHATSAPP] Sent to {to_phone}: {resp.status_code}")
        return True
    except Exception as e:
        logger.error(f"[WHATSAPP] Failed to send to {to_phone}: {e}")
        return False


def send_whatsapp_site_visit_confirmation(
    caller_phone: str,
    caller_name: str,
    site_visit_time: str,
) -> bool:
    """Send WhatsApp confirmation after a site visit is requested."""
    try:
        dt = datetime.fromisoformat(site_visit_time)
        readable = dt.strftime("%A, %d %B %Y at %I:%M %p")
    except Exception:
        readable = site_visit_time

    message = (
        f"✅ Hi {caller_name or 'there'}! We have noted your request for a site visit.\n\n"
        f"📅 *Requested Time:* {readable}\n\n"
        f"Our team will review your property preferences and contact you shortly to confirm the exact property location and time.\n\n"
        f"— Arjun (Property Consultant) 🏢"
    )
    return send_whatsapp(caller_phone, message)


# ─── Message Templates ─────────────────────────────────────────────────────────

def notify_site_visit_requested(
    caller_name: str,
    caller_phone: str,
    site_visit_time: str,
    property_preferences: str = "",
    notes: str = "",
    tts_voice: str = "",
    ai_summary: str = "",
) -> bool:
    """Sends Telegram + WhatsApp when a site visit is requested."""
    try:
        dt = datetime.fromisoformat(site_visit_time)
        readable = dt.strftime("%A, %d %B %Y at %-I:%M %p")
    except Exception:
        readable = site_visit_time

    message = (
        f"🏢 *New Site Visit Requested!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Name:*        {caller_name}\n"
        f"📞 *Phone:*       `{caller_phone}`\n"
        f"📅 *Time:*        {readable}\n"
        f"🏠 *Preferences:* {property_preferences or '—'}\n"
        f"📝 *Notes:*       {notes or '—'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        + (f"💬 *AI Summary:*\n_{ai_summary}_\n\n" if ai_summary else "")
        + f"_Captured via Arjun AI Voice Agent_"
    )
    tg_ok = send_telegram(message)

    # Also send WhatsApp confirmation to caller (#16)
    send_whatsapp_site_visit_confirmation(caller_phone, caller_name, site_visit_time)

    return tg_ok


def notify_booking_cancelled(
    caller_name: str,
    caller_phone: str,
    booking_id: str,
    reason: str = "",
) -> bool:
    message = (
        f"❌ *Booking Cancelled*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Name:*      {caller_name}\n"
        f"📞 *Phone:*     `{caller_phone}`\n"
        f"🔖 *Booking ID:* `{booking_id}`\n"
        f"💬 *Reason:*    {reason or 'Caller changed mind'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"_AI Voice Agent_ 🤖"
    )
    return send_telegram(message)


def notify_call_no_booking(
    caller_name: str,
    caller_phone: str,
    call_summary: str = "",
    tts_voice: str = "",
    ai_summary: str = "",
    duration_seconds: int = 0,
) -> bool:
    message = (
        f"📵 *Call Ended — No Booking*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Name:*        {caller_name or 'Unknown'}\n"
        f"📞 *Phone:*       `{caller_phone}`\n"
        f"⏱️ *Duration:*    {duration_seconds}s\n"
        f"🎙️ *Voice Model:* {tts_voice or '—'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        + f"💬 *Summary:*\n_{ai_summary or call_summary or 'Caller did not schedule.'}_\n\n"
        + f"_Consider a manual follow-up call_ 📲\n"
        f"_AI Voice Agent_ 🤖"
    )
    return send_telegram(message)


def notify_agent_error(caller_phone: str, error: str) -> bool:
    message = (
        f"⚠️ *Agent Error During Call*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📞 *Phone:*  `{caller_phone}`\n"
        f"🔴 *Error:*  `{error}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"_Voice Agent_"
    )
    return send_telegram(message)


# ─── Doctor Appointment Notifications ─────────────────────────────────────────

def send_whatsapp_appointment_confirmation(
    caller_phone: str,
    caller_name: str,
    appointment_time: str,
) -> bool:
    """Send WhatsApp confirmation to patient after dental appointment is booked."""
    try:
        dt = datetime.fromisoformat(appointment_time)
        readable = dt.strftime("%A, %d %B %Y at %I:%M %p")
    except Exception:
        readable = appointment_time

    message = (
        f"✅ Hi {caller_name or 'there'}! Your dental appointment with Dr. Nehra is *confirmed*.\n\n"
        f"📅 *Date & Time:* {readable}\n\n"
        f"📍 Please arrive 10 minutes early.\n"
        f"If you need to reschedule, just call us back.\n\n"
        f"— Arjun (Dr. Nehra's Clinic) 🦷"
    )
    return send_whatsapp(caller_phone, message)


def notify_appointment_confirmed(
    caller_name: str,
    caller_phone: str,
    appointment_time: str,
    dental_concern: str = "",
    booking_id: str = "",
    notes: str = "",
) -> bool:
    """Telegram + WhatsApp notification when a dental appointment is confirmed."""
    try:
        dt = datetime.fromisoformat(appointment_time)
        readable = dt.strftime("%A, %d %B %Y at %-I:%M %p")
    except Exception:
        readable = appointment_time

    message = (
        f"🦷 *New Dental Appointment!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Patient:*    {caller_name}\n"
        f"📞 *Phone:*      `{caller_phone}`\n"
        f"📅 *Time:*       {readable}\n"
        f"🔖 *Booking ID:* `{booking_id or '—'}`\n"
        f"🦷 *Concern:*    {dental_concern or '—'}\n"
        f"📝 *Notes:*      {notes or '—'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"_Dr. Nehra AI Receptionist_"
    )
    tg_ok = send_telegram(message)
    send_whatsapp_appointment_confirmation(caller_phone, caller_name, appointment_time)
    return tg_ok


def notify_doctor_call_no_booking(
    caller_name: str,
    caller_phone: str,
    call_summary: str = "",
    duration_seconds: int = 0,
) -> bool:
    """Telegram notification when a doctor call ends without booking."""
    message = (
        f"📵 *Doctor Call — No Appointment*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Name:*      {caller_name or 'Unknown'}\n"
        f"📞 *Phone:*     `{caller_phone}`\n"
        f"⏱️ *Duration:*  {duration_seconds}s\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 *Summary:*\n_{call_summary or 'Patient did not book.'}_\n\n"
        f"_Consider a follow-up call_ 📲\n"
        f"_Dr. Nehra AI Receptionist_"
    )
    return send_telegram(message)


# ─── n8n / Custom Webhook (#35) ──────────────────────────────────────────────

async def send_webhook(webhook_url: str, event_type: str, payload: dict) -> bool:
    """Deliver an event to a configurable webhook URL (for CRM embeds)."""
    if not webhook_url:
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                webhook_url,
                json={
                    "event":     event_type,
                    "timestamp": datetime.utcnow().isoformat(),
                    "data":      payload,
                },
                headers={"Content-Type": "application/json"},
            )
            logger.info(f"[WEBHOOK] Delivered {event_type} → {resp.status_code}")
            return resp.status_code < 300
    except Exception as e:
        logger.warning(f"[WEBHOOK] Failed to deliver {event_type}: {e}")
        return False


# ─── Telegram with Retry (timeout-safe) ──────────────────────────────────────

def _send_telegram_with_retry(message: str, max_retries: int = 2) -> bool:
    """Send Telegram with retry on timeout — handles long messages gracefully."""
    import time as _time

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("[TELEGRAM] Token or Chat ID not set — skipping.")
        return False

    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(
                TELEGRAM_URL,
                json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"},
                timeout=10,  # longer timeout for retries
            )
            resp.raise_for_status()
            logger.info("[TELEGRAM] Message sent.")
            return True
        except requests.exceptions.Timeout:
            logger.warning(f"[TELEGRAM] Timeout (attempt {attempt+1}/{max_retries+1})")
            if attempt < max_retries:
                _time.sleep(1)
                continue
        except Exception as e:
            logger.error(f"[TELEGRAM] Failed: {e}")
            break
    return False


# ─── Eximple Trade Inquiry Notifications ──────────────────────────────────────

def notify_eximple_inquiry(
    caller_name: str,
    caller_phone: str,
    company_name: str = "",
    trade_direction: str = "",
    port_of_loading: str = "",
    port_of_destination: str = "",
    goods_description: str = "",
    quantity: str = "",
    quantity_unit: str = "",
    incoterm: str = "",
    dispatch_date: str = "",
    container_type: str = "",
    inquiry_complete: bool = False,
    duration_seconds: int = 0,
    services: list | None = None,
    email: str = "",
    remarks: str = "",
    shipment_value: str = "",
    shipment_currency: str = "",
    pickup_address: str = "",
    drop_off_address: str = "",
    license_details: list | None = None,
    cargo_weight_kg: str = "",
    cargo_length_cm: str = "",
    cargo_width_cm: str = "",
    cargo_height_cm: str = "",
    cargo_volume_cbm: str = "",
    fcl_container_details: list | None = None,
    missing_fields: list | None = None,
    **kwargs,
) -> bool:
    """Telegram notification with all collected trade inquiry fields."""
    status_icon = "✅" if inquiry_complete else "⚠️"
    status_text = "Inquiry Submitted" if inquiry_complete else "Incomplete Inquiry"

    # Format services
    services_text = ", ".join(services) if services else "—"

    # Format FCL/LCL details
    container_detail = ""
    if container_type and container_type.upper() == "FCL" and fcl_container_details:
        parts = []
        for c in fcl_container_details:
            if isinstance(c, dict):
                parts.append(f"{c.get('container_size', '?')} × {c.get('quantity', '?')}")
            else:
                parts.append(str(c))
        container_detail = f" ({', '.join(parts)})"
    elif container_type and container_type.upper() == "LCL":
        dims = []
        if cargo_weight_kg:  dims.append(f"{cargo_weight_kg}kg")
        lcm_parts = []
        if cargo_length_cm: lcm_parts.append(str(cargo_length_cm))
        if cargo_width_cm:  lcm_parts.append(str(cargo_width_cm))
        if cargo_height_cm: lcm_parts.append(str(cargo_height_cm))
        if lcm_parts:       dims.append(f"{'×'.join(lcm_parts)}cm")
        if cargo_volume_cbm: dims.append(f"{cargo_volume_cbm} CBM")
        container_detail = f" ({', '.join(dims)})" if dims else ""

    # Format license details
    license_text = "—"
    if license_details:
        if isinstance(license_details, list):
            parts = []
            for lic in license_details:
                if isinstance(lic, dict):
                    parts.append(lic.get("name", str(lic)))
                else:
                    parts.append(str(lic))
            license_text = ", ".join(parts)
        else:
            license_text = str(license_details)

    # Format shipment value
    value_text = "—"
    if shipment_value:
        value_text = f"{shipment_currency or ''} {shipment_value}".strip()

    message = (
        f"{status_icon} *{status_text}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Name:*       {caller_name or 'Unknown'}\n"
        f"🏢 *Company:*    {company_name or '—'}\n"
        f"📞 *Phone:*      `{caller_phone}`\n"
        f"📧 *Email:*      {email or '—'}\n"
        f"⏱️ *Duration:*   {duration_seconds}s\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 *Trade:*      {trade_direction or '—'}\n"
        f"🚢 *Route:*      {port_of_loading or '—'} → {port_of_destination or '—'}\n"
        f"📍 *Pickup:*     {pickup_address or '—'}\n"
        f"📍 *Drop-off:*   {drop_off_address or '—'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 *Goods:*      {goods_description or '—'}\n"
        f"📊 *Qty:*        {quantity or '—'} {quantity_unit or ''}\n"
        f"💰 *Value:*      {value_text}\n"
        f"📜 *Incoterm:*   {incoterm or '—'}\n"
        f"📅 *Dispatch:*   {dispatch_date or '—'}\n"
        f"📦 *Container:*  {container_type or '—'}{container_detail}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔧 *Services:*   {services_text}\n"
        f"📑 *Licenses:*   {license_text}\n"
        f"📝 *Remarks:*    {remarks or '—'}\n"
    )

    if missing_fields:
        message += f"━━━━━━━━━━━━━━━━━━━━━━\n"
        message += f"❗ *Missing:*    {', '.join(missing_fields)}\n"

    message += (
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"_Eximple AI Voice Agent_ 🚢"
    )

    return _send_telegram_with_retry(message)


def notify_eximple_call_no_inquiry(
    caller_name: str,
    caller_phone: str,
    call_summary: str = "",
    duration_seconds: int = 0,
) -> bool:
    """Telegram notification when an Eximple call ends without any inquiry data."""
    message = (
        f"📵 *Eximple Call — No Inquiry Data*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Name:*      {caller_name or 'Unknown'}\n"
        f"📞 *Phone:*     `{caller_phone}`\n"
        f"⏱️ *Duration:*  {duration_seconds}s\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 *Summary:*\n_{call_summary or 'Caller did not provide inquiry details.'}_\n\n"
        f"_Consider a follow-up call_ 📲\n"
        f"_Eximple AI Voice Agent_ 🚢"
    )
    return _send_telegram_with_retry(message)

