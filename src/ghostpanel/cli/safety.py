"""SSRF / target-URL safety guard — Agent C owns this file.

Running a real browser against a customer-supplied URL is the biggest new attack
surface in Phase 1, so this guard runs before every navigation. Signature is
FROZEN (driver.py / main.py call it).

The guard defends against Server-Side Request Forgery (SSRF): a target URL that
resolves to an internal address (loopback, RFC-1918 private ranges, link-local —
crucially the cloud metadata endpoint 169.254.169.254 — reserved, multicast, or
the unspecified address) is refused. Because a public hostname can still resolve
to an internal IP (DNS rebinding), we resolve the host and inspect *every*
returned address, not just literal-IP hosts.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeURLError(Exception):
    """Raised when a target URL is refused by the safety guard."""


_OPT_IN = (
    "pass allow_private / safety.allow_private: true to test local targets"
)


def _classify(ip: ipaddress._BaseAddress) -> str | None:
    """Return a human category if `ip` is not a safe public address, else None."""
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        # 169.254.0.0/16 — includes the cloud metadata endpoint 169.254.169.254.
        return "link-local"
    if ip.is_private:
        return "private"
    if ip.is_multicast:
        return "multicast"
    if ip.is_unspecified:
        return "unspecified"
    if ip.is_reserved:
        return "reserved"
    return None


def assert_url_allowed(
    url: str,
    *,
    allow_private: bool = False,
    allowlist: list[str] | None = None,
) -> None:
    """Raise UnsafeURLError unless `url` is safe to point the browser at.

    Reject: non-http(s) schemes; loopback / private / link-local / reserved /
    multicast / unspecified IPs (resolve the host first) unless allow_private=True;
    hosts not on `allowlist` when it is non-empty. `file://` is permitted ONLY when
    allow_private=True (that is how --fixture opts in). Return None when allowed.
    """
    parts = urlsplit(url)
    scheme = parts.scheme.lower()

    # --- scheme gate ---------------------------------------------------------
    if scheme == "file":
        if not allow_private:
            raise UnsafeURLError(
                f"refusing file:// URL {url!r}: local files are only reachable "
                f"with --fixture ({_OPT_IN})."
            )
        # A file:// URL has no network host to resolve or allowlist-check.
        return
    if scheme not in ("http", "https"):
        raise UnsafeURLError(
            f"refusing scheme {scheme or '(none)'!r} in {url!r}: only http(s) "
            f"targets are allowed (use https://your-app.example.com)."
        )

    # --- host presence -------------------------------------------------------
    host = parts.hostname
    if not host:
        raise UnsafeURLError(
            f"no host found in {url!r}: give a full URL like "
            f"https://your-app.example.com/signup."
        )

    # --- allowlist (host-level, before any DNS work) -------------------------
    if allowlist:
        host_l = host.lower()
        allowed = any(
            host_l == entry.lower() or host_l.endswith("." + entry.lower())
            for entry in allowlist
            if entry
        )
        if not allowed:
            raise UnsafeURLError(
                f"host {host!r} is not on the allowlist {allowlist!r}: add it "
                f"(exact host, or a parent domain like 'example.com' to allow "
                f"'app.example.com') to test this target."
            )

    # --- SSRF address checks -------------------------------------------------
    if allow_private:
        # Explicitly opted in to internal targets (localhost / staging).
        return

    # Literal-IP host: check it directly (covers IPv6 in brackets too).
    literal_ip: ipaddress._BaseAddress | None = None
    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        category = _classify(literal_ip)
        if category is not None:
            raise UnsafeURLError(
                f"refusing {category} address {host} for target {url!r}: this "
                f"points at an internal/host network. {_OPT_IN.capitalize()}."
            )
        return

    # Hostname: resolve and reject if ANY resolved IP is internal (DNS-rebinding
    # / metadata-endpoint defence).
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURLError(
            f"could not resolve host {host!r} for target {url!r}: {exc}. "
            f"Check the URL is reachable."
        ) from exc

    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:  # pragma: no cover - getaddrinfo should return valid IPs
            continue
        category = _classify(ip)
        if category is not None:
            raise UnsafeURLError(
                f"refusing private address {ip} for {host}: host resolves to a "
                f"{category} address (possible SSRF). {_OPT_IN.capitalize()}."
            )


__all__ = ["UnsafeURLError", "assert_url_allowed"]
