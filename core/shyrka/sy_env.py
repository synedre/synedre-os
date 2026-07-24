"""
sy_env — Centralized loading of environment variables.

Usage in every sy_*.py:
    from sy_env import load_env
    load_env()

Loads .env (Docker/shared) then .env.host (host-only, override).
Python scripts run on the HOST, so .env.host takes priority
(e.g. DB_PORT=3307 overrides the DB_PORT missing from the cleaned .env).

"""

from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def load_env():
    """Loads .env.host then .env (without overriding the existing os.environ).

    Priority order (strongest to weakest):
      1. Variables already present in os.environ (subprocess overrides, cron exports)
      2. .env.host (host specifics — ports, machine-local credentials)
      3. .env (shared Docker/shyrka values)

    Loading .env.host first (override=False) guarantees that subprocess/cron
    vars take precedence over .env.host, while keeping .env.host ahead of
    .env (since .env is loaded afterwards, override=False, and does not
    touch what we just set from .env.host).
    """
    load_dotenv(ROOT / ".env.host", override=False)
    load_dotenv(ROOT / ".env", override=False)
