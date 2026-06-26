"""VisionAssistant: LiveKit Agent with live video frame capture.

Attaches to camera and screen-share tracks, captures the latest frame, and
injects it into the LLM context at the start of each user turn.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from livekit import rtc
from livekit.agents import Agent, get_job_context
from livekit.agents.llm import ChatContext, ChatMessage, ImageContent

from .config import build_lingua_prompt

logger = logging.getLogger(__name__)


class VisionAssistant(Agent):
    """Agent that injects the latest video frame into every user turn."""

    def __init__(self) -> None:
        self._latest_frame: rtc.VideoFrame | None = None
        self._video_stream: rtc.VideoStream | None = None
        self._tasks: list[asyncio.Task] = []
        self._screen_share_active = False
        self._has_video_input = False
        self._room: rtc.Room | None = None
        super().__init__(instructions=build_lingua_prompt("English", "English"))

    async def on_enter(self) -> None:
        try:
            self._room = get_job_context().room

            @self._room.on("track_subscribed")
            def _on_track(track, publication, _participant):
                try:
                    if getattr(track, "kind", None) == rtc.TrackKind.KIND_VIDEO:
                        self._attach_video(track, getattr(publication, "source", None))
                except Exception as exc:
                    logger.warning("track_subscribed handler error: %s", exc)

        except Exception as exc:
            logger.debug("Unable to bind room track_subscribed handler: %s", exc)

        # Scan for tracks that were published before we joined
        asyncio.create_task(self._scan_existing_tracks())

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        if self._latest_frame:
            try:
                new_message.content.append(ImageContent(image=self._latest_frame))
                logger.info("Injected video frame into user turn")
            except Exception as exc:
                logger.warning("Failed to attach video frame: %s", exc)
            finally:
                self._latest_frame = None
        elif self._has_video_input:
            source = "screen sharing" if self._screen_share_active else "camera"
            new_message.content.append(f"I see {source} input is available.")

    async def cleanup(self) -> None:
        if self._video_stream is not None:
            await self._video_stream.aclose()
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._tasks.clear()

    # ── Private ────────────────────────────────────────────────────────────────

    def _attach_video(self, track: rtc.Track, source: Any) -> None:
        if self._video_stream is not None:
            asyncio.create_task(self._video_stream.aclose())

        self._video_stream = rtc.VideoStream(track)
        self._has_video_input = True

        _screen_sources = {1, "SOURCE_SCREENSHARE", getattr(rtc.TrackSource, "SCREEN_SHARE", None)}
        if source in _screen_sources:
            self._screen_share_active = True
            logger.info("Screen share track attached (sid=%s)", getattr(track, "sid", None))
        else:
            logger.info("Camera track attached (sid=%s)", getattr(track, "sid", None))

        async def _read_frames() -> None:
            try:
                async for event in self._video_stream:
                    self._latest_frame = event.frame
            except Exception as exc:
                logger.error("Video stream read error: %s", exc)
            finally:
                if self._video_stream:
                    await self._video_stream.aclose()

        task = asyncio.create_task(_read_frames())
        task.add_done_callback(self._tasks.remove)
        self._tasks.append(task)

    async def _scan_existing_tracks(self) -> None:
        await asyncio.sleep(0.5)
        room = self._room
        if room is None:
            return
        try:
            for participant in getattr(room, "remote_participants", {}).values():
                for pub in getattr(participant, "track_publications", {}).values():
                    track = getattr(pub, "track", None)
                    if track and getattr(track, "kind", None) == rtc.TrackKind.KIND_VIDEO:
                        logger.info("Found existing video track (sid=%s)", getattr(track, "sid", None))
                        self._attach_video(track, getattr(pub, "source", None))
                        return
        except Exception as exc:
            logger.debug("Error scanning existing video tracks: %s", exc)


