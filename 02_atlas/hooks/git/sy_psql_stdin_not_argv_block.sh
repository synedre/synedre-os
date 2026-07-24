#!/bin/bash
#
# hook-psql-stdin-not-argv-block.sh — Hook PreToolUse Edit|Write BLOQUANT.
#
# Matérialise l'invariant du test synedre/tests/test_psql_stdin_not_argv.py
# (jobsite psql-stdin-migration, #530) : le SQL destiné à psql passe par
# STDIN (input=sql), JAMAIS par argv ("-c", sql). L'erreur se voit À L'ÉCRITURE,
# pas en attendant le test — sinon la dette repousse
# ().
#
# SCAR (2026-07-20, run GLM #896) : `docker exec ... psql -c "<sql>"`
# fait porter tout le payload par la LIGNE DE COMMANDE. Au-delà d'ARG_MAX
# l'appel échoue en « Argument list too long » et l'event part à la poubelle
# EN SILENCE — le cockpit perdait exactement les GROS events (longues
# réponses d'agent, gros tool_result), sans qu'aucune alarme ne sonne.
# `input=sql` (stdin) n'a pas cette limite (mesuré : 400 k caractères OK).
#
# Migration soldée : les 41 appels `-c sql` des modules Python ont été
# réécrits vers `input=sql` (lots 1 et 2, #530). PLAFOND_ARGV_RESTANT = 0.
# Ce hook ferme la porte à la RÉINTRODUCTION : un appel neuf s'écrit en
# `input=sql`, point — on ne remonte pas le plafond.
#
# SCOPE — .py UNIQUEMENT, comme le test. Les appels psql des modules Node
# (.cjs, ex sy_figma_capture.cjs:sqlRead) restent en '-c', sql sur des
# requêtes de lecture bornées ; ils ne sont PAS concernés par ARG_MAX de la
# même façon et sont hors champ du jobsite. Étendre le hook à ces fichiers
# casserait ce garde pour un problème qu'il ne vise pas.
#
# CE QU'IL NE PEUT PAS GARDER : que le docker exec porte bien son flag -i
# (sans -i, input= rend rc=0 SANS rien faire — échec silencieux pire que -c).
# Ça, c'est le test TestStdinExigeLeFlagInteractif (analyse AST), pas un hook
# au moment de l'écriture.
#
# Échappatoire consciente : suffixer d'un `# psql-stdin:allow <raison>`.
#
# Fail-OPEN : toute erreur / parse KO / fichier non ciblé → exit 0.
# Blocage DUR (exit 2) sur match certain.

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

# Pas de contenu lisible ou pas de fichier ciblé → ne pas gêner (fail-open).
[ -z "$CONTENT" ] && exit 0
[ -z "$FILE" ] && exit 0

# Scope : .py uniquement (cohérent avec le test, exclut les .cjs Node).
case "$FILE" in
    *.py) ;;
    *) exit 0 ;;
esac

# Le gardien n'est pas soumis à sa propre garde : le fichier de test doit
# pouvoir NOMMER le pattern (dans sa regex et sa docstring) pour le détecter.
case "$FILE" in
    *test_psql_stdin_not_argv.py) exit 0 ;;
esac

# Échappatoire assumée et tracée.
case "$CONTENT" in *"psql-stdin:allow"*) exit 0 ;; esac

# Normalise TOUS les whitespaces (espaces ET newlines) — la forme idiomatique
# Python est la liste multi-ligne `["-c",\n sql]`. On rejoint ainsi la regex
# `["\']-c["\']\s*,\s*sql` du test où \s* mange aussi les sauts de ligne.
NOSP=$(printf '%s' "$CONTENT" | tr -d '[:space:]')

HIT=""
case "$NOSP" in
    *'"-c",sql'*) HIT='"-c", sql' ;;
    *"'-c',sql"*) HIT="'-c', sql" ;;
esac

if [ -n "$HIT" ]; then
    cat >&2 << EOF

BLOQUÉ — SQL passé à psql par argv ($FILE)

  Trouvé : $HIT

  Au-delà d'ARG_MAX, l'appel « docker exec ... psql -c "<sql>" » échoue en
  « Argument list too long » et le payload est perdu EN SILENCE. Ce sont
  précisément les GROS payloads qui sautent (run GLM #896, 2026-07-20) —
  personne ne le voyait puisque c'était un simple warning stderr noyé.

  La migration vers STDIN est soldée (lots 1 et 2, #530) : zéro appel
  « -c sql » ne subsiste dans les modules Python. Ce hook refuse la
  RÉINTRODUCTION — on ne remonte pas le plafond.

  À faire — alimenter psql par stdin :
      proc = subprocess.run(_PSQL + ["-U", user, "-d", db],
                            input=sql,    # ← stdin, pas argv
                            stdout=PIPE, stderr=PIPE, ...)
  Et EXIGER « docker exec -i » (sans -i, input= rend rc=0 SANS RIEN FAIRE —
  voir le test TestStdinExigeLeFlagInteractif dans
  synedre/tests/test_psql_stdin_not_argv.py).

  Cas .cjs légitime hors champ ? (lecture bornée Node, ex sqlRead) : ce hook
  ne cible QUE les .py. Ne pas l'étendre pour faire passer un cas Python —
  écris plutôt input=sql.

  Besoin réel et conscient ? suffixe la ligne : # psql-stdin:allow <raison>

  Référence : test_psql_stdin_not_argv.py · 
  (1 doctrine = 1 hook — l'erreur se voit à l'écriture, pas au test).

EOF
    exit 2
fi

exit 0
