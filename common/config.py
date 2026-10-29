"""Load settings.yaml + .env once. Every module imports from here."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@lru_cache(maxsize=1)
def settings() -> dict:
    with open(ROOT / "config" / "settings.yaml") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def sectors() -> dict[str, list[tuple[int, int]]]:
    with open(ROOT / "config" / "sectors.yaml") as f:
        raw = yaml.safe_load(f)
    return {k: [tuple(r) for r in v] for k, v in raw.items()}


def path(key: str) -> Path:
    """Resolve a path from settings.paths relative to the repo root and create it."""
    p = ROOT / settings()["paths"][key]
    p.mkdir(parents=True, exist_ok=True)
    return p


def sec_user_agent() -> str:
    ua = os.getenv("SEC_USER_AGENT", "").strip().strip('"')
    if "@" not in ua:
        raise RuntimeError(
            "SEC_USER_AGENT is missing. Copy .env.example to .env and set "
            '"Your Name your@email.com" (SEC rejects anonymous requests).'
        )
    return ua
