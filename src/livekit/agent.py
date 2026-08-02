"""LiveKit voice worker entry point.

Responsibilities (only):
  1. prewarm()   — preload the VAD model before the first call.
  2. entrypoint()— resolve per-call config, assemble AgentSession, run until teardown.

All construction details live in focused modules:
  config.py    → VoiceSettings / CallConfig
  providers.py → create_tts / create_realtime_llm / TracedTTS
  tracing.py   → VoiceSessionTracer / RealtimeLangfuseTracer
  vision.py    → VisionAssistant
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from dotenv import load_dotenv
from livekit.agents import (
    AgentSession,
    AutoSubscribe,
    JobContext,
    JobProcess,
    RoomInputOptions,
    WorkerOptions,
    cli,
)
from livekit.agents.voice.turn import InterruptionOptions, TurnHandlingOptions
from livekit.plugins import deepgram as deepgram_plugin
from livekit.plugins import silero
from src.langgraph.agent import agent as lingua_graph
from .adapter.langgraph import LangGraphAdapter
from .config import (
    DEEPGRAM_UNSUPPORTED_LANGUAGES,
    FASTER_WHISPER_FALLBACK_DEFAULT,
    FASTER_WHISPER_FALLBACK_MODEL,
    SUPPORTED_LANGUAGES,
    CallConfig,
    VoiceSettings,
)
from .providers import TracedTTS, create_realtime_llm, create_tts
from .session_logger import SessionLogger
from .stt import FasterWhisperSTT
from .tracing import RealtimeLangfuseTracer, VoiceSessionTracer
from .vision import VisionAssistant

load_dotenv(dotenv_path=".env")
logger = logging.getLogger("voice-agent")

# Loaded once at startup; immutable for the lifetime of the worker process.
_SETTINGS = VoiceSettings.from_env()

_TURN_HANDLING = TurnHandlingOptions(interruption=InterruptionOptions(mode="vad"))
_SESSION_KWARGS = {"min_endpointing_delay": 0.8, "max_endpointing_delay": 6.0}

_SILENCE_TIMEOUT = 5.0  # seconds before re-prompting after silence

_REPROMPTS: dict[str, str] = {
    "de": "Bist du noch da?",
    "en": "Are you still there?",
    "hi": "क्या आप वहाँ हैं?",
    "ar": "هل أنت هناك؟",
    "es": "¿Sigues ahí?",
    "fr": "Tu es encore là ?",
    "zh": "你还在吗？",
    "ja": "まだいる？",
    "ko": "아직 거기 있어?",
    "pt": "Ainda está aí?",
    "it": "Sei ancora lì?",
    "nl": "Ben je er nog?",
    "ru": "Ты ещё здесь?",
    "tr": "Hâlâ orada mısın?",
}

_GREETINGS: dict[str, str] = {
    "de": "Hallo! Ich bin Teddy! Wie geht's?",
    "en": "Hey! I'm Teddy! How are you?",
    "hi": "हेलो! मैं Teddy हूँ! कैसे हो?",
    "ar": "أهلاً! أنا Teddy! كيف حالك؟",
    "es": "¡Hola! Soy Teddy. ¿Cómo estás?",
    "fr": "Salut ! Je suis Teddy. Ça va ?",
    "zh": "嗨！我是Teddy！你好吗？",
    "ja": "やあ！Teddyだよ！元気？",
    "ko": "안녕! 나는 Teddy야! 어때?",
    "pt": "Oi! Sou Teddy. Como vai?",
    "it": "Ciao! Sono Teddy. Come stai?",
    "nl": "Hoi! Ik ben Teddy. Hoe gaat het?",
    "ru": "Привет! Я Teddy! Как дела?",
    "tr": "Selam! Ben Teddy! Nasılsın?",
}


# ── Silence watchdog ───────────────────────────────────────────────────────────

async def _silence_watchdog(session: AgentSession, language: str) -> None:
    """Re-prompt the user if they go silent for more than _SILENCE_TIMEOUT seconds
    after the agent finishes speaking."""
    idle_since: float | None = None
    has_spoken = False  # wait for agent to have spoken at least once

    def on_agent_state(ev) -> None:
        nonlocal idle_since, has_spoken
        if ev.new_state == "idle":
            if has_spoken:
                idle_since = asyncio.get_event_loop().time()
        else:
            idle_since = None
            if ev.new_state in ("speaking", "thinking"):
                has_spoken = True

    def on_user_transcribed(ev) -> None:
        nonlocal idle_since
        idle_since = None  # user spoke — cancel pending reprompt

    session.on("agent_state_changed", on_agent_state)
    session.on("user_input_transcribed", on_user_transcribed)
    try:
        while True:
            await asyncio.sleep(0.5)
            if idle_since is not None:
                elapsed = asyncio.get_event_loop().time() - idle_since
                if elapsed >= _SILENCE_TIMEOUT:
                    idle_since = None  # reset so we don't spam
                    reprompt = _REPROMPTS.get(language, _REPROMPTS["de"])
                    logger.debug("silence timeout (%.1fs) — re-prompting", elapsed)
                    await session.say(reprompt, allow_interruptions=True)
    finally:
        session.off("agent_state_changed", on_agent_state)
        session.off("user_input_transcribed", on_user_transcribed)


# ── Worker lifecycle ───────────────────────────────────────────────────────────

def prewarm(proc: JobProcess) -> None:
    """Preload the VAD model to eliminate cold-start latency on the first call."""
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect(auto_subscribe=AutoSubscribe.SUBSCRIBE_ALL)
    participant = await ctx.wait_for_participant()

    cfg = CallConfig.from_room_metadata(ctx.room.metadata, _SETTINGS)
    session_id = participant.metadata or ctx.room.name
    thread_id = str(uuid.uuid5(uuid.NAMESPACE_URL, session_id))

    logger.info(
        "Room=%s participant=%s mode=%s stt=%s tts=%s language=%s",
        ctx.room.name, participant.identity,
        cfg.voice_mode, cfg.stt_model, cfg.tts_label, cfg.language,
    )

    langgraph_config = {
        "configurable": {
            "thread_id": thread_id,
            "language": cfg.language,
            "native_language": cfg.native_language,
        },
        "metadata": {
            "session_id": session_id,
            "langfuse_session_id": session_id,
            "langfuse_user_id": participant.identity,
            "voice_mode": cfg.voice_mode,
            "language": cfg.language,
            "native_language": cfg.native_language,
            "thread_id": thread_id,
            "room": ctx.room.name,
            "participant": participant.identity,
        },
        "tags": cfg.langfuse_tags(_SETTINGS),
        "run_name": f"lingua-ai-{thread_id}",
    }

    session_logger = SessionLogger(
        session_id, language=cfg.language, native_language=cfg.native_language, room=ctx.room.name,
    )

    if cfg.is_realtime:
        session = _build_realtime_session(cfg)
        realtime_tracer = RealtimeLangfuseTracer(
            voice_mode=cfg.voice_mode,
            metadata=langgraph_config["metadata"],
        )
        realtime_tracer.attach(session)
        pipeline_tracer = None
    else:
        session, pipeline_tracer = _build_pipeline_session(
            ctx, cfg, langgraph_config, session_id, thread_id, participant, session_logger,
        )
        realtime_tracer = None

    await _publish_trace_info(ctx, session_id, pipeline_tracer)

    agent = VisionAssistant()
    agent._room = ctx.room
    await session.start(
        agent=agent,
        room=ctx.room,
        room_input_options=RoomInputOptions(video_enabled=True, audio_enabled=True, text_enabled=True),
    )

    supports_say = getattr(getattr(getattr(session, "llm", None), "capabilities", None), "supports_say", True)
    if supports_say:
        greeting = _GREETINGS.get(cfg.language, _GREETINGS["en"])
        await session.say(greeting, allow_interruptions=True)
        session_logger.log("assistant", greeting)

    watchdog = asyncio.create_task(_silence_watchdog(session, cfg.language))

    try:
        await asyncio.sleep(float("inf"))
    finally:
        watchdog.cancel()
        if realtime_tracer:
            realtime_tracer.end(status_message="worker shutdown")
        if pipeline_tracer:
            pipeline_tracer.flush()
        await agent.cleanup()


# ── Session builders ───────────────────────────────────────────────────────────

def _build_realtime_session(cfg: CallConfig) -> AgentSession:
    return AgentSession(
        llm=create_realtime_llm(
            cfg.voice_mode, _SETTINGS,
            language=cfg.language,
            native_language=cfg.native_language,
        ),
        turn_handling=_TURN_HANDLING,
        **_SESSION_KWARGS,
    )


def _build_pipeline_session(
    ctx: JobContext,
    cfg: CallConfig,
    langgraph_config: dict,
    session_id: str,
    thread_id: str,
    participant,
    session_logger: SessionLogger,
) -> tuple[AgentSession, VoiceSessionTracer]:
    stt_label = (
        f"deepgram/{cfg.stt_model}" if cfg.stt_provider == "deepgram"
        else f"faster-whisper/{cfg.stt_model}"
    )
    tracer = VoiceSessionTracer(
        session_id=session_id,
        room=ctx.room.name,
        participant=participant.identity,
        thread_id=thread_id,
        stt_model=stt_label,
        llm_model=_SETTINGS.llm_model,
        tts_model=cfg.tts_label,
    )

    graph = lingua_graph

    async def _publish_caption(translation: str, turn_id: str) -> None:
        """Forward a silent translation caption to the frontend (never spoken by TTS).

        turn_id lets the frontend give each reply's caption its own line instead of
        guessing which transcript bubble it belongs to.
        """
        try:
            payload = json.dumps({"type": "caption", "translation": translation, "turn_id": turn_id}).encode()
            await ctx.room.local_participant.publish_data(payload, reliable=True)
        except Exception as exc:
            logger.warning("Failed to publish caption: %s", exc)

    async def _log_turn(role: str, text: str) -> None:
        session_logger.log(role, text)

    async def _publish_vocab_progress(progress: dict) -> None:
        """Forward vocab-card drill progress (current word, completed words) to the
        frontend so it can show tick/cross state directly on the vocab cards."""
        try:
            payload = json.dumps({"type": "vocab_progress", **progress}).encode()
            await ctx.room.local_participant.publish_data(payload, reliable=True)
        except Exception as exc:
            logger.warning("Failed to publish vocab progress: %s", exc)

    inner_tts = create_tts(cfg, _SETTINGS)
    tts = TracedTTS(inner_tts, tracer, model_name=cfg.tts_label) if tracer._enabled else inner_tts

    # Build STT — Deepgram cloud (low latency) or local faster-whisper
    use_deepgram = cfg.stt_provider == "deepgram" and cfg.language not in DEEPGRAM_UNSUPPORTED_LANGUAGES
    if cfg.stt_provider == "deepgram" and not use_deepgram:
        logger.warning(
            "Deepgram model=%s rejects language=%s; falling back to local faster-whisper",
            cfg.stt_model, cfg.language,
        )
    if use_deepgram:
        logger.info("Deepgram STT — model=%s language=%s", cfg.stt_model, cfg.language)
        stt = deepgram_plugin.STT(model=cfg.stt_model, language=cfg.language, detect_language=False)
    else:
        fallback_model = FASTER_WHISPER_FALLBACK_MODEL.get(cfg.language, FASTER_WHISPER_FALLBACK_DEFAULT)
        stt = FasterWhisperSTT(
            model=cfg.stt_model if cfg.stt_provider != "deepgram" else fallback_model,
            language=cfg.language,
            device="cpu",
            compute_type="int8",
            tracer=tracer,
        )

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=stt,
        llm=LangGraphAdapter(
            graph,
            config=langgraph_config,
            langfuse_handler=tracer.get_langchain_handler(),
            on_caption=_publish_caption if cfg.language == "ar" else None,
            on_turn=_log_turn,
            # Generic — the graph only emits vocab_progress when the active learn
            # language actually has vocab-card data (see vocab_data.json), so this
            # is a harmless no-op for languages without it.
            on_progress=_publish_vocab_progress,
        ),
        tts=tts,
        turn_handling=_TURN_HANDLING,
        **_SESSION_KWARGS,
    )
    return session, tracer


async def _publish_trace_info(
    ctx: JobContext,
    session_id: str,
    pipeline_tracer: VoiceSessionTracer | None,
) -> None:
    """Send trace metadata to the room so the frontend can link feedback to this trace."""
    try:
        payload = json.dumps({
            "type": "trace_info",
            "session_id": session_id,
            "trace_id": getattr(pipeline_tracer, "_trace_id", None),
        }).encode()
        await ctx.room.local_participant.publish_data(payload, reliable=True)
    except Exception as exc:
        logger.warning("Failed to publish trace info: %s", exc)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
