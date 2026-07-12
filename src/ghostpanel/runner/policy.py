"""Client-side mirror of the NemoClaw / OpenShell network policy.

``RequestPolicy`` parses an OpenShell network-policy *preset* (the schema
live-pulled from
https://docs.nvidia.com/nemoclaw/user-guide/openclaw/network-policy/customize-network-policy.md
— see ``policies/ghostpanel-browse-only.yaml``) and answers one question:
``allows(method, url)``. ``PlaywrightSessionRunner`` uses it to abort every
browser request the policy does not allow, so "browse but never
submit/pay/exfiltrate" is enforced *inside* the swarm even when the real
OpenShell gateway (``nemoclaw <sandbox> policy-add --from-file``,
``policy-list`` / ``policy-explain``; baseline
``nemoclaw-blueprint/policies/openclaw-sandbox.yaml``) is not in the network
path.

Mirrored semantics (per the docs):
  * Each ``network_policies.*.endpoints[]`` entry names a host (glob patterns
    like ``*`` / ``*.example.com`` supported) with ``rules`` that ALLOW
    specific HTTP method+path combinations.
  * Within an ``enforcement: enforce`` endpoint the rules are an allow-list —
    anything not explicitly allowed is denied (default-deny).
  * ``enforcement: monitor`` (or anything other than ``enforce``) endpoints
    observe but never block; a request matching only monitor endpoints passes.
  * Endpoints not listed at all go to *operator approval* in OpenShell; this
    client-side mirror has no operator, so unmatched requests are DENIED
    (fail-closed).

Deliberate mirror deviation — ports: the preset pins ports (80/443) for the
real gateway, which sees the socket. The client-side mirror matches on
host+method+path only and ignores the port: browser traffic in dev/tests
arrives on arbitrary localhost ports, and the security property Ghostpanel
mirrors is the method/path allow-list. Port pinning stays the gateway's job.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml


def _path_glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate an OpenShell path glob into a regex.

    ``**`` matches anything including ``/``; a single ``*`` matches within one
    path segment. ``"/**"`` therefore matches every path.
    """
    out: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if pattern[i : i + 2] == "**":
                out.append(".*")
                i += 2
            else:
                out.append("[^/]*")
                i += 1
        else:
            out.append(re.escape(ch))
            i += 1
    return re.compile("^" + "".join(out) + "$")


class _Endpoint:
    """One parsed ``endpoints[]`` entry: host glob + method/path allow rules."""

    def __init__(self, spec: dict[str, Any]) -> None:
        self.host_pattern: str = str(spec.get("host", "*")).lower()
        self.enforced: bool = str(spec.get("enforcement", "enforce")) == "enforce"
        # [(METHOD, compiled path regex, raw path glob)]
        self.allow_rules: list[tuple[str, re.Pattern[str], str]] = []
        for rule in spec.get("rules") or []:
            allow = (rule or {}).get("allow")
            if not isinstance(allow, dict):
                continue  # only `allow` rules exist in the documented schema
            method = str(allow.get("method", "GET")).upper()
            path_glob = str(allow.get("path", "/**"))
            self.allow_rules.append((method, _path_glob_to_regex(path_glob), path_glob))

    def matches_host(self, host: str) -> bool:
        if self.host_pattern == "*":
            return True
        return fnmatch.fnmatchcase(host.lower(), self.host_pattern)

    def allows(self, method: str, path: str) -> bool:
        return any(
            method == rule_method and rule_path.match(path)
            for rule_method, rule_path, _ in self.allow_rules
        )


class RequestPolicy:
    """``allows(method, url)`` over a parsed OpenShell preset dict."""

    def __init__(self, preset: dict[str, Any]) -> None:
        preset = preset or {}
        self.preset_name: str = str((preset.get("preset") or {}).get("name", "")) or "unnamed"
        self.endpoints: list[_Endpoint] = []
        for policy in (preset.get("network_policies") or {}).values():
            for spec in (policy or {}).get("endpoints") or []:
                if isinstance(spec, dict):
                    self.endpoints.append(_Endpoint(spec))

    # -- construction -------------------------------------------------------
    @classmethod
    def from_file(cls, path: str | Path) -> "RequestPolicy":
        """Parse a preset YAML file. Raises on unreadable/invalid YAML — a
        misconfigured policy must fail loudly, never silently no-op."""
        parsed = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError(f"Policy preset {path} is not a YAML mapping.")
        return cls(parsed)

    # -- the decision -------------------------------------------------------
    def allows(self, method: str, url: str) -> bool:
        """True iff the policy allows ``method`` against ``url``.

        Enforced endpoint matching the host: allowed only by an explicit rule
        (default-deny within the endpoint). Monitor-only match: allowed.
        No endpoint matches the host: denied (fail-closed — the mirror has no
        operator to escalate to).
        """
        method = (method or "").upper()
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        path = parts.path or "/"

        matched = [e for e in self.endpoints if e.matches_host(host)]
        if not matched:
            return False
        enforced = [e for e in matched if e.enforced]
        if not enforced:
            return True  # monitor-only endpoints never block
        return any(e.allows(method, path) for e in enforced)

    # -- introspection (GET /policy summary) --------------------------------
    @property
    def allowed_methods(self) -> list[str]:
        return sorted(
            {method for e in self.endpoints if e.enforced for method, _, _ in e.allow_rules}
        )

    @property
    def hosts(self) -> list[str]:
        return sorted({e.host_pattern for e in self.endpoints})

    def summary(self) -> dict[str, Any]:
        """The shape ``GET /policy`` reports for a loaded preset."""
        return {
            "preset": self.preset_name,
            "allowed_methods": self.allowed_methods,
            "denied_by_default": True,
            "hosts": self.hosts,
        }
