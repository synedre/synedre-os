#!/usr/bin/env bash
# hook-stop-uncommitted-warn.sh — Stop event
#
# BLOCKING: if the git worktree contains uncommitted changes at the end
# of a session, refuse the Stop and force Claude to commit. Enforces the
# "Commit in flow" doctrine: no finished work_order stays
# uncommitted.
#
# Session-aware (since 2026-05-21): if the session has a tracking file
# `.claude/session-<id>-edited.txt` (fed by hook-track-session-edits.py
# on PostToolUse Edit|Write|MultiEdit|NotebookEdit), the dirty list is
# filtered to keep only the files OF THIS SESSION. Enables Claude
# multi-session parallelism without cross-blocking.
#
# Anti-loop guard: if stop_hook_active=true (the hook already blocked
# once and Claude requested Stop again), let it pass as a warning. Otherwise
# Claude could be trapped in a loop if it cannot commit.
#
# Exclusion: .claude/settings.json modified during the session (the hook
# itself may have edited this file).
#
# Output:
#   - clean OR no dirty file of MINE -> silent exit 0
#   - dirty MINE + 1st pass -> JSON {"decision":"block","reason":"..."} (blocks)
#   - dirty MINE + 2nd pass -> JSON {"systemMessage":"..."} (non-blocking warn)

set -uo pipefail
cd ${SYNEDRE_ROOT} 2>/dev/null || exit 0

# Worker context early-return: if this hook fires inside a sub-claude
# spawned by sy_task_worker.py (SY_WORKER_CONTEXT=sy_task_worker injected by
# atlas-spawn-claude.mjs, Brunel commit #421), exit silently.
# The worker handles the commit cycle itself at end of run — the sub-claude
# must not commit (commit-in-flow doctrine reserved for user sessions).
# Scar 2026-05-23 #3 (jobsite #94): without this guard, 100+ identical hook_*
# events blocked the sub-claude without producing anything.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/is-worker-context.sh
source "${SCRIPT_DIR}/lib/is-worker-context.sh" 2>/dev/null || true
is_worker_context && exit 0

# Read stdin (Claude Code sends {"stop_hook_active": bool, "session_id": "...", ...})
stdin_raw=$(cat 2>/dev/null || true)

stop_hook_active=$(printf '%s' "$stdin_raw" | python3 -c '
import sys, json
try:
    d = json.loads(sys.stdin.read() or "{}")
    print("true" if d.get("stop_hook_active") else "false")
except Exception:
    print("false")
' 2>/dev/null || echo "false")

session_id=$(printf '%s' "$stdin_raw" | python3 -c '
import sys, json
try:
    d = json.loads(sys.stdin.read() or "{}")
    print(d.get("session_id") or "")
except Exception:
    print("")
' 2>/dev/null || echo "")

dirty=$(git status --porcelain 2>/dev/null | grep -v '\.claude/settings\.json$' || true)

if [ -z "$dirty" ]; then
  exit 0
fi

# Session-aware filter: if the tracking file exists, keep only the files
# edited BY THIS SESSION (the others = WIP from a sibling session).
#
# Zero-edit case (scar 2026-05-27): a tracked session that did
# NO Edit/Write (work_order 100% DB / read-only) has no edit log. Without a
# guard, the `[ -f "$edited_log" ]` test was false, the filter bypassed, and the
# session inherited the GLOBAL dirty state (WIP of sibling sessions sharing the
# same worktree) -> false block. No log = zero files of its own -> exit.
edited_log=".claude/session-${session_id}-edited.txt"
if [ -n "$session_id" ]; then
 if [ -f "$edited_log" ]; then
  dirty=$(printf '%s\n' "$dirty" | python3 -c "
import sys
with open('$edited_log') as f:
    tracked = {ln.strip() for ln in f if ln.strip()}
out = []
for line in sys.stdin:
    line = line.rstrip()
    if not line:
        continue
    # Porcelain format: 'XY path' or '?? path', path may be quoted if it has spaces
    parts = line.split(None, 1)
    if len(parts) < 2:
        continue
    path = parts[1].strip().strip('\"')
    # For renames 'R  old -> new', take the new one
    if ' -> ' in path:
        path = path.split(' -> ', 1)[1].strip().strip('\"')
    if path in tracked:
        out.append(line)
print('\n'.join(out))
" 2>/dev/null || printf '%s' "$dirty")
 else
  # Tracked session with no edit log = zero Edit/Write this run -> no
  # file belongs to it. Do not inherit the WIP of sibling sessions.
  dirty=""
 fi
 if [ -z "$dirty" ]; then
   # Worktree dirty but no file from my session -> OK, other sessions
   # have WIP that is not my problem.
   exit 0
 fi
fi

# Escape for JSON (newlines -> \n, quotes -> \")
escaped=$(printf '%s' "$dirty" | python3 -c 'import sys, json; print(json.dumps(sys.stdin.read()))')
# escaped contains the enclosing double quotes; strip them for interpolation
inner=${escaped:1:-1}

if [ "$stop_hook_active" = "true" ]; then
  # 2nd pass: do not re-block (anti infinite-loop). Warn only.
  cat <<EOF
{"systemMessage": "⚠️  Stop forced while worktree is dirty (anti-loop):\n${inner}\nCommit manually in the next session."}
EOF
  exit 0
fi

# 1st pass: BLOCK the Stop and instruct Claude to commit
cat <<EOF
{"decision": "block", "reason": "'Commit in flow' doctrine: uncommitted work_order is forbidden at end of session.\n\nDirty files (of this session):\n${inner}\n\nRequired action: commit (1 jobsite = 1 coherent commit) THEN yield. If the worktree contains intentional WIP, declare it explicitly in the response before Stop."}
EOF
exit 0
