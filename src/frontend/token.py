"""LiveKit room token generation for the voice agent frontend."""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from livekit import api
from livekit.protocol import room as proto_room


@dataclass(frozen=True)
class ConnectionDetails:
    server_url: str
    room_name: str
    participant_name: str
    participant_token: str

    def to_dict(self) -> dict[str, str]:
        return {
            "serverUrl": self.server_url,
            "roomName": self.room_name,
            "participantName": self.participant_name,
            "participantToken": self.participant_token,
        }


def _livekit_env() -> tuple[str, str, str]:
    url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    if not url or not api_key or not api_secret:
        raise RuntimeError(
            "Set LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET in .env"
        )
    return url, api_key, api_secret


def create_connection_details(
    *,
    agent_name: str | None = None,
    room_config: dict[str, Any] | None = None,
    voice_config: dict[str, Any] | None = None,
) -> ConnectionDetails:
    """Issue a participant JWT for a fresh voice-assistant room."""
    server_url, api_key, api_secret = _livekit_env()

    if room_config and room_config.get("agents"):
        agents = room_config["agents"]
        if agents and agents[0].get("agent_name"):
            agent_name = agents[0]["agent_name"]

    participant_name = "user"
    participant_identity = f"voice_assistant_user_{random.randint(0, 9_999):04d}"
    room_name = f"voice_assistant_room_{random.randint(0, 9_999):04d}"

    token = api.AccessToken(api_key, api_secret)
    token.with_identity(participant_identity)
    token.with_name(participant_name)
    token.with_ttl(timedelta(minutes=15))
    token.with_grants(
        api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        )
    )

    config = proto_room.RoomConfiguration()
    if agent_name:
        agent = config.agents.add()
        agent.agent_name = agent_name
    if voice_config:
        config.metadata = json.dumps(voice_config)
    token.with_room_config(config)

    return ConnectionDetails(
        server_url=server_url,
        room_name=room_name,
        participant_name=participant_name,
        participant_token=token.to_jwt(),
    )
