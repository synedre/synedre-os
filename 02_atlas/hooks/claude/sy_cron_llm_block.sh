#!/bin/bash
#
# hook-cron-llm-block.sh — Hook PreToolUse Bash BLOQUANT (LLM en cron = drain forfait).
#
# Matérialise la doctrine  (jobsite #506,
# session anti-drain du 2026-07-19). Un script qui consomme du LLM (claude -p /
# sy_ai_provider.complete / invoke_agent / spawn node-pty) enregistré en crontab
# draine le forfait Claude EN SILENCE : le coût est invisible jusqu'au plafond
# hebdomadaire. Le déclencheur du 2026-07-19 : sy_jobsite_readiness_audit --enrich
# balayait TOUT le backlog toutes les 20 min via claude -p. Retiré et passé en
# on-demand (--only) le jour même — ce hook empêche la RÉINTRODUCTION.
#
# RÈGLE : un script LLM ne s'installe pas en cron. Le LLM interne s'appelle À LA
# DEMANDE (au moment où on en a besoin), jamais sur une horloge.
#
# DÉTECTION : la commande installe un crontab (`crontab -`, `crontab <fichier>`,
# `crontab -e`, `… | crontab -`) ET une de ses lignes cron NON commentée invoque
# un script qui (analyse STATIQUE du fichier résolu) appelle un LLM, OU contient
# un `claude -p` en dur. Le parseur de lignes cron est calqué sur
# hook-cron-relative-path-block.sh (même squelette, pas de second parseur divergent).
#
# MOTEUR PARTAGÉ — 1 doctrine = 1 hook ().
# La logique de détection vit inline historiquement ; elle est extraite dans
# synedre/sy_cron_llm_detector.py (2026-07-21), module partagé avec la sentinelle
# sy_audit_cron_llm.py. Ce hook n'est plus qu'un fin wrapper Bash : il extrait la
# commande du payload, la passe au module, et bloque sur la 1ère violation.
# Les deux gardes ne peuvent pas diverger ().
#
# PORTES DE SORTIE conscientes (gérées par le module) :
#   1. Allow-list nominative : synedre/config/cron_llm_allowlist.yaml (défaut vide).
#   2. Marqueur en fin de ligne cron : `# cron-llm:allow <raison>`.
#
# FAIL-OPEN : payload/parse KO → exit 0. Blocage (exit 2) sur match LLM CERTAIN.
# Un garde-fou qui casse tout se fait désactiver — on ne bloque que le sûr.

set -uo pipefail

# Overridable pour les tests (défaut = repo live canonique).
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

# Ne se déclenche que si la commande a affaire au crontab.
printf '%s' "$CMD" | grep -qE '\bcrontab\b' || exit 0

# Lecture seule (`crontab -l` sans installation) → laisser passer.
if printf '%s' "$CMD" | grep -qE '\bcrontab[[:space:]]+-l\b' \
   && ! printf '%s' "$CMD" | grep -qE '\bcrontab[[:space:]]+(-|-e|[^[:space:]-][^[:space:]]*)([[:space:]]|$)'; then
    exit 0
fi

# Délègue la détection au moteur partagé. Format : KIND|stem|path|line
# (stem/path vides pour CLAUDE_P_INLINE). Fail-open : tout échec → vide → exit 0.
VIOLATION="$(CRON_HOOK_CMD="$CMD" CRON_HOOK_REPO="$REPO" PYTHONPATH="$REPO" python3 - <<'PY' 2>/dev/null || true
import os
from pathlib import Path
from synedre.sy_cron_llm_detector import detect_llm_cron_violations

repo = Path(os.environ.get("CRON_HOOK_REPO", "${SYNEDRE_ROOT}"))
cmd = os.environ.get("CRON_HOOK_CMD", "")
v = detect_llm_cron_violations(cmd, repo=repo)
if v:  # le hook ne veut que la 1ère ; la sentinelle prend les autres
    x = v[0]
    print("|".join((x.kind, x.stem, x.script_path, x.line)))
PY
)"

[ -z "$VIOLATION" ] && exit 0

KIND="${VIOLATION%%|*}"

if [ "$KIND" = "CLAUDE_P_INLINE" ]; then
    LINE="${VIOLATION#*|}"
    DETAIL="Cette ligne appelle \`claude -p\` DIRECTEMENT."
    WHICH=""
else
    REST="${VIOLATION#*|}"          # <stem>|<path>|<cmd>
    STEM="${REST%%|*}"; REST="${REST#*|}"
    SPATH="${REST%%|*}"; LINE="${REST#*|}"
    DETAIL="Le script invoqué \`${STEM}\` consomme du LLM (analyse statique de ${SPATH})."
    WHICH="  Script fautif : ${SPATH}"
fi

cat >&2 << EOF

BLOQUÉ — installation d'un script LLM en cron (drain silencieux du forfait)

  Ligne de cron fautive :
    ${LINE}

  ${DETAIL}
${WHICH}

  POURQUOI C'EST BLOQUÉ : un LLM récurrent en crontab draine le forfait Claude
  EN SILENCE — le coût n'apparaît nulle part avant le plafond hebdomadaire. Le
  2026-07-19, sy_jobsite_readiness_audit --enrich balayait TOUT le backlog via
  claude -p toutes les 20 min. La règle depuis : le LLM interne s'appelle À LA
  DEMANDE (au moment d'en avoir besoin), jamais sur une horloge.

  CE QU'IL FAUT FAIRE :
    • Rends l'appel LLM ON-DEMAND (ex : readiness_audit --only <codename> lancé
      au moment où on veut armer un jobsite, pas en cron).
    • OU garde en cron la partie DÉTERMINISTE seulement (verdict/scan sans LLM).

  SI C'EST VRAIMENT UN CHOIX CONSCIENT (ex worker event-driven qui no-op quand
  la queue est vide) :
    • Ajoute le script à synedre/config/cron_llm_allowlist.yaml (avec sa raison),
    • OU suffixe la ligne de cron de : # cron-llm:allow <raison>

  Référence :  — 1 doctrine = 1 hook.

EOF
exit 2
