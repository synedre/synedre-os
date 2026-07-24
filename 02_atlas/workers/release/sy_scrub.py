#!/usr/bin/env python3
"""
sy_scrub.py — transforms source text into a publish-safe OSS form.

Pure functions, idempotent. This is the "scrub" stage of the release pipeline:

    sy_extract  ->  sy_scrub  ->  stage  ->  sy_leak_gate  ->  sy_publish_audit

Doctrine (scar #618 / ADR-0001): scrub the SOURCE, then write — never scrub
the output. The writer (sy_extract) reads publish-whitelist.txt, scrubs each
listed file with scrub_text(), and writes the dest. A leak gate then checks the
staged output regardless, and publishing is never autonomous.

Transforms (order matters — see scrub_text):
  1. strip proprietary headers  (@author / @copyright / @owner / @mort /
     @license Propriétaire) — the 416-file monolith header that must never ship.
  2. strip private-memory refs  ([[feedback_*]] brain links, CLAUDE.md) — local
     only; a CLAUDE.md reference is a broken link here (gitignored in this repo).
  3. scrub tenant codenames     (substring, case-insensitive -> <TENANT>,
     denylist-driven). Substring, not '\\b' — 'palimex_v2' must not slip past
     '\\bpalimex\\b'.
  4. relativize absolute paths  (/home/ubuntu/synedre-os -> ${SYNEDRE_ROOT},
     then /home/ubuntu -> ${HOME}). SYNEDRE_ROOT before HOME.
  5. rename schema vocabulary   (vaisseau_mere_ac / vaisseau_mere /
     mother_ship / mothership -> shyrka), everywhere incl. comments. Documented
     at PUBLIC_SCHEMA; a separate pass because '_ac' suffix evades prefixes.
  6. rename proprietary prefixes (ps_ac_ -> sy_ BEFORE ac_ -> sy_; kebab
     ac- -> sy-). Lookbehind keeps mid-word 'ac' (mac_os) intact.
 6b. remap import paths        (packaged monolith imports -> flat OSS module
     names: synedre.sy_entities.base -> sy_entity_base). Runs right after the
     prefix rename because the map keys are POST-rename; extracted facades
     import each other FLAT (from sy_env import ...), resolved by sys.path at
     install time. Unknown paths are left as-is (fail-safe: a documented
     dangling lazy import beats a wrong guess).
  7. strip pg_dump artifacts    (banner / \\restrict nonce / version lines /
     SET block / set_config) — pg_dump 16 boilerplate; the \\restrict nonce is
     an ephemeral token that must never ship. Line-anchored, no-op on prose.
  8. translate SQL messages     (curated exact-string map: the FR RAISE
     EXCEPTION texts and in-function comments of the engine functions -> EN).
     Runs BEFORE the lexicon pass so the FR keys still match; identifiers
     inside the EN values are then renamed by the lexicon pass.
  9. translate lexicon          (FR building-trade vocabulary -> EN, decided
     2026-07-24: chantier->jobsite, travail->work_order, tache->task,
     cicatrice->scar, conduite->playbook; agent stays agent). Word-level,
     longest-first, snake_case-aware boundaries (underscore is a boundary,
     accented letters are not — 'detache' / 'moustache' stay intact).
 10. translate DB comments      (curated overlay comments-en.json). FAIL-CLOSED:
     when a map is provided, every COMMENT ON is either replaced by its curated
     EN text or DROPPED — unreviewed FR prose never ships. map=None = no-op
     (the facade path; facades carry no COMMENT ON).
 11. translate prose            (curated overlay prose-en.json: exact FR
     comment/docstring/message blocks -> EN). Runs LAST — the keys are curated
     from the STAGED output, so they carry post-rename identifiers and
     post-lexicon vocabulary. Unknown FR prose survives this pass and is then
     caught by the gate's accents check (fail-closed at the gate, not here:
     inline prose cannot be dropped without dropping code).

Scope: structure, not secrets. Secrets are NOT scrubbed here — they must FAIL at
the gate and demand human action, never be silently redacted into a publish.

Verified by test_scrub_mutation.py (mutation + integration layers). Filenames in
this repo are English-only (CLAUDE.md Rule 1).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TENANT_PLACEHOLDER = "<TENANT>"
SYNEDRE_ROOT_VAR = "${SYNEDRE_ROOT}"
HOME_VAR = "${HOME}"

# Neutral-by-default: the REAL monolith path map / schema tokens / SQL messages
# never live as Python literals in this shipped file (T3.4 publish-readiness —
# they used to, which was a residual vocabulary leak carrying Alex's own home
# path). They live in sy_private_config.json (gitignored), loaded by the CALLER
# (sy_extract.main / sy_leak_gate.main) and passed in as explicit overrides —
# same pattern as the codename denylist. Empty here means "no-op unless the
# caller supplies a config": correct for anyone else's monolith, and the gate
# reads the SAME private config, so there is no observation gap for Alex's own
# runs (see resolve_private_config_path).
_DEFAULT_PATH_MAP: tuple = ()


def resolve_private_config_path(preferred: Path | str) -> Path:
    """Return the private release config to use: the real (gitignored) file if
    present, else the shipped .example template — mirrors resolve_denylist_path.
    The real file holds YOUR monolith's path map / schema tokens / SQL messages
    and is private (CLAUDE.md Rule 3); the example carries neutral placeholders."""
    pref = Path(preferred)
    if pref.is_file():
        return pref
    example = pref.with_suffix(pref.suffix + ".example")
    if example.is_file():
        return example
    raise FileNotFoundError(f"no private config at {pref} (nor {example})")


def load_private_config(path: Path | str) -> dict:
    """Read the private release config (JSON: path_map / schema_tokens /
    sql_messages). Missing keys default to empty — a config that only overrides
    one axis (e.g. just schema_tokens) is valid."""
    import json

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        "path_map": [tuple(p) for p in data.get("path_map", [])],
        "schema_tokens": list(data.get("schema_tokens", [])),
        "sql_messages": [tuple(p) for p in data.get("sql_messages", [])],
    }


# ---- 1. proprietary headers -------------------------------------------------
_HEADER_TAGS = ("author", "copyright", "owner", "mort")
_HEADER_LINE_RE = re.compile(
    r"^[ \t]*[#\"']*[ \t]*@(?:" + "|".join(_HEADER_TAGS) + r")\b[^\n]*\n?",
    re.MULTILINE,
)
_LICENSE_PROP_RE = re.compile(
    r"^[ \t]*[#\"']*[ \t]*@license[ \t]+Propri[^\n]*\n?",
    re.MULTILINE | re.IGNORECASE,
)


def strip_proprietary_headers(text: str) -> str:
    """Drop @author/@copyright/@owner/@mort lines and @license Propriétaire lines.

    Matches bash comments (#), Python docstrings and bare header lines alike —
    the leading quote/comment prefix is optional in the pattern.
    """
    text = _HEADER_LINE_RE.sub("", text)
    text = _LICENSE_PROP_RE.sub("", text)
    return text


# ---- 2. private refs --------------------------------------------------------
_MEMORY_LINK_RE = re.compile(r"\[\[[a-zA-Z0-9_]+\]\]")
_CLAUDEMD_RE = re.compile(r"CLAUDE\.md", re.IGNORECASE)
# A line that is nothing but a pointer to the private brain/ moat (gitignored,
# never shipped) — a docstring/comment line like 'brain/inbox/2026-...-note.md.'.
# Dropped whole: the leading comment/quote prefix is optional, the trailing
# punctuation is swallowed. brain/ paths are never valid in the OSS tree.
_BRAIN_LINE_RE = re.compile(
    r"^[ \t]*[#\"'*]*[ \t]*brain/[^\n]*\n?", re.MULTILINE)
# Any residual inline brain/ path token (mid-sentence reference), stripped to
# nothing so a dangling private pointer never survives.
_BRAIN_INLINE_RE = re.compile(r"brain/[A-Za-z0-9_][A-Za-z0-9_./-]*")


def strip_private_refs(text: str) -> str:
    """Remove references to the private brain ([[feedback_*]] links, bare
    brain/ paths) and to the local-only CLAUDE.md (gitignored in this repo -> a
    broken link if kept). brain/ is the private moat: any reference to it in
    shipped code is a dead pointer at best, a leak at worst."""
    text = _MEMORY_LINK_RE.sub("", text)
    text = _CLAUDEMD_RE.sub("", text)
    text = _BRAIN_LINE_RE.sub("", text)
    text = _BRAIN_INLINE_RE.sub("", text)
    return text


# ---- 3. codenames -----------------------------------------------------------
def load_denylist(path: Path | str) -> list[str]:
    """Read the codename denylist. One token per line; '#' and blank lines are
    ignored. Order in the file does not matter — scrub_codenames sorts
    longest-first when matching."""
    tokens: list[str] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tokens.append(line)
    return tokens


def resolve_denylist_path(preferred: Path | str) -> Path:
    """Return the denylist to use: the real (gitignored) file if present, else
    the shipped .example template. The real file holds YOUR tenant codenames and
    is private (CLAUDE.md Rule 3); the example carries only neutral placeholders."""
    pref = Path(preferred)
    if pref.is_file():
        return pref
    example = pref.with_suffix(pref.suffix + ".example")
    if example.is_file():
        return example
    raise FileNotFoundError(f"no denylist at {pref} (nor {example})")


def scrub_codenames(text: str, denylist: list[str]) -> str:
    """Replace any tenant codename (substring, case-insensitive) with <TENANT>.

    Tokens are matched longest-first so 'smokevapeshop' wins over 'smoke' when
    both are substrings (sorted here, so any caller-supplied list is safe).
    Substring deliberately, not '\\b': 'palimex_v2' would slip past '\\bpalimex\\b'.
    Accept false positives (e.g. the common word 'smoke') over a real leak.
    """
    for token in sorted(denylist, key=len, reverse=True):
        if not token:
            continue
        text = re.sub(re.escape(token), TENANT_PLACEHOLDER, text, flags=re.IGNORECASE)
    return text


# ---- 4. paths ---------------------------------------------------------------
def relativize_paths(text: str, path_map=None) -> str:
    """Turn absolute paths into env-relative ones. *path_map* is an iterable of
    (literal, replacement) pairs applied in order, so list the longest/most-
    specific first ('/home/ubuntu/synedre-os' before '/home/ubuntu'). Defaults
    to the monolith literals; neutral tests pass their own map."""
    for literal, var in (path_map if path_map is not None else _DEFAULT_PATH_MAP):
        text = text.replace(literal, var)
    return text


# ---- 5. prefixes ------------------------------------------------------------
_PS_AC_RE = re.compile(r"(?<![A-Za-z0-9])ps_ac_")
_AC_RE = re.compile(r"(?<![A-Za-z0-9])ac_")
_AC_KEBAB_RE = re.compile(r"(?<![A-Za-z0-9])ac-")


# The public canonical name for the monolith's private PG schema. 'vaisseau_mere'
# (FR: mothership) is Alex's private schema; in the OSS it is the engine's own
# schema, named after the neutral engine dir core/shyrka/. A FIXED public name
# (not an env var) — Alex's call, 2026-07-23.
PUBLIC_SCHEMA = "shyrka"
# The private vocabulary to collapse into PUBLIC_SCHEMA (T3.4: moved to
# sy_private_config.json, see resolve_private_config_path / load_private_config
# above — the .example ships a neutral placeholder). Empty by default: a
# no-op unless the caller supplies a config, same rationale as _DEFAULT_PATH_MAP.
_DEFAULT_SCHEMA_TOKENS: tuple = ()


def scrub_schema_namespace(text: str, schema_tokens=None) -> str:
    """Rename the private mothership/schema vocabulary to 'shyrka'.

    'vaisseau_mere_ac' ends in '_ac' (not 'ac_'), so rename_prefixes can't catch
    it (rename_prefixes matches the 'ac_' prefix, not an '_ac' suffix). This pass
    collapses the WHOLE private vocabulary — 'vaisseau_mere_ac' / 'vaisseau_mere'
    (FR) and 'mother_ship' / 'mothership' (EN) — into PUBLIC_SCHEMA ('shyrka'),
    everywhere in the text including comments. *schema_tokens* defaults to the
    monolith tokens; neutral tests pass their own. Sorted longest-first so the
    '_ac' suffix / '_db' suffix is taken whole before the bare root.
    """
    tokens = schema_tokens if schema_tokens is not None else _DEFAULT_SCHEMA_TOKENS
    for tok in sorted(tokens, key=len, reverse=True):
        text = text.replace(tok, PUBLIC_SCHEMA)
    return text


def rename_prefixes(text: str) -> str:
    """Rename proprietary prefixes to the public 'sy_' namespace.

    ps_ac_ runs before ac_ (else 'ps_ac_foo' -> 'ps_sy_foo', stranded). The
    lookbehind (not alnum before) keeps mid-word 'ac' intact ('mac_os').
    """
    text = _PS_AC_RE.sub("sy_", text)
    text = _AC_RE.sub("sy_", text)
    text = _AC_KEBAB_RE.sub("sy-", text)
    return text


# ---- 6b. import paths (packaged monolith -> flat OSS) ------------------------
# The renames above fix module NAMES (ac_env -> sy_env) but not module PATHS: a
# monolith import like `from synedre.ac_entities.base import X` comes out of
# rename_prefixes as `from synedre.sy_entities.base import X` — a package path
# that exists nowhere in the OSS tree (the facades live flat in core/shyrka/ and
# the pillar dirs, resolved by sys.path at install time). This pass remaps each
# known packaged path to its flat OSS module name. Keys are POST-rename (the
# pass runs right after rename_prefixes). One entry per extracted module that
# is imported somewhere; unknown paths survive untouched — fail-safe, a dangling
# lazy import is documented in publish-whitelist.txt rather than guessed at.
_DEFAULT_IMPORT_MAP = (
    # one entry per extracted module (mechanical rule: extract a module, add
    # its packaged path here — the integration test's flat-import check is the
    # backstop when one is forgotten)
    ("synedre.sy_entities.base", "sy_entity_base"),
    ("synedre.sy_pg_contract", "sy_pg_contract"),
    ("synedre.sy_env", "sy_env"),
    ("synedre.db", "sy_db"),
    ("synedre.sy_logger", "sy_logger"),
    ("synedre.sy_cron_beat", "sy_cron_beat"),
    ("synedre.sy_reflex", "sy_reflex"),
    ("synedre.sy_conscience_health", "sy_conscience_health"),
    ("synedre.sy_agent_runner", "sy_agent_runner"),
    ("synedre.sy_session_split", "sy_session_split"),
    ("synedre.sy_session_handoff_resume", "sy_session_handoff_resume"),
    ("synedre.sy_session_start", "sy_session_start"),
)


def remap_import_paths(text: str, import_map=None) -> str:
    """Remap packaged monolith import paths to the flat OSS module names.

    Exact-string, longest-first (so 'synedre.sy_entities.base' wins before any
    shorter overlapping key), wherever the token appears — import statements
    and prose alike. Unknown paths are left as-is: better a documented dangling
    lazy import than a wrong guess."""
    for old, new in sorted(
        import_map if import_map is not None else _DEFAULT_IMPORT_MAP,
        key=lambda p: len(p[0]), reverse=True,
    ):
        text = text.replace(old, new)
    return text


# ---- 7. pg_dump artifacts ---------------------------------------------------
# pg_dump 16 prefixes every dump with session boilerplate (a block of SET
# statements + a set_config search_path call), a banner, version metadata and a
# \\restrict <token> line. The \\restrict token is a dump-integrity nonce (PG
# 17+/the --restrict flag) — an ephemeral, secret-ish value that must NEVER ship.
# The rest is tooling noise. None of it belongs in a published bootstrap.sql.
# The regexes are line-anchored and specific (e.g. 'SET <snake_var> = ...;'), so
# they are a no-op on prose or code that merely happens to contain the word SET.
_PG_DUMP_BANNER_RE = re.compile(
    r"^--[^\n]*\n--\s*PostgreSQL database dump(?:\s+complete)?\s*\n--[^\n]*\n",
    re.MULTILINE,
)
_RESTRICT_TOKEN_RE = re.compile(
    r"^\\(?:un)?restrict\s+\S+\s*\n", re.MULTILINE,
)
_DUMP_VERSION_RE = re.compile(
    r"^--\s*Dumped (?:from|by) (?:database|pg_dump) version[^\n]*\n",
    re.MULTILINE,
)
_PG_SET_RE = re.compile(
    r"^SET\s+[a-z_]+\s*=\s*[^;\n]*;\n", re.MULTILINE,
)
_PG_SET_CONFIG_RE = re.compile(
    r"^SELECT\s+pg_catalog\.set_config\([^;\n]*\);\n", re.MULTILINE | re.IGNORECASE,
)


def strip_pg_dump_artifacts(text: str) -> str:
    """Drop pg_dump 16 boilerplate: the 'PostgreSQL database dump' banner, the
    \\restrict/\\unrestrict integrity nonce, the version-metadata lines, the
    block of SET statements and the set_config search_path call.

    These are tooling noise in a published bootstrap.sql, and the \\restrict
    nonce is an ephemeral token that must never ship. Line-anchored and specific
    (a SET must read 'SET <snake_var> = <value>;'), so normal prose/code that
    merely contains the word 'SET' is untouched.
    """
    text = _PG_DUMP_BANNER_RE.sub("", text)
    text = _RESTRICT_TOKEN_RE.sub("", text)
    text = _DUMP_VERSION_RE.sub("", text)
    text = _PG_SET_RE.sub("", text)
    text = _PG_SET_CONFIG_RE.sub("", text)
    return text


# ---- 8. SQL messages (curated FR -> EN, exact-string) ------------------------
# The engine functions were authored in French in the monolith. Their RAISE
# EXCEPTION texts and in-function comments are prose a regex cannot translate,
# so each known FR string maps to a curated EN replacement — curated per-run in
# sy_private_config.json (T3.4: moved out of this shipped file, same rationale
# as _DEFAULT_SCHEMA_TOKENS). Keys must match the dumped text EXACTLY (including
# the SQL '' quote doubling); identifiers left as-is in the EN values are
# renamed right after by translate_lexicon, which is why this pass runs BEFORE
# it. Empty by default: a no-op unless the caller supplies a config.
_DEFAULT_SQL_MESSAGES: tuple = ()


def translate_sql_messages(text: str, messages=None) -> str:
    """Replace the known FR strings of the engine functions with curated EN.

    Exact-string (str.replace), never regex: the keys carry SQL quote doubling
    and multi-line comment blocks that must match byte-for-byte. Unknown FR
    prose is NOT handled here — the lexicon pass and the gate's lexicon check
    are the backstop for anything this curated map does not know."""
    for fr, en in (messages if messages is not None else _DEFAULT_SQL_MESSAGES):
        text = text.replace(fr, en)
    return text


# ---- 9. lexicon (FR building-trade vocabulary -> EN) -------------------------
# Wording decided by Alex 2026-07-24 (sy_lexicon entry_scope='oss-distro'): the
# building-site semantics survive translation — chantier->jobsite,
# travail->work_order, tache->task, cicatrice->scar, conduite->playbook; agent
# stays agent. Word-level with snake_case-aware boundaries: an underscore IS a
# boundary (sy_chantier_travail must match) but letters — including accented
# ones — are NOT ('detache', 'moustache', 'travailler' stay intact).
_DEFAULT_LEXICON = (
    ("chantiers", "jobsites"), ("chantier", "jobsite"),
    ("travaux", "work_orders"), ("travail", "work_order"),
    ("tâches", "tasks"), ("tâche", "task"),
    ("taches", "tasks"), ("tache", "task"),
    ("cicatrices", "scars"), ("cicatrice", "scar"),
    ("conduites", "playbooks"), ("conduite", "playbook"),
)
# Boundary class: ASCII alnum + Latin-1 letters. Underscore excluded on purpose.
_LEX_B = "A-Za-zÀ-ÿ0-9"


def translate_lexicon(text: str, lexicon=None) -> str:
    """Translate the FR orchestration vocabulary into the EN building-trade
    lexicon, longest-first (plural before singular), in three case variants
    (lower / Capitalized / UPPER). Identifiers and prose alike: mid-word hits
    are excluded by the boundary class, and any FR residue this pass cannot
    know is caught by the gate's lexicon check (defense in depth)."""
    pairs = lexicon if lexicon is not None else _DEFAULT_LEXICON
    for fr, en in sorted(pairs, key=lambda p: len(p[0]), reverse=True):
        for f, e in ((fr, en), (fr.capitalize(), en.capitalize()), (fr.upper(), en.upper())):
            text = re.sub(
                rf"(?<![{_LEX_B}]){re.escape(f)}(?![{_LEX_B}])", e, text,
            )
    return text


# ---- 10. DB comments (curated EN overlay, fail-closed) -----------------------
# COMMENT ON statements are French prose dumped from the private DB. A curated
# overlay (comments-en.json: {"tables": {name: en}, "columns": {"t.c": en},
# "constraints": {name: en}, "indexes": {name: en}} — keys use the POST-lexicon
# names) replaces each one; a comment absent from the overlay is DROPPED, never
# shipped untranslated. Runs LAST so the identifiers in the statement are
# already renamed when the key is derived.
_COMMENT_STMT_RE = re.compile(
    r"COMMENT ON (TABLE|COLUMN|CONSTRAINT|INDEX)[ \t]+"
    r"(\S+(?:[ \t]+ON[ \t]+\S+)?)[ \t]+IS[ \t]+'((?:[^']|'')*)';\n?"
)


def load_comment_map(path: Path | str) -> dict:
    """Read the curated EN comment overlay (JSON)."""
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))


