"""TTS and realtime-LLM provider factories.

create_tts()          : builds the TTS backend for a pipeline-mode call.
create_realtime_llm() : builds the realtime LLM for openai_realtime / gemini_live / ultravox.
TracedTTS             : TTS wrapper that emits a Langfuse span per synthesis call.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from livekit.agents import tts as tts_base
from livekit.plugins import hume, openai

from .config import (
    EDGE_TTS_RATE_OVERRIDES,
    EDGE_TTS_VOICES,
    KOKORO_VOICES,
    SUPPORTED_LANGUAGES,
    TTS_PROVIDER_OVERRIDES,
    TTS_SPEED_OVERRIDES,
    CallConfig,
    VoiceSettings,
    build_lingua_prompt,
)

if TYPE_CHECKING:
    from .tracing import VoiceSessionTracer

logger = logging.getLogger(__name__)


def create_tts(cfg: CallConfig, settings: VoiceSettings) -> tts_base.TTS:
    """Instantiate the TTS backend for a pipeline call."""
    provider = TTS_PROVIDER_OVERRIDES.get(cfg.language, cfg.tts_provider.lower())
    if provider != cfg.tts_provider.lower():
        logger.info(
            "TTS provider override — language=%s configured=%s using=%s",
            cfg.language, cfg.tts_provider, provider,
        )

    if provider == "nvidia_riva":
        from .riva_tts import RivaTTS
        logger.info("NVIDIA Riva TTS — language=%s", cfg.language)
        return RivaTTS(api_key=settings.nvidia_api_key or "missing", language=cfg.language)

    if provider == "openai":
        kwargs: dict[str, Any] = {}

        using_kokoro = bool(settings.tts_base_url)
        arabic_no_kokoro = using_kokoro and cfg.language == "ar"

        if arabic_no_kokoro:
            # Kokoro has no Arabic voice — route Arabic to real OpenAI TTS API.
            logger.info("Arabic TTS: Kokoro has no Arabic voice, falling back to OpenAI TTS API")
            kwargs["voice"] = "alloy"
            # No base_url → uses real OpenAI endpoint
        else:
            # Kokoro needs an explicit model name (not "default") so the plugin picks
            # AudioChunkedStream (raw bytes) rather than SSEChunkedStream (text events).
            # tts-1-hd gives the best Kokoro quality; tts-1 is standard.
            effective_model = cfg.tts_model if cfg.tts_model not in ("default", "") else "tts-1-hd"
            if effective_model and effective_model != "default":
                kwargs["model"] = effective_model

            # Pick language-appropriate Kokoro voice when using local server.
            if using_kokoro and cfg.language in KOKORO_VOICES:
                kwargs["voice"] = KOKORO_VOICES[cfg.language]
                logger.info("Kokoro TTS — language=%s voice=%s", cfg.language, kwargs["voice"])
            elif cfg.tts_voice:
                kwargs["voice"] = cfg.tts_voice

            if settings.tts_base_url:
                kwargs["base_url"] = settings.tts_base_url
            if settings.tts_api_key:
                kwargs["api_key"] = settings.tts_api_key

        if cfg.language in TTS_SPEED_OVERRIDES:
            kwargs["speed"] = TTS_SPEED_OVERRIDES[cfg.language]
            logger.info("TTS speed override — language=%s speed=%s", cfg.language, kwargs["speed"])

        return openai.TTS(**kwargs)

    if provider == "edge_tts":
        from .edge_tts_wrapper import EdgeTTSProvider
        voice = EDGE_TTS_VOICES.get(cfg.language, EDGE_TTS_VOICES["en"])
        rate = EDGE_TTS_RATE_OVERRIDES.get(cfg.language, "+0%")
        logger.info("Edge TTS — language=%s voice=%s rate=%s", cfg.language, voice, rate)
        return EdgeTTSProvider(language=cfg.language, rate=rate)

    if provider == "hume":
        return hume.TTS()

    raise ValueError(f"Unsupported TTS provider: {provider!r}. Expected 'openai', 'edge_tts', or 'hume'.")


def create_realtime_llm(
    voice_mode: str,
    settings: VoiceSettings,
    language: str = "en",
    native_language: str = "en",
) -> Any:
    """Instantiate the realtime LLM for the given voice mode."""
    learning_language = SUPPORTED_LANGUAGES.get(language, "English")
    native_lang_name  = SUPPORTED_LANGUAGES.get(native_language, "English")
    prompt = build_lingua_prompt(learning_language, native_lang_name)
    logger.info("Realtime LLM prompt — teaching=%s native=%s mode=%s", learning_language, native_lang_name, voice_mode)

    if voice_mode == "openai_realtime":
        return openai.realtime.RealtimeModel(
            model=settings.openai_realtime_model,
            voice=settings.openai_realtime_voice,
            instructions=prompt,
        )
    if voice_mode == "gemini_live":
        from livekit.plugins import google
        return google.beta.realtime.RealtimeModel(
            model=settings.gemini_live_model,
            voice=settings.gemini_live_voice,
            instructions=prompt,
        )
    if voice_mode == "ultravox":
        from livekit.plugins import ultravox
        return ultravox.realtime.RealtimeModel(
            model=settings.ultravox_model,
            voice=settings.ultravox_voice,
            system_prompt=prompt,
            enable_greeting_prompt=False,
            first_speaker="FIRST_SPEAKER_USER",
        )
    raise ValueError(f"Unknown realtime voice mode: {voice_mode!r}")


class TracedTTS(tts_base.TTS):
    """TTS wrapper that emits a Langfuse span for every synthesis call."""

    def __init__(
        self,
        inner: tts_base.TTS,
        tracer: "VoiceSessionTracer",
        model_name: str,
    ) -> None:
        super().__init__(
            capabilities=inner.capabilities,
            sample_rate=inner.sample_rate,
            num_channels=inner.num_channels,
        )
        self._inner = inner
        self._tracer = tracer
        self._model_name = model_name

    def synthesize(self, text: str, **kwargs: Any) -> tts_base.SynthesizeStream:
        span = self._tracer.tts_span(text=text, model=self._model_name)
        stream = self._inner.synthesize(text, **kwargs)
        original_aclose = stream.aclose

        async def _aclose_and_end() -> None:
            try:
                await original_aclose()
            finally:
                span.end(output={"char_count": len(text)})

        stream.aclose = _aclose_and_end
        return stream
