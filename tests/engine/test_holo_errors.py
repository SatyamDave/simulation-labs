"""LiveHoloClient surfaces auth/quota failures as clean, classifiable messages.

A raw provider exception (``AuthenticationError: Error code: 401 - {'error': …}``)
becomes a persona's ``failure_reason`` and is shown verbatim by the CLI, so the
client must translate the ones the user can act on into human text — without
leaking the provider payload.
"""

from __future__ import annotations

import pytest

from ghostpanel.engine.holo_client import (
    HoloClientError,
    LiveHoloClient,
    _classify_api_error,
)


class _ProviderError(Exception):
    """Stand-in for an openai SDK error carrying a numeric ``status_code``."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def _client_that_raises(exc: Exception, max_retries: int = 1) -> LiveHoloClient:
    client = LiveHoloClient(
        api_key="k", base_url="http://x", model="m", rpm=600.0, max_retries=max_retries
    )

    class _Completions:
        async def create(self, **_kwargs):
            raise exc

    class _Chat:
        completions = _Completions()

    class _Fake:
        chat = _Chat()

    client._client = _Fake()  # type: ignore[assignment]
    return client


# --- unit: the classifier --------------------------------------------------
def test_classify_401_is_clean_and_hides_payload():
    msg = _classify_api_error(
        _ProviderError("Error code: 401 - {'error': {'message': 'bad key'}}", 401)
    )
    assert msg is not None
    assert "401" in msg
    assert "key" in msg.lower()
    assert "{'error'" not in msg  # raw provider payload must not leak


def test_classify_429_mentions_rate_limit():
    msg = _classify_api_error(_ProviderError("slow down", 429))
    assert msg is not None
    assert "429" in msg and "rate limit" in msg.lower()


def test_classify_unknown_returns_none():
    assert _classify_api_error(_ProviderError("teapot", 418)) is None


# --- integration: _chat re-raises the clean message ------------------------
async def test_chat_wraps_auth_error():
    client = _client_that_raises(_ProviderError("Error code: 401 - {...}", 401))
    with pytest.raises(HoloClientError) as ei:
        await client._chat(b"\x89PNG\r\n", "prompt")
    text = str(ei.value)
    assert "401" in text and "{...}" not in text


async def test_chat_wraps_rate_limit_after_retries():
    client = _client_that_raises(_ProviderError("429 too many", 429), max_retries=1)
    with pytest.raises(HoloClientError) as ei:
        await client._chat(b"\x89PNG\r\n", "prompt")
    assert "429" in str(ei.value)


async def test_chat_passes_unknown_error_through_unwrapped():
    """An error we can't phrase better than its own text is re-raised as-is."""
    boom = _ProviderError("nonsense 418", 418)
    client = _client_that_raises(boom)
    with pytest.raises(_ProviderError):
        await client._chat(b"\x89PNG\r\n", "prompt")
