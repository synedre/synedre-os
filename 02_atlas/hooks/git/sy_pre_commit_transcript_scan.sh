#!/usr/bin/env bash
# hook-pre-commit-transcript-scan.sh — PreToolUse Bash
#
# Before a `git commit`, scans the current session's JSONL transcript to
# detect recurring errors (creds, paths, flags) and BLOCKS the commit as
# long as no feedback_* memory has been engraved to cover the likely
# relapse. Applies the doctrine .
#
# Anti-loop: marker /tmp/claude-pre-commit-scanned-<session>-<hits-hash>.
# 1st detection -> block. 2nd attempt with the same hits -> let it through
# (Claude has seen the warning and decided to proceed).
#
# Skips:
#   - command is not a `git commit` (or is an --amend / commit-tree)
#   - no readable transcript_path
#   - no error line in the transcript
#
# JSON output systemMessage / decision=block.

set -uo pipefail
PAYLOAD=$(cat 2>/dev/null || true)

# Filter tool_name=Bash + extract command + transcript_path
read -r TOOL_NAME CMD TRANSCRIPT SESSION < <(printf '%s' "$PAYLOAD" | python3 -c '
import json, sys
try:
    d = json.loads(sys.stdin.read() or "{}")
    print(
        d.get("tool_name") or "?",
        ((d.get("tool_input") or {}).get("command") or "").replace("\n", " ")[:500].replace(" ", "<SP>"),
        d.get("transcript_path") or "",
        d.get("session_id") or "nosession",
    )
except Exception:
    print("? ? ? nosession")
' 2>/dev/null) || exit 0

[ "$TOOL_NAME" = "Bash" ] || exit 0
CMD_DECODED=$(printf '%s' "$CMD" | sed 's/<SP>/ /g')
# Hardening #380 (Lovelace): catch `git commit` even with interleaved flags
# (`git -c core.hooksPath=... commit`), same bypass class as the coverage hook.
echo "$CMD_DECODED" | grep -qE '\bgit[[:space:]]+([^[:space:]]+[[:space:]]+)*commit\b' || exit 0
echo "$CMD_DECODED" | grep -qE -- '--amend|commit-tree' && exit 0
[ -n "$TRANSCRIPT" ] && [ -r "$TRANSCRIPT" ] || exit 0

# Transcript scan: extract stdout/stderr ONLY from real command outputs
# (.toolUseResult, type:"user" lines of the transcript), grep recurring error patterns.
# Cap at 10 hits so the reason does not blow up.
#
# IMPORTANT (false-positive fix): we do NOT scan .attachment.stdout — that is where
# the contexts injected by the hooks live (SessionStart injects the qualified scars
# via sy_scars_inject.py, and they contain words like "fatal:true"). The old
# query `.. | objects | select(has("stdout"))` descended everywhere and matched those
# scars -> block on every session carrying a scar with "fatal". has("toolUseResult")
# targets only the Bash command outputs (across 6 transcripts, 100% of toolUseResult
# entries come from a tool_use name:"Bash"). The anti-noise grep on the hook's own
# signature has become dead code (its outputs go to .attachment, never scanned).
HITS=$(jq -r '
  select(has("toolUseResult"))
  | .toolUseResult
  | (.stdout // ""), (.stderr // "")
' "$TRANSCRIPT" 2>/dev/null \
  | grep -iE 'FATAL|role "[^"]+" does not exist|command not found|permission denied|psql: error|ENOENT|MODULE_NOT_FOUND|EACCES|address already in use' \
  | grep -viE '\[expected\]|# ok to ignore' \
  | sort -u | head -10)

if [ -z "$HITS" ]; then
  exit 0
fi

# Session-level marker: at most 1 block per session (whatever the hit set,
# which mutates with the hook's own outputs in the transcript).
MARKER="/tmp/claude-pre-commit-scanned-${SESSION}"

if [ -f "$MARKER" ]; then
  # 2nd attempt: Claude has already seen the warning, let it through as a warn
  inner=$(printf '%s' "$HITS" | python3 -c 'import sys, json; s=json.dumps(sys.stdin.read()); print(s[1:-1])')
  cat <<EOF
{"systemMessage": "⚠️  Pre-commit scan: commit allowed despite unacknowledged transcript errors (anti-loop).\n${inner}"}
EOF
  exit 0
fi

# 1st detection: set the marker + block
touch "$MARKER"
inner=$(printf '%s' "$HITS" | python3 -c 'import sys, json; s=json.dumps(sys.stdin.read()); print(s[1:-1])')
cat <<EOF
{"decision": "block", "reason": "📋 Pre-commit transcript scan — recurring errors detected in the session.\n\nGrep of stdout/stderr (max 10):\n${inner}\n\nBefore committing: check that each pattern has a feedback_* or reference_* memory covering the canonical value (creds, path, user...). Otherwise engrave a memory in ${HOME}/.claude/projects/-home-ubuntu-synedre-os/memory/ and point to it from MEMORY.md.\n\nRerun the same git commit to pass (anti-loop: 2nd attempt is let through)."}
EOF
exit 0
