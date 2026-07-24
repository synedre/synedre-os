#!/usr/bin/env bash
#
# hook-no-rebase-on-shared-branch.sh — PreToolUse Bash hook.
#
# ENFORCES  : on `synedre-os`, `preprod` is
# shared by N simultaneous Claude sessions (single worktree) AND merged into `main`
# on every `./ship`. A rebase there rewrites SHAs ALREADY PUBLISHED on origin/main ->
# main<->preprod divergence for identical content.
#
# Scar 2026-07-17: main and preprod on the SAME commit (4550bfc7f). A reflex
# `git pull --rebase` — triggered by a mere rejected push (Dependabot had
# merged a PR onto origin/preprod) — replayed 153 commits and rewrote their
# SHAs. Divergence of 152/154 commits for a real diff of 2 files. Unrepairable
# without a force-push on a branch shared by 3 active sessions.
#
# Blocks: `git rebase`, `git pull --rebase|-r`, `git push --force|-f` — ONLY
# when the current branch is shared (preprod|main) and we are inside the repo.
# Lets through: `git rebase --abort|--continue|--skip|--quit` (getting out of an
# in-progress rebase must never be trapped), and any rebase on a feature branch.
#
# Fail-open everywhere: any error -> exit 0. This hook NEVER traps a session.

set -uo pipefail

REPO=${SYNEDRE_ROOT}

PAYLOAD=$(cat 2>/dev/null || true)
[ -z "$PAYLOAD" ] && exit 0

command -v jq >/dev/null 2>&1 || exit 0

CMD=$(printf '%s' "$PAYLOAD" | jq -r '.tool_input.command // empty' 2>/dev/null)
[ -z "$CMD" ] && exit 0

cd "$REPO" 2>/dev/null || exit 0

BRANCH=$(git branch --show-current 2>/dev/null || echo "")
case "$BRANCH" in
  preprod|main) ;;   # shared branches -> keep guarding
  *) exit 0 ;;       # feature branch -> rebase allowed
esac

# Getting out of an in-progress rebase is ALWAYS allowed (never trap).
printf '%s' "$CMD" | grep -qE 'git[[:space:]]+rebase[[:space:]]+--(abort|continue|skip|quit)' && exit 0

# Command starts only (^, ;, &&, ||, |) — reduces false positives on text
# that merely MENTIONS the command (heredoc, commit message, doc).
BOL='(^|;|&&|\|\||\|)[[:space:]]*'
VIOLATION=""

if printf '%s' "$CMD" | grep -qE "${BOL}git[[:space:]]+rebase\b"; then
  VIOLATION="git rebase"
elif printf '%s' "$CMD" | grep -qE "${BOL}git[[:space:]]+pull\b[^;&|]*(--rebase|[[:space:]]-r\b)"; then
  VIOLATION="git pull --rebase"
elif printf '%s' "$CMD" | grep -qE "${BOL}git[[:space:]]+push\b[^;&|]*(--force\b|--force-with-lease\b|[[:space:]]-f\b)"; then
  VIOLATION="git push --force"
fi

[ -z "$VIOLATION" ] && exit 0

cat >&2 <<EOF

BLOCKED — History rewrite on a shared branch (doctrine )

  You are attempting a \`${VIOLATION}\` on \`${BRANCH}\`, shared by N Claude
  sessions (single worktree). Its SHAs are ALREADY published on origin/main via
  \`./ship\` (ship-prod.sh does \`git merge preprod\`): rewriting them makes
  main<->preprod diverge for IDENTICAL content.

  Scar 2026-07-17: a reflex \`git pull --rebase\` on a rejected push replayed
  153 commits and made main<->preprod diverge by 152 commits — for a real diff
  of 2 files. Unrepairable without a force-push on a branch with 3 active
  sessions.

  What you must do — if your push was rejected (non-fast-forward, typically
  a Dependabot PR merged on GitHub):
    git fetch origin ${BRANCH}
    git log --oneline ${BRANCH}..origin/${BRANCH}   # SEE what is missing locally
    git pull --no-rebase origin ${BRANCH}           # merge — NEVER --rebase
    git push origin ${BRANCH}

  Rewriting history for good = Alex's decision, never an AI reflex:
  lay out the cost for him and let him decide.

EOF
exit 2
