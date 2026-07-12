"""Compatibility shim for the CLAUDE.md class registry.

The registry lists the concrete ``EventSink`` at
``ghostpanel.server.events.WebSocketEventSink``; the implementation lives in
``ghostpanel.server.ws``. Re-export it here so both import paths resolve.
"""

from __future__ import annotations

from .ws import WebSocketEventSink, WebSocketHub

__all__ = ["WebSocketEventSink", "WebSocketHub"]
