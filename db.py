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
# EXIMPLE TABLE
# ═══════════════════════════════════════════════════════════════════════════════

def save_eximple_call(
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
    # Inquiry fields
    email: str = "",
    company_name: str = "",
    services: list | None = None,
    license_details: list | None = None,
    trade_direction: str = "",
    port_of_loading: str = "",
    port_of_destination: str = "",
    pickup_address: str = "",
    drop_off_address: str = "",
    goods_description: str = "",
    quantity: float | None = None,
    quantity_unit: str = "",
    shipment_value: float | None = None,
    shipment_currency: str = "",
    incoterm: str = "",
    dispatch_date: str | None = None,
    container_type: str = "",
    fcl_container_details: list | None = None,
    cargo_weight_kg: float | None = None,
    cargo_length_cm: float | None = None,
    cargo_width_cm: float | None = None,
    cargo_height_cm: float | None = None,
    cargo_volume_cbm: float | None = None,
    remarks: str = "",
    compliance_status: str = "not_screened",
    inquiry_complete: bool = False,
    missing_fields: list | None = None,
    extraction_conflicts: list | None = None,
) -> dict:
    """Insert a call log into the eximple_calls table."""
    supabase = get_supabase()
    if not supabase:
        logger.info(f"Supabase not configured. Local log → {phone} {duration}s")
        return {"success": False, "message": "Supabase not configured"}

    import json as _json

    data: dict = {
        "phone_number":    phone,
        "duration_seconds": duration,
        "transcript":      transcript,
        "summary":         summary,
        "sentiment":       sentiment,
        "was_booked":      was_booked,
        "interrupt_count": interrupt_count,
        "inquiry_complete": inquiry_complete,
    }
    if caller_name:                      data["caller_name"]            = caller_name
    if estimated_cost_usd is not None:   data["estimated_cost_usd"]     = estimated_cost_usd
    if call_date:                        data["call_date"]              = call_date
    if call_hour is not None:            data["call_hour"]              = call_hour
    if call_day_of_week:                 data["call_day_of_week"]       = call_day_of_week
    # Inquiry fields
    if email:                            data["email"]                  = email
    if company_name:                     data["company_name"]           = company_name
    if services:                         data["services"]               = services
    if license_details:                  data["license_details"]        = license_details
    if trade_direction:                  data["trade_direction"]        = trade_direction
    if port_of_loading:                  data["port_of_loading"]        = port_of_loading
    if port_of_destination:              data["port_of_destination"]    = port_of_destination
    if pickup_address:                   data["pickup_address"]         = pickup_address
    if drop_off_address:                 data["drop_off_address"]       = drop_off_address
    if goods_description:                data["goods_description"]      = goods_description
    if quantity is not None:             data["quantity"]               = quantity
    if quantity_unit:                    data["quantity_unit"]           = quantity_unit
    if shipment_value is not None:       data["shipment_value"]         = shipment_value
    if shipment_currency:                data["shipment_currency"]      = shipment_currency
    if incoterm:                         data["incoterm"]               = incoterm
    if dispatch_date:                    data["dispatch_date"]          = dispatch_date
    if container_type:                   data["container_type"]         = container_type
    if fcl_container_details:            data["fcl_container_details"]  = fcl_container_details
    if cargo_weight_kg is not None:      data["cargo_weight_kg"]        = cargo_weight_kg
    if cargo_length_cm is not None:      data["cargo_length_cm"]        = cargo_length_cm
    if cargo_width_cm is not None:       data["cargo_width_cm"]         = cargo_width_cm
    if cargo_height_cm is not None:      data["cargo_height_cm"]        = cargo_height_cm
    if cargo_volume_cbm is not None:     data["cargo_volume_cbm"]       = cargo_volume_cbm
    if remarks:                          data["remarks"]                = remarks
    if compliance_status:                data["compliance_status"]      = compliance_status
    if missing_fields:                   data["missing_fields"]         = missing_fields
    if extraction_conflicts:             data["extraction_conflicts"]   = extraction_conflicts

    return _insert_with_retry(supabase, "eximple_calls", data, phone)


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
