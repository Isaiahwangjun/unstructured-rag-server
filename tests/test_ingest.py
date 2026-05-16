"""Round-trip test: ingest a 2-chunk fixture, query, assert the
right chunk wins. The OpenAI embedder is stubbed so this test runs
without a network call or an API key."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "tiny_chunks.json"


def _fake_embed(texts: list[str]) -> list[list[float]]:
    """Map the test corpus to deterministic vectors so we can assert
    on which chunk wins a query.

    We use 3-dim vectors here. Chroma stores whatever dim we hand it,
    so as long as the query vector and the indexed vectors share a
    space, distances are meaningful.
    """
    vectors: list[list[float]] = []
    for t in texts:
        if "Dogs" in t or "dogs" in t:
            vectors.append([1.0, 0.0, 0.0])
        elif "Cars" in t or "cars" in t:
            vectors.append([0.0, 1.0, 0.0])
        else:
            vectors.append([0.0, 0.0, 1.0])
    return vectors


@pytest.fixture
def isolated_chroma(tmp_path, monkeypatch):
    """Point Chroma at a tmp dir so this test doesn't pollute (or get
    polluted by) the local persistent store."""
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / ".chroma"))
    monkeypatch.setenv("COLLECTION", "test_collection")

    # Reload config + reset the lazy-singleton clients.
    import importlib
    from rag_server import config, embed, store

    importlib.reload(config)
    importlib.reload(embed)
    importlib.reload(store)
    yield


def test_ingest_then_query(isolated_chroma, monkeypatch):
    from rag_server import embed, ingest, store

    monkeypatch.setattr(embed, "embed_texts", _fake_embed)

    n = ingest.ingest_file(FIXTURE)
    assert n == 2

    # Query for "dogs" — fixture maps Dogs body to [1,0,0]
    hits = store.query(_fake_embed(["dogs"])[0], k=2)
    assert len(hits) == 2
    assert hits[0]["id"] == "tiny::c_0001"
    assert "Dogs" in hits[0]["body"]
    assert hits[0]["headings"] == ["Animals"]
    assert hits[0]["page_start"] == 1

    # The car chunk should be the second hit, with a worse score.
    assert hits[1]["id"] == "tiny::c_0002"
    assert hits[1]["score"] > hits[0]["score"]


def test_list_sources(isolated_chroma, monkeypatch):
    from rag_server import embed, ingest, store

    monkeypatch.setattr(embed, "embed_texts", _fake_embed)
    ingest.ingest_file(FIXTURE)

    assert store.list_sources() == ["tiny"]


def test_id_namespacing_prevents_collision(isolated_chroma, monkeypatch, tmp_path):
    """Two chunks.json files with overlapping ids should both survive
    in the store, distinguished by the source-prefixed id."""
    from rag_server import embed, ingest, store

    monkeypatch.setattr(embed, "embed_texts", _fake_embed)

    # Original tiny fixture (source = "tiny.pdf")
    ingest.ingest_file(FIXTURE)

    # Build a second chunks.json with the same ids but different source.
    other = json.loads(FIXTURE.read_text())
    other["source"] = "other.pdf"
    other_path = tmp_path / "other_chunks.json"
    other_path.write_text(json.dumps(other), encoding="utf-8")
    ingest.ingest_file(other_path)

    sources = store.list_sources()
    assert sources == ["other", "tiny"], sources

    # Both 'c_0001' chunks should coexist under namespaced ids.
    hits = store.query(_fake_embed(["dogs"])[0], k=4)
    ids = [h["id"] for h in hits]
    assert "tiny::c_0001" in ids
    assert "other::c_0001" in ids
