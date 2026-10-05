#!/usr/bin/env python3
"""
sy_session_start.py — Automatic Phase 0 checks at Synedre session startup.

Runs sequentially: automation errors, cron verification, git status,
log freshness, calendar reminder, and P0 inbox scan.

Infrastructure health belongs to the `/status` skill, not here (see the
removed `check_healthcheck` block below).

Usage :
    python3 synedre/sy_session_start.py
"""

import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Absolute paths based on the script location
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

sys.path.insert(0, str(SCRIPT_DIR))
from sy_logger import AutomateLog

# Calendrier hebdomadaire (lundi=0 … dimanche=6)
WEEKLY_CALENDAR = {
    0: ("PRODUCT", "Code, features, modules, bugs"),
    1: ("CLIENTS", "Calls, pipeline, leads, email"),
    2: ("CONTENT", "Blog, docs, tutorials"),
    3: ("INFRA & SECURITY", "Deploy, audit, hardening"),
    4: ("STRATEGY & ADMIN", "Roadmap, legal, accounting"),
    5: ("WATCH", "Trends, competition"),
    6: ("REST", "No active agent"),
}

# Critical logs to watch (file name without extension)
KEY_LOGS = ["coverwatch.log", "reactor.log", "inbox.log", "backup.log"]

FRESHNESS_HOURS = 24


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 30) -> tuple[int, str]:
    """Runs a command and returns (returncode, output)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode, output
    except subprocess.TimeoutExpired:
        return 1, f"TIMEOUT ({timeout}s)"
    except FileNotFoundError:
        return 1, f"Command not found: {cmd[0]}"


# `check_healthcheck` was removed: `sy_healthcheck.py` was DELIBERATELY
# deleted on 2026-05-03 (e925b92eb, “batch dead archive Tier B1”), because
# nobody read its cron.log and the `/status` skill
# (.claude/skills/status/SKILL.md) invokes the work order directly via
# docker/curl/git. The call outlived its target: its preflight made it
# audible, but it emitted a warning at EVERY session — a permanent “partial”
# summary under which a real warning went unnoticed.
# A warning nobody can clear eventually warns about nothing.


def check_automate_errors(log: AutomateLog) -> str:
    """Runs sy_logger.py --errors to list automation errors."""
    with log.timed_step("automate_errors") as s:
        script = str(SCRIPT_DIR / "sy_logger.py")
        code, output = _run(["python3", script, "--errors"], cwd=str(PROJECT_ROOT), timeout=30)
        if code != 0:
            s.error(f"Exit code {code}")
        return output[:500] if output else "(no output)"


def check_crons(log: AutomateLog) -> str:
    """Checks that the files referenced in the crontab exist."""
    with log.timed_step("cron_check") as s:
        code, output = _run(["crontab", "-l"], timeout=30)
        if code != 0:
            s.warning("Impossible de lire crontab")
            return "[WARNING] crontab inaccessible"

        lines = output.splitlines()
        missing = []
        checked = 0
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Look for Python/shell file paths in the line
            parts = line.split()
            for part in parts:
                if part.endswith(".py") or part.endswith(".sh"):
                    # Resolve environment variables ($HUB, etc.)
                    resolved = os.path.expandvars(part)
                    # If the variable is not resolved, try PROJECT_ROOT
                    if "$" in resolved:
                        # Undefined variable — replace $HUB with PROJECT_ROOT
                        resolved = resolved.replace("$HUB", str(PROJECT_ROOT))
                        resolved = resolved.replace("${HUB}", str(PROJECT_ROOT))
                    p = Path(resolved)
                    if not p.is_absolute():
                        p = PROJECT_ROOT / resolved
                    if not p.exists():
                        missing.append(part)
                    checked += 1

        if missing:
            detail = f"{checked} scripts checked, {len(missing)} missing: {', '.join(missing[:5])}"
            s.warning(detail)
            return detail
        else:
            detail = f"{checked} scripts checked, all present"
            return detail


def check_git_status(log: AutomateLog) -> str:
    """Shows uncommitted changes."""
    with log.timed_step("git_status") as s:
        code, output = _run(["git", "status", "--short"], cwd=str(PROJECT_ROOT), timeout=30)
        if code != 0:
            s.error("git status failed")
            return "[ERROR] git status failed"
        if not output:
            return "Working tree propre"
        count = len(output.splitlines())
        detail = f"{count} modified file(s)"
        if count > 0:
            s.warning(detail)
        return f"{detail}\n{output[:400]}"


def check_logs_freshness(log: AutomateLog) -> str:
    """Checks that the critical logs were modified within the last 24h."""
    with log.timed_step("logs_freshness") as s:
        now = datetime.now()
        threshold = now - timedelta(hours=FRESHNESS_HOURS)
        results = []
        stale_count = 0

        for log_name in KEY_LOGS:
            log_path = SCRIPT_DIR / log_name
            if not log_path.exists():
                results.append(f"  {log_name}: ABSENT")
                stale_count += 1
                continue
            mtime = datetime.fromtimestamp(log_path.stat().st_mtime)
            age_h = (now - mtime).total_seconds() / 3600
            if mtime < threshold:
                results.append(f"  {log_name}: STALE ({age_h:.0f}h)")
                stale_count += 1
            else:
                results.append(f"  {log_name}: OK ({age_h:.0f}h)")

        if stale_count > 0:
            s.warning(f"{stale_count}/{len(KEY_LOGS)} logs stale or missing")

        return "\n".join(results)


def check_calendar(log: AutomateLog) -> str:
    """Recalls the day's focus according to the weekly calendar."""
    with log.timed_step("calendar_reminder") as s:
        weekday = datetime.now().weekday()
        focus, detail = WEEKLY_CALENDAR[weekday]
        day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][weekday]
        return f"{day_name} — {focus}\n  {detail}"


