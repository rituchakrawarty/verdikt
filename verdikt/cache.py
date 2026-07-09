"""Tiny persistent disk cache — the main cost lever.

Gathering evidence hits free public APIs; the real money is Claude tokens. If we
remember what we already fetched and already reasoned, the *second* time anyone
investigates an entity it is fast and nearly free — and the answer is identical,
so due-diligence quality is untouched.

Simple by design: one JSON file per entry under `.cache/<namespace>/`, keyed by a
hash of the inputs, with an optional time-to-live.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"

# Sources change slowly; reasoning is deterministic given the evidence.
SOURCE_TTL = 7 * 24 * 3600      # 1 week
CLAUDE_TTL = 30 * 24 * 3600     # 1 month


def _path(namespace: str, key) -> Path:
    digest = hashlib.sha1(
        json.dumps(key, sort_keys=True, default=str).encode()
    ).hexdigest()[:20]
    folder = CACHE_DIR / namespace
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{digest}.json"


def get(namespace: str, key, ttl: int | None = None):
    path = _path(namespace, key)
    if not path.exists():
        return None
    try:
        record = json.loads(path.read_text())
    except (ValueError, OSError):
        return None
    if ttl is not None and time.time() - record.get("ts", 0) > ttl:
        return None
    return record.get("value")


def put(namespace: str, key, value) -> None:
    try:
        _path(namespace, key).write_text(
            json.dumps({"ts": time.time(), "value": value}, default=str)
        )
    except OSError:
        pass
