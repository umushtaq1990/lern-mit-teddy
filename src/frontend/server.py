"""FastAPI server: token API + static voice-call UI (Next.js web app equivalent)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()  # must run before importing .auth, which reads env vars at module load time

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from . import auth  # noqa: E402
from .token import ConnectionDetails, create_connection_details  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_PORT = int(os.getenv("FRONTEND_PORT", "8080"))

app = FastAPI(
    title="LangGraph Voice Frontend",
    description="Python frontend for the LangGraph voice call agent",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("AUTH_SESSION_SECRET", "dev-only-insecure-secret"),
    max_age=30 * 24 * 3600,  # 30 days — logged-in users stay logged in across visits
    same_site="lax",
    https_only=os.getenv("SESSION_COOKIE_SECURE", "true").lower() in ("1", "true", "yes"),
)
app.include_router(auth.router)


class RoomAgentConfig(BaseModel):
    agent_name: str | None = Field(default=None, alias="agent_name")


class RoomConfigBody(BaseModel):
    agents: list[RoomAgentConfig] | None = None


class VoiceConfig(BaseModel):
    voice_mode: str = "pipeline"
    language: str | None = None         # language to learn (BCP-47 code)
    native_language: str | None = None  # user's native language (BCP-47 code)
    stt_model: str | None = None
    tts_provider: str | None = None
    tts_voice: str | None = None
    tts_model: str | None = None


class ConnectionDetailsRequest(BaseModel):
    room_config: RoomConfigBody | None = None
    voice_config: VoiceConfig | None = None
    user_name: str | None = None


class FeedbackRequest(BaseModel):
    session_id: str
    rating: int = Field(..., ge=0, le=1, description="1 = thumbs up, 0 = thumbs down")
    comment: str | None = None


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/me")
def me(request: Request) -> dict[str, Any]:
    """Current logged-in user (if any), for the frontend to skip the name gate
    and show a logged-in state. Returns {"user": null} when not logged in."""
    user = auth.current_user(request)
    if not user:
        return {"user": None, "login_available": auth.is_configured()}
    return {
        "user": {"user_id": user.user_id, "display_name": user.display_name, "email": user.email},
        "login_available": True,
    }


@app.post("/api/connection-details")
def connection_details(request: Request, body: ConnectionDetailsRequest | None = None) -> dict[str, str]:
    """Same contract as the Next.js POST /api/connection-details route."""
    try:
        room_config: dict[str, Any] | None = None
        agent_name = os.getenv("LIVEKIT_AGENT_NAME") or None
        voice_cfg: dict[str, Any] | None = None

        if body:
            if body.room_config:
                room_config = body.room_config.model_dump(by_alias=True)
                if body.room_config.agents and body.room_config.agents[0].agent_name:
                    agent_name = body.room_config.agents[0].agent_name
            if body.voice_config:
                voice_cfg = {k: v for k, v in body.voice_config.model_dump().items() if v is not None}

        logged_in = auth.current_user(request)

        details: ConnectionDetails = create_connection_details(
            agent_name=agent_name,
            room_config=room_config,
            voice_config=voice_cfg,
            user_name=body.user_name if body else None,
            auth_user_id=logged_in.user_id if logged_in else None,
            auth_display_name=logged_in.display_name if logged_in else None,
        )
        return details.to_dict()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/feedback")
def submit_feedback(body: FeedbackRequest) -> dict[str, str]:
    """Record user feedback (thumbs up/down) to Langfuse.

    Strategy: look up the voice session trace by session_id, then score it.
    If not found, create a lightweight feedback trace so the score has a valid trace_id.
    """
    pk = os.getenv("LANGFUSE_PUBLIC_KEY")
    sk = os.getenv("LANGFUSE_SECRET_KEY")
    if not pk or not sk:
        return {"status": "skipped", "reason": "Langfuse not configured"}
    try:
        import urllib.request
        import urllib.parse
        import base64
        from langfuse import Langfuse

        host = os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL") or "https://cloud.langfuse.com"
        lf = Langfuse(public_key=pk, secret_key=sk, host=host)

        # Find the existing voice session trace for this room so the score
        # appears directly on the session trace in Langfuse.
        trace_id: str | None = None
        try:
            creds = base64.b64encode(f"{pk}:{sk}".encode()).decode()
            params = urllib.parse.urlencode({"sessionId": body.session_id, "limit": 1})
            req = urllib.request.Request(
                f"{host}/api/public/traces?{params}",
                headers={"Authorization": f"Basic {creds}"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                import json as _json
                data = _json.loads(resp.read())
                traces = data.get("data") or data.get("traces") or []
                if traces:
                    trace_id = traces[0]["id"]
        except Exception:
            pass  # fall through to creating a new trace

        if not trace_id:
            # No existing trace — create a minimal feedback trace linked to the session
            trace_id = lf.create_trace_id()
            span = lf.start_observation(
                trace_context={"trace_id": trace_id},
                name="user-feedback",
                as_type="span",
                input={"session_id": body.session_id},
                metadata={"session_id": body.session_id},
            )
            span.end()

        lf.create_score(
            trace_id=trace_id,
            name="user-feedback",
            value=float(body.rating),
            data_type="BOOLEAN",
            comment=body.comment or "",
            metadata={"rating_label": "thumbs_up" if body.rating == 1 else "thumbs_down"},
        )
        lf.flush()
        return {"status": "ok", "trace_id": trace_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


_NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", headers=_NO_CACHE)


@app.get("/static/{filename:path}")
def static_file(filename: str) -> FileResponse:
    path = STATIC_DIR / filename
    if not path.exists() or not path.is_file():
        from fastapi import HTTPException
        raise HTTPException(status_code=404)
    return FileResponse(path, headers=_NO_CACHE)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def main() -> None:
    import uvicorn

    uvicorn.run(
        "src.frontend.server:app",
        host=os.getenv("FRONTEND_HOST", "127.0.0.1"),
        port=DEFAULT_PORT,
        reload=os.getenv("FRONTEND_RELOAD", "true").lower() in ("1", "true", "yes"),
        # Azure Container Apps terminates TLS at its ingress and forwards to this
        # container over plain HTTP — without trusting X-Forwarded-Proto, uvicorn
        # (and anything building absolute URLs, like the OAuth redirect_uri) sees
        # every request as http://, not https://.
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
