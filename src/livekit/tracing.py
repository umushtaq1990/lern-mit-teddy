"""Langfuse tracing for the voice agent pipeline (Langfuse SDK v4 compatible).

Two tracer classes cover the two runtime modes:
  VoiceSessionTracer    — pipeline mode (STT → LangGraph → TTS child spans)
  RealtimeLangfuseTracer— realtime mode (OpenAI / Gemini / Ultravox session trace)

Both classes gracefully no-op when LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY
are absent, so the agent works in environments without observability configured.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("voice-tracer")


# ── Span wrappers ──────────────────────────────────────────────────────────────

class _NoopSpan:
    """Returned when Langfuse is disabled — every call is a silent no-op."""

    def end(self, **_: Any) -> None:
        pass

    def update(self, **_: Any) -> None:
        pass


class _Span:
    """Wraps a Langfuse v4 observation to support end(output=…, level=…) kwargs.

    Langfuse v4 moved those kwargs from end() into update(); this adapter bridges
    callers that use the old API without requiring changes at each call site.
    """

    def __init__(self, span: Any) -> None:
        self._span = span

    def end(self, *, output: Any = None, level: Any = None, status_message: Any = None, **_: Any) -> None:
        kw: dict[str, Any] = {}
        if output is not None:
            kw["output"] = output
        if level is not None:
            kw["level"] = level
        if status_message is not None:
            kw["status_message"] = status_message
        if kw:
            try:
                self._span.update(**kw)
            except Exception:
                pass
        try:
            self._span.end()
        except Exception:
            pass

    def update(self, **kwargs: Any) -> None:
        try:
            self._span.update(**kwargs)
        except Exception:
            pass


# ── Private helpers for realtime transcript parsing ────────────────────────────

def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_as_text(item) for item in value).strip()
    if hasattr(value, "text"):
        return str(value.text)
    return str(value)


def _role_name(role: Any) -> str | None:
    if role is None:
        return None
    if hasattr(role, "value"):
        return str(role.value)
    return str(role).lower().replace("chatrole.", "")


# ── Pipeline mode tracer ───────────────────────────────────────────────────────

class VoiceSessionTracer:
    """One Langfuse trace covering a complete pipeline voice session.

    Usage:
        tracer = VoiceSessionTracer(session_id=…, room=…, …)
        # Inside FasterWhisperSTT:
        span = tracer.stt_span(audio_duration_s=1.2, model="faster-whisper/base")
        span.end(output={"text": "hello"})
        # Inside TracedTTS:
        span = tracer.tts_span(text="Hello!", model="kokoro:af_sky")
        span.end()
        # At session end:
        tracer.flush()
    """

    def __init__(
        self,
        *,
        session_id: str,
        room: str,
        participant: str,
        thread_id: str | None,
        stt_model: str = "faster-whisper/base",
        llm_model: str = "gpt-4.1-nano",
        tts_model: str = "hume",
    ) -> None:
        self._enabled = False
        self._lf: Any = None
        self._trace_id: str | None = None
        self._root_span: Any = None

        pk = os.getenv("LANGFUSE_PUBLIC_KEY")
        sk = os.getenv("LANGFUSE_SECRET_KEY")
        if not (pk and sk):
            logger.info("Langfuse keys not set — pipeline tracing disabled")
            return

        try:
            from langfuse import Langfuse  # noqa: PLC0415

            host = (
                os.getenv("LANGFUSE_HOST")
                or os.getenv("LANGFUSE_BASE_URL")
                or "https://cloud.langfuse.com"
            )
            self._lf = Langfuse(public_key=pk, secret_key=sk, host=host)
            self._trace_id = self._lf.create_trace_id()
            self._root_span = self._lf.start_observation(
                trace_context={"trace_id": self._trace_id},
                name="voice-session",
                as_type="span",
                input={
                    "session_id": session_id,
                    "room": room,
                    "participant": participant,
                    "thread_id": thread_id or "none",
                },
                metadata={
                    "stt_model": stt_model,
                    "llm_model": llm_model,
                    "tts_model": tts_model,
                },
            )
            self._enabled = True
            logger.info(
                "Langfuse pipeline tracing enabled — session=%s url=%s",
                session_id,
                self._lf.get_trace_url(trace_id=self._trace_id),
            )
        except Exception as exc:
            logger.warning("Langfuse init failed — tracing disabled: %s", exc)

    def get_langchain_handler(self) -> Any:
        """Return a LangChain callback that links every LLM call to this trace."""
        if not self._enabled or not self._trace_id:
            return None
        try:
            from langfuse.langchain import CallbackHandler  # noqa: PLC0415

            return CallbackHandler(trace_context={"trace_id": self._trace_id})
        except Exception as exc:
            logger.warning("get_langchain_handler failed: %s", exc)
            return None

    def stt_span(
        self,
        *,
        audio_duration_s: float,
        model: str = "faster-whisper/base",
        language: str = "en",
    ) -> _NoopSpan | _Span:
        if not self._enabled or not self._trace_id:
            return _NoopSpan()
        try:
            raw = self._lf.start_observation(
                trace_context={"trace_id": self._trace_id},
                name="stt",
                as_type="span",
                input={"audio_duration_seconds": round(audio_duration_s, 3)},
                metadata={"model": model, "language": language},
            )
            return _Span(raw)
        except Exception:
            return _NoopSpan()

    def tts_span(self, *, text: str, model: str = "hume") -> _NoopSpan | _Span:
        if not self._enabled or not self._trace_id:
            return _NoopSpan()
        try:
            raw = self._lf.start_observation(
                trace_context={"trace_id": self._trace_id},
                name="tts",
                as_type="span",
                input={"text": text, "char_count": len(text)},
                metadata={"model": model},
            )
            return _Span(raw)
        except Exception:
            return _NoopSpan()

    def turn_event(self, *, role: str, text: str) -> None:
        """Record one ground-truth conversation turn (from the real STT/TTS pipeline,
        not reconstructed from LangGraph's internal message state — those can include
        injected non-speech messages and don't reliably map to who actually said what).
        """
        if not self._enabled or not self._root_span or not text:
            return
        try:
            self._root_span.create_event(name="turn", metadata={"role": role, "text": text})
        except Exception:
            logger.debug("Unable to record Langfuse turn event", exc_info=True)

    def flush(self) -> None:
        if not self._enabled or not self._lf:
            return
        try:
            if self._root_span:
                self._root_span.end()
            self._lf.flush()
            logger.info("Langfuse pipeline trace flushed")
        except Exception as exc:
            logger.warning("Langfuse flush error: %s", exc)


# ── Realtime mode tracer ───────────────────────────────────────────────────────

class RealtimeLangfuseTracer:
    """Langfuse trace for a realtime (OpenAI / Gemini / Ultravox) voice session.

    Attach to an AgentSession via attach(session) immediately after creation.
    The tracer incrementally builds a full-session transcript from AgentSession
    events and writes it to Langfuse on session close.

    Usage:
        tracer = RealtimeLangfuseTracer(voice_mode="openai_realtime", metadata={…})
        tracer.attach(session)
        # … session runs …
        tracer.end()  # also called automatically via the "close" event
    """

    def __init__(self, *, voice_mode: str, metadata: dict[str, Any]) -> None:
        self.enabled = False
        self.client: Any = None
        self.span: Any = None
        self.transcript: list[dict[str, Any]] = []
        self.usage: Any = None
        self.ended = False
        self._voice_mode = voice_mode
        self._metadata = metadata

        pk = os.getenv("LANGFUSE_PUBLIC_KEY")
        sk = os.getenv("LANGFUSE_SECRET_KEY")
        if not (pk and sk):
            logger.info("Langfuse keys not set — realtime tracing disabled")
            return

        host = os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST")
        try:
            from langfuse import Langfuse  # noqa: PLC0415

            self.client = Langfuse(public_key=pk, secret_key=sk, base_url=host)
            trace_id = self.client.create_trace_id()
            self.span = self.client.start_observation(
                trace_context={"trace_id": trace_id},
                name=f"realtime_voice_session:{voice_mode}",
                as_type="agent",
                input={"session": self._session_snapshot(), "user_transcript": []},
                output={"agent_transcript": [], "full_transcript": [], "usage": None},
                metadata=metadata,
            )
            self.enabled = True
            logger.info(
                "Langfuse realtime trace started — %s",
                self.client.get_trace_url(trace_id=trace_id),
            )
        except Exception as exc:
            logger.warning("Unable to start Langfuse realtime trace: %s", exc)

    def attach(self, session: Any) -> None:
        if not self.enabled:
            return
        session.on("user_input_transcribed", self._on_user_input_transcribed)
        session.on("conversation_item_added", self._on_conversation_item_added)
        session.on("speech_created", self._on_speech_created)
        session.on("session_usage_updated", self._on_session_usage_updated)
        session.on("error", self._on_error)
        session.on("close", self._on_close)

    def end(self, *, level: str = "DEFAULT", status_message: str | None = None) -> None:
        if not self.enabled or self.ended:
            return
        self.ended = True
        try:
            if self.span:
                inp, out = self._trace_io()
                self.span.update(
                    input=inp,
                    output=out,
                    metadata={**self._metadata, "turn_count": len(self.transcript)},
                    level=level,
                    status_message=status_message,
                )
                self.span.end()
            if self.client:
                self.client.flush()
            logger.info("Langfuse realtime trace ended")
        except Exception as exc:
            logger.warning("Unable to end Langfuse realtime trace: %s", exc)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _session_snapshot(self) -> dict[str, Any]:
        return {
            "session_id": self._metadata.get("session_id"),
            "room": self._metadata.get("room"),
            "participant": self._metadata.get("participant"),
            "voice_mode": self._voice_mode,
        }

    def _trace_io(self) -> tuple[dict[str, Any], dict[str, Any]]:
        user_turns = [t for t in self.transcript if t["role"] == "user"]
        agent_turns = [t for t in self.transcript if t["role"] != "user"]
        return (
            {"session": self._session_snapshot(), "user_transcript": user_turns},
            {"agent_transcript": agent_turns, "full_transcript": self.transcript, "usage": self.usage},
        )

    def _sync(self) -> None:
        if not self.enabled or not self.span:
            return
        try:
            inp, out = self._trace_io()
            self.span.update(
                input=inp,
                output=out,
                metadata={**self._metadata, "turn_count": len(self.transcript)},
            )
            if self.client:
                self.client.flush()
        except Exception as exc:
            logger.debug("Unable to sync Langfuse trace: %s", exc)

    def _append_turn(self, role: str, content: str, source: str) -> None:
        content = content.strip()
        if not content:
            return
        if self.transcript and self.transcript[-1]["role"] == role and self.transcript[-1]["content"] == content:
            return
        self.transcript.append({"role": role, "content": content, "source": source})
        self._sync()

    def _emit_event(self, name: str, **kwargs: Any) -> None:
        if not self.enabled or not self.span:
            return
        try:
            self.span.create_event(name=name, metadata=kwargs)
        except Exception as exc:
            logger.debug("Unable to record Langfuse event %s: %s", name, exc)

    def _on_user_input_transcribed(self, event: Any) -> None:
        transcript = getattr(event, "transcript", "")
        is_final = bool(getattr(event, "is_final", False))
        self._emit_event(
            "user_input_transcribed",
            transcript=transcript,
            is_final=is_final,
            speaker_id=getattr(event, "speaker_id", None),
            language=str(getattr(event, "language", "")) or None,
        )
        if is_final and transcript:
            self._append_turn("user", transcript, "user_input_transcribed")

    def _on_conversation_item_added(self, event: Any) -> None:
        item = getattr(event, "item", None)
        role = _role_name(getattr(item, "role", None))
        content = _as_text(getattr(item, "content", ""))
        self._emit_event(
            "conversation_item_added",
            role=role,
            content=content,
            interrupted=bool(getattr(item, "interrupted", False)),
        )
        if role and content:
            self._append_turn(role, content, "conversation_item_added")

    def _on_speech_created(self, event: Any) -> None:
        self._emit_event(
            "speech_created",
            user_initiated=bool(getattr(event, "user_initiated", False)),
            source=getattr(event, "source", None),
        )

    def _on_session_usage_updated(self, event: Any) -> None:
        usage = getattr(event, "usage", None)
        self.usage = (
            usage.model_dump() if hasattr(usage, "model_dump") else (str(usage) if usage is not None else None)
        )
        self._emit_event("session_usage_updated", usage=self.usage)
        self._sync()

    def _on_error(self, event: Any) -> None:
        error = getattr(event, "error", None)
        source = getattr(event, "source", None)
        self._emit_event(
            "error",
            error=str(error),
            source=source.__class__.__name__ if source is not None else None,
        )
        self.end(level="ERROR", status_message=str(error))

    def _on_close(self, event: Any) -> None:
        error = getattr(event, "error", None)
        reason = getattr(event, "reason", None)
        self._emit_event("close", reason=str(reason), error=str(error) if error else None)
        self.end(
            level="ERROR" if error else "DEFAULT",
            status_message=str(error) if error else str(reason),
        )