def check_client_bugs(log: AutomateLog) -> str:
    """Scans the last 5 lines of inbox.log for P0 alerts."""
    with log.timed_step("client_bugs") as s:
        inbox_log = SCRIPT_DIR / "inbox.log"
        if not inbox_log.exists():
            s.warning("inbox.log introuvable")
            return "[WARNING] inbox.log introuvable"

        try:
            lines = inbox_log.read_text().strip().splitlines()
        except Exception as e:
            s.error(str(e))
            return f"[ERROR] Lecture inbox.log : {e}"

        last_lines = lines[-5:] if len(lines) >= 5 else lines
        p0_lines = [l for l in last_lines if "P0" in l.upper()]

        if p0_lines:
            detail = f"{len(p0_lines)} P0 alert(s) detected"
            s.error(detail)
            return detail + "\n" + "\n".join(f"  {l[:200]}" for l in p0_lines)
        else:
            return f"No P0 alert in the last {len(last_lines)} lines"


def main() -> None:
    counts = {"ok": 0, "warning": 0, "error": 0}

    with AutomateLog("sy_session_start") as log:
        print("=" * 60)
        print(f"  SESSION START — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        checks = [
            ("Automate errors", check_automate_errors),
            ("Cron check", check_crons),
            ("Git status", check_git_status),
            ("Logs freshness", check_logs_freshness),
            ("Calendar", check_calendar),
            ("Client bugs (inbox P0)", check_client_bugs),
        ]

        for label, fn in checks:
            print(f"\n--- {label} ---")
            result = fn(log)
            print(result)

        # Count the statuses from the recorded steps
        for step in log._data["steps"]:
            status = step.get("status", "ok")
            if status in counts:
                counts[status] += 1
            elif status == "skip":
                counts["ok"] += 1

        # Overall result
        if counts["error"] > 0:
            log.set_result("error", f"{counts['error']} error(s)")
        elif counts["warning"] > 0:
            log.set_result("partial", f"{counts['warning']} warning(s)")
        else:
            log.set_result("ok")

        print("\n" + "=" * 60)
        print(f"  SUMMARY: {counts['ok']} OK | {counts['warning']} WARNING | {counts['error']} ERROR")
        print("=" * 60)


if __name__ == "__main__":
    main()
