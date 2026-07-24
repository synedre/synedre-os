#!/bin/bash
#
# hook-sql-escape-roundtrip.sh — BLOCKING PreToolUse Edit|Write hook.
#
# Materializes  : in PostgreSQL
# (standard_conforming_strings = on, verified), a backslash inside a literal is ALREADY
# literal — `'a\b'` is a\b. Doubling it ADDS a backslash instead of escaping one.
#
# SCAR (jobsite #466, 2026-07-17): `synedre/sy_entities/base.py:_esc` did
# `.replace("\\", "\\\\")` — a MariaDB reflex (where the backslash IS an escape),
# inherited from before the MariaDB drop on 2026-04-30. Result: ALL entity
# writes silently corrupted values containing a backslash. Measured round-trip:
# 3 of 5 cases broken (JSON+quotes +2 chars, Windows path +3, regex +2).
# 30 fields unreadable in the database (discoveries_json, decisions_json, context_json) — the
# columns being TEXT, PG validated nothing: the corruption went unnoticed for months.
#
# This hook guards against the RETURN of the reflex: "escape the backslash" gets
# retyped all by itself, it is a MySQL/MariaDB developer automatism.
#
# What it CANNOT guard: that the round-trip was actually played out. That is the
# discipline of the doctrine (write -> read back -> compare on backslash, double
# quote, single quote, nested JSON) — a hook cannot prove a test in your place.
#
# Conscious escape hatch: suffix with `# sql-escape:allow <reason>`.
#
# Fail-OPEN: any error / broken parse -> exit 0. HARD block (exit 2) on a certain match.

set -uo pipefail

INPUT=$(cat)

CONTENT=""
FILE=""
if command -v jq >/dev/null 2>&1; then
    FILE=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
    # Edit -> new_string ; Write -> content ; MultiEdit -> concat of the edits.
    CONTENT=$(printf '%s' "$INPUT" | jq -r '
        [ .tool_input.new_string?, .tool_input.content?,
          (.tool_input.edits? // [] | .[]?.new_string?) ]
        | map(select(. != null)) | join("\n")
    ' 2>/dev/null)
fi

# No readable content or not a targeted file -> do not get in the way (fail-open).
[ -z "$CONTENT" ] && exit 0
[ -z "$FILE" ] && exit 0
case "$FILE" in
    *.py|*.ts|*.js|*.mjs|*.cjs) ;;
    *) exit 0 ;;
esac

# Deliberate and traceable escape hatch.
case "$CONTENT" in *"sql-escape:allow"*) exit 0 ;; esac

# Normalize whitespace to catch formatting variants.
NOSP=$(printf '%s' "$CONTENT" | tr -d ' ')

HIT=""
# Python / JS: backslash doubling inside a replace.
case "$NOSP" in
    *'replace("\\","\\\\")'*)   HIT='replace("\\", "\\\\")' ;;
    *"replace('\\\\','\\\\\\\\')"*) HIT="replace('\\\\', '\\\\\\\\')" ;;
    *'replaceAll("\\","\\\\")'*) HIT='replaceAll("\\", "\\\\")' ;;
esac

if [ -n "$HIT" ]; then
    cat >&2 << EOF

BLOCKED — backslash doubling in a SQL escape ($FILE)

  Found: $HIT

  In PostgreSQL, the backslash is NOT escaped. The database runs with
  standard_conforming_strings = on: a backslash inside a literal is ALREADY
  literal ('a\\b' is a\\b). Doubling it ADDS a backslash — it protects nothing.

  This is a MariaDB reflex (where the backslash IS an escape character).
  MariaDB was dropped on 2026-04-30. This same reflex corrupted 30 fields in
  the database for months, without a sound: the columns are TEXT, PG validates
  nothing, and nobody was reading back (jobsite #466).

  What to do — escape ONLY the single quote:
    s = str(value).replace("'", "''")
    return f"'{s}'"

  Then PROVE it with a round-trip (write -> read back -> compare) on the cases
  that bite: backslash, double quote, single quote, quote+backslash, nested JSON.
  Never conclude by reading the code — that is what let the original through.

  Real and conscious need? suffix the line: # sql-escape:allow <reason>

  Reference:  — 1 doctrine = 1 hook.

EOF
    exit 2
fi

exit 0
