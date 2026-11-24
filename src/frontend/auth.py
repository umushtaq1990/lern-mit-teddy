"""Optional login via Microsoft Entra External ID (CIAM), alongside the
existing free-typed name gate. A logged-in user gets a durable identity
(the token's `oid` claim) across devices; the free-typed name path is
untouched for anyone who skips login.

Uses plain authorization-code + PKCE — no MSAL dependency, since the flow
is simple enough (one app, one user flow, no downstream API scopes beyond
the user's own profile) to do directly with httpx + PyJWT.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from jwt import PyJWKClient

from src.db.repository import upsert_user
from src.db.session import get_session_factory
from src.settings import get_settings

_jwk_client: PyJWKClient | None = None
_jwk_client_jwks_uri: str | None = None


def is_configured() -> bool:
    s = get_settings()
    return bool(s.auth_tenant_id and s.auth_domain and s.auth_client_id and s.auth_client_secret)


def _authority() -> str:
    s = get_settings()
    return f"https://{s.auth_domain}.ciamlogin.com/{s.auth_tenant_id}"


def _authorization_endpoint() -> str:
    return f"{_authority()}/oauth2/v2.0/authorize"


def _token_endpoint() -> str:
    return f"{_authority()}/oauth2/v2.0/token"


def _jwks_uri() -> str:
    return f"{_authority()}/discovery/v2.0/keys"


def _issuer() -> str:
    s = get_settings()
    return f"https://{s.auth_tenant_id}.ciamlogin.com/{s.auth_tenant_id}/v2.0"


def _get_jwk_client() -> PyJWKClient:
    """Cached PyJWKClient, rebuilt if the configured JWKS URI ever changes
    (e.g. between test runs with different settings)."""
    global _jwk_client, _jwk_client_jwks_uri
    uri = _jwks_uri()
    if _jwk_client is None or _jwk_client_jwks_uri != uri:
        _jwk_client = PyJWKClient(uri)
        _jwk_client_jwks_uri = uri
    return _jwk_client


@dataclass(frozen=True)
class AuthUser:
    user_id: str  # stable identity (token's oid/sub claim)
    display_name: str
    email: str | None


def _redirect_uri(request: Request) -> str:
    return str(request.url_for("auth_callback"))


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login(request: Request) -> RedirectResponse:
    if not is_configured():
        raise HTTPException(status_code=503, detail="Login is not configured")

    state = secrets.token_urlsafe(24)
    code_verifier = _b64url(secrets.token_bytes(32))
    code_challenge = _b64url(hashlib.sha256(code_verifier.encode()).digest())

    request.session["auth_state"] = state
    request.session["auth_code_verifier"] = code_verifier

    params = {
        "client_id": get_settings().auth_client_id,
        "response_type": "code",
        "redirect_uri": _redirect_uri(request),
        "response_mode": "query",
        "scope": "openid profile email offline_access",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    url = f"{_authorization_endpoint()}?{httpx.QueryParams(params)}"
    return RedirectResponse(url)


@router.get("/callback", name="auth_callback")
async def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None) -> RedirectResponse:
    if error:
        return RedirectResponse(f"/?auth_error={error}")

    expected_state = request.session.pop("auth_state", None)
    code_verifier = request.session.pop("auth_code_verifier", None)
    if not code or not state or not expected_state or state != expected_state:
        raise HTTPException(status_code=400, detail="Invalid or missing auth state")

    settings = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _token_endpoint(),
            data={
                "client_id": settings.auth_client_id,
                "client_secret": settings.auth_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _redirect_uri(request),
                "code_verifier": code_verifier,
            },
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Token exchange failed: {resp.text}")

    id_token = resp.json().get("id_token")
    if not id_token:
        raise HTTPException(status_code=502, detail="No id_token in token response")

    signing_key = _get_jwk_client().get_signing_key_from_jwt(id_token)
    claims = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256"],
        audience=settings.auth_client_id,
        issuer=_issuer(),
    )

    user_id = claims.get("oid") or claims.get("sub")
    display_name = claims.get("name") or (claims.get("emails") or [None])[0] or user_id
    email = (claims.get("emails") or [None])[0]

    request.session["user"] = {"user_id": user_id, "display_name": display_name, "email": email}

    db = get_session_factory()()
    try:
        upsert_user(db, user_id=user_id, display_name=display_name, email=email)
    finally:
        db.close()

    return RedirectResponse("/")


@router.post("/logout")
def logout(request: Request) -> dict[str, str]:
    request.session.pop("user", None)
    return {"status": "ok"}


def current_user(request: Request) -> AuthUser | None:
    data = request.session.get("user")
    if not data:
        return None
    return AuthUser(user_id=data["user_id"], display_name=data["display_name"], email=data.get("email"))
