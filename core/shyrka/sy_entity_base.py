"""
sy_entity_base — Generic Entity class.

Implements CRUD and the validation pipeline for the sy_* tables.
Child classes override `validate()` with the business rules.

Pattern d'utilisation :
    from sy_entities.dictionary import DictionaryEntity, ValidationError
    dico = DictionaryEntity()
    try:
        new_id = dico.create({'slug': 'foo', 'word': 'Foo', ...})
    except ValidationError as e:
        print(e.errors, e.warnings)

Ported from MariaDB to PostgreSQL.
Hits `sy_postgres` (schema `shyrka`) via subprocess `psql`.

"""

import os
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sy_env import load_env  # noqa: E402

load_env()


# ─── Connexion DB (subprocess docker exec psql) ─────────────────────────────

PG_CONTAINER = os.environ.get("PG_CONTAINER", "sy_postgres")
PG_DB = os.environ.get("PG_DB", "sy_hub")
PG_USER = os.environ.get("PG_USER", "claude_pg")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "")
PG_SCHEMA = os.environ.get("PG_SCHEMA", "shyrka")

# Backward-compat alias — entities still import DB_NAME as the table
# prefix. In PG this prefix is the schema (shyrka).
DB_NAME = PG_SCHEMA

# psycopg2 pool cutover: ON by default. Each facade tries the pool
# (127.0.0.1:5433, byte-identical output proven) and falls back to docker-exec-psql
# on ANY exception → full parity + resilience (never break the fleet's DB access).
# Kill-switch: SY_ENTITY_PG_POOL=0.
_USE_POOL = os.environ.get("SY_ENTITY_PG_POOL", "1") != "0"


class ValidationError(Exception):
    """Raised when an entity fails validation."""

    def __init__(self, errors: list[str], warnings: list[str] | None = None):
        self.errors = errors
        self.warnings = warnings or []
        super().__init__(" | ".join(errors))


