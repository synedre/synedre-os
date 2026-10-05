#!/usr/bin/env python3
"""sy_reflex.py — Decentralized reflex facade (settings.json → DB → decision bridge).

Reads a Claude Code hook event from stdin (JSON), loads the active rules from
shyrka.sy_reflex, makes a decision (deny/warn/allow) and logs it into
sy_reflex_audit.

Exit code semantics:
  0 : allow (no reflex triggered, or warn)
  2 : deny  (reflex triggered with action=deny, or fail-closed on a sensitive zone)

Failure handling (3 distinct classes):
  1. Primary DB (sy_reflex) unreachable: TARGETED fail-closed on codemyshop/core/
     (exit 2) ; hors zone sensible → exit 0.
  2. Secondary DB (sy_client codenames) unreachable + fail_mode=closed → exit 2.
     fail_mode=open → exit 0.
  3. Unexpected Python bug (KeyError, etc.) → exit 0 + stderr. A facade bug must
     never block the editing work_order.

Usage (called by the PreToolUse Edit|Write hook):
  echo '<json>' | python3 synedre/sy_reflex.py

"""

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

# ─── DB connection (same pattern as sy_entities/base.py) ───────────────────────

_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_DIR.parent))

try:
    from sy_env import load_env
    load_env()
except Exception:
    pass

PG_CONTAINER = os.environ.get("PG_CONTAINER", "sy_postgres")
PG_DB        = os.environ.get("PG_DB", "sy_hub")
PG_USER      = os.environ.get("PG_USER", "claude_pg")
PG_PASSWORD  = os.environ.get("PG_PASSWORD", "")
PG_SCHEMA    = os.environ.get("PG_SCHEMA", "shyrka")

# Sensitive zones (asymmetry law): any path containing one of these substrings
# triggers fail-closed when the primary DB is unreachable.
# Hardening = add entries here; never remove one without a security review.
_SENSITIVE_PATH_MARKERS: tuple[str, ...] = (
    "codemyshop/core/",   # OSS core — historique
    ".env.host",          # secrets niveau 1 : SSH + root DB + SMTP
    ".env",               # level-2 secrets: global keys (Anthropic, Stripe…)
    "vault/",             # off-repo credentials store
)


# ─── Helpers DB ────────────────────────────────────────────────────────────────

def _run_sql(sql: str, timeout: int = 10) -> str:
    """Runs SQL via docker exec psql. Raises RuntimeError on failure."""
    full_sql = f"SET search_path TO {PG_SCHEMA}, public; {sql}"
    r = subprocess.run(
        [
            "docker", "exec",
            "-e", f"PGPASSWORD={PG_PASSWORD}",
            PG_CONTAINER, "psql",
            "-U", PG_USER, "-d", PG_DB,
            "-tA", "-F\t", "-q", "-c", full_sql,
        ],
        capture_output=True, text=True, timeout=timeout,
    )
    if r.returncode != 0:
        raise RuntimeError(f"psql error: {r.stderr.strip()}")
    return r.stdout.rstrip("\n")


def _run_sql_write(sql: str, timeout: int = 10) -> str:
    """Runs write SQL through a temp file (handles apostrophes/newlines)."""
    full_sql = f"SET search_path TO {PG_SCHEMA}, public;\n{sql}"
    container_path = f"/tmp/_reflex_{os.getpid()}_{uuid.uuid4().hex[:8]}.sql"
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sql", delete=False, encoding="utf-8"
    ) as f:
        f.write(full_sql)
        tmp_path = f.name
    try:
        subprocess.run(
            ["docker", "cp", tmp_path, f"{PG_CONTAINER}:{container_path}"],
            check=True, capture_output=True, timeout=10,
        )
        r = subprocess.run(
            [
                "docker", "exec",
                "-e", f"PGPASSWORD={PG_PASSWORD}",
                PG_CONTAINER, "psql",
                "-U", PG_USER, "-d", PG_DB,
                "-v", "ON_ERROR_STOP=1",
                "-tA", "-F\t", "-q", "-f", container_path,
            ],
            capture_output=True, text=True, timeout=timeout,
        )
        subprocess.run(
            ["docker", "exec", PG_CONTAINER, "rm", "-f", container_path],
            capture_output=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"psql write error: {r.stderr.strip()}")
        return r.stdout
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ─── Business DB functions ──────────────────────────────────────────────────────

