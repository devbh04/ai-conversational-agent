import os
import time
import logging
from supabase import create_client, Client

logger = logging.getLogger("db")

# ─── Retry helper ─────────────────────────────────────────────────────────────
_MAX_RETRIES = 3
_RETRY_DELAYS = [1.0, 2.0, 4.0]


def _is_retryable(err_str: str) -> bool:
    transient = ("525", "ssl", "timeout", "connection", "network", "502", "503", "504")
    el = err_str.lower()
    return any(k in el for k in transient)


# ─── Client ───────────────────────────────────────────────────────────────────

def get_supabase() -> Client | None:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception as e:
        logger.error(f"Failed to init Supabase client: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# REAL ESTATE TABLE
# ═══════════════════════════════════════════════════════════════════════════════

def save_real_estate_call(
    phone: str,
    duration: int,
    transcript: str,
    summary: str = "",
    caller_name: str = "",
    sentiment: str = "unknown",
    estimated_cost_usd: float | None = None,
    call_date: str | None = None,
    call_hour: int | None = None,
    call_day_of_week: str | None = None,
    was_booked: bool = False,
    interrupt_count: int = 0,
    property_preferences: str = "",
    site_visit_time: str = "",
) -> dict:
    """Insert a call log into the real_estate_calls table."""
    supabase = get_supabase()
    if not supabase:
        logger.info(f"Supabase not configured. Local log → {phone} {duration}s")
        return {"success": False, "message": "Supabase not configured"}

    data: dict = {
        "phone_number":    phone,
        "duration_seconds": duration,
        "transcript":      transcript,
        "summary":         summary,
        "sentiment":       sentiment,
        "was_booked":      was_booked,
        "interrupt_count": interrupt_count,
    }
    if caller_name:                    data["caller_name"]            = caller_name
    if estimated_cost_usd is not None: data["estimated_cost_usd"]     = estimated_cost_usd
    if call_date:                      data["call_date"]              = call_date
    if call_hour is not None:          data["call_hour"]              = call_hour
    if call_day_of_week:               data["call_day_of_week"]       = call_day_of_week
    if property_preferences:           data["property_preferences"]   = property_preferences
    if site_visit_time:                data["site_visit_time"]        = site_visit_time

    return _insert_with_retry(supabase, "real_estate_calls", data, phone)


# ═══════════════════════════════════════════════════════════════════════════════
# DOCTOR TABLE
# ═══════════════════════════════════════════════════════════════════════════════

def save_doctor_call(
    phone: str,
    duration: int,
    transcript: str,
    summary: str = "",
    caller_name: str = "",
    sentiment: str = "unknown",
    estimated_cost_usd: float | None = None,
    call_date: str | None = None,
    call_hour: int | None = None,
    call_day_of_week: str | None = None,
    was_booked: bool = False,
    interrupt_count: int = 0,
    dental_concern: str = "",
    appointment_time: str = "",
    booking_id: str = "",
) -> dict:
    """Insert a call log into the doctor_calls table."""
    supabase = get_supabase()
    if not supabase:
        logger.info(f"Supabase not configured. Local log → {phone} {duration}s")
        return {"success": False, "message": "Supabase not configured"}

    data: dict = {
        "phone_number":    phone,
        "duration_seconds": duration,
        "transcript":      transcript,
        "summary":         summary,
        "sentiment":       sentiment,
        "was_booked":      was_booked,
        "interrupt_count": interrupt_count,
    }
    if caller_name:                    data["caller_name"]            = caller_name
    if estimated_cost_usd is not None: data["estimated_cost_usd"]     = estimated_cost_usd
    if call_date:                      data["call_date"]              = call_date
    if call_hour is not None:          data["call_hour"]              = call_hour
    if call_day_of_week:               data["call_day_of_week"]       = call_day_of_week
    if dental_concern:                 data["dental_concern"]         = dental_concern
    if appointment_time:               data["appointment_time"]       = appointment_time
    if booking_id:                     data["booking_id"]             = booking_id

    return _insert_with_retry(supabase, "doctor_calls", data, phone)


# ═══════════════════════════════════════════════════════════════════════════════
# LEGACY — keep for backward compat with old call_logs table
# ═══════════════════════════════════════════════════════════════════════════════

def save_call_log(
    phone: str,
    duration: int,
    transcript: str,
    summary: str = "",
    caller_name: str = "",
    **kwargs,
) -> dict:
    """Legacy function — writes to call_logs table."""
    supabase = get_supabase()
    if not supabase:
        return {"success": False, "message": "Supabase not configured"}
    data = {
        "phone_number": phone,
        "duration_seconds": duration,
        "transcript": transcript,
        "summary": summary,
    }
    if caller_name:
        data["caller_name"] = caller_name
    return _insert_with_retry(supabase, "call_logs", data, phone)


# ─── Shared insert with retry ─────────────────────────────────────────────────

def _insert_with_retry(supabase: Client, table: str, data: dict, phone: str) -> dict:
    for attempt in range(_MAX_RETRIES):
        try:
            res = supabase.table(table).insert(data).execute()
            logger.info(f"Saved call log to {table} for {phone}")
            return {"success": True, "data": res.data}
        except Exception as e:
            err = str(e)
            if _is_retryable(err) and attempt < _MAX_RETRIES - 1:
                delay = _RETRY_DELAYS[attempt]
                logger.warning(f"Transient error (attempt {attempt+1}), retrying in {delay}s: {err[:80]}")
                time.sleep(delay)
                continue
            logger.error(f"Failed to save to {table}: {e}")
            return {"success": False, "message": err}
    return {"success": False, "message": "Max retries exceeded"}


# ─── Fetch helpers ────────────────────────────────────────────────────────────

def fetch_call_logs(table: str = "call_logs", limit: int = 50) -> list:
    supabase = get_supabase()
    if not supabase:
        return []
    try:
        res = (supabase.table(table).select("*")
               .order("created_at", desc=True).limit(limit).execute())
        return res.data
    except Exception as e:
        logger.error(f"Failed to fetch from {table}: {e}")
        return []
