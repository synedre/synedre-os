#!/usr/bin/env python3
#        under 130k — sessions will no longer cross the threshold; OR migrate the
#        handoff to a sy_session_handoff table.
"""sy_session_split.py — Stop hook: session splitting at a context threshold.

Jobsite #508 (cost-routing) — cuts the quadratic cost of long sessions
(history + tool results resent on every turn). Triggered on every Stop:
  1. measures the REAL context (message.usage of the last assistant message =
     input + cache_read + cache_creation) and the turn count;
  2. if the threshold is crossed AND not already "armed" for this crossing:
       - Pass 1 (stop_hook_active=false) → {"decision":"block","reason":...}
         forces writing a persistent handoff + signals the split.
       - Pass 2 (stop_hook_active=true)  → {"systemMessage":...} warn (anti-loop).
  3. re-armed when the context drops back under the low threshold (= compaction happened).

The native backstop (CLAUDE_CODE_AUTO_COMPACT_WINDOW=150000 in ./glm and ./codex)
guarantees the memory reset via Haiku=glm-4.7 (free) — even if this hook misses or
nobody runs /clear (autonomous case). This hook adds the control layer:
persistent handoff (resume/crash) + metrics (runaway detector, cost dashboard).

Safeguards:
  - Kill-switch SY_SESSION_SPLIT_DISABLED=1 → exit 0.
  - NO worker guard: we deliberately act on autonomous sessions (core of the goal).
  - Anti-loop: session-level "armed" marker (1 block per crossing,
    re-armed after compaction) + stop_hook_active (pass 2, same turn).
  - Total graceful degradation: any exception → exit 0 (never bricks).

All paths/thresholds can be overridden via env (for unit tests).

"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ─── Bootstrap ─────────────────────────────────────────────────────────────────

_DIR = Path(__file__).resolve().parent
try:
    sys.path.insert(0, str(_DIR.parent))
    from sy_env import load_env  # type: ignore
    load_env()
except Exception:
    pass  # fail-open: thresholds/defaults work without env loaded

# ─── Config (overridable via env for tests) ────────────────────────────────────

SEUIL_HAUT = int(os.environ.get("SY_SESSION_SPLIT_CTX_THRESHOLD", "130000"))
SEUIL_TOUR = int(os.environ.get("SY_SESSION_SPLIT_TURN_THRESHOLD", "150"))
SEUIL_BAS  = int(os.environ.get("SY_SESSION_SPLIT_CTX_REARM", "100000"))

LOG_PATH      = Path(os.environ.get(
    "SY_SESSION_SPLIT_LOG",
    str(_DIR / "logs" / "sy_session_split" / "split_log.jsonl")))
HANDOFF_DIR   = Path(os.environ.get(
    "SY_SESSION_SPLIT_HANDOFF_DIR",
    str(_DIR / "state" / "session-handoffs")))
MARKER_DIR    = Path(os.environ.get(
    "SY_SESSION_SPLIT_MARKER_DIR", "/tmp"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ─── Transcript measurement (1 pass, real usage) ───────────────────────────────

def _measure(transcript_path: str) -> tuple[int, int, int, int]:
    """Returns (turns, ctx_total, input_tokens, cache_read).

    ctx_total = input + cache_read + cache_creation of the LAST assistant message.
    This is the window actually resent to the model = the real quadratic cost.
    """
    turns = 0
    last_usage: dict | None = None
    try:
        with open(transcript_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") == "assistant":
                    turns += 1
                    msg = obj.get("message")
                    if isinstance(msg, dict):
                        u = msg.get("usage")
                        if isinstance(u, dict):
                            last_usage = u
    except OSError:
        return 0, 0, 0, 0

    u = last_usage or {}
    inp = int(u.get("input_tokens", 0) or 0)
    cache_read = int(u.get("cache_read_input_tokens", 0) or 0)
    cache_create = int(u.get("cache_creation_input_tokens", 0) or 0)
    return turns, inp + cache_read + cache_create, inp, cache_read


# ─── Effects: persistent handoff + JSONL log ───────────────────────────────────

def _write_handoff(session_id: str, turns: int, ctx: int, cwd: str = "") -> Path | None:
    """Creates a versioned handoff stub (never overwrites). The agent fills it in.

    ``cwd`` is written in the header and is authoritative for the resume SCOPE:
    all worktrees share this handoff directory (hooks point absolutely to
    ${SYNEDRE_ROOT}/synedre/), so without this line a handoff from
    `wt/jobsite-X` would surface in a session opened elsewhere.
    Read by sy_session_handoff_resume._cwd_of() — do not change the format alone.
    """
    try:
        HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
        sid_safe = (session_id or "nosession").replace("/", "_").replace("\\", "_")
        path = HANDOFF_DIR / f"{sid_safe}-{_now_stamp()}.md"
        path.write_text(
            f"# Session handoff — split (context ~{ctx // 1000}k, "
            f"{turns} turns)\n\n"
            f"> Session `{session_id}` — {_now_iso()}\n"
            f"> Work_order directory: `{cwd or os.getcwd()}`\n"
            f"> Detected by `sy_session_split.py` (jobsite #508). The context "
            f"crossed the split threshold: quadratic cost.\n"
            f"> **Fill in the 4 sections below**, then split the session "
            f"(/clear in interactive mode; native compaction resets in autonomous mode).\n\n"
            f"## 🎯 Session objective\n"
            f"(in 1-3 sentences: what this session was meant to accomplish)\n\n"
            f"## ✅ Current state\n"
            f"(done: modified files, decisions, commits)\n\n"
            f"## ➡️ Next concrete step\n"
            f"(the immediate next action to resume)\n\n"
            f"## ⚠️ Critical context not to lose\n"
            f"(invariants, constraints, gotchas, key files)\n",
            encoding="utf-8",
        )
        return path
    except Exception as exc:
        print(f"[sy_session_split] handoff write failed: {exc}", file=sys.stderr)
        return None


def _log(**fields) -> None:
    """Fail-open JSONL append (_log_borne pattern). Feeds runaway + cost."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": _now_iso(), **fields}
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[sy_session_split] log failed: {exc}", file=sys.stderr)


