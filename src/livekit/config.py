"""Voice agent configuration: env-var defaults and per-call overrides.

Two frozen dataclasses keep config honest:
- VoiceSettings  : loaded once at startup from environment variables.
- CallConfig     : derived per-call from room metadata + VoiceSettings defaults.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

REALTIME_MODES: frozenset[str] = frozenset({"openai_realtime", "gemini_live", "ultravox"})

SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "ar": "Arabic",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Portuguese",
    "it": "Italian",
    "nl": "Dutch",
    "ru": "Russian",
    "tr": "Turkish",
    "hi": "Hindi",
}

# Languages the configured Deepgram model (nova-2) rejects outright (HTTP 400 on
# connect). Confirmed for Arabic: https://developers.deepgram.com/docs/models-languages-overview
# — sessions using these must fall back to local faster-whisper instead.
DEEPGRAM_UNSUPPORTED_LANGUAGES: frozenset[str] = frozenset({"ar"})

# Slower OpenAI TTS playback (0.25-4.0, default 1.0) for beginner learners in
# languages where kids need more time to follow along. Not used for languages
# covered by TTS_PROVIDER_OVERRIDES below — Edge TTS's rate control (real
# prosody) replaces this audio-stretch approach for those.
TTS_SPEED_OVERRIDES: dict[str, float] = {}

# Force Edge TTS (native regional neural voice + real prosody-based rate control)
# for these languages regardless of the globally configured TTS_PROVIDER — a
# beginner needs a natural, unhurried accent, not OpenAI's audio-stretched "speed".
TTS_PROVIDER_OVERRIDES: dict[str, str] = {"ar": "edge_tts"}

# Edge TTS speech-rate override per language (SSML-style percentage, e.g. "-15%").
EDGE_TTS_RATE_OVERRIDES: dict[str, str] = {"ar": "-15%"}

# faster-whisper model size to use when falling back from Deepgram (see
# DEEPGRAM_UNSUPPORTED_LANGUAGES above). "base" is fast but weak on accented or
# imperfect beginner pronunciation; Arabic gets "small" for meaningfully better
# accuracy at some added CPU latency.
FASTER_WHISPER_FALLBACK_MODEL: dict[str, str] = {"ar": "small"}
FASTER_WHISPER_FALLBACK_DEFAULT = "base"

_LANG_NAME_TO_CODE: dict[str, str] = {v: k for k, v in SUPPORTED_LANGUAGES.items()}


def build_lingua_prompt(learning_language: str, native_language: str) -> str:
    """Return the target-language prompt for pipeline / realtime LLMs.

    Accepts full language names (e.g. "German", "English") as used by providers.py
    and delegates to the per-language prompt package in src/langgraph/prompts/.
    """
    from src.langgraph.prompts import build_prompt
    lang_code   = _LANG_NAME_TO_CODE.get(learning_language, "en")
    native_code = _LANG_NAME_TO_CODE.get(native_language, "en")
    return build_prompt(lang_code, native_code)

# Kokoro-FastAPI language → voice mapping (used by providers.py and tts_label).
# Arabic deliberately absent — Kokoro has no Arabic voice; falls back to OpenAI.
KOKORO_VOICES: dict[str, str] = {
    "en": "af_sky",
    "de": "ef_dora",
    "hi": "hf_alpha",
}

# Microsoft Edge TTS neural voices — native speakers for all four languages.
EDGE_TTS_VOICES: dict[str, str] = {
    "en": "en-US-JennyNeural",
    "de": "de-DE-SeraphinaMultilingualNeural",
    "hi": "hi-IN-SwaraNeural",
    "ar": "ar-SA-ZariyahNeural",
}

_WHISPER_MODELS: frozenset[str] = frozenset({
    "tiny.en", "tiny", "base.en", "base", "small.en", "small",
    "medium.en", "medium", "large-v1", "large-v2", "large-v3", "large",
    "distil-large-v2", "distil-medium.en", "distil-small.en",
    "distil-large-v3", "distil-large-v3.5", "large-v3-turbo", "turbo",
})

_STT_ALIASES: dict[str, str] = {
    "nova-3": "base", "nova-2": "base", "nova": "base", "deepgram": "base",
}


def _normalize_stt_model(raw: str) -> str:
    """Map an arbitrary STT_MODEL string to a valid faster-whisper model size."""
    value = raw.strip().split("#", 1)[0].strip().lower()
    if not value:
        return "base"
    if value in _STT_ALIASES:
        return _STT_ALIASES[value]
    if value in _WHISPER_MODELS:
        return value
    for token in value.replace(",", " ").split():
        if token in _STT_ALIASES:
            return _STT_ALIASES[token]
        if token in _WHISPER_MODELS:
            return token
    return "base"


# ── VoiceSettings ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class VoiceSettings:
    """Env-var defaults for the voice worker. Created once at startup via from_env()."""

    voice_mode: str
    llm_model: str
    langgraph_url: str
    language: str  # BCP-47 language code, e.g. "en", "es", "fr"

    # STT
    stt_provider: str  # "deepgram" or "faster_whisper"
    stt_model: str

    # TTS (pipeline mode)
    tts_provider: str
    tts_model: str
    tts_voice: str
    tts_base_url: str | None
    tts_api_key: str | None

    # Realtime provider specifics
    openai_realtime_model: str
    openai_realtime_voice: str
    gemini_live_model: str
    gemini_live_voice: str
    ultravox_model: str
    ultravox_voice: str

    @classmethod
    def from_env(cls) -> "VoiceSettings":
        stt_provider = os.getenv("STT_PROVIDER", "faster_whisper").lower().strip()
        stt_raw = os.getenv("STT_MODEL", "base")
        if stt_provider == "deepgram":
            # Don't normalize — Deepgram models have their own naming (nova-2, nova-3, etc.)
            stt_model = stt_raw.strip() or "nova-2"
        else:
            stt_model = _normalize_stt_model(stt_raw)
            normalized = stt_raw.strip().split("#", 1)[0].strip().lower()
            if stt_model != normalized and normalized:
                logger.warning("STT_MODEL=%r is not a valid faster-whisper size; using %r", stt_raw, stt_model)
        raw_lang = os.getenv("LANGUAGE", "en").strip().lower().split("-")[0]
        language = raw_lang if raw_lang in SUPPORTED_LANGUAGES else "en"
        return cls(
            voice_mode=os.getenv("VOICE_MODE", "pipeline").lower(),
            llm_model=os.getenv("LLM_MODEL", "gpt-4.1-nano"),
            langgraph_url=os.getenv("LANGGRAPH_URL", "http://localhost:2024"),
            language=language,
            stt_provider=stt_provider,
            stt_model=stt_model,
            tts_provider=os.getenv("TTS_PROVIDER", "hume"),
            tts_model=os.getenv("TTS_MODEL", "default"),
            tts_voice=os.getenv("TTS_VOICE", "ash"),
            tts_base_url=os.getenv("TTS_BASE_URL") or None,
            tts_api_key=os.getenv("TTS_API_KEY") or None,
            openai_realtime_model=os.getenv("OPENAI_REALTIME_MODEL", "gpt-4o-mini-realtime-preview"),
            openai_realtime_voice=os.getenv("OPENAI_REALTIME_VOICE", "alloy"),
            gemini_live_model=os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview"),
            gemini_live_voice=os.getenv("GEMINI_LIVE_VOICE", "Puck"),
            ultravox_model=os.getenv("ULTRAVOX_MODEL", "fixie-ai/ultravox"),
            ultravox_voice=os.getenv("ULTRAVOX_VOICE", "Mark"),
        )


# ── CallConfig ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CallConfig:
    """Per-call voice configuration resolved from room metadata + env defaults."""

    voice_mode: str
    language: str         # language to learn (BCP-47 code)
    native_language: str  # user's native language (BCP-47 code)
    stt_provider: str     # "deepgram" or "faster_whisper"
    stt_model: str
    tts_provider: str
    tts_model: str
    tts_voice: str
    tts_base_url: str | None  # always from VoiceSettings — not overridable per call

    @property
    def is_realtime(self) -> bool:
        return self.voice_mode in REALTIME_MODES

    @property
    def tts_label(self) -> str:
        """Human-readable TTS identifier for tags/traces, e.g. 'edge_tts:de-DE-SeraphinaMultilingualNeural'."""
        effective_provider = TTS_PROVIDER_OVERRIDES.get(self.language, self.tts_provider)
        if effective_provider == "edge_tts":
            voice = EDGE_TTS_VOICES.get(self.language, EDGE_TTS_VOICES["en"])
            return f"edge_tts:{voice}"
        if effective_provider == "openai" and self.tts_base_url:
            voice = KOKORO_VOICES.get(self.language, self.tts_voice)
            return f"kokoro:{voice}"
        return f"{effective_provider}:{self.tts_voice}"

    @property
    def language_name(self) -> str:
        return SUPPORTED_LANGUAGES.get(self.language, "English")

    @property
    def native_language_name(self) -> str:
        return SUPPORTED_LANGUAGES.get(self.native_language, "English")

    def langfuse_tags(self, settings: VoiceSettings) -> list[str]:
        tags = ["voice-call", "lingua-ai", f"voice_mode:{self.voice_mode}", f"language:{self.language}", f"native:{self.native_language}"]
        if self.is_realtime:
            realtime_info: dict[str, tuple[str, str]] = {
                "openai_realtime": (settings.openai_realtime_model, settings.openai_realtime_voice),
                "gemini_live": (settings.gemini_live_model, settings.gemini_live_voice),
                "ultravox": (settings.ultravox_model, settings.ultravox_voice),
            }
            model, voice = realtime_info.get(self.voice_mode, ("", ""))
            tags.extend(["stack:realtime", f"model:{model}", f"voice:{voice}"])
        else:
            tags.extend([
                "stack:pipeline",
                f"llm:openai:{settings.llm_model}",
                f"stt:{self.stt_provider}:{self.stt_model}",
                f"tts:{self.tts_label}",
            ])
        return tags

    @classmethod
    def from_room_metadata(cls, metadata_json: str | None, defaults: VoiceSettings) -> "CallConfig":
        meta: dict = {}
        if metadata_json:
            try:
                meta = json.loads(metadata_json)
            except Exception:
                logger.warning("Failed to parse room metadata JSON; using env defaults")
        if meta:
            logger.info("Per-call config from room metadata: %s", meta)
        raw_lang = (meta.get("language") or defaults.language).strip().lower().split("-")[0]
        language = raw_lang if raw_lang in SUPPORTED_LANGUAGES else defaults.language
        raw_native = (meta.get("native_language") or "en").strip().lower().split("-")[0]
        native_language = raw_native if raw_native in SUPPORTED_LANGUAGES else "en"
        return cls(
            voice_mode=meta.get("voice_mode", defaults.voice_mode).lower(),
            language=language,
            native_language=native_language,
            stt_provider=defaults.stt_provider,
            stt_model=meta.get("stt_model") or defaults.stt_model,
            tts_provider=meta.get("tts_provider") or defaults.tts_provider,
            tts_model=meta.get("tts_model") or defaults.tts_model,
            tts_voice=meta.get("tts_voice") or defaults.tts_voice,
            tts_base_url=defaults.tts_base_url,
        )
