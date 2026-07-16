"""Tests for the pluggable model-backend registry (INF-A)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ghostpanel.engine.models import (
    EchoModelClient,
    available,
    build_model,
    default_backend,
)
from ghostpanel_contracts import Action, ActionType, HoloClient


@dataclass
class _SettingsStub:
    """Minimal stand-in for server.config.Settings (only the Holo knobs)."""

    hai_api_key: str = "test-key"
    holo_base_url: str = "https://api.hcompany.ai/v1/"
    hai_model: str = "holo3-1-35b-a3b"
    hai_rpm: float = 5.0


def test_available_lists_both_backends():
    names = available()
    assert "holo" in names
    assert "echo" in names


def test_build_holo_is_holoclient():
    client = build_model("holo", _SettingsStub())
    assert isinstance(client, HoloClient)


def test_build_echo_is_holoclient():
    client = build_model("echo", _SettingsStub())
    assert isinstance(client, EchoModelClient)
    assert isinstance(client, HoloClient)


def test_build_unknown_raises_valueerror():
    with pytest.raises(ValueError) as exc:
        build_model("gpt-9000", _SettingsStub())
    # error message lists the available backends
    assert "echo" in str(exc.value)
    assert "holo" in str(exc.value)


def test_name_is_case_insensitive():
    assert isinstance(build_model("ECHO", _SettingsStub()), HoloClient)


def test_default_backend_reads_env(monkeypatch):
    monkeypatch.delenv("MODEL_BACKEND", raising=False)
    assert default_backend() == "holo"
    monkeypatch.setenv("MODEL_BACKEND", "echo")
    assert default_backend() == "echo"


@pytest.mark.asyncio
async def test_echo_navigate_returns_valid_action():
    client = build_model("echo", _SettingsStub())
    action = await client.navigate(b"", "sign up", [])
    assert isinstance(action, Action)
    assert action.type == ActionType.CLICK
    assert action.x is not None and action.y is not None


@pytest.mark.asyncio
async def test_echo_localize_returns_coords():
    client = EchoModelClient(x=42, y=99)
    coords = await client.localize(b"", "the button")
    assert coords == (42, 99)
