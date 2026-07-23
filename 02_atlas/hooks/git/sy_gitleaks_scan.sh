#!/bin/bash
#
# hook-gitleaks-scan.sh — Scanner de secrets self-contained (gitleaks absent).
#
# Enforce la doctrine anti-leak #673 À L'ÉCRITURE : scanne les LIGNES AJOUTÉES du
# diff stagé pour des VALEURS de secret en clair (mots de passe DB, 64-hex PG,
# connection strings, clés privées, tokens/clés API, clés AWS). Exit 1 + liste
# (valeurs REDACTÉES) si fuite. Née de la revue Mitnick #422 : mdp PG prod payante
# <TENANT> en clair git-tracké, non détecté car la section 2 ne checkait que les
# NOMS de fichiers, pas le contenu.
#
# Échappatoire volontaire : suffixe `# gitleaks:allow <raison>` sur la ligne
# (faux positif légitime, ex fixture de test).
set -uo pipefail

# Diff stagé, lignes ajoutées seulement ; exclut binaires / templates / locks.
DIFF=$(git diff --cached -U0 --no-color -- . \
  ':(exclude)*.example' ':(exclude)*.lock' ':(exclude)*.jpg' ':(exclude)*.jpeg' \
  ':(exclude)*.png' ':(exclude)*.gif' ':(exclude)*.webp' ':(exclude)*.pdf' \
  ':(exclude)*.min.js' ':(exclude)*.map' 2>/dev/null \
  | grep -E '^\+' | grep -vE '^\+\+\+' || true)

[ -z "$DIFF" ] && exit 0

# Lectures d'env / placeholders / échappatoire → jamais un secret en clair.
ALLOW='os\.environ|process\.env|getenv|import os|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|CHANGE_?ME|change-me|<[a-z0-9_-]+>|xxxx+|placeholder|example|your-|REDACTED|\*\*\*|gitleaks:allow'

FOUND=0
flag() {
  # $1 = type ; $2 = ligne. Redacte tout token >=12 chars avant d'imprimer.
  local safe
  safe=$(printf '%s' "$2" | sed -E 's/[A-Za-z0-9/+=_!@#$%^&*.:-]{12,}/<REDACTED>/g' | cut -c1-110)
  echo "  ✗ FUITE [$1] : ${safe#+}"
  FOUND=1
}

while IFS= read -r line; do
  printf '%s' "$line" | grep -qiE "$ALLOW" && continue
  printf '%s' "$line" | grep -qiE "(password|passwd|[^a-z]pwd|[^a-z]pass)\s*[:=]>?\s*['\"][^'\"]{6,}['\"]" && flag "mot-de-passe" "$line" && continue
  printf '%s' "$line" | grep -qE "(PG|POSTGRES|MYSQL|MARIADB|DB|REDIS)_?PASS(WORD)?\s*=\s*['\"]?[A-Za-z0-9!@#%_-]{8,}" && flag "db-password" "$line" && continue
  printf '%s' "$line" | grep -qE "PGPASSWORD=[0-9a-f]{64}|['\"][0-9a-f]{64}['\"]" && flag "pg-secret-hex" "$line" && continue
  printf '%s' "$line" | grep -qiE "(postgres|postgresql|mysql|mariadb|redis|mongodb)://[^:@/]+:[^@/[:space:]]{4,}@" && flag "connection-string" "$line" && continue
  printf '%s' "$line" | grep -qE "BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY" && flag "cle-privee" "$line" && continue
  printf '%s' "$line" | grep -qE "AKIA[0-9A-Z]{16}" && flag "aws-key" "$line" && continue
  printf '%s' "$line" | grep -qiE "(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|bearer)\s*[:=]>?\s*['\"][A-Za-z0-9_/+=.-]{20,}['\"]" && flag "token/apikey" "$line" && continue
done <<< "$DIFF"

if [ "$FOUND" = 1 ]; then
  echo ""
  echo "  ══ COMMIT BLOQUÉ — secret en clair dans le diff stagé (doctrine anti-leak #673) ══"
  echo "  → Externalise la valeur : os.environ / process.env / \$VAR, la valeur vit dans .env* (gitignoré)."
  echo "  → Faux positif légitime ? suffixe la ligne avec '# gitleaks:allow <raison>'."
  exit 1
fi
exit 0
