import os
import sys
import json
import logging
import certifi
import pytz
import re
import asyncio
import time
import httpx
from collections import defaultdict
from datetime import datetime, timedelta
from dotenv import load_dotenv
from typing import Annotated

# Ensure project root is on sys.path so shared modules (db, notify, etc.) are importable
_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_AGENT_DIR))
sys.path.insert(0, _PROJECT_ROOT)

# Fix for macOS SSL certificate verification
os.environ["SSL_CERT_FILE"] = certifi.where()

# ── Sentry error tracking (#21) ───────────────────────────────────────────────
import sentry_sdk
_sentry_dsn = os.environ.get("SENTRY_DSN", "")
if _sentry_dsn:
    from sentry_sdk.integrations.asyncio import AsyncioIntegration
    sentry_sdk.init(
        dsn=_sentry_dsn,
        traces_sample_rate=0.1,
        integrations=[AsyncioIntegration()],
        environment=os.environ.get("ENVIRONMENT", "production"),
    )

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.getLogger("hpack").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
logger = logging.getLogger("real-estate-agent")
logging.basicConfig(level=logging.INFO)

from livekit import api
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RoomInputOptions,
    WorkerOptions,
    cli,
    llm,
)
from livekit.plugins import openai, sarvam, silero

CONFIG_FILE = os.path.join(_AGENT_DIR, "config.json")

# ── Backend API client (connection pooling for speed) ─────────────────────────
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8001")
_backend = httpx.AsyncClient(base_url=BACKEND_API_URL, timeout=10.0)

# ── Rate limiting (#37) ───────────────────────────────────────────────────────
_call_timestamps: dict = defaultdict(list)
RATE_LIMIT_CALLS  = 5
RATE_LIMIT_WINDOW = 3600  # 1 hour

def is_rate_limited(phone: str) -> bool:
    if phone in ("unknown", "demo"):
        return False
    now = time.time()
    _call_timestamps[phone] = [t for t in _call_timestamps[phone] if now - t < RATE_LIMIT_WINDOW]
    if len(_call_timestamps[phone]) >= RATE_LIMIT_CALLS:
        return True
    _call_timestamps[phone].append(now)
    return False


# ── Config loader (#17 partial — per-client path awareness) ───────────────────
def get_live_config(phone_number: str | None = None):
    """Load config — tries per-client file first, then default config.json."""
    config = {}
    paths = []
    if phone_number and phone_number != "unknown":
        clean = phone_number.replace("+", "").replace(" ", "")
        paths.append(f"configs/{clean}.json")
    paths += [os.path.join(_PROJECT_ROOT, "configs", "default.json"), CONFIG_FILE]

    for path in paths:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    config = json.load(f)
                    logger.info(f"[CONFIG] Loaded: {path}")
                    break
            except Exception as e:
                logger.error(f"[CONFIG] Failed to read {path}: {e}")

    return {
        "agent_instructions":       config.get("agent_instructions", ""),
        "stt_min_endpointing_delay":config.get("stt_min_endpointing_delay", 0.05),
        "llm_model":                config.get("llm_model", "gpt-4o-mini"),
        "llm_provider":             config.get("llm_provider", "openai"),
        "tts_voice":                config.get("tts_voice", "kavya"),
        "tts_language":             config.get("tts_language", "hi-IN"),
        "tts_provider":             config.get("tts_provider", "sarvam"),
        "stt_provider":             config.get("stt_provider", "sarvam"),
        "stt_language":             config.get("stt_language", "unknown"),
        "lang_preset":              config.get("lang_preset", "multilingual"),
        "max_turns":                config.get("max_turns", 25),
        **config,
    }


# ── Token counter (#11) ───────────────────────────────────────────────────────
def count_tokens(text: str) -> int:
    try:
        import tiktoken
        enc = tiktoken.encoding_for_model("gpt-4o")
        return len(enc.encode(text))
    except Exception:
        return len(text.split())


# ── IST time context ──────────────────────────────────────────────────────────
def get_ist_time_context() -> str:
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    today_str = now.strftime("%A, %B %d, %Y")
    time_str  = now.strftime("%I:%M %p")
    days_lines = []
    for i in range(7):
        day   = now + timedelta(days=i)
        label = "Today" if i == 0 else ("Tomorrow" if i == 1 else day.strftime("%A"))
        days_lines.append(f"  {label}: {day.strftime('%A %d %B %Y')} → ISO {day.strftime('%Y-%m-%d')}")
    days_block = "\n".join(days_lines)
    return (
        f"\n\n[SYSTEM CONTEXT]\n"
        f"Current date & time: {today_str} at {time_str} IST\n"
        f"Resolve ALL relative day references using this table:\n{days_block}\n"
        "Always use ISO dates when calling book_site_visit. Appointments in IST (+05:30).]"
    )


