import pytest


@pytest.fixture(autouse=True)
def no_outbound_ai(monkeypatch):
    """Tests never call third-party AI APIs. Keyless fallbacks (Pollinations)
    stay off during tests; the keyless-provider unit test re-enables it with a
    faked network layer."""
    from backend.core.config_new import settings

    monkeypatch.setattr(settings, "POLLINATIONS_ENABLED", False)
