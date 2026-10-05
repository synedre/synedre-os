#!/bin/bash
#
# hook-inline-secret-paste-block.sh — BLOCKING PreToolUse Bash hook (inline anti-leak).
#
# Materializes the anti-leak secrets doctrine ( §"Anti-leak secrets" +
# 3-level secrets doctrine). Closes a recurring CLASS of scars
# (#890 #827 #821 #774 #739 #735 #721, 7 P0/P1 occurrences): an agent blocked
# by an unsourced environment (`PG_HOST unreachable`, `.env not loaded`)
# works around it by pasting the secret's VALUE directly into the command. Fast
# to type, disastrous for secret rotation (the value leaks into the
# transcript, the logs, the history).
#
# Rule: NEVER paste a secret value inline. Source the env:
#     set -a && . .env && . .env.host && set +a      then reference $VAR.
#
# Detection: the VALUE (not the $VAR reference, not `grep ^VAR= .env`) of a
# variable with a sensitive name (PASS|PASSWORD|SECRET|KEY|TOKEN|PWD|CRED|API...) and
# length >= 12 appears LITERALLY (grep -F) in the command.
#
# Security of the hook itself: it reads secrets but NEVER re-echoes them —
# the error message cites ONLY the variable NAME, never its value.
#
# Fail-OPEN: any error / broken parse / missing .env → exit 0 (we never block
# a command by accident). HARD block (exit 2) only on a certain match.
#
# v1 scope + KNOWN LIMITS (Mitnick review 2026-07-13, verdict clean-with-notes):
#   - Sources: .env + .env.host (origin of the 7 scars). Tenant .env files
#     (codemyshop/tenants/<x>/.env, ~4 active: Stripe webhook...) are NOT
#     covered in v1 — future extension if it recurs.
#   - Gating by sensitive NAME: a sensitive value carried by a neutrally named
#     variable (e.g. NUXT_TENANT_DB_* connection string) escapes the radar.
#   - LITERAL detection: bypassable via encoding (base64/hex) or multi-variable
#     split (A="ab"; B="cd"; ...$A$B) — out of scope for v1, accepted.
#   - Length threshold = 8 (covers short live passwords like
#     *_HUB_ADMIN_PASSWORD; below that = too many false positives).
#   - NEVER invoke this hook under `bash -x`/`-v`: the trace would expand $val
#     (leak). The script itself does not self-trace.

set -uo pipefail

REPO="${SYNEDRE_ROOT}"

INPUT=$(cat)

COMMAND=""
if command -v jq >/dev/null 2>&1; then
    COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
