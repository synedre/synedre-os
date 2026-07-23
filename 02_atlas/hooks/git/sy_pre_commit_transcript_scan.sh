#!/usr/bin/env bash
# hook-pre-commit-transcript-scan.sh — PreToolUse Bash
#
# Avant `git commit`, scanne le transcript JSONL de la session courante pour
# détecter les erreurs récurrentes (creds, paths, flags) et BLOQUE le commit
# tant qu'aucune mémoire feedback_* n'a été gravée pour couvrir la rechute
# probable. Applique la doctrine .
#
# Anti-boucle : marker /tmp/claude-pre-commit-scanned-<session>-<hits-hash>.
# 1ère détection → block. 2e tentative avec mêmes hits → laisse passer (Claude
# a vu l'avertissement et a décidé de procéder).
#
# Skips :
#   - commande n'est pas un `git commit` (ou est un --amend / commit-tree)
#   - pas de transcript_path lisible
#   - aucune ligne d'erreur dans le transcript
#
# Sortie JSON systemMessage / decision=block.

set -uo pipefail
PAYLOAD=$(cat 2>/dev/null || true)

# Filtre tool_name=Bash + extraction command + transcript_path
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
# Durcissement #380 (Lovelace) : capter `git commit` même avec flags intercalés
# (`git -c core.hooksPath=... commit`), même classe de bypass que le hook coverage.
echo "$CMD_DECODED" | grep -qE '\bgit[[:space:]]+([^[:space:]]+[[:space:]]+)*commit\b' || exit 0
echo "$CMD_DECODED" | grep -qE -- '--amend|commit-tree' && exit 0
[ -n "$TRANSCRIPT" ] && [ -r "$TRANSCRIPT" ] || exit 0

# Scan transcript : extraire stdout/stderr UNIQUEMENT des vraies sorties de commande
# (.toolUseResult, lignes type:"user" du transcript), grep patterns d'erreur récurrentes.
# Limiter à 10 hits pour ne pas exploser le reason.
#
# IMPORTANT (fix faux positif) : on ne scanne PAS .attachment.stdout — c'est là que vivent
# les contextes injectés par les hooks (SessionStart injecte les cicatrices qualifiées
# via sy_cicatrices_inject.py, qui contiennent des mots comme « fatal:true »). L'ancienne
# requête `.. | objects | select(has("stdout"))` descendait partout et matchait ces
# cicatrices → block à chaque session portant une cicatrice avec « fatal ». has("toolUseResult")
# cible les seules sorties de commande Bash (sur 6 transcripts, 100% des toolUseResult
# proviennent d'un tool_use name:"Bash"). La grep anti-bruit sur la signature du hook
# elle-même est devenue morte (ses outputs vont en .attachment, jamais scannés).
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

# Marker session-level : 1 block max par session (peu importe le set de hits,
# qui mutate avec les outputs du hook lui-même dans le transcript).
MARKER="/tmp/claude-pre-commit-scanned-${SESSION}"

if [ -f "$MARKER" ]; then
  # 2e tentative : Claude a déjà vu le warning, on laisse passer en warn
  inner=$(printf '%s' "$HITS" | python3 -c 'import sys, json; s=json.dumps(sys.stdin.read()); print(s[1:-1])')
  cat <<EOF
{"systemMessage": "⚠️  Pre-commit scan : commit autorisé malgré erreurs transcript non-acknowledgées (anti-boucle).\n${inner}"}
EOF
  exit 0
fi

# 1ère détection : poser le marker + bloquer
touch "$MARKER"
inner=$(printf '%s' "$HITS" | python3 -c 'import sys, json; s=json.dumps(sys.stdin.read()); print(s[1:-1])')
cat <<EOF
{"decision": "block", "reason": "📋 Pre-commit scan transcript — erreurs récurrentes détectées dans la session.\n\nGrep des stdout/stderr (max 10) :\n${inner}\n\nAvant de commiter : vérifier que chaque pattern a une mémoire feedback_* ou reference_* couvrant la valeur canonique (creds, path, user…). Sinon graver une mémoire dans ${HOME}/.claude/projects/-home-ubuntu-synedre-os/memory/ et la pointer depuis MEMORY.md.\n\nRelancer le même git commit pour passer (anti-boucle : 2e tentative laissée passer)."}
EOF
exit 0
