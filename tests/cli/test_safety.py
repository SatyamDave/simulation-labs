"""Tests for cli/safety.py — the SSRF / target-URL guard (Agent C).

safety.py is implemented, so these run for real. Hostname cases monkeypatch
`socket.getaddrinfo` to a fixed PUBLIC address so the suite stays fully offline
and deterministic (no DNS). If safety.py were still a stub the guard would raise
NotImplementedError, so the calls are wrapped with an xfail(strict=False) guard
that flips to pass once implemented.
"""

from __future__ import annotations

import socket

import pytest

from ghostpanel.cli.safety import UnsafeURLError, assert_url_allowed

# --- offline DNS: force any hostname to resolve to a public IP ---------------
_PUBLIC_IP = "93.184.216.34"  # public (example.com); passes the SSRF checks


@pytest.fixture
def public_dns(monkeypatch):
    def _fake_getaddrinfo(host, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (_PUBLIC_IP, 0))
        ]

    monkeypatch.setattr(
        "ghostpanel.cli.safety.socket.getaddrinfo", _fake_getaddrinfo
    )


def _is_stub() -> bool:
    try:
        assert_url_allowed("https://example.com", allow_private=True)
        return False
    except NotImplementedError:
        return True
    except Exception:
        return False


pytestmark = pytest.mark.xfail(
    _is_stub(), reason="pending Agent C safety.py", strict=False
)


def test_allows_plain_https(public_dns):
    assert_url_allowed("https://example.com")  # no raise


def test_rejects_non_http_scheme():
    with pytest.raises(UnsafeURLError):
        assert_url_allowed("ftp://example.com/x")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1",
        "http://localhost",  # resolves to loopback
        "http://10.0.0.5",
        "http://169.254.169.254",  # cloud metadata endpoint (link-local)
    ],
)
def test_rejects_internal_and_metadata_addresses(url):
    with pytest.raises(UnsafeURLError):
        assert_url_allowed(url)


def test_rejects_host_absent_from_nonempty_allowlist():
    with pytest.raises(UnsafeURLError):
        assert_url_allowed("https://evil.com", allowlist=["example.com"])


def test_allows_subdomain_via_suffix_allowlist(public_dns):
    # app.example.com is a suffix match for the allowlist entry example.com
    assert_url_allowed("https://app.example.com", allowlist=["example.com"])


def test_file_url_allowed_only_with_allow_private():
    with pytest.raises(UnsafeURLError):
        assert_url_allowed("file:///tmp/page.html")
    # opting in (how --fixture works) permits it
    assert_url_allowed("file:///tmp/page.html", allow_private=True)
