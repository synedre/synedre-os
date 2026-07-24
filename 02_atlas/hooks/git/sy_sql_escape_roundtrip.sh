#!/bin/bash
#
# hook-sql-escape-roundtrip.sh — Hook PreToolUse Edit|Write BLOQUANT.
#
# Matérialise  : en PostgreSQL
# (standard_conforming_strings = on, vérifié), l'antislash dans un littéral est DÉJÀ
# littéral — `'a\b'` vaut a\b. Le doubler AJOUTE un antislash au lieu d'en protéger un.
#
# SCAR (jobsite #466, 2026-07-17) : `synedre/sy_entities/base.py:_esc` faisait
# `.replace("\\", "\\\\")` — un réflexe MariaDB (où l'antislash EST un échappement),
# hérité d'avant le drop de MariaDB le 2026-04-30. Résultat : TOUTES les écritures
# d'entités corrompaient silencieusement les valeurs contenant un antislash. Aller-retour
# mesuré : 3 cas cassés sur 5 (JSON+guillemets +2 car., chemin Windows +3, regex +2).
# 30 champs illisibles en base (discoveries_json, decisions_json, context_json) — les
# colonnes étant TEXT, PG ne validait rien : la corruption a passé des mois sans un bruit.
#
# Ce hook garde la REPRISE du réflexe : « échapper l'antislash » se re-tape tout seul,
# c'est un automatisme de développeur MySQL/MariaDB.
#
# Ce qu'il NE peut pas garder : que l'aller-retour ait été réellement joué. Ça, c'est la
# discipline de la doctrine (écrire → relire → comparer sur antislash, guillemet,
# apostrophe, JSON imbriqué) — un hook ne peut pas prouver un test à ta place.
#
# Échappatoire consciente : suffixer d'un `# sql-escape:allow <raison>`.
#
# Fail-OPEN : toute erreur / parse KO → exit 0. Blocage DUR (exit 2) sur match certain.

set -uo pipefail

INPUT=$(cat)

CONTENT=""
FILE=""
if command -v jq >/dev/null 2>&1; then
    FILE=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
    # Edit -> new_string ; Write -> content ; MultiEdit -> concat des edits.
    CONTENT=$(printf '%s' "$INPUT" | jq -r '
        [ .tool_input.new_string?, .tool_input.content?,
          (.tool_input.edits? // [] | .[]?.new_string?) ]
        | map(select(. != null)) | join("\n")
    ' 2>/dev/null)
fi

# Pas de contenu lisible ou pas un fichier ciblé → ne pas gêner (fail-open).
[ -z "$CONTENT" ] && exit 0
[ -z "$FILE" ] && exit 0
case "$FILE" in
    *.py|*.ts|*.js|*.mjs|*.cjs) ;;
    *) exit 0 ;;
esac

# Échappatoire assumée et tracée.
case "$CONTENT" in *"sql-escape:allow"*) exit 0 ;; esac

# Normalise les espaces pour attraper les variantes de formatage.
NOSP=$(printf '%s' "$CONTENT" | tr -d ' ')

HIT=""
# Python / JS : doublement d'antislash dans un replace.
case "$NOSP" in
    *'replace("\\","\\\\")'*)   HIT='replace("\\", "\\\\")' ;;
    *"replace('\\\\','\\\\\\\\')"*) HIT="replace('\\\\', '\\\\\\\\')" ;;
    *'replaceAll("\\","\\\\")'*) HIT='replaceAll("\\", "\\\\")' ;;
esac

if [ -n "$HIT" ]; then
    cat >&2 << EOF

BLOQUÉ — doublement d'antislash dans un échappement SQL ($FILE)

  Trouvé : $HIT

  En PostgreSQL, l'antislash NE s'échappe PAS. La base tourne en
  standard_conforming_strings = on : un antislash dans un littéral est DÉJÀ
  littéral ('a\\b' vaut a\\b). Le doubler AJOUTE un antislash — il ne protège rien.

  C'est un réflexe MariaDB (où l'antislash EST un caractère d'échappement).
  MariaDB a été droppé le 2026-04-30. Ce même réflexe a corrompu 30 champs en
  base pendant des mois, sans un bruit : les colonnes sont TEXT, PG ne valide
  rien, et personne ne relisait (jobsite #466).

  À faire — n'échapper QUE l'apostrophe :
    s = str(value).replace("'", "''")
    return f"'{s}'"

  Puis PROUVER par aller-retour (écrire -> relire -> comparer) sur les cas qui
  mordent : antislash, guillemet, apostrophe, apostrophe+antislash, JSON imbriqué.
  Ne conclus jamais par lecture du code — c'est ce qui a laissé passer l'original.

  Besoin réel et conscient ? suffixe la ligne : # sql-escape:allow <raison>

  Référence :  — 1 doctrine = 1 hook.

EOF
    exit 2
fi

exit 0
