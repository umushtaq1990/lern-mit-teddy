"""LiveKit room token generation for the voice agent frontend."""

from __future__ import annotations

import json
import os
import random
import re
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


def _sanitize_user_id(user_name: str) -> str:
    """Turn a free-typed name into a stable identity: lowercase, alphanumeric/underscore only."""
    slug = re.sub(r"[^a-z0-9_]+", "_", user_name.strip().lower()).strip("_")
    return slug[:40]


def create_connection_details(
    *,
    agent_name: str | None = None,
    room_config: dict[str, Any] | None = None,
    voice_config: dict[str, Any] | None = None,
    user_name: str | None = None,
    auth_user_id: str | None = None,
    auth_display_name: str | None = None,
) -> ConnectionDetails:
    """Issue a participant JWT for a fresh voice-assistant room.

    `auth_user_id` (from a logged-in Entra External ID session) takes
    priority as the stable identity when present — it's already durable and
    unique, unlike a free-typed name that could collide or change. Falls back
    to the free-typed `user_name` gate, then to a random anonymous identity.
    """
    server_url, api_key, api_secret = _livekit_env()

    if room_config and room_config.get("agents"):
        agents = room_config["agents"]
        if agents and agents[0].get("agent_name"):
            agent_name = agents[0]["agent_name"]

    if auth_user_id:
        participant_identity = _sanitize_user_id(auth_user_id)
        participant_name = (auth_display_name or auth_user_id).strip()[:200]
    else:
        user_slug = _sanitize_user_id(user_name) if user_name else ""
        if user_slug:
            participant_name = user_name.strip()[:200]
            participant_identity = user_slug
        else:
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
