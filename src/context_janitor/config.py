from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROVIDERS = frozenset({"heuristic", "openai", "anthropic", "gemini"})
FALLBACKS = frozenset({"heuristic", "none"})
LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
FORMATS = frozenset({"json", "names", "raw"})


@dataclass(frozen=True)
class JanitorConfig:
    provider: str = "heuristic"
    model: str | None = None
    limit: int = 5
    fallback: str = "heuristic"
    cache: bool = False
    timeout_ms: int = 800
    log_level: str = "WARNING"
    format: str = "json"
    price_per_million_tokens: float = 5.0
    keep: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", self.provider.lower())
        object.__setattr__(self, "fallback", self.fallback.lower())
        object.__setattr__(self, "log_level", self.log_level.upper())
        object.__setattr__(self, "format", self.format.lower())

        if self.provider not in PROVIDERS:
            raise ValueError(f"provider must be one of: {', '.join(sorted(PROVIDERS))}.")
        if self.fallback not in FALLBACKS:
            raise ValueError(f"fallback must be one of: {', '.join(sorted(FALLBACKS))}.")
        if self.log_level not in LOG_LEVELS:
            raise ValueError(f"log_level must be one of: {', '.join(sorted(LOG_LEVELS))}.")
        if self.format not in FORMATS:
            raise ValueError(f"format must be one of: {', '.join(sorted(FORMATS))}.")
        if self.limit <= 0:
            raise ValueError("limit must be greater than zero.")
        if self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be greater than zero.")
        if self.price_per_million_tokens < 0:
            raise ValueError("price_per_million_tokens must be zero or greater.")


DEFAULT_CONFIG = JanitorConfig()


def load_config(start: Path | None = None, explicit_path: str | None = None) -> JanitorConfig:
    path = Path(explicit_path) if explicit_path else find_config(start or Path.cwd())
    if not path:
        return JanitorConfig()
    values = _read_simple_yaml(path)
    return JanitorConfig(
        provider=str(values.get("provider", DEFAULT_CONFIG.provider)),
        model=_optional_str(values.get("model")),
        limit=int(values.get("limit", DEFAULT_CONFIG.limit)),
        fallback=str(values.get("fallback", DEFAULT_CONFIG.fallback)),
        cache=_bool(values.get("cache", DEFAULT_CONFIG.cache)),
        timeout_ms=int(values.get("timeout_ms", values.get("timeout", DEFAULT_CONFIG.timeout_ms))),
        log_level=str(values.get("log_level", DEFAULT_CONFIG.log_level)),
        format=str(values.get("format", DEFAULT_CONFIG.format)),
        price_per_million_tokens=float(
            values.get("price_per_million_tokens", DEFAULT_CONFIG.price_per_million_tokens)
        ),
        keep=_tuple(values.get("keep", DEFAULT_CONFIG.keep)),
    )


def find_config(start: Path) -> Path | None:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for directory in [current, *current.parents]:
        candidate = directory / ".janitor.yaml"
        if candidate.exists():
            return candidate
    return None


def merge_config(config: JanitorConfig, overrides: dict[str, Any]) -> JanitorConfig:
    values = config.__dict__ | {key: value for key, value in overrides.items() if value is not None}
    return JanitorConfig(**values)


def _read_simple_yaml(path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise ValueError(f"{path}:{line_number}: expected 'key: value'.")
        key, raw_value = stripped.split(":", 1)
        values[key.strip()] = _parse_scalar(raw_value.strip())
    return values


def _parse_scalar(value: str) -> Any:
    value = value.split(" #", 1)[0].strip()
    if not value:
        return None
    if value[0:1] in {"'", '"'} and value[-1:] == value[0]:
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    if lowered in {"null", "none"}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


def _tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return tuple(part.strip() for part in str(value).split(",") if part.strip())
