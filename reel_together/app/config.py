"""Runtime configuration for Reel Together.

Home Assistant writes the add-on options the user sets in the UI to
``/data/options.json``. We read those when present and fall back to environment
variables so the app is also runnable as a plain container during development.
"""
from __future__ import annotations

import json
import os

OPTIONS_PATH = os.environ.get("REEL_OPTIONS_PATH", "/data/options.json")


def _load_options() -> dict:
    try:
        with open(OPTIONS_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


_OPTIONS = _load_options()


def _opt(key: str, env: str, default=None):
    """Prefer an HA add-on option, then an env var, then the default."""
    val = _OPTIONS.get(key)
    if val not in (None, ""):
        return val
    return os.environ.get(env, default)


def _as_bool(val, default: bool = False) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


# --- Public settings -------------------------------------------------------
TMDB_API_KEY: str = (_opt("tmdb_api_key", "REEL_TMDB_API_KEY", "") or "").strip()
METADATA_PROVIDER: str = (_opt("metadata_provider", "REEL_PROVIDER", "auto") or "auto").lower()
LOG_LEVEL: str = (_opt("log_level", "REEL_LOG_LEVEL", "info") or "info").lower()
ALLOW_DIRECT_ACCESS: bool = _as_bool(_opt("allow_direct_access", "REEL_ALLOW_DIRECT", False))

PORT: int = int(os.environ.get("REEL_PORT", "8099"))
DB_PATH: str = os.environ.get("REEL_TOGETHER_DB", "/data/reel_together.db")

# Home Assistant's Supervisor proxies ingress traffic from this fixed address.
INGRESS_IP = "172.30.32.2"


def active_provider_name() -> str:
    """Resolve the provider actually used for search.

    ``auto`` uses TMDB when a key is configured, otherwise Wikipedia.
    """
    if METADATA_PROVIDER == "auto":
        return "tmdb" if TMDB_API_KEY else "wikipedia"
    return METADATA_PROVIDER


def public_config() -> dict:
    """Non-secret config surfaced to the front-end."""
    return {
        "provider": active_provider_name(),
        "provider_mode": METADATA_PROVIDER,
        "tmdb_enabled": bool(TMDB_API_KEY),
    }
