#!/usr/bin/env bash
#
# hook-no-rebase-on-shared-branch.sh — Hook PreToolUse Bash.
#
# ENFORCE  : sur `synedre-os`, `preprod` est
# partagée par N sessions Claude simultanées (worktree unique) ET mergée sur `main`
# à chaque `./ship`. Un rebase y réécrit des SHA DÉJÀ PUBLIÉS sur origin/main →
# divergence main↔preprod pour un contenu identique.
#
# Scar 2026-07-17 : main et preprod au MÊME commit (4550bfc7f). Un
# `git pull --rebase` réflexe — déclenché par un simple push rejeté (Dependabot
# avait mergé une PR sur origin/preprod) — a rejoué 153 commits et réécrit leurs
# SHA. Divergence 152/154 commits pour un diff réel de 2 fichiers. Irréparable
# sans force-push sur une branche partagée par 3 sessions actives.
#
# Bloque : `git rebase`, `git pull --rebase|-r`, `git push --force|-f` — UNIQUEMENT
# quand la branche courante est partagée (preprod|main) et qu'on est dans le repo.
# Laisse passer : `git rebase --abort|--continue|--skip|--quit` (sortir d'un rebase
# en cours ne doit jamais être piégé), et tout rebase sur une branche de feature.
#
# Fail-open partout : toute erreur → exit 0. Ce hook ne piège JAMAIS une session.

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
  preprod|main) ;;   # branches partagées → on garde
  *) exit 0 ;;       # feature branch → rebase libre
esac

# Sortir d'un rebase en cours reste TOUJOURS autorisé (ne jamais piéger).
printf '%s' "$CMD" | grep -qE 'git[[:space:]]+rebase[[:space:]]+--(abort|continue|skip|quit)' && exit 0

# Débuts de commande uniquement (^, ;, &&, ||, |) — réduit les faux positifs sur
# le texte qui MENTIONNE la commande (heredoc, message de commit, doc).
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

BLOQUE — Réécriture d'historique sur branche partagée (doctrine )

  Tu tentes un \`${VIOLATION}\` sur \`${BRANCH}\`, partagée par N sessions Claude
  (worktree unique). Ses SHA sont DÉJÀ publiés sur origin/main via \`./ship\`
  (ship-prod.sh fait \`git merge preprod\`) : les réécrire fait diverger
  main↔preprod pour un contenu IDENTIQUE.

  Scar 2026-07-17 : un \`git pull --rebase\` réflexe sur un push rejeté a
  rejoué 153 commits et fait diverger main↔preprod de 152 commits — pour un diff
  réel de 2 fichiers. Irréparable sans force-push sur une branche à 3 sessions
  actives.

  Ce que tu dois faire — si ton push a été rejeté (non-fast-forward, typiquement
  une PR Dependabot mergée sur GitHub) :
    git fetch origin ${BRANCH}
    git log --oneline ${BRANCH}..origin/${BRANCH}   # VOIR ce qui manque en local
    git pull --no-rebase origin ${BRANCH}           # merge — surtout PAS --rebase
    git push origin ${BRANCH}

  Réécrire l'historique pour de bon = décision d'Alex, jamais un réflexe d'IA :
  expose-lui le coût et laisse-le trancher.

EOF
exit 2
