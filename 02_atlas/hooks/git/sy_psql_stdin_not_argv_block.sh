#!/bin/bash
#
# hook-psql-stdin-not-argv-block.sh — BLOCKING PreToolUse Edit|Write hook.
#
# Materializes the invariant of the test synedre/tests/test_psql_stdin_not_argv.py
# (jobsite psql-stdin-migration, #530): SQL destined for psql goes through
# STDIN (input=sql), NEVER through argv ("-c", sql). The error shows up AT
# WRITE TIME, not by waiting for the test — otherwise the debt keeps being
# pushed back
# ().
#
# SCAR (2026-07-20, GLM run #896): `docker exec ... psql -c "<sql>"`
# makes the COMMAND LINE carry the entire payload. Beyond ARG_MAX the call
# fails with "Argument list too long" and the event goes to the trash
# SILENTLY — the cockpit was losing exactly the BIG events (long agent
# responses, large tool_result), without any alarm going off.
# `input=sql` (stdin) has no such limit (measured: 400 k characters OK).
#
# Migration settled: the 41 `-c sql` calls in the Python modules were
# rewritten to `input=sql` (batches 1 and 2, #530). PLAFOND_ARGV_RESTANT = 0.
# This hook closes the door on REINTRODUCTION: a new call is written with
# `input=sql`, period — we do not raise the ceiling back up.
#
# SCOPE — .py ONLY, like the test. The psql calls in the Node modules
# (.cjs, e.g. sy_figma_capture.cjs:sqlRead) stay on '-c', sql for bounded
# read queries; they are NOT affected by ARG_MAX in the same way and are
# out of the jobsite's scope. Extending the hook to those files would
# break this guard for a problem it does not target.
#
# WHAT IT CANNOT GUARD: that the docker exec carries its -i flag
# (without -i, input= returns rc=0 WITHOUT doing anything — a silent failure
# worse than -c). That is the job of the TestStdinExigeLeFlagInteractif test
# (AST analysis), not of a write-time hook.
#
# Conscious escape hatch: suffix with `# psql-stdin:allow <reason>`.
#
# Fail-OPEN: any error / broken parse / non-targeted file -> exit 0.
# HARD block (exit 2) on a certain match.

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

# No readable content or no targeted file -> do not get in the way (fail-open).
[ -z "$CONTENT" ] && exit 0
[ -z "$FILE" ] && exit 0

# Scope: .py only (consistent with the test, excludes the Node .cjs files).
case "$FILE" in
    *.py) ;;
    *) exit 0 ;;
esac

# The guardian is not subject to its own guard: the test file must be able
# to NAME the pattern (in its regex and its docstring) in order to detect it.
case "$FILE" in
    *test_psql_stdin_not_argv.py) exit 0 ;;
esac

# Deliberate and traceable escape hatch.
case "$CONTENT" in *"psql-stdin:allow"*) exit 0 ;; esac

# Normalize ALL whitespace (spaces AND newlines) — the idiomatic Python form
# is the multi-line list `["-c",\n sql]`. We thereby match the test's regex
# `["\']-c["\']\s*,\s*sql` where \s* also swallows line breaks.
NOSP=$(printf '%s' "$CONTENT" | tr -d '[:space:]')

HIT=""
case "$NOSP" in
    *'"-c",sql'*) HIT='"-c", sql' ;;
    *"'-c',sql"*) HIT="'-c', sql" ;;
esac

if [ -n "$HIT" ]; then
    cat >&2 << EOF

BLOCKED — SQL passed to psql via argv ($FILE)

  Found: $HIT

  Beyond ARG_MAX, the call 'docker exec ... psql -c "<sql>"' fails with
  "Argument list too long" and the payload is lost SILENTLY. It is
  precisely the BIG payloads that get dropped (GLM run #896, 2026-07-20) —
  nobody saw it since it was a mere stderr warning drowned in the noise.

  The migration to STDIN is settled (batches 1 and 2, #530): zero
  '-c sql' calls remain in the Python modules. This hook refuses any
  REINTRODUCTION — we do not raise the ceiling back up.

  What to do — feed psql via stdin:
      proc = subprocess.run(_PSQL + ["-U", user, "-d", db],
                            input=sql,    # <- stdin, not argv
                            stdout=PIPE, stderr=PIPE, ...)
  And REQUIRE 'docker exec -i' (without -i, input= returns rc=0 WITHOUT
  DOING ANYTHING — see the TestStdinExigeLeFlagInteractif test in
  synedre/tests/test_psql_stdin_not_argv.py).

  Legitimate out-of-scope .cjs case? (bounded Node read, e.g. sqlRead): this
  hook targets ONLY .py files. Do not extend it to push a Python case
  through — write input=sql instead.

  Real and conscious need? suffix the line: # psql-stdin:allow <reason>

  Reference: test_psql_stdin_not_argv.py -
  (1 doctrine = 1 hook — the error shows up at write time, not at test time).

EOF
    exit 2
fi

exit 0
