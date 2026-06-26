"""Native Python voice client — joins LiveKit with your microphone (no browser)."""

from __future__ import annotations

import asyncio
import logging
import os
from dotenv import load_dotenv
from livekit import rtc

from .token import create_connection_details

logger = logging.getLogger("voice-frontend-native")


async def run_voice_session() -> None:
    load_dotenv()
    details = create_connection_details()
    room = rtc.Room()

    @room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            audio_stream = rtc.AudioStream(track)
            asyncio.create_task(_play_agent_audio(audio_stream))

    logger.info("Connecting to %s room=%s", details.server_url, details.room_name)
    await room.connect(details.server_url, details.participant_token)

    devices = rtc.MediaDevices()
    mic = devices.open_input(enable_aec=True)
    track = rtc.LocalAudioTrack.create_audio_track("mic", mic.source)
    options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    await room.local_participant.publish_track(track, options)
    logger.info("Microphone published — speak to the agent (Ctrl+C to quit)")

    try:
        while room.isconnected():
            await asyncio.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Stopping…")
    finally:
        await mic.aclose()
        await room.disconnect()


async def _play_agent_audio(stream: rtc.AudioStream) -> None:
    """Play agent audio through the default output device when supported."""
    try:
        devices = rtc.MediaDevices()
        speaker = devices.open_output()
        async for event in stream:
            speaker.write(event.frame)
    except Exception as exc:
        logger.warning("Agent audio playback unavailable: %s", exc)
    finally:
        await stream.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        asyncio.run(run_voice_session())
    except KeyboardInterrupt:
        logger.info("Stopped.")


if __name__ == "__main__":
    main()