def translate_db_comments(text: str, comment_map: dict | None = None) -> str:
    """Replace every COMMENT ON with its curated EN text, or DROP it.

    Fail-closed by construction: with a map provided, no original comment body
    ever survives — it is either swapped for reviewed EN prose or removed. With
    comment_map=None the pass is a no-op (the facade path: .py/.sh facades
    carry no COMMENT ON). EN apostrophes are SQL-escaped by doubling — never a
    backslash (PostgreSQL standard_conforming_strings)."""
    if comment_map is None:
        return text

    def _key(kind: str, target: str):
        name = target.split(".")[-1].strip('"')
        if kind == "TABLE":
            return comment_map.get("tables", {}).get(name)
        if kind == "COLUMN":
            parts = target.split(".")
            tbl = parts[-2] if len(parts) >= 2 else ""
            return comment_map.get("columns", {}).get(f"{tbl}.{name}")
        if kind == "CONSTRAINT":
            cname = target.split()[0]
            return comment_map.get("constraints", {}).get(cname)
        return comment_map.get("indexes", {}).get(name)

    def _repl(m: re.Match) -> str:
        en = _key(m.group(1), m.group(2))
        if en is None:
            return ""  # fail-closed: unreviewed prose never ships
        return f"COMMENT ON {m.group(1)} {m.group(2)} IS '{en.replace(chr(39), chr(39) * 2)}';\n"

    return _COMMENT_STMT_RE.sub(_repl, text)


