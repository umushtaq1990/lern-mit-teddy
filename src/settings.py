"""Single shared configuration surface for the whole app.

Every env var read anywhere in `src/` should go through this module instead of
a bare `os.getenv()` call — that's what makes every other package importable
and testable without env-var-before-import ordering tricks, and gives one
place that documents the full config surface.

Usage: `from src.settings import get_settings` then `get_settings().foo`.
`get_settings()` is lazily constructed and cached — nothing here runs at
import time, so importing this module (or anything that imports it) never
requires any env var to be set.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # ── LiveKit ──────────────────────────────────────────────────────────────
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_agent_name: str = ""

    # ── LLM ──────────────────────────────────────────────────────────────────
    llm_model: str = "gpt-4.1-nano"
    openai_api_key: str = ""

    # ── Voice pipeline ───────────────────────────────────────────────────────
    voice_mode: str = "pipeline"
    language: str = "en"
    langgraph_url: str = "http://localhost:2024"

    # STT
    stt_provider: str = "faster_whisper"
    stt_model: str = "base"
    deepgram_api_key: str = ""

    # TTS (pipeline mode)
    tts_provider: str = "hume"
    tts_model: str = "default"
    tts_voice: str = "ash"
    tts_base_url: str | None = None
    tts_api_key: str | None = None
    hume_api_key: str = ""
    hume_secret_key: str = ""
    hume_config_id: str = ""
    nvidia_api_key: str = ""
    nvidia_tts_function_id: str = "ddacc747-1269-4fab-bfd9-8f593dead106"

    # Realtime provider specifics
    openai_realtime_model: str = "gpt-4o-mini-realtime-preview"
    openai_realtime_voice: str = "alloy"
    gemini_live_model: str = "gemini-3.1-flash-live-preview"
    gemini_live_voice: str = "Puck"
    ultravox_model: str = "fixie-ai/ultravox"
    ultravox_voice: str = "Mark"

    # ── Langfuse tracing ─────────────────────────────────────────────────────
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""
    langfuse_base_url: str = ""

    # ── Auth (Microsoft Entra External ID / CIAM) ───────────────────────────
    auth_tenant_id: str = ""
    auth_domain: str = ""  # e.g. "lernmitteddyusers"
    auth_client_id: str = ""
    auth_client_secret: str = ""
    auth_session_secret: str = "dev-only-insecure-secret"
    session_cookie_secure: bool = True

    # ── Frontend ─────────────────────────────────────────────────────────────
    frontend_host: str = "127.0.0.1"
    frontend_port: int = 8080
    frontend_reload: bool = True
    frontend_url: str = ""

    # ── Database (new) ───────────────────────────────────────────────────────
    database_url: str = "sqlite:///./local.db"

    # ── MLflow (new) ─────────────────────────────────────────────────────────
    mlflow_tracking_uri: str = "sqlite:///./mlflow.db"

    # ── Cloud export job (pipelines/langfuse_export) ────────────────────────
    # Documented here for visibility even though the export job reads these
    # itself via os.environ — it's a standalone job by design (see its own
    # module docstring) and intentionally does not import this settings module.
    sql_server: str = ""
    sql_database: str = ""
    sql_user: str = ""
    sql_password: str = ""
    storage_connection_string: str = ""
    storage_container: str = "transcripts"

    # ── Urdu/Arabic learning app (new, isolated module: src/urdu_arabic) ────
    urdu_arabic_session_secret: str = "dev-only-insecure-secret"
    urdu_arabic_otp_ttl_seconds: int = 300
    urdu_arabic_host: str = "127.0.0.1"
    urdu_arabic_port: int = 8090

    # OTP delivery: email via Gmail SMTP (stdlib smtplib, an App Password --
    # see src/urdu_arabic/otp_delivery.py docstring for setup) and WhatsApp
    # via Twilio's REST API (httpx, no SDK dependency added). Any of these
    # left unset falls back to logging the code instead of sending it, same
    # as before -- never a hard failure for local dev.
    urdu_arabic_smtp_host: str = "smtp.gmail.com"
    urdu_arabic_smtp_port: int = 587
    urdu_arabic_smtp_user: str = ""
    urdu_arabic_smtp_app_password: str = ""
    urdu_arabic_otp_email_from_name: str = "Lisan"

    urdu_arabic_twilio_account_sid: str = ""
    urdu_arabic_twilio_auth_token: str = ""
    # Twilio's shared sandbox WhatsApp number -- works immediately for
    # testing (recipients must first join the sandbox), swap for your own
    # Twilio WhatsApp-enabled number once approved for production.
    urdu_arabic_twilio_whatsapp_from: str = "whatsapp:+14155238886"

    # ── Local LLM (Ollama) ───────────────────────────────────────────────────
    # Same pattern as JME: a local Ollama server, plain HTTP, no OpenAI spend.
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_timeout_seconds: int = 60


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