def _load_reflexes(event: str) -> list[dict]:
    """Loads the active reflexes EVALUATED by this facade for a given event.

    The `tier='bras'` filter is MANDATORY: only decentralized (Bras) reflexes are
    evaluated here. `tier='tronc'` rows are REGISTRY entries describing survival
    reflexes executed by an external hook file (settings.json) — evaluating them
    here would double-trigger them (and a tronc row without
    path_glob/pattern would fall into the `else: triggered=True` branch → deny in
    general). Raises RuntimeError on failure.
    """
    sql = (
        f"SELECT id_reflex, path_glob, pattern, handler, action, reason, fail_mode, "
        f"tool_matcher "
        f"FROM sy_reflex "
        f"WHERE active=1 AND tier='bras' AND event={_esc(event)};"
    )
    raw = _run_sql(sql)
    rows = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        rows.append({
            "id_reflex":    parts[0],
            "path_glob":    parts[1] if parts[1] != "" else None,
            "pattern":      parts[2] if parts[2] != "" else None,
            "handler":      parts[3] if parts[3] != "" else None,
            "action":       parts[4],
            "reason":       parts[5],
            "fail_mode":    parts[6],
            # tool_matcher (regex on tool_name): '' / absent for legacy reflexes
            "tool_matcher": parts[7] if len(parts) > 7 and parts[7] != "" else None,
        })
    return rows


# PRODUCT / OSS identifiers — NOT client tenants in the sense of the core
# boundary. The tenant-codename guard forbids hardcoding a *client tenant
# codename* inside codemyshop/core/ (OSS sovereignty). But "codemyshop" is
# also the PRODUCT NAME, legitimately present in the canonical license header
# `@author CodeMyShop | @copyright 2026 CodeMyShop` of the WHOLE core, and
# "codemyshop-demo" is the OSS demo instance. Keeping them in the matcher
# (word-boundary IGNORECASE regex) makes "CodeMyShop" match → DENY on every
# new core file. They are therefore excluded from the matcher: fail-closed
# stays intact for real tenants (<TENANT>, <TENANT>-v2, <TENANT>, …).
_PRODUCT_OSS_CODENAMES = frozenset({"codemyshop", "codemyshop-demo"})


# sy_client holds the CLIENT codename (<TENANT>, <TENANT>), not the TENANT
# codename written in code (<TENANT>, <TENANT>-home, <TENANT>-v2): without the
# fleet inventory, “autokur” entered roughly thirty core files without a single
# deny (observed 2026-09-14). The tenant inventory is sy_client_vps.
_CODENAMES_SQL = (
    "SELECT codename FROM sy_client WHERE active=1 "
    "UNION SELECT deploy_codename FROM sy_client_vps "
    "WHERE active=1 AND deploy_codename IS NOT NULL AND deploy_codename <> '';"
)


def _load_codenames() -> list[str]:
    """Loads client (sy_client) and tenant (sy_client_vps) codenames,
    excluding product/OSS identifiers. Raises RuntimeError on failure."""
    raw = _run_sql(_CODENAMES_SQL)
    return sorted({
        c
        for line in raw.splitlines()
        if (c := line.strip()) and c.lower() not in _PRODUCT_OSS_CODENAMES
    })


def _esc(value) -> str:
    """Minimal escaping for SQL literal."""
    if value is None:
        return "NULL"
    s = str(value).replace("'", "''")
    return f"'{s}'"