# ── Language presets ──────────────────────────────────────────────────────────
LANGUAGE_PRESETS = {
    "hinglish":    {"label": "Hinglish (Hindi+English)", "tts_language": "hi-IN", "tts_voice": "kavya",  "instruction": "Speak in natural Hinglish — mix Hindi and English like educated Indians do. Default to Hindi but use English words when more natural."},
    "hindi":       {"label": "Hindi",                   "tts_language": "hi-IN", "tts_voice": "ritu",   "instruction": "Speak only in pure Hindi. Avoid English words wherever a Hindi equivalent exists."},
    "english":     {"label": "English (India)",         "tts_language": "en-IN", "tts_voice": "dev",    "instruction": "Speak only in Indian English with a warm, professional tone."},
    "tamil":       {"label": "Tamil",                   "tts_language": "ta-IN", "tts_voice": "priya",  "instruction": "Speak only in Tamil. Use standard spoken Tamil for a professional context."},
    "telugu":      {"label": "Telugu",                  "tts_language": "te-IN", "tts_voice": "kavya",  "instruction": "Speak only in Telugu. Use clear, polite spoken Telugu."},
    "gujarati":    {"label": "Gujarati",                "tts_language": "gu-IN", "tts_voice": "rohan",  "instruction": "Speak only in Gujarati. Use polite, professional Gujarati."},
    "bengali":     {"label": "Bengali",                 "tts_language": "bn-IN", "tts_voice": "neha",   "instruction": "Speak only in Bengali (Bangla). Use standard, polite spoken Bengali."},
    "marathi":     {"label": "Marathi",                 "tts_language": "mr-IN", "tts_voice": "shubh",  "instruction": "Speak only in Marathi. Use polite, standard spoken Marathi."},
    "kannada":     {"label": "Kannada",                 "tts_language": "kn-IN", "tts_voice": "rahul",  "instruction": "Speak only in Kannada. Use clear, professional spoken Kannada."},
    "malayalam":   {"label": "Malayalam",               "tts_language": "ml-IN", "tts_voice": "ritu",   "instruction": "Speak only in Malayalam. Use polite, professional spoken Malayalam."},
    "multilingual":{"label": "Multilingual (Auto)",     "tts_language": "hi-IN", "tts_voice": "kavya",  "instruction": "Detect the caller's language from their first message and reply in that SAME language for the entire call. Supported: Hindi, Hinglish, English, Tamil, Telugu, Gujarati, Bengali, Marathi, Kannada, Malayalam. Switch if caller switches."},
}

def get_language_instruction(lang_preset: str) -> str:
    preset = LANGUAGE_PRESETS.get(lang_preset, LANGUAGE_PRESETS["multilingual"])
    return f"\n\n[LANGUAGE DIRECTIVE]\n{preset['instruction']}"


# ══════════════════════════════════════════════════════════════════════════════
# TOOL CONTEXT — All AI-callable functions
# Tools that need data back (availability, business hours) → sync HTTP to backend
# Tools that are side-effects (booking, etc.) → fire-and-forget HTTP to backend
# Tools that need LiveKit context (transfer, end call) → stay in-process
# ══════════════════════════════════════════════════════════════════════════════

