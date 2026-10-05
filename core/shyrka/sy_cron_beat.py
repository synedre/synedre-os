#!/usr/bin/env python3
"""
sy_cron_beat.py — Heartbeat of supervised cron scripts.
Part of the cron dead-man supervision.

Writes `sy_cron_heartbeat.last_beat_at` to prove that a cron script ACTUALLY
ran. Read by `synedre/sy_cron_deadman.py`, which declares dead any script
whose silence exceeds its `max_silence_s`.

    from sy_cron_beat import beat, beating

    beat("sy_whatsapp_to_<TENANT>")                      # forme minimale
    beat("sy_x", status="fail", duration_ms=1234)      # full form

    with beating("sy_x"):                              # recommended form
        run_once()                                     # beats 'ok', or 'fail' if it raises

HARD CONSTRAINT — the beat lives INSIDE the script, NEVER in the crontab line.
A `; beat` appended to the cron command would have reported "alive" even
though python never ran: the line sourced `.env.host` in shell, the `.` failed
(dash, file absent from cron's cwd) and the `&&` broke the chain BEFORE the
redirection. Cron did fire; the script did not. The beat must prove that the
SCRIPT ran, not that cron fired.

FAIL-OPEN — a failing beat (DB down, docker stopped) must NEVER take down the
business script: supervision is an observer, not a dependency. Any error goes
to stderr and the function returns. Accepted corollary: if the DB is dead,
nobody beats anymore and the detector will scream about a mass cron die-off
— that is the intended behavior: a dead DB IS an outage.

NO SELF-REGISTRATION — `beat()` does an UPDATE, never an INSERT. A script
unknown to the registry would otherwise invent its own thresholds (`expected_interval_s`,
`max_silence_s`), and the detector would supervise with magic values.
Registration is a deliberate act: the registry declares what is monitored.
An unregistered beat warns on stderr instead of vanishing silently.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from time import monotonic

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sy_env import load_env  # noqa: E402
from sy_entity_base import _esc, DB_NAME, _run_sql_write  # noqa: E402

load_env()

VALID_STATUS = ("ok", "fail")


def beat(script_name: str, status: str = "ok", duration_ms: int | None = None) -> bool:
    """Record a heartbeat. Returns True if the script is registered and was stamped.

    NEVER raises (fail-open). Returns False if the script is not in the registry, if
    the arguments are invalid, or if the DB is unreachable.
    """
    try:
        if not script_name or not isinstance(script_name, str):
            print("[sy_cron_beat] empty or invalid script_name — beat ignored",
                  file=sys.stderr)
            return False
        if status not in VALID_STATUS:
            # Do not let it through: the column has a CHECK, the UPDATE would fail
            # in the DB and fail-open would swallow the error — the script would look dead.
            print(f"[sy_cron_beat] invalid status {status!r} (expected {VALID_STATUS}) "
                  f"— beat ignored for {script_name}", file=sys.stderr)
            return False

        # _esc() returns the value ALREADY wrapped in quotes (and None -> NULL, int -> str).
        # Never re-quote it: `'{_esc(x)}'` produces ''x'' and breaks the SQL.
        dur: int | None = None
        if duration_ms is not None:
            try:
                dur = max(0, int(duration_ms))
            except (TypeError, ValueError):
                dur = None  # garbage duration = no duration; never a reason not to beat

        # `fail_since` = the start of the current FAILURE SERIES, not this failure:
        # keep the first value (COALESCE) while it is failing, then clear it once it
        # returns to 'ok'. The column is therefore NULL precisely when the last
        # beat succeeded — allowing the deadman to distinguish an isolated failure
        # from an established outage without a counter or arbitrary threshold.
        out = _run_sql_write(
            f"UPDATE {DB_NAME}.sy_cron_heartbeat "
            f"   SET last_beat_at = now(), "
            f"       last_status = {_esc(status)}, "
            f"       fail_since = CASE WHEN {_esc(status)} = 'fail' "
            f"                         THEN COALESCE(fail_since, now()) END, "
            f"       last_duration_ms = {_esc(dur)} "
            f" WHERE script_name = {_esc(script_name)} "
            f"RETURNING script_name;"
        )
        if not (out or "").strip():
            print(f"[sy_cron_beat] {script_name} is NOT in the "
                  f"sy_cron_heartbeat registry — beat lost, nobody is watching it. "
                  f"Register it (explicit expected_interval_s + max_silence_s).",
                  file=sys.stderr)
            return False
        return True
    except Exception as e:  # strict fail-open: supervision never kills the business logic
        print(f"[sy_cron_beat] beat failed for {script_name}: {e}", file=sys.stderr)
        return False


def beat_main(script_name: str, main_fn) -> int:
    """Run `main()` and beat, mapping its RETURN CODE to the status.

    Call form for in-house crons, where all expose `main() -> int` (0 = ok):

        if __name__ == "__main__":
            sys.exit(beat_main("sy_x", main))

    `beating()` does NOT fit here: it only sees exceptions, while these scripts
    report failure with `return 1` without raising. The script would beat 'ok'
    while failing — it would look healthy. Trap found while wiring the 3 WhatsApp
    crons.

    `main()` returning None = success (`sys.exit(None)` -> 0 convention). An
    exception leaves rc=1 (hence 'fail') and is ALWAYS re-raised.
    """
    rc = 1
    t0 = monotonic()
    try:
        r = main_fn()
        rc = 0 if r is None else int(r)
        return rc
    finally:
        beat(script_name, status="ok" if rc == 0 else "fail",
             duration_ms=int((monotonic() - t0) * 1000))


@contextmanager
def beating(script_name: str):
    """Automatically beats on exit, on ALL paths — success and exception alike.

    Recommended form: "beat on every exit path" is exactly the
    kind of discipline that gets forgotten on the error branch, and a script that
    crashes without beating would be counted as dead while it did run (two
    distinct failures not to confuse: `fail` = it ran and ended badly; silence =
    it did not run at all).

    The original exception is ALWAYS re-raised: this handler observes, it
    swallows nothing.
    """
    t0 = monotonic()
    status = "ok"
    try:
        yield
    except BaseException:
        status = "fail"
        raise
    finally:
        beat(script_name, status=status,
             duration_ms=int((monotonic() - t0) * 1000))
