#!/usr/bin/env python3
"""
sy_logger.py — Mandatory structured logging for all Synedre automates.

Every automate MUST use this module to log its execution.
Logs are persisted as JSON Lines in automation/logs/{nom_automate}/.

Usage in an automate:

    from sy_logger import AutomateLog

    with AutomateLog("sy_coverwatch") as log:
        log.step("scan_db", detail="42 articles scanned")
        result = do_something()
        if result.ok:
            log.step("cover_generated", detail=result.path)
        else:
            log.step("cover_generated", status="error", detail=result.error)

The context manager saves automatically on exit (even when an exception occurs).

Reading the logs:

    python3 synedre/sy_logger.py --report sy_coverwatch        # last run
    python3 synedre/sy_logger.py --report sy_coverwatch --last 5  # last 5
    python3 synedre/sy_logger.py --slow sy_coverwatch          # slow steps (>5s)
    python3 synedre/sy_logger.py --errors                      # errors across all automates
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

LOG_ROOT = Path(__file__).parent / "logs"
LOG_ROOT.mkdir(exist_ok=True)


class AutomateLog:
    """Structured log for an automate run."""

    def __init__(self, automate_name: str, context: dict | None = None):
        self.name = automate_name
        self.log_dir = LOG_ROOT / automate_name
        self.log_dir.mkdir(exist_ok=True)
        self._t0 = time.time()
        self._data: dict[str, Any] = {
            "automate": automate_name,
            "timestamp": datetime.now().isoformat(),
            "env": "prod" if "--prod" in sys.argv else "preprod",
            "steps": [],
            "errors": [],
            "warnings": [],
            "counters": {},
            "duration_s": 0,
            "result": None,
        }
        if context:
            self._data["context"] = context

    def step(self, name: str, status: str = "ok", detail: str = "",
             duration_ms: int = 0) -> None:
        """Record a step. status: ok | error | warning | skip."""
        entry: dict[str, Any] = {
            "name": name,
            "status": status,
            "time": datetime.now().isoformat(),
        }
        if detail:
            entry["detail"] = detail[:500]  # truncate overly long details
        if duration_ms:
            entry["duration_ms"] = duration_ms
        self._data["steps"].append(entry)

        if status == "error":
            self._data["errors"].append(f"{name}: {detail[:200]}")
        elif status == "warning":
            self._data["warnings"].append(f"{name}: {detail[:200]}")

    def timed_step(self, name: str):
        """Context manager to measure the duration of a step.

        Usage:
            with log.timed_step("generate_cover") as s:
                result = generate()
                if not result:
                    s.error("Gemini timeout")
        """
        return _TimedStep(self, name)

    def count(self, key: str, increment: int = 1) -> None:
        """Increment a counter (articles processed, links injected, etc.)."""
        self._data["counters"][key] = self._data["counters"].get(key, 0) + increment

    def set_result(self, result: str, detail: str = "") -> None:
        """Set the final result: ok | error | partial | skip."""
        self._data["result"] = result
        if detail:
            self._data["result_detail"] = detail

    def save(self) -> Path:
        """Persist the log to DB (primary) + file (fallback)."""
        self._data["duration_s"] = round(time.time() - self._t0, 2)
        self._data["step_count"] = len(self._data["steps"])
        self._data["error_count"] = len(self._data["errors"])
        self._data["warning_count"] = len(self._data["warnings"])
        if self._data["result"] is None:
            self._data["result"] = "error" if self._data["errors"] else "ok"

        # DB (source of truth)
        self._save_to_db()

        # Push to /hub/errors observability if the run failed
        # (Phase 3 — front+back+automates error unification)
        if self._data["result"] in ("error", "exception"):
            self._save_to_cs_server_errors()

        # JSONL file (fallback + CLI --report compatibility)
        date_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        log_file = self.log_dir / f"{date_str}.jsonl"
        with open(log_file, "w") as f:
            f.write(json.dumps(self._data, ensure_ascii=False) + "\n")
        return log_file

    def _save_to_cs_server_errors(self) -> None:
        """Push the run failure into cs_server_errors (PG shyrka) for
        the error to appear in /hub/errors with source='python_automate'.

        Best-effort: silent fallback. The JSONL file remains the source
        of truth for the detailed log; cs_server_errors is just the UI-side
        triage index.

        Conventions :
          - tenant       = 'sy-hub' (Python automates run on the shyrka side)
          - source       = 'python_automate'
          - current_url  = '/automate/{nom_automate}' (for grouping)
          - status       = 500 (server error by convention)
          - exception_type    = type Python ou 'AutomateError'
          - exception_message = first error message of the run (truncated to 1000 chars)
          - stack_trace_raw   = pretty JSON of errors[] + counters{} for
                                  quick context without having to grep the JSONL
        """
        import subprocess
        try:
            errors_list = self._data.get("errors", []) or ["(result=error without an explicit message)"]
            first_error = errors_list[0]
            # Extract the exception type if present (format "exception_name: ExceptionType: msg")
            exc_type = "AutomateError"
            if ": " in first_error:
                # Step "exception" stocke "exception: ExcType: msg"
                parts = first_error.split(": ", 2)
                if len(parts) >= 2 and parts[0] == "exception":
                    exc_type = parts[1]
                elif len(parts) >= 2:
                    exc_type = parts[0]
            exc_msg = first_error[:1000]
            stack_payload = json.dumps({
                "errors": errors_list,
                "warnings": self._data.get("warnings", []),
                "counters": self._data.get("counters", {}),
                "result": self._data.get("result"),
                "result_detail": self._data.get("result_detail", ""),
                "duration_s": self._data.get("duration_s", 0),
            }, ensure_ascii=False, indent=2)[:8000]

            pg_password = os.environ.get("PG_PASSWORD", "")
            if not pg_password:
                return
            # direct docker exec — psql via stdin to avoid SQL escaping of
            # error messages (they may contain quotes).
            sql = """
                SET search_path TO shyrka;
                INSERT INTO cs_server_errors
                  (tenant, source, method, current_url, status,
                   exception_type, exception_message, stack_trace_raw)
                VALUES
                  ('sy-hub', 'python_automate', NULL, $cu$/automate/{name}$cu$, 500,
                   $et${exc_type}$et$, $em${exc_msg}$em$, $st${stack}$st$);
            """.format(
                name=self.name.replace("$", "_"),
                exc_type=exc_type.replace("$", "_"),
                exc_msg=exc_msg.replace("$", "_"),
                stack=stack_payload.replace("$", "_"),
            )
            subprocess.run(
                ["docker", "exec", "-i", "-e", f"PGPASSWORD={pg_password}",
                 "sy_postgres", "psql", "-U", "claude_pg", "-d", "sy_hub", "-q"],
                input=sql.encode("utf-8"),
                capture_output=True, timeout=5, check=False,
            )
        except Exception:
            pass  # silent — the JSONL keeps the detailed trace

    def _save_to_db(self) -> None:
        """Insert the log into sy_automate_logs (PG — post-MariaDB)."""
        try:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).resolve().parent))
            import sy_hook_pg
            conn = sy_hook_pg.connect(timeout=3, autocommit=True)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO sy_automate_logs "
                "(automate, env, result, duration_s, step_count, error_count, "
                " warning_count, counters, steps, errors, warnings, "
                " result_detail, context, date_add) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    self._data["automate"],
                    self._data.get("env", "preprod"),
                    self._data.get("result"),
                    self._data.get("duration_s", 0),
                    self._data.get("step_count", 0),
                    self._data.get("error_count", 0),
                    self._data.get("warning_count", 0),
                    json.dumps(self._data.get("counters", {}), ensure_ascii=False),
                    json.dumps(self._data.get("steps", []), ensure_ascii=False),
                    json.dumps(self._data.get("errors", []), ensure_ascii=False),
                    json.dumps(self._data.get("warnings", []), ensure_ascii=False),
                    self._data.get("result_detail", ""),
                    json.dumps(self._data.get("context"), ensure_ascii=False) if self._data.get("context") else None,
                    self._data["timestamp"],
                )
            )
            conn.close()
        except Exception:
            pass  # file fallback ensures persistence

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            # SystemExit (whatever the code) = a deliberate decision by the
            # script, not a crash. Many audits use exit != 0 to report
            # findings (e.g. pageaudit exit 1 = a11y violations detected).
            # The cron wrapper keeps the exit-code classification; the
            # logger reflects the business state the script wrote in its
            # own steps.
            # Only real Python exceptions (KeyError, etc.) are surfaced
            # as "exception".
            if exc_type is not SystemExit and not issubclass(exc_type, KeyboardInterrupt):
                self.step("exception", status="error",
                           detail=f"{exc_type.__name__}: {exc_val}")
                self._data["result"] = "exception"
        self.save()
        return False  # do not swallow the exception


class _TimedStep:
    """Helper for timed_step()."""

    def __init__(self, log: AutomateLog, name: str):
        self._log = log
        self._name = name
        self._status = "ok"
        self._detail = ""

    def error(self, detail: str = "") -> None:
        self._status = "error"
        self._detail = detail

    def warning(self, detail: str = "") -> None:
        self._status = "warning"
        self._detail = detail

    def __enter__(self):
        self._t0 = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        ms = int((time.time() - self._t0) * 1000)
        if exc_type and self._status == "ok":
            self._status = "error"
            self._detail = f"{exc_type.__name__}: {exc_val}"
        self._log.step(self._name, status=self._status,
                       detail=self._detail, duration_ms=ms)
        return False


# ── CLI: reading and analyzing the logs ───────────────────────────────────────

def _read_logs(automate: str, last: int = 1) -> list[dict]:
    """Read the last N logs of an automate."""
    log_dir = LOG_ROOT / automate
    if not log_dir.exists():
        return []
    files = sorted(log_dir.glob("*.jsonl"), reverse=True)[:last]
    logs = []
    for f in files:
        for line in f.read_text().strip().splitlines():
            try:
                logs.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return logs


def _report(automate: str, last: int = 1) -> None:
    """Print a readable report of the latest runs."""
    logs = _read_logs(automate, last)
    if not logs:
        print(f"No logs for {automate}")
        return

    for log in logs:
        ts = log.get("timestamp", "?")
        dur = log.get("duration_s", 0)
        result = log.get("result", "?")
        errors = log.get("error_count", 0)
        warnings = log.get("warning_count", 0)
        steps = log.get("step_count", 0)
        counters = log.get("counters", {})

        status_icon = "✓" if result == "ok" else "✗" if result == "error" else "⚠"
        print(f"\n{status_icon} {automate} — {ts} — {dur}s — {result}")
        print(f"  {steps} steps | {errors} errors | {warnings} warnings")

        if counters:
            print(f"  Compteurs : {json.dumps(counters, ensure_ascii=False)}")

        if errors:
            print(f"  ERRORS:")
            for e in log.get("errors", []):
                print(f"    ✗ {e}")

        if warnings:
            print(f"  WARNINGS :")
            for w in log.get("warnings", []):
                print(f"    ⚠ {w}")

        # Slow steps (>5s)
        slow = [s for s in log.get("steps", []) if s.get("duration_ms", 0) > 5000]
        if slow:
            print(f"  LENTES (>5s) :")
            for s in slow:
                print(f"    🐌 {s['name']} — {s['duration_ms']}ms — {s.get('detail', '')}")


def _report_slow(automate: str, threshold_ms: int = 5000) -> None:
    """List slow steps over the last 10 runs."""
    logs = _read_logs(automate, last=10)
    slow_steps: list[tuple[str, str, int]] = []
    for log in logs:
        ts = log.get("timestamp", "?")[:19]
        for s in log.get("steps", []):
            if s.get("duration_ms", 0) > threshold_ms:
                slow_steps.append((ts, s["name"], s["duration_ms"]))

    if not slow_steps:
        print(f"No slow steps (>{threshold_ms}ms) for {automate}")
        return

    print(f"\n🐌 Slow steps for {automate} (>{threshold_ms}ms):")
    for ts, name, ms in sorted(slow_steps, key=lambda x: -x[2]):
        print(f"  {ts} | {name:30s} | {ms:>7d}ms")


def _report_all_errors(fresh_days: int = 7) -> None:
    """List the errors of all automates (latest run of each).

    Only surfaces errors whose latest run is < `fresh_days` days old.
    A manual tool (e.g. sy_component_check) whose latest run dates
    from 15 days ago is not a "current error" to watch.
    """
    if not LOG_ROOT.exists():
        print("No logs")
        return

    cutoff = datetime.now() - timedelta(days=fresh_days)
    has_errors = False
    for d in sorted(LOG_ROOT.iterdir()):
        if not d.is_dir():
            continue
        logs = _read_logs(d.name, last=1)
        for log in logs:
            if not log.get("errors"):
                continue
            ts_str = log.get("timestamp", "")
            try:
                ts_dt = datetime.fromisoformat(ts_str[:19])
            except ValueError:
                continue
            if ts_dt < cutoff:
                continue
            has_errors = True
            print(f"\n✗ {d.name} — {ts_str[:19]}")
            for e in log["errors"]:
                print(f"    {e}")

    if not has_errors:
        print("✓ No errors on the latest run of any automate")


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--errors" in args:
        _report_all_errors()
    elif "--report" in args:
        idx = args.index("--report")
        name = args[idx + 1] if idx + 1 < len(args) else ""
        last = 1
        if "--last" in args:
            li = args.index("--last")
            last = int(args[li + 1]) if li + 1 < len(args) else 5
        _report(name, last)
    elif "--slow" in args:
        idx = args.index("--slow")
        name = args[idx + 1] if idx + 1 < len(args) else ""
        _report_slow(name)
    else:
        print(__doc__)
