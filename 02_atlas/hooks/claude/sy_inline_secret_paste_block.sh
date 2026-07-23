#!/bin/bash
#
# hook-inline-secret-paste-block.sh — Hook PreToolUse Bash BLOQUANT (anti-leak inline).
#
# Matérialise la doctrine anti-leak secrets ( §"Anti-leak secrets" +
# doctrine des secrets 3 niveaux). Comble une CLASSE de cicatrices récurrente
# (#890 #827 #821 #774 #739 #735 #721, 7 occurrences P0/P1) : un agent bloqué
# par un environnement non sourcé (`PG_HOST inaccessible`, `.env pas chargé`)
# contourne en collant la VALEUR du secret directement dans la commande. Rapide
# à taper, désastreux pour la rotation des secrets (la valeur fuite dans le
# transcript, les logs, l'historique).
#
# Règle : on ne colle JAMAIS une valeur de secret inline. On source l'env :
#     set -a && . .env && . .env.host && set +a      puis on référence $VAR.
#
# Détection : la VALEUR (pas la référence $VAR, pas `grep ^VAR= .env`) d'une
# variable à nom sensible (PASS|PASSWORD|SECRET|KEY|TOKEN|PWD|CRED|API...) et de
# longueur >= 12 apparaît LITTÉRALEMENT (grep -F) dans la commande.
#
# Sécurité du hook lui-même : il lit des secrets mais ne les ré-échote JAMAIS —
# le message d'erreur ne cite QUE le NOM de la variable, jamais sa valeur.
#
# Fail-OPEN : toute erreur / parse KO / absence de .env → exit 0 (on ne bloque
# jamais une commande par accident). Blocage DUR (exit 2) uniquement sur match
# certain.
#
# Périmètre v1 + LIMITES CONNUES (revue Mitnick 2026-07-13, verdict clean-with-notes) :
#   - Sources : .env + .env.host (origine des 7 cicatrices). Les .env tenant
#     (codemyshop/tenants/<x>/.env, ~4 actifs : Stripe webhook…) NE sont PAS
#     couverts en v1 — extension future si récurrence.
#   - Gating par NOM sensible : une valeur sensible portée par une variable au
#     nom neutre (ex. chaîne de connexion NUXT_TENANT_DB_*) échappe au radar.
#   - Détection LITTÉRALE : contournable par encodage (base64/hex) ou split
#     multi-variables (A="ab"; B="cd"; …$A$B) — hors scope v1, assumé.
#   - Seuil de longueur = 8 (couvre les mots de passe live courts type
#     *_HUB_ADMIN_PASSWORD ; en-dessous = trop de faux positifs).
#   - NE JAMAIS invoquer ce hook sous `bash -x`/`-v` : la trace expanserait $val
#     (fuite). Le script lui-même ne s'auto-trace pas.

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

# Pas de commande lisible → ne pas gêner (fail-open).
[ -z "$COMMAND" ] && exit 0

