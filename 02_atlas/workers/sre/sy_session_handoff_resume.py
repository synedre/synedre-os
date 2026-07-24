#!/usr/bin/env python3
#        session splitting abandoned (sy_session_split.py removed).
"""sy_session_handoff_resume.py — SessionStart hook: auto-recall of the latest handoff.

When a new session starts (startup/clear/resume), automatically re-injects the most
recent handoff produced by sy_session_split.py — to resume without re-explaining
anything after a session split. Closes the loop: split creates → resume re-injects.

Filters (anti-noise + anti-loop):
  - < 24h (SY_HANDOFF_RESUME_MAX_AGE_H) — no stale handoff.
  - handoff session_id ≠ current session_id — never re-inject oneself.
  - SAME WORK_ORDER DIRECTORY as the current session. All worktrees share
    this handoff folder (hooks wired with absolute paths to
    ${SYNEDRE_ROOT}/synedre/): without this scope, the handoff from
    `wt/jobsite-X` surfaces in a session opened on another tenant —
    resuming on the wrong subject. Handoffs predating this scope lack
    the "Work_order directory" line: accepted (compat, they expire in 24h)
    but flagged as such in the banner.
  - handoff FILLED IN (original placeholders absent) — no useless blank stub.
  - kill-switch SY_HANDOFF_RESUME_DISABLED=1.
Absolute fail-open: slightest issue → print nothing (exit 0).

Output = TWO-CHANNEL JSON (pattern of sy_scars_inject_agent.py / hook-stop-
uncommitted-warn.sh), because raw stdout is only visible to the agent:
  - ``systemMessage``                      → DISPLAYED IN ALEX'S TERMINAL.
    Identity card of the resumed handoff: WHO (short session + tenant) and WHAT
    (subject + next step + file path). Without it, the resume is invisible
    to the human and ripe for confusion ("what is it talking about?").
  - ``hookSpecificOutput.additionalContext`` → injected into the agent context.
    The full handoff body, as before.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

_DIR = Path(__file__).resolve().parent
try:
    sys.path.insert(0, str(_DIR.parent))
    from sy_env import load_env  # type: ignore
    load_env()
except Exception:
    pass

HANDOFF_DIR = Path(os.environ.get(
    "SY_SESSION_SPLIT_HANDOFF_DIR",
    str(_DIR / "state" / "session-handoffs")))
MAX_AGE_S = int(os.environ.get("SY_HANDOFF_RESUME_MAX_AGE_H", "24")) * 3600

# Markers of the blank-stub placeholders created by sy_session_split.py.
_PLACEHOLDER_MARKERS = (
    "(in 1-3 sentences",
    "(done:",
    "(the immediate next action",
    "(invariants, constraints",
)


def _title(body: str) -> str:
    """Handoff subject = H1 title, stripped of the "Session handoff —" prefix."""
    for line in body.splitlines():
        if line.startswith("# "):
            t = line[2:].strip()
            return t.split("—", 1)[1].strip() if "—" in t else t
    return "(untitled)"


def _tenant(body: str) -> str:
    """Tenant codename if explicitly named (``tenant `xxx``` )."""
    m = re.search(r"tenants?\s+`([a-z0-9][a-z0-9._-]*)`", body)
    return m.group(1) if m else ""


def _cwd_of(body: str) -> str:
    """Work_order directory written by sy_session_split._write_handoff().
    Empty string = legacy handoff, written before the scope was introduced."""
    m = re.search(r"^>\s*Work_order directory\s*:\s*`([^`]+)`", body, re.M)
    return m.group(1).strip() if m else ""


def _same_dir(a: str, b: str) -> bool:
    """Directory comparison tolerant to symlinks and trailing slash."""
    try:
        return os.path.realpath(a) == os.path.realpath(b)
    except OSError:
        return a.rstrip("/") == b.rstrip("/")


def _plain(s: str) -> str:
    """Markdown → bare text: bold/code/bullets/numbering stripped (terminal-readable)."""
    s = re.sub(r"\*\*|`|__", "", s)
    s = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", s)
    return s.strip(" :—-")


def _next_step(body: str) -> str:
    """Next step: the "next step" section title (after its dash),
    else the first prose line of that section. Empty if the section is missing."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("#") or "next concrete step" not in line.lower():
            continue
        head = line.lstrip("# ").strip()
        if "—" in head:
            return _plain(head.split("—", 1)[1])[:140]
        for nxt in lines[i + 1:]:
            s = nxt.strip()
            if s.startswith("#"):
                break
            if s and not s.startswith(("```", ">", "|")):
                return _plain(s)[:140]
        return _plain(head)[:140]
    return ""


def _emit(path: Path, body: str, age_h: float) -> None:
    """Writes both channels: identity card for Alex, body for the agent."""
    sid = path.stem.rsplit("-", 1)[0] if "-" in path.stem else path.stem
    age = f"{age_h:.0f} h ago" if age_h >= 1 else "less than 1 h ago"
    who = f"session {sid[:8]} · {age}"
    if tenant := _tenant(body):
        who += f" · tenant {tenant}"
    if not _cwd_of(body):
        who += " · ⚠ unknown directory (legacy handoff)"

    banner = [f"📤 Handoff resumed — {who}", f"   Subject : {_title(body)}"]
    if step := _next_step(body):
        banner.append(f"   Next    : {step}")
    banner.append(f"   File    : {path}")

    print(json.dumps({
        "systemMessage": "\n".join(banner),
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                "📤 PREVIOUS SESSION HANDOFF "
                "(auto-loaded by sy_session_handoff_resume.py)\n"
                "Resume from the state described below — "
                "do not start over from scratch.\n"
                f"(source: {path.name})\n\n{body}\n"
            ),
        },
    }, ensure_ascii=False))


def main() -> int:
    try:
        return _run()
    except Exception as exc:
        print(f"[sy_session_handoff_resume] fail-open: {exc}", file=sys.stderr)
        return 0


def _run() -> int:
    if os.environ.get("SY_HANDOFF_RESUME_DISABLED") == "1":
        return 0
    if not HANDOFF_DIR.is_dir():
        return 0

    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    current_sid = (payload.get("session_id") or "").strip()
    current_cwd = (payload.get("cwd") or "").strip() or os.getcwd()

    now = time.time()
    best: tuple[float, Path, str] | None = None
    for p in HANDOFF_DIR.glob("*.md"):
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if now - mtime > MAX_AGE_S:
            continue
        # session_id = name without the timestamp suffix (the stamp has no '-')
        sid_in_name = p.stem.rsplit("-", 1)[0] if "-" in p.stem else p.stem
        if current_sid and sid_in_name == current_sid:
            continue  # never re-inject the current session
        try:
            body = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if any(mk in body for mk in _PLACEHOLDER_MARKERS):
            continue  # blank stub, not filled in yet
        h_cwd = _cwd_of(body)
        if h_cwd and current_cwd and not _same_dir(h_cwd, current_cwd):
            continue  # other worktree / other jobsite — not our resume
        if best is None or mtime > best[0]:
            best = (mtime, p, body)

    if best is None:
        return 0

    mtime, p, body = best
    _emit(p, body, (now - mtime) / 3600)
    return 0


if __name__ == "__main__":
    sys.exit(main())
