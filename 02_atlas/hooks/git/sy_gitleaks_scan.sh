#!/bin/bash
#
# hook-gitleaks-scan.sh — Self-contained secrets scanner (gitleaks absent).
#
# Enforces anti-leak doctrine #673 AT WRITE TIME: scans the ADDED LINES of the
# staged diff for plaintext secret VALUES (DB passwords, 64-hex PG,
# connection strings, private keys, tokens/API keys, AWS keys). Exit 1 + list
# (REDACTED values) on leak. Born from Mitnick review #422: paid prod PG password
# for <TENANT> plaintext and git-tracked, undetected because section 2 only checked
# file NAMES, not content.
#
# Deliberate escape hatch: suffix `# gitleaks:allow <reason>` on the line
# (legitimate false positive, e.g. test fixture).
set -uo pipefail

# Staged diff, added lines only; excludes binaries / templates / locks.
DIFF=$(git diff --cached -U0 --no-color -- . \
  ':(exclude)*.example' ':(exclude)*.lock' ':(exclude)*.jpg' ':(exclude)*.jpeg' \
  ':(exclude)*.png' ':(exclude)*.gif' ':(exclude)*.webp' ':(exclude)*.pdf' \
  ':(exclude)*.min.js' ':(exclude)*.map' 2>/dev/null \
  | grep -E '^\+' | grep -vE '^\+\+\+' || true)

[ -z "$DIFF" ] && exit 0

# Env reads / placeholders / escape hatch → never a plaintext secret.
ALLOW='os\.environ|process\.env|getenv|import os|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|CHANGE_?ME|change-me|<[a-z0-9_-]+>|xxxx+|placeholder|example|your-|REDACTED|\*\*\*|gitleaks:allow'

FOUND=0
flag() {
  # $1 = type; $2 = line. Redacts any token >=12 chars before printing.
  local safe
  safe=$(printf '%s' "$2" | sed -E 's/[A-Za-z0-9/+=_!@#$%^&*.:-]{12,}/<REDACTED>/g' | cut -c1-110)
  echo "  ✗ LEAK [$1]: ${safe#+}"
  FOUND=1
}

while IFS= read -r line; do
  printf '%s' "$line" | grep -qiE "$ALLOW" && continue
  printf '%s' "$line" | grep -qiE "(password|passwd|[^a-z]pwd|[^a-z]pass)\s*[:=]>?\s*['\"][^'\"]{6,}['\"]" && flag "password" "$line" && continue
  printf '%s' "$line" | grep -qE "(PG|POSTGRES|MYSQL|MARIADB|DB|REDIS)_?PASS(WORD)?\s*=\s*['\"]?[A-Za-z0-9!@#%_-]{8,}" && flag "db-password" "$line" && continue
  printf '%s' "$line" | grep -qE "PGPASSWORD=[0-9a-f]{64}|['\"][0-9a-f]{64}['\"]" && flag "pg-secret-hex" "$line" && continue
  printf '%s' "$line" | grep -qiE "(postgres|postgresql|mysql|mariadb|redis|mongodb)://[^:@/]+:[^@/[:space:]]{4,}@" && flag "connection-string" "$line" && continue
  printf '%s' "$line" | grep -qE "BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY" && flag "private-key" "$line" && continue
  printf '%s' "$line" | grep -qE "AKIA[0-9A-Z]{16}" && flag "aws-key" "$line" && continue
  printf '%s' "$line" | grep -qiE "(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|bearer)\s*[:=]>?\s*['\"][A-Za-z0-9_/+=.-]{20,}['\"]" && flag "token/apikey" "$line" && continue
done <<< "$DIFF"

if [ "$FOUND" = 1 ]; then
  echo ""
  echo "  ══ COMMIT BLOCKED — plaintext secret in the staged diff (anti-leak doctrine #673) ══"
  echo "  → Externalize the value: os.environ / process.env / \$VAR; the value lives in .env* (gitignored)."
  echo "  → Legitimate false positive? suffix the line with '# gitleaks:allow <reason>'."
  exit 1
fi
exit 0