class AgentTools(llm.ToolContext):

    def __init__(self, caller_phone: str, caller_name: str = ""):
        super().__init__(tools=[])
        self.caller_phone        = caller_phone
        self.caller_name         = caller_name
        self.booking_intent: dict | None = None
        self.property_preferences = ""
        self.sip_domain          = os.getenv("VOBIZ_SIP_DOMAIN")
        self.ctx_api             = None
        self.room_name           = None
        self._sip_identity       = None
        self._tts_voice          = ""

    # ── Tool: Transfer to Human (stays in agent — needs SIP context) ──────
    @llm.function_tool(description="Transfer this call to a human agent. Use if: caller asks for human, is angry, or query is outside scope.")
    async def transfer_call(self) -> str:
        logger.info("[TOOL] transfer_call triggered")
        destination = os.getenv("DEFAULT_TRANSFER_NUMBER")
        if destination and self.sip_domain and "@" not in destination:
            clean_dest  = destination.replace("tel:", "").replace("sip:", "")
            destination = f"sip:{clean_dest}@{self.sip_domain}"
        if destination and not destination.startswith("sip:"):
            destination = f"sip:{destination}"
        try:
            if self.ctx_api and self.room_name and destination and self._sip_identity:
                await self.ctx_api.sip.transfer_sip_participant(
                    api.TransferSIPParticipantRequest(
                        room_name=self.room_name,
                        participant_identity=self._sip_identity,
                        transfer_to=destination,
                        play_dialtone=False,
                    )
                )
                return "Transfer initiated successfully."
            return "Unable to transfer right now."
        except Exception as e:
            logger.error(f"Transfer failed: {e}")
            return "Unable to transfer right now."

    # ── Tool: End Call (stays in agent — needs SIP context) ────────────────
    @llm.function_tool(description="End the call. Use ONLY when caller says bye/goodbye or after booking is fully confirmed.")
    async def end_call(self) -> str:
        logger.info("[TOOL] end_call triggered — hanging up.")
        try:
            if self.ctx_api and self.room_name and self._sip_identity:
                await self.ctx_api.sip.transfer_sip_participant(
                    api.TransferSIPParticipantRequest(
                        room_name=self.room_name,
                        participant_identity=self._sip_identity,
                        transfer_to="tel:+00000000",
                        play_dialtone=False,
                    )
                )
        except Exception as e:
            logger.warning(f"[END-CALL] SIP hangup failed: {e}")
        return "Call ended."

    # ── Tool: Book Site Visit (fire-and-forget to backend) ────────────
    @llm.function_tool(description="Save site visit request. Call this ONCE after you have name, phone, preferred time, and property preferences (BHK, budget, area).")
    async def book_site_visit(
        self,
        visit_time:  Annotated[str,  "ISO 8601 datetime for the visit e.g. '2026-03-01T10:00:00+05:30'"],
        caller_name: Annotated[str,  "Full name of the caller"],
        caller_phone:Annotated[str,  "Phone number of the caller"],
        property_preferences: Annotated[str, "Summary of what they want: e.g. 2BHK, 50L budget, Andheri"],
        notes:       Annotated[str,  "Any extra notes or requests"] = "",
    ) -> str:
        logger.info(f"[TOOL] book_site_visit: {caller_name} at {visit_time}")
        try:
            self.booking_intent = {
                "visit_time":   visit_time,
                "caller_name":  caller_name,
                "caller_phone": caller_phone,
                "notes":        notes,
            }
            self.caller_name = caller_name
            self.property_preferences = property_preferences
            # Fire-and-forget to backend — don't block the agent
            asyncio.create_task(_backend.post("/api/re/book-site-visit", json={
                "visit_time":   visit_time,
                "caller_name":  caller_name,
                "caller_phone": caller_phone,
                "property_preferences": property_preferences,
                "notes":        notes,
                "tts_voice":    self._tts_voice,
            }))
            return f"Site visit noted for {caller_name} at {visit_time}. I'll have the team send a WhatsApp confirmation."
        except Exception as e:
            logger.error(f"[TOOL] book_site_visit failed: {e}")
            return "I had trouble noting down the visit. Please try again."



    # ── Tool: Business Hours (sync — agent needs hours data) ──────────────
    @llm.function_tool(description="Check if the business is currently open and what the operating hours are.")
    async def get_business_hours(self) -> str:
        try:
            resp = await _backend.get("/api/re/business-hours")
            data = resp.json()
            return data.get("message", "Unable to check business hours right now.")
        except Exception as e:
            logger.error(f"[TOOL] get_business_hours failed: {e}")
            return "Unable to check business hours right now."


# ══════════════════════════════════════════════════════════════════════════════
# AGENT CLASS
# ══════════════════════════════════════════════════════════════════════════════

