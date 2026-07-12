"""Container-tag helpers must never exceed Supermemory's 100-char limit.

Regression: a ``file://`` fixture path (or a very long hostname) previously
produced a >100-char persona tag, which Supermemory rejects with HTTP 400
``too_big`` — silently dropping the write, since the store swallows errors.
"""

from __future__ import annotations

from ghostpanel.memory import persona_site_tag, site_tag
from ghostpanel.memory.store import domain_slug

_LONG_FILE_URL = (
    "file:///Users/udsy/.superset/worktrees/simulation-labs/"
    "memory-improvement/fixtures/hostile_form.html"
)
_LONG_HOST_URL = "https://" + ("very-long-subdomain-segment." * 8) + "example.com/checkout"


def test_normal_domain_tags_are_readable_and_unchanged():
    assert site_tag("https://www.stripe.com/checkout") == "gp:site:stripe-com"
    assert persona_site_tag("tremor", "https://stripe.com") == "gp:persona:tremor:site:stripe-com"


def test_all_tags_stay_within_100_chars():
    for url in (_LONG_FILE_URL, _LONG_HOST_URL):
        assert len(site_tag(url)) <= 100, url
        for pid in ("power-user", "grandma-72", "impatient-mobile"):
            assert len(persona_site_tag(pid, url)) <= 100, (pid, url)


def test_capping_is_deterministic_and_distinct():
    # Same input -> same tag (write and later recall must agree).
    assert site_tag(_LONG_FILE_URL) == site_tag(_LONG_FILE_URL)
    # Different long inputs -> different tags (the hash suffix disambiguates).
    assert site_tag(_LONG_FILE_URL) != site_tag(_LONG_HOST_URL)
    assert domain_slug("https://stripe.com") == "stripe-com"
