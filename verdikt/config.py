"""Central configuration for Verdikt.

All secrets come from environment variables so nothing is baked into source.
The PubMed and openFDA keys are optional: both APIs work without a key at a
lower rate limit, so the tool degrades gracefully when they are missing.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """Load KEY=VALUE lines from a project-root .env into os.environ.

    Zero-dependency and non-destructive: a value already set in the real
    environment always wins over the file. This lets a user drop their secret
    into a gitignored .env instead of exporting it every shell.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


@dataclass(frozen=True)
class Config:
    # --- Claude (the reasoning engine) ---
    anthropic_api_key: str | None = None
    model: str = "claude-opus-4-8"

    # --- Optional source API keys (leave blank to run unauthenticated) ---
    ncbi_api_key: str | None = None      # PubMed / E-utilities
    openfda_api_key: str | None = None   # openFDA drug label API

    # --- Networking ---
    timeout: int = 30
    user_agent: str = "Verdikt/0.1 (Evidence-to-Decision Engine; +https://github.com/verdikt)"
    # A contact email is required by NCBI E-utilities etiquette.
    contact_email: str = "research@verdikt.local"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            model=os.getenv("VERDIKT_MODEL", "claude-opus-4-8"),
            ncbi_api_key=os.getenv("NCBI_API_KEY"),
            openfda_api_key=os.getenv("OPENFDA_API_KEY"),
            contact_email=os.getenv("VERDIKT_CONTACT_EMAIL", "research@verdikt.local"),
        )


CONFIG = Config.from_env()
