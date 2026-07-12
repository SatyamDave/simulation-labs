"""Tests for SupermemoryStore against a monkeypatched fake AsyncSupermemory —
no network. Verifies mode gating, tag routing, write counting, degradation on
error, and Protocol conformance."""

from __future__ import annotations

import pytest
from ghostpanel.memory.store import (
    MODE_OFF,
    MODE_RETURNING_USER,
    MODE_SITE_HINTS,
    INSIGHTS_TAG,
    MemoryStore,
    persona_site_tag,
    site_tag,
)
from ghostpanel.memory.supermemory_store import SupermemoryStore
from ghostpanel_contracts import PersonaConfig


# --- fakes -----------------------------------------------------------------
class _Row:
    def __init__(self, memory="", similarity=0.9, metadata=None):
        self.memory = memory
        self.similarity = similarity
        self.metadata = metadata or {}


class _SearchResp:
    def __init__(self, results):
        self.results = results
        self.total = len(results)
        self.timing = 1.0


class _FakeSearch:
    def __init__(self, rows_by_tag):
        self._rows_by_tag = rows_by_tag
        self.calls: list[dict] = []

    async def memories(self, **kwargs):
        self.calls.append(kwargs)
        return _SearchResp(self._rows_by_tag.get(kwargs.get("container_tag"), []))


class _FakeDocs:
    def __init__(self):
        self.adds: list[dict] = []

    async def add(self, **kwargs):
        self.adds.append(kwargs)
        return object()


class _FakeClient:
    def __init__(self, rows_by_tag=None):
        self.search = _FakeSearch(rows_by_tag or {})
        self.documents = _FakeDocs()
        self.closed = False

    async def close(self):
        self.closed = True


class _BoomSearch:
    async def memories(self, **kwargs):
        raise RuntimeError("network down")


class _BoomDocs:
    async def add(self, **kwargs):
        raise RuntimeError("network down")


class _BoomClient:
    def __init__(self):
        self.search = _BoomSearch()
        self.documents = _BoomDocs()


def _persona(pid="grandma-70"):
    return PersonaConfig(id=pid, name="Margaret")


# --- Protocol conformance --------------------------------------------------
def test_isinstance_memorystore():
    store = SupermemoryStore(api_key="x")
    assert isinstance(store, MemoryStore)


# --- recall_hints ----------------------------------------------------------
async def test_recall_hints_off_makes_no_call():
    store = SupermemoryStore(api_key="x")
    fake = _FakeClient()
    store._client = fake
    out = await store.recall_hints(
        target_url="https://example.com", task="sign up",
        persona=_persona(), mode=MODE_OFF,
    )
    assert out == []
    assert fake.search.calls == []


async def test_recall_hints_site_searches_site_tag():
    url = "https://example.com/x"
    fake = _FakeClient({site_tag(url): [_Row(memory="Use the top-right menu")]})
    store = SupermemoryStore(api_key="x")
    store._client = fake
    out = await store.recall_hints(
        target_url=url, task="sign up", persona=_persona(), mode=MODE_SITE_HINTS,
    )
    assert out == ["Use the top-right menu"]
    tags = [c["container_tag"] for c in fake.search.calls]
    assert tags == [site_tag(url)]  # only the site tag, not the persona tag


async def test_recall_hints_returning_user_searches_both_tags():
    url = "https://example.com/x"
    p = _persona()
    fake = _FakeClient({
        site_tag(url): [_Row(memory="site hint")],
        persona_site_tag(p.id, url): [_Row(memory="your own past visit")],
    })
    store = SupermemoryStore(api_key="x")
    store._client = fake
    out = await store.recall_hints(
        target_url=url, task="sign up", persona=p, mode=MODE_RETURNING_USER,
    )
    tags = {c["container_tag"] for c in fake.search.calls}
    assert tags == {site_tag(url), persona_site_tag(p.id, url)}
    # persona's own memory leads.
    assert out[0] == "your own past visit"
    assert "site hint" in out


async def test_recall_hints_dedups():
    url = "https://example.com"
    fake = _FakeClient({site_tag(url): [_Row(memory="dup"), _Row(memory="dup")]})
    store = SupermemoryStore(api_key="x")
    store._client = fake
    out = await store.recall_hints(
        target_url=url, task="t", persona=_persona(), mode=MODE_SITE_HINTS,
    )
    assert out == ["dup"]


async def test_recall_hints_degrades_on_error():
    store = SupermemoryStore(api_key="x")
    store._client = _BoomClient()
    out = await store.recall_hints(
        target_url="https://example.com", task="t",
        persona=_persona(), mode=MODE_SITE_HINTS,
    )
    assert out == []


# --- remember_run ----------------------------------------------------------
async def test_remember_run_writes_expected_docs(report, personas):
    store = SupermemoryStore(api_key="x")
    fake = _FakeClient()
    store._client = fake
    n = await store.remember_run(
        run_id=report.run_id, target_url=report.target_url, task=report.task,
        report=report, personas=personas,
    )
    # 3 playbooks + 2 insights + 3 persona visits = 8 records.
    assert n == 8
    assert len(fake.documents.adds) == 8
    assert all(a["dreaming"] == "instant" for a in fake.documents.adds)
    assert all(a["custom_id"].startswith("run-abc:") for a in fake.documents.adds)
    # no crashed-bot (error) written anywhere.
    assert all("crashed-bot" not in a["custom_id"] for a in fake.documents.adds)


async def test_remember_run_degrades_on_error(report, personas):
    store = SupermemoryStore(api_key="x")
    store._client = _BoomClient()
    n = await store.remember_run(
        run_id=report.run_id, target_url=report.target_url, task=report.task,
        report=report, personas=personas,
    )
    assert n == 0


# --- recall_insights -------------------------------------------------------
async def test_recall_insights_maps_fields():
    meta = {
        "site": "example-com", "persona_id": "grandma-70", "persona_name": "Margaret",
        "impairment": "blur+tremor", "outcome": "stuck", "steps_survived": 7,
    }
    fake = _FakeClient({INSIGHTS_TAG: [_Row(memory="abandoned at step 7", similarity=0.8, metadata=meta)]})
    store = SupermemoryStore(api_key="x")
    store._client = fake
    out = await store.recall_insights(query="blur")
    assert len(out) == 1
    rec = out[0]
    assert rec.content == "abandoned at step 7"
    assert rec.impairment == "blur+tremor"
    assert rec.steps_survived == 7
    assert rec.score == pytest.approx(0.8)
    assert rec.metadata == meta


async def test_recall_insights_filters_by_impairment():
    rows = [
        _Row(memory="a", metadata={"impairment": "blur+tremor"}),
        _Row(memory="b", metadata={"impairment": "none"}),
    ]
    fake = _FakeClient({INSIGHTS_TAG: rows})
    store = SupermemoryStore(api_key="x")
    store._client = fake
    out = await store.recall_insights(query="", impairment="blur+tremor")
    assert [r.content for r in out] == ["a"]
    # empty query falls back to a broad q.
    assert fake.search.calls[0]["q"] == "abandonment usability accessibility"


async def test_recall_insights_degrades_on_error():
    store = SupermemoryStore(api_key="x")
    store._client = _BoomClient()
    out = await store.recall_insights(query="x")
    assert out == []


# --- aclose ----------------------------------------------------------------
async def test_aclose_idempotent_and_closes():
    store = SupermemoryStore(api_key="x")
    fake = _FakeClient()
    store._client = fake
    await store.aclose()
    assert fake.closed
    await store.aclose()  # idempotent, no raise
