import pytest

from app.core.config import (
    INSECURE_SECRET_PLACEHOLDER,
    settings,
    validate_security_configuration,
)


def test_security_configuration_accepts_valid_secret_and_duration(monkeypatch):
    monkeypatch.setattr(
        settings, "auth_secret_key", "valid-test-secret-with-at-least-32-characters"
    )
    monkeypatch.setattr(settings, "auth_token_minutes", 30)
    validate_security_configuration()


@pytest.mark.parametrize(
    "secret",
    ["", "short", INSECURE_SECRET_PLACEHOLDER, None],
)
def test_security_configuration_rejects_missing_weak_or_placeholder_secret(
    monkeypatch, secret
):
    monkeypatch.setattr(settings, "auth_secret_key", secret)
    with pytest.raises(RuntimeError, match="FOODLOOP_AUTH_SECRET_KEY"):
        validate_security_configuration()


@pytest.mark.parametrize("duration", [0, -1, True, "30"])
def test_security_configuration_rejects_invalid_token_duration(monkeypatch, duration):
    monkeypatch.setattr(
        settings, "auth_secret_key", "valid-test-secret-with-at-least-32-characters"
    )
    monkeypatch.setattr(settings, "auth_token_minutes", duration)
    with pytest.raises(RuntimeError, match="FOODLOOP_AUTH_TOKEN_MINUTES"):
        validate_security_configuration()