class OutboundAssistant(Agent):

    def __init__(self, agent_tools: AgentTools, first_line: str = "", live_config: dict | None = None):
        tools = llm.find_function_tools(agent_tools)
        self._first_line  = first_line
        self._live_config = live_config or {}
        live_config_loaded = self._live_config

        base_instructions = live_config_loaded.get("agent_instructions", "")
        ist_context       = get_ist_time_context()
        lang_preset       = live_config_loaded.get("lang_preset", "multilingual")
        lang_instruction  = get_language_instruction(lang_preset)
        final_instructions = base_instructions + ist_context + lang_instruction

        # Token counter (#11)
        token_count = count_tokens(final_instructions)
        logger.info(f"[PROMPT] System prompt: {token_count} tokens")
        if token_count > 600:
            logger.warning(f"[PROMPT] Prompt exceeds 600 tokens — consider trimming for latency")

        super().__init__(instructions=final_instructions, tools=tools)

    async def on_enter(self):
        greeting = self._live_config.get(
            "first_line",
            self._first_line or (
                "Haan ji, namaskar! Aap kaunsi property dhundh rahe hain — buy karna hai ya rent?"
            )
        )
        await self.session.generate_reply(
            instructions=f"Say exactly this phrase: '{greeting}'"
        )


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRYPOINT
# ══════════════════════════════════════════════════════════════════════════════

agent_is_speaking = False

