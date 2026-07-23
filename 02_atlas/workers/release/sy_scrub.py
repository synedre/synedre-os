#!/usr/bin/env python3
"""
sy_scrub.py — transforms source text into a publish-safe OSS form.

Pure functions, idempotent. This is the "scrub" stage of the release pipeline:

    sy_extract  ->  sy_scrub  ->  stage  ->  sy_leak_gate  ->  sy_publish_audit

Doctrine (cicatrice #618 / ADR-0001): scrub the SOURCE, then write — never scrub
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
  7. strip pg_dump artifacts    (banner / \\restrict nonce / version lines /
     SET block / set_config) — pg_dump 16 boilerplate; the \\restrict nonce is
     an ephemeral token that must never ship. Line-anchored, no-op on prose.

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

# Monolith path literals. Exposed as an override point so neutral test fixtures
# can pass their own map; the defaults match Alex's install. Carrying the real
# literals here is a residual vocabulary leak (release/ is gate-excluded by
# construction — see sy_leak_gate._EXCLUDE_DIRS); moving them to a private
# gitignored config is a T3.4 (publish-readiness) task.
_DEFAULT_PATH_MAP = (
    ("/home/ubuntu/synedre-os", SYNEDRE_ROOT_VAR),
    ("/home/ubuntu", HOME_VAR),
)


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


def strip_private_refs(text: str) -> str:
    """Remove references to the private brain ([[feedback_*]] etc.) and to the
    local-only CLAUDE.md (gitignored in this repo -> a broken link if kept)."""
    text = _MEMORY_LINK_RE.sub("", text)
    text = _CLAUDEMD_RE.sub("", text)
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
# Override point for the tokens to collapse into PUBLIC_SCHEMA (residual vocab
# leak in the pipeline source, gate-excluded, T3.4 moves to private config). The
# full private vocabulary of the monolith's central mothership/schema concept:
# 'vaisseau_mere_ac' (PG schema) + 'vaisseau_mere' (FR root), 'mother_ship' (EN
# snake) + 'mothership' (EN fused). Order is irrelevant — scrub_schema_namespace
# sorts longest-first so the '_ac' suffix is taken whole before the bare root.
# All collapse to 'shyrka' everywhere, INCLUDING comments (Alex, 2026-07-23).
_DEFAULT_SCHEMA_TOKENS = (
    "vaisseau_mere_ac", "vaisseau_mere", "mother_ship", "mothership",
)


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


# ---- 6. pg_dump artifacts ---------------------------------------------------
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


# ---- orchestration ----------------------------------------------------------
def scrub_text(text, denylist=None, *, path_map=None, schema_tokens=None) -> str:
    """Apply all transforms in order. denylist=None skips codenames. path_map /
    schema_tokens override the monolith defaults (neutral test fixtures pass
    their own so the test stays token-free in the public repo)."""
    text = strip_proprietary_headers(text)
    text = strip_private_refs(text)
    if denylist:
        text = scrub_codenames(text, denylist)
    text = relativize_paths(text, path_map)
    text = scrub_schema_namespace(text, schema_tokens)
    text = rename_prefixes(text)
    text = strip_pg_dump_artifacts(text)
    return text


# ---- CLI (manual single-file check) ----------------------------------------
def main() -> None:
    if len(sys.argv) < 2:
        print("usage: sy_scrub.py <source-file> [denylist.txt]", file=sys.stderr)
        sys.exit(2)
    src = Path(sys.argv[1]).read_text(encoding="utf-8")
    deny = load_denylist(sys.argv[2]) if len(sys.argv) > 2 else None
    sys.stdout.write(scrub_text(src, deny))


if __name__ == "__main__":
    main()
