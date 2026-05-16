"""OpenAI embedding wrapper.

Single-call entry point: `embed_texts(texts) -> list[list[float]]`.
Batches inputs at the API layer so we don't blow the per-request
token budget on long documents, and retries once on a rate-limit so
a transient blip doesn't kill an ingest.

Stays small on purpose. If we ever add another embedder, the
pluggable seam is at this function — not at the call sites.
"""

from __future__ import annotations

import time
from typing import Iterable

from openai import OpenAI, RateLimitError

from . import config

# OpenAI's text-embedding-3-* accepts up to 2048 inputs per request,
# but we cap lower to keep retries cheap and request bodies small.
_BATCH_SIZE = 256

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        config.require_openai_key()
        kwargs: dict = {"api_key": config.OPENAI_API_KEY}
        if config.OPENAI_BASE_URL:
            kwargs["base_url"] = config.OPENAI_BASE_URL
        _client = OpenAI(**kwargs)
    return _client


def _batches(items: list[str], n: int) -> Iterable[list[str]]:
    for i in range(0, len(items), n):
        yield items[i : i + n]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed every text. Order of output matches order of input."""
    if not texts:
        return []
    client = _get_client()
    out: list[list[float]] = []
    for batch in _batches(texts, _BATCH_SIZE):
        try:
            resp = client.embeddings.create(model=config.EMBED_MODEL, input=batch)
        except RateLimitError:
            time.sleep(2)
            resp = client.embeddings.create(model=config.EMBED_MODEL, input=batch)
        out.extend(d.embedding for d in resp.data)
    return out