async def entrypoint(ctx: JobContext):
    global agent_is_speaking

    # ── Connect ───────────────────────────────────────────────────────────
    await ctx.connect()
    logger.info(f"[ROOM] Connected: {ctx.room.name}")

    # ── Extract caller info ───────────────────────────────────────────────
    phone_number = None
    caller_name  = ""
    caller_phone = "unknown"
    is_outbound  = False

    # Try metadata first (outbound dispatch)
    metadata = ctx.job.metadata or ""
    if metadata:
        try:
            meta = json.loads(metadata)
            phone_number = meta.get("phone_number")
            if phone_number and phone_number.startswith("+"):
                is_outbound = True
        except Exception:
            pass

    # Extract from SIP participants
    for identity, participant in ctx.room.remote_participants.items():
        # Name from caller ID (#32)
        if participant.name and participant.name not in ("", "Caller", "Unknown"):
            caller_name = participant.name
            logger.info(f"[CALLER-ID] Name from SIP: {caller_name}")
        if not phone_number:
            attr = participant.attributes or {}
            phone_number = attr.get("sip.phoneNumber") or attr.get("phoneNumber")
        if not phone_number and "+" in identity:
            import re as _re
            m = _re.search(r"\+\d{7,15}", identity)
            if m:
                phone_number = m.group()

    caller_phone = phone_number or "unknown"

    # ── Outbound: Dial via SIP trunk ──────────────────────────────────────
    if is_outbound and phone_number:
        sip_trunk_id = os.getenv("SIP_TRUNK_ID", "")
        if not sip_trunk_id:
            logger.error("[OUTBOUND] SIP_TRUNK_ID not set")
            return
        try:
            logger.info(f"[OUTBOUND] Dialing {phone_number}")
            await ctx.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    sip_trunk_id=sip_trunk_id,
                    sip_call_to=phone_number,
                    room_name=ctx.room.name,
                    participant_identity=f"sip_{phone_number.replace('+', '')}",
                    participant_name=phone_number,
                )
            )
            logger.info(f"[OUTBOUND] Ringing {phone_number}")
        except Exception as e:
            logger.error(f"[OUTBOUND] Dial failed: {e}")
            return

    # ── Rate limiting (#37) ───────────────────────────────────────────────
    if is_rate_limited(caller_phone):
        logger.warning(f"[RATE-LIMIT] Blocked {caller_phone} — too many calls in 1h")
        return

    # ── Load config ───────────────────────────────────────────────────────
    live_config   = get_live_config(caller_phone)
    delay_setting = live_config.get("stt_min_endpointing_delay", 0.05)
    llm_model     = live_config.get("llm_model", "gpt-4o-mini")
    llm_provider  = live_config.get("llm_provider", "openai")
    tts_voice     = live_config.get("tts_voice", "kavya")
    tts_language  = live_config.get("tts_language", "hi-IN")
    tts_provider  = live_config.get("tts_provider", "sarvam")
    stt_provider  = live_config.get("stt_provider", "sarvam")
    stt_language  = live_config.get("stt_language", "unknown")  # auto-detect (#20)
    max_turns     = live_config.get("max_turns", 25)

    # Override OS env vars from UI config
    for key in ["LIVEKIT_URL","LIVEKIT_API_KEY","LIVEKIT_API_SECRET","OPENAI_API_KEY",
                "SARVAM_API_KEY","CAL_API_KEY","TELEGRAM_BOT_TOKEN","SUPABASE_URL","SUPABASE_KEY"]:
        val = live_config.get(key.lower(), "")
        if val:
            os.environ[key] = val

    # ── Caller memory (#15) ───────────────────────────────────────────────
    async def get_caller_history(phone: str) -> str:
        if phone == "unknown":
            return ""
        try:
            import db
            sb = db.get_supabase()
            if not sb:
                return ""
            result = (sb.table("real_estate_calls")
                        .select("summary, created_at")
                        .eq("phone_number", phone)
                        .order("created_at", desc=True)
                        .limit(1)
                        .execute())
            if result.data:
                last = result.data[0]
                return f"\n\n[CALLER HISTORY: Last call {last['created_at'][:10]}. Summary: {last['summary']}]"
        except Exception as e:
            logger.warning(f"[MEMORY] Could not load history: {e}")
        return ""

    caller_history = await get_caller_history(caller_phone)
    if caller_history:
        logger.info(f"[MEMORY] Loaded caller history for {caller_phone}")
        # Append to live_config instructions
        live_config["agent_instructions"] = (live_config.get("agent_instructions","") + caller_history)

    # ── Instantiate tools ─────────────────────────────────────────────────
    agent_tools = AgentTools(caller_phone=caller_phone, caller_name=caller_name)
    agent_tools._sip_identity = (
        f"sip_{caller_phone.replace('+','')}" if phone_number else "inbound_caller"
    )
    agent_tools.ctx_api   = ctx.api
    agent_tools.room_name = ctx.room.name
    agent_tools._tts_voice = tts_voice

    # ── Determine model mode ────────────────────────────────────────────────
    model_mode = os.getenv("MODEL", "normal").lower()

    # ── Build LLM / STT / TTS — only needed for "normal" mode ─────────────
    agent_llm = None
    agent_stt = None
    agent_tts = None

    if model_mode != "gemini":
        # ── Build LLM (#8 Groq support) ───────────────────────────────────
        if llm_provider == "groq":
            agent_llm = openai.LLM.with_groq(
                model=llm_model or "llama-3.3-70b-versatile",
                max_completion_tokens=120,
            )
            logger.info(f"[LLM] Using Groq: {llm_model}")
        elif llm_provider == "claude":
            # Claude Haiku 3.5 via Anthropic API (#27)
            _anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
            agent_llm = openai.LLM(
                model=llm_model or "claude-haiku-3-5-latest",
                base_url="https://api.anthropic.com/v1/",
                api_key=_anthropic_key,
                max_completion_tokens=120,
            )
            logger.info(f"[LLM] Using Claude via Anthropic: {llm_model}")
        elif llm_provider == "azure":
            agent_llm = openai.LLM.with_azure(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT", llm_model or "gpt-4o-mini"),
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
                api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            )
            logger.info(f"[LLM] Using Azure OpenAI: {llm_model}")
        else:
            agent_llm = openai.LLM(model=llm_model, max_completion_tokens=120)  # cap tokens (#7)
            logger.info(f"[LLM] Using OpenAI: {llm_model}")

        # ── Build STT (#1 16kHz, #20 auto-detect, #9 Deepgram) ──────────────
        if stt_provider == "deepgram":
            try:
                from livekit.plugins import deepgram
                agent_stt = deepgram.STT(
                    model="nova-2-general",
                    language="multi",        # multilingual mode
                    interim_results=False,
                )
                logger.info("[STT] Using Deepgram Nova-2")
            except ImportError:
                logger.warning("[STT] deepgram plugin not installed — falling back to Sarvam")
                agent_stt = sarvam.STT(
                    language=stt_language,
                    model="saaras:v3",
                    mode="translate",
                    flush_signal=True,
                    sample_rate=16000,
                )
        else:
            agent_stt = sarvam.STT(
                language=stt_language,      # "unknown" = auto-detect (#20)
                model="saaras:v3",
                mode="translate",
                flush_signal=True,
                sample_rate=16000,          # force 16kHz (#1)
            )
            logger.info("[STT] Using Sarvam Saaras v3")

        # ── Build TTS (#2 24kHz, #10 ElevenLabs) ────────────────────────────
        if tts_provider == "elevenlabs":
            try:
                from livekit.plugins import elevenlabs
                _el_voice_id = live_config.get("elevenlabs_voice_id", "21m00Tcm4TlvDq8ikWAM")
                agent_tts = elevenlabs.TTS(
                    model="eleven_turbo_v2_5",
                    voice_id=_el_voice_id,
                )
                logger.info(f"[TTS] Using ElevenLabs Turbo v2.5 — voice: {_el_voice_id}")
            except ImportError:
                logger.warning("[TTS] elevenlabs plugin not installed — falling back to Sarvam")
                agent_tts = sarvam.TTS(
                    target_language_code=tts_language,
                    model="bulbul:v3",
                    speaker=tts_voice,
                    speech_sample_rate=24000,
                )
        else:
            agent_tts = sarvam.TTS(
                target_language_code=tts_language,
                model="bulbul:v3",
                speaker=tts_voice,
                speech_sample_rate=24000,          # force 24kHz (#2)
            )
            logger.info(f"[TTS] Using Sarvam Bulbul v3 — voice: {tts_voice} lang: {tts_language}")

    # ── Sentence chunker (keep responses short for voice) ─────────────────
    def before_tts_cb(agent_response: str) -> str:
        sentences = re.split(r'(?<=[।.!?])\s+', agent_response.strip())
        return sentences[0] if sentences else agent_response

    # ── Turn counter + auto-close (#29) ──────────────────────────────────
    turn_count    = 0
    interrupt_count = 0  # (#30)

    # ── Build agent ───────────────────────────────────────────────────────
    agent = OutboundAssistant(
        agent_tools=agent_tools,
        first_line=live_config.get("first_line", ""),
        live_config=live_config,
    )

    # ── Build session (#3 noise cancellation attempted) ───────────────────
    try:
        from livekit.agents import noise_cancellation as nc
        _noise_cancel = nc.BVC()
        logger.info("[AUDIO] BVC noise cancellation enabled")
    except Exception:
        _noise_cancel = None
        logger.info("[AUDIO] BVC not available — running without noise cancellation")

    room_input = RoomInputOptions(close_on_disconnect=False)
    if _noise_cancel:
        try:
            room_input = RoomInputOptions(close_on_disconnect=False, noise_cancellation=_noise_cancel)
        except Exception:
            room_input = RoomInputOptions(close_on_disconnect=False)

    if model_mode == "gemini":
        from livekit.plugins import google

        logger.info("[MODEL] Using Gemini 2.5 Flash Live (Vertex AI) — native audio mode")
        gemini_voice = live_config.get("gemini_voice", "Puck")

        gemini_model = google.realtime.RealtimeModel(
            model="gemini-2.5-flash-native-audio-preview-12-2025",
            voice=gemini_voice,
            temperature=0.8,
            instructions=agent.instructions,
            api_key=os.getenv("GOOGLE_API_KEY"),
            # Enable thinking for better reasoning (adds latency):
            # thinking_config=google.ThinkingConfig(enabled=True),
        )

        session = AgentSession(
            llm=gemini_model,
            allow_interruptions=True,
        )
    else:
        # ── Normal mode: Azure OpenAI + Sarvam STT/TTS pipeline ──────────
        session = AgentSession(
            stt=agent_stt,
            llm=agent_llm,
            tts=agent_tts,
            turn_detection="stt",
            min_endpointing_delay=float(delay_setting),  # 0.05 default (#6)
            allow_interruptions=True,
        )

    await session.start(room=ctx.room, agent=agent, room_input_options=room_input)

    # ── TTS pre-warm (#12) — only in normal mode ─────────────────────────
    if session.tts and hasattr(session.tts, "prewarm"):
        try:
            await session.tts.prewarm()  # type: ignore[misc]
            logger.info("[TTS] Pre-warmed successfully")
        except Exception as e:
            logger.debug(f"[TTS] Pre-warm skipped: {e}")

    logger.info("[AGENT] Session live — waiting for caller audio.")
    call_start_time = datetime.now()

    # ── Upsert active_calls (fire-and-forget to backend) ──────────────────
    asyncio.create_task(_backend.post("/api/internal/active-call", json={
        "room_id":     ctx.room.name,
        "phone":       caller_phone,
        "caller_name": caller_name,
        "status":      "active",
    }))

    # ── Session event handlers ────────────────────────────────────────────
    @session.on("agent_speech_started")
    def _agent_speech_started(ev):
        global agent_is_speaking
        agent_is_speaking = True

    @session.on("agent_speech_finished")
    def _agent_speech_finished(ev):
        global agent_is_speaking
        agent_is_speaking = False

    # Interrupt logging (#30)
    @session.on("agent_speech_interrupted")
    def _on_interrupted(ev):
        nonlocal interrupt_count
        interrupt_count += 1
        logger.info(f"[INTERRUPT] Agent interrupted. Total: {interrupt_count}")

    FILLER_WORDS = {
        "okay.", "okay", "ok", "uh", "hmm", "hm", "yeah", "yes",
        "no", "um", "ah", "oh", "right", "sure", "fine", "good",
        "haan", "han", "theek", "theek hai", "accha", "ji", "ha",
    }

    @session.on("user_speech_committed")
    def on_user_speech_committed(ev):
        nonlocal turn_count
        global agent_is_speaking

        transcript = ev.user_transcript.strip()
        transcript_lower = transcript.lower().rstrip(".")

        if agent_is_speaking:
            logger.debug(f"[FILTER-ECHO] Dropped: '{transcript}'")
            return
        if not transcript or len(transcript) < 3:
            return
        if transcript_lower in FILLER_WORDS:
            logger.debug(f"[FILTER-FILLER] Dropped: '{transcript}'")
            return

        # Real-time transcript stream — fire-and-forget to backend
        asyncio.create_task(_backend.post("/api/internal/transcript", json={
            "room_id": ctx.room.name,
            "phone":   caller_phone,
            "role":    "user",
            "content": transcript,
        }))

        # Turn counter + auto-close (#29)
        turn_count += 1
        logger.info(f"[TRANSCRIPT] Turn {turn_count}/{max_turns}: '{transcript}'")
        if turn_count >= max_turns:
            logger.info(f"[LIMIT] Reached {max_turns} turns — wrapping up")
            asyncio.create_task(
                session.generate_reply(
                    instructions="Politely wrap up: thank the caller, say they can call back anytime, and say a warm goodbye."
                )
            )

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant):
        global agent_is_speaking
        logger.info(f"[HANGUP] Participant disconnected: {participant.identity}")
        agent_is_speaking = False
        asyncio.create_task(unified_shutdown_hook(ctx))

    # ══════════════════════════════════════════════════════════════════════
    # POST-CALL SHUTDOWN HOOK — Single fire-and-forget to backend
    # ══════════════════════════════════════════════════════════════════════

    async def unified_shutdown_hook(shutdown_ctx: JobContext):
        logger.info("[SHUTDOWN] Sequence started.")

        duration = int((datetime.now() - call_start_time).total_seconds())

        # Build transcript
        transcript_text = ""
        try:
            messages = agent.chat_ctx.messages
            if callable(messages):
                messages = messages()
            lines = []
            for msg in messages:
                if getattr(msg, "role", None) in ("user", "assistant"):
                    content = getattr(msg, "content", "")
                    if isinstance(content, list):
                        content = " ".join(str(c) for c in content if isinstance(c, str))
                    lines.append(f"[{msg.role.upper()}] {content}")
            transcript_text = "\n".join(lines)
        except Exception as e:
            logger.error(f"[SHUTDOWN] Transcript read failed: {e}")
            transcript_text = "unavailable"

        # Update active_calls to completed — fire-and-forget
        asyncio.create_task(_backend.post("/api/internal/active-call", json={
            "room_id":     ctx.room.name,
            "phone":       caller_phone,
            "caller_name": caller_name,
            "status":      "completed",
        }))

        # Single fire-and-forget POST — backend handles everything:
        # sentiment analysis, cost estimation, DB writes, notifications, webhooks
        try:
            asyncio.create_task(_backend.post("/api/internal/call-completed", json={
                "phone":           caller_phone,
                "caller_name":     agent_tools.caller_name or "",
                "duration":        duration,
                "transcript":      transcript_text,
                "agent_type":      "real_estate",
                "booking_intent":  agent_tools.booking_intent,
                "property_preferences": agent_tools.property_preferences,
                "interrupt_count": interrupt_count,
                "tts_voice":       tts_voice,
                "room_name":       ctx.room.name,
            }))
            logger.info("[SHUTDOWN] Dispatched call-completed to backend.")
        except Exception as e:
            logger.error(f"[SHUTDOWN] Failed to dispatch to backend: {e}")

    ctx.add_shutdown_callback(unified_shutdown_hook)


# ══════════════════════════════════════════════════════════════════════════════
# WORKER ENTRY
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name="real-estate-agent",
        port=8083,
    ))
