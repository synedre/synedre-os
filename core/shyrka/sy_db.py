"""
synedre/db.py — PostgreSQL connection helper for sandbox agents.

Why this file exists (scar 2026-05-23, jobsite #94):
  The sub-claudes spawned by sy_task_worker via atlas-spawn-claude.mjs run
  in a Linux host context (not inside Docker). They have no access to:
    - the internal Docker hostname `sy_postgres` (not resolvable from the host)
    - the Docker socket (missing permissions for `docker exec sy_postgres psql`)

  Solution: the sy_postgres container exposes its port 5432 on 127.0.0.1:5433
  host-side. The TCP connection localhost:5433 is reachable from any host
  process, including a sub-claude spawned by the task worker.

  This `get_conn()` helper must be preferred over any `docker exec sy_postgres psql`
  in Python scripts used by agents. It is self-contained — it does not depend
  on sy_entities/base.py (which itself uses docker exec for its connections).

Usage:
    from synedre.db import get_conn
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT now()")
        print(cur.fetchone())
    conn.close()

Environment variables (all optional except PG_PASSWORD):
    PG_HOST      — default: localhost
    PG_PORT      — default: 5433  (exposed port of the sy_postgres container)
    PG_USER      — default: claude_pg
    PG_DB        — default: sy_hub
    PG_PASSWORD  — REQUIRED (raises KeyError if missing)

These vars are injected automatically by atlas-spawn-claude.mjs into the env
of every sub-claude spawned by the task worker (except PG_PASSWORD, inherited
via process.env of the cron that starts sy_task_worker.py).
"""

import os
import psycopg2


def get_conn():
    """
    Returns a psycopg2 connection to sy_postgres via TCP localhost:5433.

    Raises:
        KeyError: if PG_PASSWORD is not set in the environment.
        psycopg2.OperationalError: if the TCP connection fails.
    """
    return psycopg2.connect(
        host=os.environ.get('PG_HOST', 'localhost'),
        port=int(os.environ.get('PG_PORT', '5433')),
        user=os.environ.get('PG_USER', 'claude_pg'),
        password=os.environ['PG_PASSWORD'],  # required — raises KeyError if missing
        dbname=os.environ.get('PG_DB', 'sy_hub'),
    )
