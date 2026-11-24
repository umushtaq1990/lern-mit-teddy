"""src.frontend.auth tests — importable with zero env vars set (Phase 0 fix:
AUTH_* used to be read as module-level globals at import time), with the
CIAM token endpoint mocked so nothing touches the network."""

from __future__ import annotations

from src.frontend import auth


def test_is_configured_false_when_unset(test_settings):
    test_settings(
        AUTH_TENANT_ID="", AUTH_DOMAIN="", AUTH_CLIENT_ID="", AUTH_CLIENT_SECRET=""
    )
    assert auth.is_configured() is False


def test_is_configured_true_when_all_set(test_settings):
    test_settings(
        AUTH_TENANT_ID="tenant-123",
        AUTH_DOMAIN="my-ciam",
        AUTH_CLIENT_ID="client-abc",
        AUTH_CLIENT_SECRET="secret-xyz",
    )
    assert auth.is_configured() is True


def test_authority_urls_derive_from_settings(test_settings):
    test_settings(
        AUTH_TENANT_ID="tenant-123",
        AUTH_DOMAIN="my-ciam",
        AUTH_CLIENT_ID="client-abc",
        AUTH_CLIENT_SECRET="secret-xyz",
    )
    assert auth._authority() == "https://my-ciam.ciamlogin.com/tenant-123"
    assert auth._authorization_endpoint().endswith("/oauth2/v2.0/authorize")
    assert auth._token_endpoint().endswith("/oauth2/v2.0/token")
    assert auth._issuer() == "https://tenant-123.ciamlogin.com/tenant-123/v2.0"


def test_current_user_none_without_session_data():
    class _FakeRequest:
        session: dict = {}

    assert auth.current_user(_FakeRequest()) is None


def test_current_user_reads_session():
    class _FakeRequest:
        session = {"user": {"user_id": "abc", "display_name": "Sam", "email": "sam@example.com"}}

    user = auth.current_user(_FakeRequest())
    assert user is not None
    assert user.user_id == "abc"
    assert user.display_name == "Sam"
    assert user.email == "sam@example.com"
