from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Any

from .models import Tool
from .ranker import tokens


@dataclass(frozen=True)
class CacheEntry:
    names: list[str]
    similarity: float


def default_cache_path() -> Path:
    return Path.home() / ".janitor_cache" / "cache.json"


def clear_cache(cache_path: Path | None = None) -> bool:
    path = cache_path or default_cache_path()
    if not path.exists():
        return False
    path.unlink()
    return True


def cache_info(cache_path: Path | None = None) -> dict[str, Any]:
    path = cache_path or default_cache_path()
    payload = _read_cache(path)
    entries = [entry for entry in payload.values() if isinstance(entry, dict)]
    created_at: list[int] = []
    for entry in entries:
        value = entry.get("created_at")
        if isinstance(value, int):
            created_at.append(value)
    return {
        "path": str(path),
        "exists": path.exists(),
        "entries": len(entries),
        "providers": sorted({str(entry.get("provider")) for entry in entries if entry.get("provider")}),
        "models": sorted({str(entry.get("model")) for entry in entries if entry.get("model")}),
        "oldest_created_at": min(created_at) if created_at else None,
        "newest_created_at": max(created_at) if created_at else None,
    }


def get_cached_selection(
    prompt: str,
    tools: list[Tool],
    provider: str,
    model: str | None,
    limit: int,
    cache_path: Path | None = None,
    similarity_threshold: float = 0.92,
) -> CacheEntry | None:
    path = cache_path or default_cache_path()
    payload = _read_cache(path)
    catalog_hash = _catalog_hash(tools)
    exact_key = _entry_key(prompt, catalog_hash, provider, model, limit)
    exact = payload.get(exact_key)
    if exact:
        return CacheEntry(names=list(exact.get("names", [])), similarity=1.0)

    prompt_terms = set(tokens(prompt))
    if not prompt_terms:
        return None

    best: CacheEntry | None = None
    for entry in payload.values():
        if entry.get("catalog_hash") != catalog_hash:
            continue
        if entry.get("provider") != provider or entry.get("model") != model or entry.get("limit") != limit:
            continue
        cached_terms = set(entry.get("prompt_tokens", []))
        similarity = _jaccard(prompt_terms, cached_terms)
        if similarity >= similarity_threshold and (best is None or similarity > best.similarity):
            best = CacheEntry(names=list(entry.get("names", [])), similarity=similarity)
    return best


def store_selection(
    prompt: str,
    tools: list[Tool],
    selected: list[Tool],
    provider: str,
    model: str | None,
    limit: int,
    cache_path: Path | None = None,
) -> None:
    path = cache_path or default_cache_path()
    payload = _read_cache(path)
    catalog_hash = _catalog_hash(tools)
    payload[_entry_key(prompt, catalog_hash, provider, model, limit)] = {
        "prompt": prompt,
        "prompt_tokens": tokens(prompt),
        "catalog_hash": catalog_hash,
        "provider": provider,
        "model": model,
        "limit": limit,
        "names": [tool.name for tool in selected],
        "created_at": int(time()),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_cache(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _catalog_hash(tools: list[Tool]) -> str:
    catalog = [{"name": tool.name, "description": tool.description} for tool in tools]
    return hashlib.sha256(json.dumps(catalog, sort_keys=True).encode("utf-8")).hexdigest()


def _entry_key(prompt: str, catalog_hash: str, provider: str, model: str | None, limit: int) -> str:
    payload = {
        "prompt": prompt,
        "catalog_hash": catalog_hash,
        "provider": provider,
        "model": model,
        "limit": limit,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
