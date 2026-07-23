#!/usr/bin/env bash
# hook-stop-uncommitted-warn.sh — événement Stop
#
# BLOQUANT : si la worktree git contient des changes non-committés à la fin
# d'une session, refuse le Stop et force Claude à commiter. Applique la
# doctrine  « Commit en flux » : aucun travail terminé ne reste
# uncommitted.
#
# Session-aware (depuis 2026-05-21) : si la session a un fichier de tracking
# `.claude/session-<id>-edited.txt` (alimenté par hook-track-session-edits.py
# sur PostToolUse Edit|Write|MultiEdit|NotebookEdit), on filtre le dirty
# list pour ne garder que les fichiers DE CETTE SESSION. Permet le
# parallélisme multi-sessions Claude sans blocage croisé.
#
# Garde-fou anti-boucle : si stop_hook_active=true (le hook a déjà bloqué
# une fois et Claude a re-demandé Stop), on laisse passer en warning. Sinon
# Claude pourrait être piégé en boucle s'il ne peut pas commiter.
#
# Exclusion : .claude/settings.json modifié pendant la session (le hook
# lui-même peut avoir édité ce fichier).
#
# Sortie :
#   - clean OR pas de fichier MIEN dirty → exit 0 silencieux
#   - dirty MIEN + 1ère passe → JSON {"decision":"block","reason":"..."} (bloque)
#   - dirty MIEN + 2e passe   → JSON {"systemMessage":"..."} (warn non-bloquant)

set -uo pipefail
cd ${SYNEDRE_ROOT} 2>/dev/null || exit 0

# Worker context early-return : si ce hook est déclenché dans un sous-claude
# spawné par sy_task_worker.py (SY_WORKER_CONTEXT=sy_task_worker injecté par
# atlas-spawn-claude.mjs, commit Brunel #421), on sort silencieusement.
# Le worker gère lui-même le cycle commit en fin de run — le sous-claude ne
# doit pas commiter (doctrine commit-en-flux réservée aux sessions utilisateur).
# Cicatrice 2026-05-23 #3 (chantier #94) : sans ce guard, 100+ events hook_*
# identiques bloquaient le sous-claude sans rien produire.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/is-worker-context.sh
source "${SCRIPT_DIR}/lib/is-worker-context.sh" 2>/dev/null || true
is_worker_context && exit 0

# Lecture stdin (Claude Code envoie {"stop_hook_active": bool, "session_id": "...", ...})
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

# Filtre session-aware : si fichier de tracking existe, ne garder que les
# fichiers édités PAR CETTE SESSION (les autres = WIP d'une session sœur).
#
# Cas zéro-édition (cicatrice 2026-05-27) : une session trackée qui n'a fait
# AUCUN Edit/Write (travail 100% DB / lecture) n'a pas de log d'édition. Sans
# guard, le test `[ -f "$edited_log" ]` était faux, le filtre shunté, et la
# session héritait du dirty GLOBAL (WIP des sessions sœurs partageant la même
# worktree) → faux blocage. Pas de log = zéro fichier à elle → on sort.
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
    # Format porcelain : 'XY path' ou '?? path', path peut être quoté si espaces
    parts = line.split(None, 1)
    if len(parts) < 2:
        continue
    path = parts[1].strip().strip('\"')
    # Pour les renames 'R  old -> new', on prend le new
    if ' -> ' in path:
        path = path.split(' -> ', 1)[1].strip().strip('\"')
    if path in tracked:
        out.append(line)
print('\n'.join(out))
" 2>/dev/null || printf '%s' "$dirty")
 else
  # Session trackée sans log d'édition = zéro Edit/Write ce run → aucun
  # fichier ne lui appartient. Ne pas hériter du WIP des sessions sœurs.
  dirty=""
 fi
 if [ -z "$dirty" ]; then
   # Worktree dirty mais aucun fichier de ma session → OK, autres sessions
   # ont du WIP qui n'est pas mon problème.
   exit 0
 fi
fi

# Échapper pour JSON (newlines → \n, quotes → \")
escaped=$(printf '%s' "$dirty" | python3 -c 'import sys, json; print(json.dumps(sys.stdin.read()))')
# escaped contient les guillemets englobants ; les retirer pour interpolation
inner=${escaped:1:-1}

if [ "$stop_hook_active" = "true" ]; then
  # 2e passage : ne pas re-bloquer (anti-boucle infinie). Warn seulement.
  cat <<EOF
{"systemMessage": "⚠️  Stop forcé alors que worktree dirty (anti-boucle) :\n${inner}\nCommiter manuellement à la prochaine session."}
EOF
  exit 0
fi

# 1ère passe : BLOQUE le Stop et instruit Claude de commiter
cat <<EOF
{"decision": "block", "reason": "Doctrine  « Commit en flux » : travail non-committé interdit en fin de session.\n\nFichiers dirty (de cette session) :\n${inner}\n\nAction requise : commiter (1 chantier = 1 commit cohérent) PUIS rendre la main. Si la worktree contient du WIP volontaire, le déclarer explicitement dans la réponse avant Stop."}
EOF
exit 0