def _esc(value) -> str:
    """SQL escaping for literal insertion into a PostgreSQL SQL string.

    ONLY the single quote is escaped (`''`). Backslashes are NOT escaped: PG runs
    with `standard_conforming_strings = on` (verified), so a backslash in a literal
    is ALREADY literal — `'a\\b'` is a\\b, 4 characters.

    The old `.replace("\\", "\\\\")` was a MariaDB reflex (where the backslash IS
    an escape character). MariaDB has since been dropped; from then on, this line
    ADDED a backslash instead of protecting one, and silently corrupted any value
    containing one. A measured round-trip: JSON with quotes +2 characters,
    Windows path +3, regex +2 — 3 out of 5 cases broken.

    Measured damage: 17 of the 212 work_orders had an unreadable `discoveries_json`
    (JSON escapes its quotes as `\"`, which the doubling turned into `\\"`). The
    column being TEXT, PG validated nothing: the corruption went through silently.

    Lesson learned (a guardrail
    installed is not a guardrail that bites).
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        # PG strict bool: `TRUE`/`FALSE` rather than `1`/`0` (a BOOLEAN
        # column rejects an INSERT with int 1). PG implicitly casts
        # `TRUE`→`1` on the legacy smallint side (sy_client_vps), so 100% retro-compat.
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    s = str(value).replace("'", "''")
    return f"'{s}'"


def _qualify(table: str) -> str:
    """Qualifies a table with the PG schema."""
    if "." in table:
        return table  # already qualified
    return f"{PG_SCHEMA}.{table}"


def _dedup_day() -> str:
    """UTC day bucket (YYYYMMDD) for NON-AUTO dedup signatures.

    The 24h window is encoded IN the signature (`<key>:<day>@<agent>`) rather
    qu'en gaps-and-islands applicatif : l'UPSERT existant (ON CONFLICT
    dup_signature) then merges the occurrences of a same day and preserves
    cross-day recurrence (cf. the NON-AUTO scar dedup run).

    UTC to align runtime and backfill (`to_char(date_add AT TIME ZONE 'UTC',
    'YYYYMMDD')`) — the cross-midnight cut of a night session falls in gap<7d →
    classified BURST by the sensor, outside the recurrence metric.
    """
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _bind(sql: str, params) -> str:
    """Renders `params` into `sql` through `sy_db.mogrify` — a real driver's quoting.

    This replaces `_esc()`: with bound parameters, escaping is no longer a concern.
    `params=None` leaves SQL unchanged, so hundreds of legacy callers change not one
    character — the debt is repaid file by file, without a big bang in the foundation.

    ⚠️ `%`: without `params`, SQL is sent AS IS; with parameters, every literal `%`
    must be doubled (`LIKE '%%x%%'`), otherwise mogrify interprets it as a placeholder.
    """
    if not params:
        return sql
    from sy_db import mogrify  # noqa: PLC0415 — lazy: no I/O at import time (scar #370)
    return mogrify(sql, params)


def _run_sql_write(sql: str, params: tuple | list | None = None) -> str:
    """Executes write SQL via a stdin file (handles apostrophes/newlines).

    `params` (optional) goes through `_bind`: bound values, nothing left to escape.

    Prepends `SET search_path TO shyrka;` for unqualified queries
    (safety — the _qualify() helpers already qualify everything).

    Container file name made
    unique per pid+uuid to support concurrent multi-process. Before this
    fix, 5 parallel Python sessions were all writing to /tmp/_entity.sql
    (shared container path) → race: worker A copies its file, worker B
    overwrites, worker A execs and reads B's file → INSERT silently
    lost, parallel multi-jobsite S3 broken.
    """
    full_sql = f"SET search_path TO {PG_SCHEMA}, public;\n{_bind(sql, params)}"
    if _USE_POOL:
        try:
            from synedre.sy_pg_pool import pool_write
            return pool_write(full_sql)
        except Exception:  # noqa: BLE001 — docker fallback (parity + resilience)
            pass
    import uuid as _uuid
    container_path = f"/tmp/_entity_{os.getpid()}_{_uuid.uuid4().hex[:8]}.sql"
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sql", delete=False, encoding="utf-8"
    ) as f:
        f.write(full_sql)
        tmp_path = f.name
    try:
        # Copy into the container then exec psql (per-process unique path)
        subprocess.run(
            ["docker", "cp", tmp_path, f"{PG_CONTAINER}:{container_path}"],
            check=True, capture_output=True,
        )
        r = subprocess.run(
            ["docker", "exec", "-e", f"PGPASSWORD={PG_PASSWORD}",
             PG_CONTAINER, "psql", "-U", PG_USER, "-d", PG_DB,
             "-v", "ON_ERROR_STOP=1",
             "-tA", "-F\t", "-q", "-f", container_path],
            capture_output=True, text=True, timeout=30,
        )
        subprocess.run(
            ["docker", "exec", PG_CONTAINER, "rm", "-f", container_path],
            capture_output=True,
        )
        if r.returncode != 0 or "ERROR:" in (r.stderr or ""):
            raise RuntimeError(f"SQL write failed: {r.stderr or r.stdout}")
        return r.stdout
    finally:
        os.unlink(tmp_path)


def _run_sql_read(sql: str, params: tuple | list | None = None) -> str:
    """Executes read SQL via psql.

    `params` (optional) goes through `_bind`: bound values, nothing left to escape.

    Tab-separated tuple-only output (-tA -F$'\\t') for compat with
    the legacy code that parses lines via .split('\\t').

    ⚠️ Do not use for TEXT columns that may contain newlines
    (current_task, next_action, description…): the split on \\n breaks the
    parsing. Use _run_sql_csv() instead.
    """
    full_sql = f"SET search_path TO {PG_SCHEMA}, public; {_bind(sql, params)}"
    if _USE_POOL:
        try:
            from synedre.sy_pg_pool import pool_read
            return pool_read(full_sql)
        except Exception:  # noqa: BLE001 — docker fallback (parity + resilience)
            pass
    r = subprocess.run(
        ["docker", "exec", "-e", f"PGPASSWORD={PG_PASSWORD}",
         PG_CONTAINER, "psql", "-U", PG_USER, "-d", PG_DB,
         "-tA", "-F\t", "-q", "-c", full_sql],
        capture_output=True, text=True, timeout=15,
    )
    if r.returncode != 0:
        raise RuntimeError(f"SQL read failed: {r.stderr}")
    # rstrip("\n") only: .strip() would eat the trailing \t
    # when the last column is NULL (cf. sy_invoicing).
    return r.stdout.rstrip("\n")


def _run_sql_csv(sql: str, params: tuple | list | None = None) -> list[list[str]]:
    """Executes read SQL, returns the parsed rows (CSV mode).

    `params` (optional) goes through `_bind`: bound values, nothing left to escape.

    Unlike _run_sql_read, correctly handles TEXT columns
    containing newlines via CSV quoting (RFC 4180). Bug fix
    jobsite-doctrine-v2 #151 : ChantierEntity._select_full retournait []
    for work_orders whose next_action contained a line break.

    NULL is returned as an empty string. The caller must re-map '' → None
    if it needs to distinguish NULL from an empty string.
    """
    import csv
    import io
    full_sql = f"SET search_path TO {PG_SCHEMA}, public; {_bind(sql, params)}"
    if _USE_POOL:
        try:
            from synedre.sy_pg_pool import pool_csv
            return pool_csv(full_sql)
        except Exception:  # noqa: BLE001 — docker fallback (parity + resilience)
            pass
    r = subprocess.run(
        ["docker", "exec", "-e", f"PGPASSWORD={PG_PASSWORD}",
         PG_CONTAINER, "psql", "-U", PG_USER, "-d", PG_DB,
         "-A", "--csv", "-t", "-q", "-c", full_sql],
        capture_output=True, text=True, timeout=15,
    )
    if r.returncode != 0:
        raise RuntimeError(f"SQL csv read failed: {r.stderr}")
    reader = csv.reader(io.StringIO(r.stdout))
    return [row for row in reader if row]


# ─── Entity class ───────────────────────────────────────────────────────────

class Entity:
    """Base class. Subclass with table, pk, and a validate() override."""

    table: str = ""
    pk: str = ""
    canonical_client: str = "sy-hub"  # always sy-hub
    fields: tuple = ()  # Whitelist of columns accepted for INSERT/UPDATE

    # ── Validation (to override) ────────────────────────────────────────

    def validate(self, data: dict, mode: str = "create") -> list[str]:
        """Validates the data. Returns warnings (non-blocking).
        Raises ValidationError on blocking errors."""
        return []

    # ── Helpers DB ──────────────────────────────────────────────────────

    def exists(self, **filters) -> bool:
        if not filters:
            return False
        where = " AND ".join(f"{k}={_esc(v)}" for k, v in filters.items())
        out = _run_sql_read(
            f"SELECT 1 FROM {_qualify(self.table)} WHERE {where} LIMIT 1;"
        )
        return bool(out)

    def find_one(self, **filters) -> dict | None:
        results = self.find(**filters)
        return results[0] if results else None

    def find(self, **filters) -> list[dict]:
        where = ""
        if filters:
            where = "WHERE " + " AND ".join(
                f"{k}={_esc(v)}" for k, v in filters.items()
            )
        # Includes self.pk in addition to self.fields so callers always
        # get the identifier back (otherwise id_task=None on the Python side).
        col_list = list(self.fields)
        if self.pk and self.pk not in col_list:
            col_list = [self.pk] + col_list
        cols = ",".join(col_list) if col_list else "*"
        # Use _run_sql_csv instead of _run_sql_read to support multi-line TEXT columns
        # natively, without corrupting/truncating dictionaries
        # (backlog #368, scar 2026-07-17).
        raw_rows = _run_sql_csv(
            f"SELECT {cols} FROM {_qualify(self.table)} {where};"
        )
        return [dict(zip(col_list, cells)) for cells in raw_rows]


    # ── CRUD ─────────────────────────────────────────────────────────────

    def create(self, data: dict, dry_run: bool = False) -> int | None:
        warnings = self.validate(data, mode="create")
        # Force the canonical client_id
        if "client_id" in self.fields:
            data["client_id"] = self.canonical_client

        if dry_run:
            return None

        # Filter on the whitelisted columns
        clean = {k: v for k, v in data.items() if k in self.fields}
        cols = ",".join(clean.keys())
        vals = ",".join(_esc(v) for v in clean.values())
        # PG : RETURNING en ligne (remplace LAST_INSERT_ID() MariaDB)
        sql = (
            f"INSERT INTO {_qualify(self.table)} "
            f"({cols}, date_add, date_upd) VALUES ({vals}, NOW(), NOW()) "
            f"RETURNING {self.pk};"
        )
        out = _run_sql_write(sql)
        # Fetch the inserted ID (first non-empty line of the result)
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("INSERT"):
                continue
            try:
                return int(line)
            except ValueError:
                continue
        return None

    def update(self, pk_value: int, data: dict) -> None:
        warnings = self.validate(data, mode="update")
        clean = {k: v for k, v in data.items() if k in self.fields}
        if not clean:
            return
        sets = ", ".join(f"{k}={_esc(v)}" for k, v in clean.items())
        sql = (
            f"UPDATE {_qualify(self.table)} SET {sets}, date_upd=NOW() "
            f"WHERE {self.pk}={_esc(pk_value)};"
        )
        _run_sql_write(sql)

    def delete(self, pk_value: int) -> None:
        sql = f"DELETE FROM {_qualify(self.table)} WHERE {self.pk}={_esc(pk_value)};"
        _run_sql_write(sql)