def _armed_path(session_id: str) -> Path:
    sid_safe = (session_id or "nosession").replace("/", "_").replace("\\", "_")
    return MARKER_DIR / f"sy-session-split-armed-{sid_safe}"


# ─── Decision (separated from IO for testability) ──────────────────────────────

def _decide(
    *,
    stop_active: bool,
    session_id: str,
    turns: int,
    ctx: int,
    inp: int,
    cache_read: int,
    cwd: str = "",
) -> tuple[int, dict | None]:
    """Returns (exit_code, output_json | None). Performs the side effects."""
    seuil_franchi = ctx >= SEUIL_HAUT or turns >= SEUIL_TOUR
    armed = _armed_path(session_id)

    if seuil_franchi:
        if stop_active:
            # Pass 2 — anti-loop, same turn
            _log(session_id=session_id, turns=turns, input_tokens=inp,
                 cache_read=cache_read, ctx=ctx, action="warn")
            return 0, {"systemMessage":
                f"⚠️ Session context at ~{ctx // 1000}k tokens / {turns} turns — "
                f"handoff already requested (anti-loop). Split the session "
                f"(/clear) to resume from the handoff."}
        if armed.exists():
            # Already notified for this crossing — wait for native compaction
            return 0, None
        # Pass 1 — 1st crossing: block + persistent handoff
        handoff = _write_handoff(session_id, turns, ctx, cwd)
        try:
            MARKER_DIR.mkdir(parents=True, exist_ok=True)
            armed.touch()
        except OSError:
            pass
        _log(session_id=session_id, turns=turns, input_tokens=inp,
             cache_read=cache_read, ctx=ctx, action="block",
             handoff=(str(handoff) if handoff else None))
        reason = (
            f"🔄 SESSION SPLIT — context ~{ctx // 1000}k tokens / "
            f"{turns} turns (quadratic cost: the history is resent on every "
            f"turn). Doctrine #508: produce a resume handoff BEFORE "
            f"continuing.\n\n"
            f"👉 Fill in the 4 handoff sections: {handoff}\n"
            f"   (Objective / Current state / Next step / Critical context)\n\n"
            f"Then split: /clear in interactive mode (and resume by pasting the "
            f"handoff). In autonomous mode, native compaction (150k backstop) resets "
            f"the context — but the persistent handoff remains your resume / "
            f"crash guarantee."
        )
        return 0, {"decision": "block", "reason": reason}

    # Below the threshold: re-arm if a native compaction just happened
    if ctx < SEUIL_BAS and armed.exists():
        try:
            armed.unlink()
        except OSError:
            pass
        _log(session_id=session_id, turns=turns, input_tokens=inp,
             cache_read=cache_read, ctx=ctx, action="rearmed")
    return 0, None


# ─── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    """Absolute fail-open: any exception → exit 0 (never bricks a session)."""
    try:
        return _run()
    except Exception as exc:
        print(f"[sy_session_split] UNEXPECTED ERROR (fail-open): {exc}",
              file=sys.stderr)
        return 0


def _run() -> int:
    if os.environ.get("SY_SESSION_SPLIT_DISABLED") == "1":
        return 0
    # NO worker guard: we deliberately act on autonomous sessions.

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    session_id = payload.get("session_id", "") or "nosession"
    transcript_path = payload.get("transcript_path", "") or ""
    stop_active = payload.get("stop_hook_active") is True

    if not transcript_path or not Path(transcript_path).is_file():
        return 0

    turns, ctx, inp, cache_read = _measure(transcript_path)
    exit_code, output = _decide(
        stop_active=stop_active, session_id=session_id,
        turns=turns, ctx=ctx, inp=inp, cache_read=cache_read,
        cwd=payload.get("cwd", "") or "",
    )
    if output is not None:
        sys.stdout.write(json.dumps(output, ensure_ascii=False))
        sys.stdout.write("\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
