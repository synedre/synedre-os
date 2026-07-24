#!/bin/bash
#
# hook-cron-llm-block.sh — BLOCKING PreToolUse Bash hook (LLM in cron = plan drain).
#
# Materializes the doctrine  (jobsite #506,
# anti-drain session of 2026-07-19). A script that consumes LLM (claude -p /
# sy_ai_provider.complete / invoke_agent / spawn node-pty) registered in crontab
# drains the Claude plan SILENTLY: the cost is invisible until the weekly
# cap. The 2026-07-19 trigger: sy_jobsite_readiness_audit --enrich
# swept the ENTIRE backlog every 20 min via claude -p. Removed and switched to
# on-demand (--only) the same day — this hook prevents its REINTRODUCTION.
#
# RULE: an LLM script is never installed in cron. The internal LLM is called ON
# DEMAND (at the moment it is needed), never on a clock.
#
# DETECTION: the command installs a crontab (`crontab -`, `crontab <file>`,
# `crontab -e`, `… | crontab -`) AND one of its non-commented cron lines invokes
# a script that (STATIC analysis of the resolved file) calls an LLM, OR contains
# a hardcoded `claude -p`. The cron line parser mirrors
# hook-cron-relative-path-block.sh (same skeleton, no second diverging parser).
#
# SHARED ENGINE — 1 doctrine = 1 hook ().
# The detection logic historically lived inline; it was extracted into
# synedre/sy_cron_llm_detector.py (2026-07-21), a module shared with the
# sy_audit_cron_llm.py sentinel. This hook is now just a thin Bash wrapper: it
# extracts the command from the payload, passes it to the module, and blocks on
# the 1st violation. The two guards cannot diverge ().
#
# Conscious EXIT DOORS (handled by the module):
#   1. Nominative allow-list: synedre/config/cron_llm_allowlist.yaml (empty by default).
#   2. End-of-cron-line marker: `# cron-llm:allow <reason>`.
#
# FAIL-OPEN: payload/parse KO -> exit 0. Block (exit 2) on a CERTAIN LLM match.
# A safety guard that breaks everything gets disabled — only block what is certain.

set -uo pipefail

# Overridable for tests (default = canonical live repo).
REPO="${CRON_LL_HOOK_REPO:-${SYNEDRE_ROOT}}"
PAYLOAD="$(cat 2>/dev/null || true)"
[ -z "$PAYLOAD" ] && exit 0

CMD="$(printf '%s' "$PAYLOAD" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get("tool_input", {}).get("command", "") or "")
except Exception:
    pass
' 2>/dev/null || true)"
[ -z "$CMD" ] && exit 0

# Only fires if the command deals with crontab.
printf '%s' "$CMD" | grep -qE '\bcrontab\b' || exit 0

# Read-only (`crontab -l` without installing) -> let it pass.
if printf '%s' "$CMD" | grep -qE '\bcrontab[[:space:]]+-l\b' \
   && ! printf '%s' "$CMD" | grep -qE '\bcrontab[[:space:]]+(-|-e|[^[:space:]-][^[:space:]]*)([[:space:]]|$)'; then
    exit 0
fi

# Delegate detection to the shared engine. Format: KIND|stem|path|line
# (stem/path empty for CLAUDE_P_INLINE). Fail-open: any failure -> empty -> exit 0.
VIOLATION="$(CRON_HOOK_CMD="$CMD" CRON_HOOK_REPO="$REPO" PYTHONPATH="$REPO" python3 - <<'PY' 2>/dev/null || true
import os
from pathlib import Path
from synedre.sy_cron_llm_detector import detect_llm_cron_violations

repo = Path(os.environ.get("CRON_HOOK_REPO", "${SYNEDRE_ROOT}"))
cmd = os.environ.get("CRON_HOOK_CMD", "")
v = detect_llm_cron_violations(cmd, repo=repo)
if v:  # the hook only wants the 1st one; the sentinel takes the others
    x = v[0]
    print("|".join((x.kind, x.stem, x.script_path, x.line)))
PY
)"

[ -z "$VIOLATION" ] && exit 0

KIND="${VIOLATION%%|*}"

if [ "$KIND" = "CLAUDE_P_INLINE" ]; then
    LINE="${VIOLATION#*|}"
    DETAIL="This line calls \`claude -p\` DIRECTLY."
    WHICH=""
else
    REST="${VIOLATION#*|}"          # <stem>|<path>|<cmd>
    STEM="${REST%%|*}"; REST="${REST#*|}"
    SPATH="${REST%%|*}"; LINE="${REST#*|}"
    DETAIL="The invoked script \`${STEM}\` consumes LLM (static analysis of ${SPATH})."
    WHICH="  Offending script: ${SPATH}"
fi

cat >&2 << EOF

BLOCKED — installing an LLM script in cron (silent plan drain)

  Offending cron line:
    ${LINE}

  ${DETAIL}
${WHICH}

  WHY THIS IS BLOCKED: a recurring LLM in crontab drains the Claude plan
  SILENTLY — the cost shows up nowhere until the weekly cap. On
  2026-07-19, sy_jobsite_readiness_audit --enrich swept the ENTIRE backlog via
  claude -p every 20 min. The rule since then: the internal LLM is called ON
  DEMAND (at the moment it is needed), never on a clock.

  WHAT TO DO:
    - Make the LLM call ON-DEMAND (e.g. readiness_audit --only <codename> run
      at the moment you want to arm a jobsite, not in cron).
    - OR keep only the DETERMINISTIC part in cron (verdict/scan without LLM).

  IF THIS IS TRULY A CONSCIOUS CHOICE (e.g. an event-driven worker that no-ops
  when the queue is empty):
    - Add the script to synedre/config/cron_llm_allowlist.yaml (with its reason),
    - OR suffix the cron line with: # cron-llm:allow <reason>

  Reference:  — 1 doctrine = 1 hook.

EOF
exit 2