fi
if [ -z "$COMMAND" ]; then
    COMMAND=$(printf '%s' "$INPUT" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' \
              | head -1 \
              | sed 's/.*"command"[[:space:]]*:[[:space:]]*"\(.*\)"/\1/' \
              2>/dev/null || true)
fi

# No readable command → do not get in the way (fail-open).
[ -z "$COMMAND" ] && exit 0

MATCH_VAR=""
for ENV_FILE in "$REPO/.env" "$REPO/.env.host"; do
    [ -r "$ENV_FILE" ] || continue
    # IFS='=' → everything after the first '=' goes into val (values containing '=' OK).
    # `|| [ -n "$name" ]`: WITHOUT this, the LAST line of a file with no final
    # newline is never processed — `read` returns false and `while` exits before
    # running the body. Found on 2026-07-17 (jobsite #448): .env has 257
    # lines and line 257, with no final newline, carried FACEBOOK_PASSWD — never
    # protected. A secret added at the end of the file (the most natural gesture
    # there is) thus silently escaped the radar.
    while IFS='=' read -r name val || [ -n "$name" ]; do
        # Ignore comments, empty lines, exports without '='.
        case "$name" in ''|\#*) continue;; esac
        # Pure Bash: this hook runs on every Bash PreToolUse. The former loop
        # launched sed + two grep processes per variable (~500 forks, 3.5 s per command).
        name="${name#"${name%%[![:space:]]*}"}"
        name="${name%"${name##*[![:space:]]}"}"
        if [[ "$name" =~ ^export[[:space:]]+(.+)$ ]]; then
            name="${BASH_REMATCH[1]}"
        fi
        upper_name="${name^^}"
        # Only target variables with a SENSITIVE name (reduces false positives).
        [[ "$upper_name" =~ (PASS|PASSWORD|SECRET|KEY|TOKEN|PWD|CRED|API) ]] || continue
        # ...but an IDENTIFIER variable carries no secret: a login, a
        # user, an email, a host or a port are written in plaintext by nature. The
        # gate above catches them by accident when the name contains "API"
        # (MISTRAL_API_LOGIN, POSTHOG_API_HOST, <TENANT>_<TENANT>_API_USER) — and
        # MISTRAL_API_LOGIN holds Alex's email address, which  itself documents
        # in plaintext as the canonical mailbox. Result: every sentence citing his
        # address was blocked. A secret that cannot be a secret has no place
        # in the radar (false positive observed 2026-07-17, jobsite #448).
        # `_ID` is deliberately NOT excluded: AWS_ACCESS_KEY_ID stays armed (caution
        # on AWS keys — an FP there is rare, a hole would be costly).
        if [[ "$upper_name" =~ (_LOGIN|_USER|_USERNAME|_EMAIL|_FROM|_HOST|_PORT)$ ]]; then
            continue
        fi
        # Normalize the value AS THE SHELL SEES IT, not as the text writes it.
        # Pre-existing hole found on 2026-07-17 (jobsite #448): 14 lines of
        # .env/.env.host end with a ';' (SMTP_PASS, IMAP_PASSWORD,
        # N26_PASSWORD, <TENANT>_OVH_PASSWORD, <TENANT>_PASSWD, FACEBOOK_PASSWD...).
        # The shell treats that ';' as a command separator and NEVER puts it
        # in the value; the hook, however, read it as the last character of the
        # secret. The two strings differed by one character → the
        # `grep -F` below could structurally NEVER match, and those
        # 14 secrets were not protected at all. The hook looked armed but did not
        # bite — same family as "plugged in != working".
        # Order: trailing spaces → ';' → spaces → dequote (covers `"val" ;`).
        val="${val%"${val##*[![:space:]]}"}"
        val="${val%;}"
        val="${val%"${val##*[![:space:]]}"}"
        # Dequote the value.
        val="${val%\"}"; val="${val#\"}"; val="${val%\'}"; val="${val#\'}"
        # Anti-FP threshold: value >= 8 chars, no spaces (covers short live
        # passwords like *_HUB_ADMIN_PASSWORD; below that = too many false positives).
        [ "${#val}" -lt 8 ] && continue
        case "$val" in *' '*) continue;; esac
        # Does the VALUE appear literally in the command? (fixed-string)
        if [[ "$COMMAND" == *"$val"* ]]; then
            MATCH_VAR="$name"
            break 2
        fi
    done < "$ENV_FILE"
done

if [ -n "$MATCH_VAR" ]; then
    # BLOCK — NEVER echo the value, only the variable name.
    cat >&2 << EOF

BLOCKED — secret value pasted inline (variable: $MATCH_VAR)

  The VALUE of a secret appears literally in your command. Working around an
  unsourced environment by pasting the value is FORBIDDEN: it leaks into the
  transcript, the logs and the history, and breaks secret rotation
  (scars #890 #827 #821 #774 #739 #735 #721).

  What you must do — source the env, then reference the VARIABLE:
    set -a && . $REPO/.env && . $REPO/.env.host && set +a
    ... \$$MATCH_VAR ...        # never the plaintext value

  Reference:  §"Anti-leak secrets" — 1 doctrine = 1 hook.

EOF
    exit 2
fi

exit 0