def _audit_file_fallback(record: dict) -> None:
    """Local JSONL file safety net when the audit DB is unreachable.

    sy_reflex_audit goes through the same DB as the reflexes. In fail-closed
    mode (the DB outage is precisely what triggers the deny), the trace would
    be lost. We then write a JSONL line under reports/ so that the trace of a
    block is NEVER lost. Best-effort, never raises.
    """
    try:
        import json as _json
        from datetime import datetime as _dt, timezone as _tz
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "reports", "sy_reflex_audit_fallback.jsonl",
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        record = dict(record)
        record["ts"] = _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        record["audit_via"] = "file-fallback"
        with open(path, "a", encoding="utf-8") as f:
            f.write(_json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[sy_reflex] audit file-fallback failed: {exc}", file=sys.stderr)


def _log_audit(
    id_reflex, event, tool_name, file_path, decision,
    reason, cwd, session_id, matched_token,
) -> None:
    """Inserts a row into sy_reflex_audit. Best-effort (does not raise).

    If the DB is unreachable, falls back to a local JSONL file safety net
    (debt settled) — the trace of a deny survives a DB outage.
    """
    if os.environ.get("SY_REFLEX_AUDIT_DISABLED") == "1":
        return
    record = {
        "id_reflex": id_reflex, "event": event, "tool_name": tool_name,
        "file_path": file_path, "decision": decision, "reason": reason,
        "cwd": cwd, "session_id": session_id, "matched_token": matched_token,
    }
    try:
        sql = (
            f"INSERT INTO sy_reflex_audit "
            f"(id_reflex, event, tool_name, file_path, decision, reason, "
            f" cwd, session_id, matched_token) "
            f"VALUES ("
            f"{_esc(id_reflex)}, {_esc(event)}, {_esc(tool_name)}, "
            f"{_esc(file_path)}, {_esc(decision)}, {_esc(reason)}, "
            f"{_esc(cwd)}, {_esc(session_id)}, {_esc(matched_token)});"
        )
        _run_sql_write(sql, timeout=8)
    except Exception as exc:
        print(f"[sy_reflex] audit DB failed → file fallback: {exc}", file=sys.stderr)
        _audit_file_fallback(record)


# ─── Logique principale ─────────────────────────────────────────────────────────

def _build_codename_regex(codenames: list[str]) -> re.Pattern:
    """Builds a word-boundary OR regex over all codenames."""
    escaped = [re.escape(c) for c in codenames]
    pattern = r"\b(?:" + "|".join(escaped) + r")\b"
    return re.compile(pattern, re.IGNORECASE)


# ReDoS guard: an armed catastrophic pattern (e.g. `(a+)+$`) would make
# re.search loop → the hook never returns → bricked session. We bound (1) the
# length of the inspected text, (2) the matching time via SIGALRM. On overrun →
# treated as NOT matched (fail-open: a pathological pattern must never block
# the work_order) + stderr trace.
_MAX_MATCH_LEN = 16384          # blast-radius: only the first 16 KB are matched
_REGEX_TIMEOUT_S = 0.25         # matching budget per reflex


class _RegexTimeout(Exception):
    pass


def _safe_search(pattern, text: str, *, compiled: bool = False):
    """re.search bounded in time (SIGALRM) and in length. Returns the match or None.

    fail-open on timeout: None (no trigger) rather than bricking. Always restores
    the previous handler/timer. SIGALRM = single-threaded hook process (safe here).
    """
    if text and len(text) > _MAX_MATCH_LEN:
        text = text[:_MAX_MATCH_LEN]

    def _handler(signum, frame):
        raise _RegexTimeout()

    old = signal.signal(signal.SIGALRM, _handler)
    try:
        signal.setitimer(signal.ITIMER_REAL, _REGEX_TIMEOUT_S)
        try:
            return pattern.search(text) if compiled else re.search(pattern, text)
        except _RegexTimeout:
            print("[sy_reflex] regex timeout (ReDoS guard) → reflex skipped",
                  file=sys.stderr)
            return None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def _extract_content(tool_name: str, tool_input: dict) -> str:
    """Extracts the textual content to inspect depending on the tool type.

    - Write           → the written content
    - Edit/MultiEdit  → the new string
    - Bash            → the command (Bash reflex matching)
    - Read            → the path being read
    - Agent           → the sub-agent prompt
    - WebFetch        → the URL
    - WebSearch       → the query
    """
    if tool_name == "Write":
        return tool_input.get("content", "")
    if tool_name in ("Edit", "MultiEdit"):
        return tool_input.get("new_string", "")
    if tool_name == "Bash":
        return tool_input.get("command", "")
    if tool_name == "Read":
        return tool_input.get("file_path", "")
    if tool_name == "Agent":
        return tool_input.get("prompt", "")
    if tool_name == "WebFetch":
        return tool_input.get("url", "")
    if tool_name == "WebSearch":
        return tool_input.get("query", "")
    return ""


def main() -> int:
    """Main entry point. Returns the exit code."""
    # ── Class 3: global anti-brick envelope ─────────────────────────────────
    try:
        return _run()
    except Exception as exc:
        print(
            f"[sy_reflex] UNEXPECTED ERROR (fail-open-error): {exc}",
            file=sys.stderr,
        )
        # Best-effort audit sans id_reflex
        try:
            _log_audit(
                None, None, None, None,
                "fail-open-error", str(exc), None, None, None,
            )
        except Exception:
            pass
        return 0


def _run() -> int:
    # ── Lecture stdin ───────────────────────────────────────────────────────
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[sy_reflex] stdin parse error: {exc}", file=sys.stderr)
        return 0

    hook_event  = payload.get("hook_event_name", "")
    tool_name   = payload.get("tool_name", "")
    tool_input  = payload.get("tool_input", {})
    cwd         = payload.get("cwd", "")
    session_id  = payload.get("session_id", "")

    # ── Pre-filter: a subject to inspect ─────────────────────────────────────
    # Extended: Edit/Write → file_path, Bash → command,
    # Read → file_path, Agent → prompt, WebFetch → url, WebSearch → query.
    # No identifiable subject → allow (anti-brick).
    file_path = tool_input.get("file_path", "")
    command   = tool_input.get("command", "")
    prompt    = tool_input.get("prompt", "")
    url       = tool_input.get("url", "")
    query     = tool_input.get("query", "")

    # Canonical subject for the audit: first non-empty field.
    # The prompt is truncated (200 chars) to avoid saturating the audit column.
    audit_subject = (
        file_path or command or url or query
        or (prompt[:200] if prompt else "")
    )
    if not audit_subject:
        return 0

    # ── Class 1: load the reflexes (primary DB) ─────────────────────────────
    try:
        reflexes = _load_reflexes(hook_event)
    except Exception as exc:
        # Primary DB unreachable: fail-closed on any sensitive zone
        if any(m in file_path for m in _SENSITIVE_PATH_MARKERS):
            msg = (
                f"[sy_reflex] Primary DB unreachable + sensitive zone "
                f"(file_path={file_path!r}) → DENY (fail-closed). "
                f"Error: {exc}"
            )
            print(msg, file=sys.stderr)
            _log_audit(
                None, hook_event, tool_name, audit_subject,
                "fail-closed", str(exc), cwd, session_id, None,
            )
            return 2
        # Hors zone sensible → laisser passer
        print(
            f"[sy_reflex] Primary DB unreachable (outside sensitive zone) → allow. "
            f"Error: {exc}",
            file=sys.stderr,
        )
        return 0

    # ── Evaluation of candidate reflexes ────────────────────────────────────
    content = _extract_content(tool_name, tool_input)

    for reflex in reflexes:
        # ── Tool filter (tool_matcher = regex on tool_name) ─────────────────
        # Targeted reflex (e.g. 'Bash', 'Edit|Write') → only applies to the
        # matching tools. Legacy reflex (empty/NULL matcher) → historical scope
        # = file edits only, NEVER Bash (zero regression).
        tool_matcher = reflex["tool_matcher"]
        if tool_matcher:
            try:
                if not re.search(tool_matcher, tool_name):
                    continue
            except re.error as exc:
                print(f"[sy_reflex] invalid tool_matcher in reflex "
                      f"{reflex['id_reflex']}: {exc}", file=sys.stderr)
                continue
        elif tool_name not in ("Edit", "Write", "MultiEdit"):
            continue

        path_glob = reflex["path_glob"]
        # path_glob filter: NULL = all; otherwise substring
        if path_glob is not None and path_glob not in file_path:
            continue

        # Candidate reflex — determine the action
        action     = reflex["action"]
        reason     = reflex["reason"]
        fail_mode  = reflex["fail_mode"]
        id_reflex  = reflex["id_reflex"]
        handler    = reflex["handler"]
        pattern    = reflex["pattern"]

        matched_token = None
        triggered     = False

        if handler == "tenant-codename":
            # ── Class 2: load the codenames (secondary DB) ──────────────────
            try:
                codenames = _load_codenames()
            except Exception as exc:
                if fail_mode == "closed":
                    msg = (
                        f"[sy_reflex] Secondary DB (sy_client) unreachable "
                        f"+ fail_mode=closed → DENY. Error: {exc}"
                    )
                    print(msg, file=sys.stderr)
                    _log_audit(
                        id_reflex, hook_event, tool_name, audit_subject,
                        "fail-closed", str(exc), cwd, session_id, None,
                    )
                    return 2
                else:
                    # fail_mode=open : laisser passer
                    print(
                        f"[sy_reflex] Secondary DB unreachable + fail_mode=open → allow. "
                        f"Error: {exc}",
                        file=sys.stderr,
                    )
                    continue

            if not codenames:
                continue

            regex = _build_codename_regex(codenames)
            m = _safe_search(regex, content, compiled=True)
            if m:
                triggered     = True
                matched_token = m.group(0)

        elif pattern is not None:
            # Pure regex-based reflex (no handler) — ReDoS guard active
            try:
                m = _safe_search(pattern, content)
                if m:
                    triggered     = True
                    matched_token = m.group(0)
            except re.error as exc:
                print(
                    f"[sy_reflex] invalid regex in reflex {id_reflex}: {exc}",
                    file=sys.stderr,
                )
                continue
        else:
            # No handler, no pattern: the reflex triggers on path_glob alone
            triggered = True

        if not triggered:
            continue

        # ── Decision ─────────────────────────────────────────────────────────
        _log_audit(
            id_reflex, hook_event, tool_name, audit_subject,
            action, reason, cwd, session_id, matched_token,
        )

        # Human-readable subject depending on the tool type.
        if file_path:
            subject = f"file    : {file_path}"
        elif command:
            subject = f"commande: {command[:160]}"
        elif url:
            subject = f"url     : {url[:160]}"
        elif query:
            subject = f"query   : {query[:160]}"
        else:
            subject = f"prompt  : {(prompt or '')[:160]}"

        if action == "deny":
            print(
                f"[sy_reflex] DENY — {reason}\n"
                f"  {subject}\n"
                f"  token   : {matched_token}",
                file=sys.stderr,
            )
            return 2

        if action == "warn":
            print(
                f"[sy_reflex] WARN — {reason}\n"
                f"  {subject}\n"
                f"  token   : {matched_token}",
                file=sys.stderr,
            )
            # warn → continue (exit 0 au final)

    # No deny reflex triggered
    return 0


if __name__ == "__main__":
    sys.exit(main())