# ---- 11. prose (curated FR -> EN blocks, exact-string) -----------------------
# The facades were authored in French in the monolith: whole docstrings, comment
# blocks and user-facing echo messages. Like the SQL messages, prose is text a
# regex cannot translate — each known FR block maps to a curated EN replacement
# (prose-en.json: a JSON array of [fr, en] pairs). Keys are curated FROM the
# staged output (byte-exact, extracted by line range — never retyped), so they
# match post-rename identifiers and post-lexicon vocabulary: this pass runs
# LAST. A FR block edited in the monolith stops matching its key, survives in
# FR, and FAILS the gate's accents check — curation is forced, never skipped.


def load_prose_pairs(path: Path | str) -> list:
    """Read the curated FR->EN prose overlay (JSON array of [fr, en] pairs)."""
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))


def translate_prose(text: str, pairs=None) -> str:
    """Replace each known FR prose block with its curated EN text.

    Exact-string (str.replace), never regex: keys are multi-line blocks lifted
    verbatim from the staged files. pairs=None is a no-op. Idempotent: once
    replaced, the FR key no longer appears. Unknown FR prose is NOT handled
    here — the gate's accents check is the fail-closed backstop."""
    if not pairs:
        return text
    for fr, en in pairs:
        text = text.replace(fr, en)
    return text


