from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Any

from .models import Tool
from .ranker import PromptAliases, tokens


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
    prompt_aliases: PromptAliases | None = None,
) -> CacheEntry | None:
    path = cache_path or default_cache_path()
    payload = _read_cache(path)
    catalog_hash = _catalog_hash(tools)
    alias_hash = _aliases_hash(prompt_aliases)
    exact_key = _entry_key(prompt, catalog_hash, provider, model, limit, alias_hash)
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
        if entry.get("alias_hash", "") != alias_hash:
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
    prompt_aliases: PromptAliases | None = None,
) -> None:
    path = cache_path or default_cache_path()
    payload = _read_cache(path)
    catalog_hash = _catalog_hash(tools)
    alias_hash = _aliases_hash(prompt_aliases)
    payload[_entry_key(prompt, catalog_hash, provider, model, limit, alias_hash)] = {
        "prompt": prompt,
        "prompt_tokens": tokens(prompt),
        "catalog_hash": catalog_hash,
        "alias_hash": alias_hash,
        "provider": provider,
        "model": model,
        "limit": limit,
        "names": [tool.name for tool in selected],
        "created_at": int(time()),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_cache(path, payload)


def _read_cache(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_cache(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_name = temp_file.name
            temp_file.write(encoded)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass


def _catalog_hash(tools: list[Tool]) -> str:
    catalog = [{"name": tool.name, "description": tool.description} for tool in tools]
    return hashlib.sha256(json.dumps(catalog, sort_keys=True).encode("utf-8")).hexdigest()


def _aliases_hash(prompt_aliases: PromptAliases | None) -> str:
    if not prompt_aliases:
        return ""
    payload = {key: list(values) for key, values in sorted(prompt_aliases.items())}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _entry_key(
    prompt: str,
    catalog_hash: str,
    provider: str,
    model: str | None,
    limit: int,
    alias_hash: str,
) -> str:
    payload = {
        "prompt": prompt,
        "catalog_hash": catalog_hash,
        "alias_hash": alias_hash,
        "provider": provider,
        "model": model,
        "limit": limit,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)
