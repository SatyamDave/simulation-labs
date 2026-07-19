"""Tests for `sim try` onboarding helpers (P2 auto-Chromium, P3 interactive key).

These lock in the low-friction first-run behavior without ever hitting the network
or a real browser: the interactive prompt only fires on a TTY (never in CI), and a
present key short-circuits both the prompt and any install.
"""

from __future__ import annotations

import pytest

from ghostpanel.cli import main as cli_main


@pytest.fixture(autouse=True)
def _clear_keys(monkeypatch):
    """No ambient key/backend should leak in from the dev machine or .env."""
    for var in ("GEMINI_API_KEY", "HAI_API_KEY", "MODEL_BACKEND", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_resolve_backend_uses_present_key_without_prompting(monkeypatch):
    """A configured key resolves straight to a backend — never prompts."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    # If this tried to prompt, getpass would raise in a non-tty; it must not.
    assert cli_main._resolve_try_backend() == "gemini"


def test_resolve_backend_non_tty_no_key_returns_none(monkeypatch, capsys):
    """In CI / piped input (no tty) with no key: print guidance, return None — never hang."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    assert cli_main._resolve_try_backend() is None
    assert "No model API key found" in capsys.readouterr().out


def test_resolve_backend_tty_paste_sets_key(monkeypatch):
    """On a tty, a pasted key is accepted and resolves to the gemini backend (P3)."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr("getpass.getpass", lambda *a, **k: "pasted-key ")
    assert cli_main._resolve_try_backend() == "gemini"
    import os

    assert os.environ["GEMINI_API_KEY"] == "pasted-key"


def test_resolve_backend_tty_empty_paste_cancels(monkeypatch):
    """Empty paste cancels cleanly (returns None), does not set a key."""
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr("getpass.getpass", lambda *a, **k: "   ")
    assert cli_main._resolve_try_backend() is None


def test_ensure_chromium_true_when_present(monkeypatch):
    """When the browser executable exists, we return True and never shell out (P2)."""
    called = {"install": False}

    class _FakeChromium:
        executable_path = "/fake/chromium"

    class _FakePW:
        chromium = _FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: _FakePW())
    monkeypatch.setattr("os.path.exists", lambda p: True)

    import subprocess

    def _boom(*a, **k):
        called["install"] = True
        raise AssertionError("should not install when Chromium is present")

    monkeypatch.setattr(subprocess, "run", _boom)
    assert cli_main._ensure_chromium() is True
    assert called["install"] is False