# ---- orchestration ----------------------------------------------------------
def scrub_text(
    text, denylist=None, *, path_map=None, schema_tokens=None,
    import_map=None, sql_messages=None, lexicon=None, comment_map=None,
    prose_pairs=None,
) -> str:
    """Apply all transforms in order. denylist=None skips codenames;
    comment_map=None skips the COMMENT overlay (facade path); prose_pairs=None
    skips the prose overlay. path_map / schema_tokens / import_map /
    sql_messages / lexicon override the monolith defaults (neutral test
    fixtures pass their own so the test stays token-free in the public repo)."""
    text = strip_proprietary_headers(text)
    text = strip_private_refs(text)
    if denylist:
        text = scrub_codenames(text, denylist)
    text = relativize_paths(text, path_map)
    text = scrub_schema_namespace(text, schema_tokens)
    text = rename_prefixes(text)
    text = remap_import_paths(text, import_map)
    text = strip_pg_dump_artifacts(text)
    text = translate_sql_messages(text, sql_messages)
    text = translate_lexicon(text, lexicon)
    text = translate_db_comments(text, comment_map)
    text = translate_prose(text, prose_pairs)
    return text


# ---- CLI (manual single-file check) ----------------------------------------
def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    comments = None
    prose = None
    for a in sys.argv[1:]:
        if a.startswith("--comments="):
            comments = load_comment_map(a.split("=", 1)[1])
        if a.startswith("--prose="):
            prose = load_prose_pairs(a.split("=", 1)[1])
    if not args:
        print("usage: sy_scrub.py <source-file> [denylist.txt] "
              "[--comments=map.json] [--prose=pairs.json]",
              file=sys.stderr)
        sys.exit(2)
    src = Path(args[0]).read_text(encoding="utf-8")
    deny = load_denylist(args[1]) if len(args) > 1 else None
    sys.stdout.write(scrub_text(src, deny, comment_map=comments, prose_pairs=prose))


if __name__ == "__main__":
    main()