MATCH_VAR=""
for ENV_FILE in "$REPO/.env" "$REPO/.env.host"; do
    [ -r "$ENV_FILE" ] || continue
    # IFS='=' → tout ce qui suit le premier '=' va dans val (valeurs avec '=' OK).
    # `|| [ -n "$name" ]` : SANS ça, la DERNIÈRE ligne d'un fichier sans saut de
    # ligne final n'est jamais traitée — `read` renvoie faux et `while` sort avant
    # d'exécuter le corps. Trouvé le 2026-07-17 (chantier #448) : .env fait 257
    # lignes dont la 257e, sans newline final, portait FACEBOOK_PASSWD — jamais
    # protégé. Un secret ajouté en fin de fichier (le geste le plus naturel qui
    # soit) échappait donc au radar en silence.
    while IFS='=' read -r name val || [ -n "$name" ]; do
        # Ignore commentaires, lignes vides, exports sans '='.
        case "$name" in ''|\#*) continue;; esac
        name=$(printf '%s' "$name" | sed 's/^[[:space:]]*export[[:space:]]*//; s/[[:space:]]*$//')
        # Ne cible que les variables à nom SENSIBLE (réduit les faux positifs).
        printf '%s' "$name" | grep -qiE '(PASS|PASSWORD|SECRET|KEY|TOKEN|PWD|CRED|API)' || continue
        # …mais une variable d'IDENTIFIANT ne porte pas de secret : un login, un
        # user, un email, un host ou un port s'écrivent en clair par nature. Le
        # gate ci-dessus les attrape par accident quand le nom contient "API"
        # (MISTRAL_API_LOGIN, POSTHOG_API_HOST, <TENANT>_<TENANT>_API_USER) — et
        # MISTRAL_API_LOGIN vaut l'email d'Alex, que  documente lui-même
        # en clair comme boîte canonique. Résultat : toute phrase citant son
        # adresse était bloquée. Un secret qui ne peut pas être un secret n'a rien
        # à faire dans le radar (faux positif constaté 2026-07-17, chantier #448).
        # `_ID` N'EST PAS exclu à dessein : AWS_ACCESS_KEY_ID reste armé (prudence
        # sur les clés AWS — un FP y est rare, un trou serait cher).
        if printf '%s' "$name" | grep -qiE '(_LOGIN|_USER|_USERNAME|_EMAIL|_FROM|_HOST|_PORT)$'; then
            continue
        fi
        # Normalise la valeur COMME LE SHELL LA VOIT, pas comme le texte l'écrit.
        # Trou pré-existant trouvé le 2026-07-17 (chantier #448) : 14 lignes de
        # .env/.env.host finissent par un ';' (SMTP_PASS, IMAP_PASSWORD,
        # N26_PASSWORD, <TENANT>_OVH_PASSWORD, <TENANT>_PASSWD, FACEBOOK_PASSWD…).
        # Le shell traite ce ';' comme un séparateur de commande et ne le met
        # JAMAIS dans la valeur ; le hook, lui, le lisait comme le dernier
        # caractère du secret. Les deux chaînes différaient d'un caractère → le
        # `grep -F` ci-dessous ne pouvait structurellement JAMAIS matcher, et ces
        # 14 secrets n'étaient pas protégés du tout. Le hook paraissait armé et ne
        # mordait pas — même famille que « branché ≠ marche ».
        # Ordre : espaces de fin → ';' → espaces → déquote (couvre `"val" ;`).
        val="${val%"${val##*[![:space:]]}"}"
        val="${val%;}"
        val="${val%"${val##*[![:space:]]}"}"
        # Déquote la valeur.
        val="${val%\"}"; val="${val#\"}"; val="${val%\'}"; val="${val#\'}"
        # Seuil anti-FP : valeur >= 8 chars, sans espace (couvre les mots de passe
        # live courts type *_HUB_ADMIN_PASSWORD ; en-dessous = trop de faux positifs).
        [ "${#val}" -lt 8 ] && continue
        case "$val" in *' '*) continue;; esac
        # La VALEUR apparaît-elle littéralement dans la commande ? (fixed-string)
        if printf '%s' "$COMMAND" | grep -qF -- "$val"; then
            MATCH_VAR="$name"
            break 2
        fi
    done < "$ENV_FILE"
done

if [ -n "$MATCH_VAR" ]; then
    # BLOQUE — ne JAMAIS échoter la valeur, seulement le nom de variable.
    cat >&2 << EOF

BLOQUÉ — valeur de secret collée inline (variable : $MATCH_VAR)

  La VALEUR d'un secret apparaît littéralement dans ta commande. Contourner un
  environnement non sourcé en collant la valeur est INTERDIT : elle fuite dans
  le transcript, les logs et l'historique, et casse la rotation des secrets
  (cicatrices #890 #827 #821 #774 #739 #735 #721).

  Ce que tu dois faire — sourcer l'env, puis référencer la VARIABLE :
    set -a && . $REPO/.env && . $REPO/.env.host && set +a
    ... \$$MATCH_VAR ...        # jamais la valeur en clair

  Référence :  §"Anti-leak secrets" — 1 doctrine = 1 hook.

EOF
    exit 2
fi

exit 0
