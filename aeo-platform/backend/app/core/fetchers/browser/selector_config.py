"""Browser selector configuration with hot-reload.

Loads CSS selectors and text patterns from selectors.yaml.
Checks file modification time on each access — edit the YAML
and changes take effect on the next fetch() call.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_SELECTORS_FILE = Path(__file__).parent / "selectors.yaml"
_cache: dict[str, Any] = {}
_cache_mtime: float = 0.0


def _load() -> dict[str, Any]:
    """Load and cache the YAML config, reloading only when the file changes."""
    global _cache, _cache_mtime

    try:
        current_mtime = _SELECTORS_FILE.stat().st_mtime
    except OSError:
        if not _cache:
            logger.warning("Selectors file not found: %s", _SELECTORS_FILE)
        return _cache

    if current_mtime != _cache_mtime:
        try:
            with open(_SELECTORS_FILE, "r", encoding="utf-8") as f:
                _cache = yaml.safe_load(f) or {}
            _cache_mtime = current_mtime
            logger.info("Reloaded browser selectors from %s", _SELECTORS_FILE)
        except Exception as e:
            logger.error("Failed to load selectors YAML: %s", e)

    return _cache


def get_platform_config(platform: str) -> dict[str, Any]:
    """Return the full config dict for a platform (e.g. 'kimi', 'deepseek')."""
    return _load().get(platform, {})


def get(platform: str, key: str, default: Any = None) -> Any:
    """Get a single selector/text value with fallback default."""
    return get_platform_config(platform).get(key, default)
