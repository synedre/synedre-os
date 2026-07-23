"""Mutation + integration tests for the release scrub pipeline (T3.1).

This file IS the validation criterion of the run (run-mode plan testable: the
proof that the OSS snapshot is 0-leak even when the source leaks). Four layers:

  MUTATION   — synthetic leak mutants. For each mutant we assert (a) the scrub
               cleans it, and (b) if the scrub regressed, the gate would still
               catch the RAW mutant (defense in depth — scrub and gate are
               verified by separate concerns, never one validating its own work).

  SECRET     — secrets are NEVER scrubbed: a secret must FAIL and demand human
               action, never be silently rewritten. We assert the gate flags
               every secret class and masks the value to <SECRET>.

  AGGREGATE  — one global assertion: every non-secret class combined, scrubbed,
               passes the gate at 0 findings.

  INTEGRATION — the real writer over the whitelisted monolith files into a tmp
               tree, then the gate. Skipped without SY_SRC_ROOT. Iterates the
               real denylist so no codename is ever hardcoded here.

INVARIANT — every literal in MUTANTS / SECRET_MUTANTS is FICTIONAL (acme,
mothership_db, /home/testuser, sk-ant-fake...). A real codename / path / schema
written into this file would enter git history and resurface at publish (T3.4).
"""
from __future__ import annotations

from pathlib import Path

import pytest

import sy_scrub
from sy_leak_gate import scan_text, scan_root, report

# --- neutral fixture config (FICTIONAL tokens only) --------------------------
# Override values injected into scrub_text / scan_text so the mutation tests
# exercise the MECHANISM without ever naming a real tenant / path / schema.
NEUTRAL_DENYLIST = ["acme", "acme_corp", "acmecorp", "acme_v2", "example_brand"]
NEUTRAL_PATH_MAP = [
    ("/home/testuser/monolith", "${MONOLITH_ROOT}"),
    ("/home/testuser", "${HOME}"),
]
NEUTRAL_SCHEMA_TOKENS = ["mothership_db", "mothership"]
NEUTRAL_PATH_LITERALS = ["/home/testuser"]  # detection side for the gate


def _scrub(text):
    return sy_scrub.scrub_text(
        text, NEUTRAL_DENYLIST,
        path_map=NEUTRAL_PATH_MAP, schema_tokens=NEUTRAL_SCHEMA_TOKENS,
    )


def _gate(text):
    return scan_text(
        text, NEUTRAL_DENYLIST,
        path_literals=NEUTRAL_PATH_LITERALS, schema_tokens=NEUTRAL_SCHEMA_TOKENS,
    )


# === MUTATION: one mutant per leak class =====================================
# (id, mutant_text, forbidden_after_scrub, expected_after_scrub)
MUTANTS = [
    # proprietary headers — the whole @author/@license line is dropped. Use a
    # fictional author so the committed test never carries a real name.
    ("header_author",
     '# @author Jane Doe <jane@example.com>\n',
     ["@author", "jane@example.com", "Jane Doe"], []),
    ("header_license_proprietary",
     '# @license Propriétaire — all rights reserved\n',
     ["@license Propri", "Propriétaire"], []),
    # codenames — substring + case-insensitive + longest-first
    ("codename_inline",
     '# TODO rotate acme prod key\n',
     ["acme"], ["<TENANT>"]),
    ("codename_quoted",
     'tenant = "acme_corp"\n',
     ["acme"], []),
    ("codename_snake_case_trap",
     '# ACMECORP and acme_v2 leak (snake_case defeats \\bacme\\b)\n',
     ["acmecorp", "acme"], []),
    ("codename_case_insensitive",
     'label = "ACME_PROD"\n',
     ["acme"], []),
    # paths — relativize, longest/most-specific first
    ("path_abs",
     'REPO=/home/testuser/monolith\n',
     ["/home/testuser"], ["${MONOLITH_ROOT}"]),
    ("path_home_substring",
     'LOGS=/home/testuser/logs\n',
     ["/home/testuser"], ["${HOME}"]),
    # schema — private 'mothership_db' (mirrors the monolith's schema token) is
    # renamed to the public canonical engine name. shyrka is the neutral engine
    # (core/shyrka/); it is public, so naming it here is fine.
    ("schema_namespace",
     'from mothership_db import foo\n',
     ["mothership_db", "mothership"], ["shyrka"]),
    # prefix rename — ps_ac_ BEFORE ac_ (ordering proof)
    ("prefix_ps_ac_order",
     'table = ps_ac_scars\n',
     ["ps_ac_", "ps_sy_", "ac_scars"], ["sy_scars"]),
    # prefix lookbehind — ac_ renamed, mac_os left intact
    ("prefix_lookbehind",
     'from ac_logger import X\nval = mac_os\n',
     ["ac_logger"], ["sy_logger", "mac_os"]),
    ("prefix_kebab",
     'service = ac-runner\n',
     ["ac-runner"], ["sy-runner"]),
    # private refs — brain links + local-only CLAUDE.md
    ("private_ref_brain_link",
     '# cf [[feedback_run_vs_chantier]] section 2\n',
     ["[[", "]]"], []),
    ("private_ref_claudemd",
     '# see local CLAUDE.md for the rule\n',
     ["CLAUDE.md"], []),
    # pg_dump 16 boilerplate — banner / \restrict nonce / SET block / set_config
    # / version metadata are stripped. The nonce is an ephemeral token that must
    # never ship. A codename (acme) + schema token ride along so the gate still
    # detects the RAW dump — the gate knows nothing of '\restrict'.
    ("pg_dump_artifacts",
     '--\n-- PostgreSQL database dump\n--\n'
     '\\restrict testnonceforpgdumpnotreal\n'
     'SET statement_timeout = 0;\n'
     'SET row_security = off;\n'
     "SELECT pg_catalog.set_config('search_path', '', false);\n"
     '-- Dumped from database version 16.13\n'
     'CREATE TABLE mothership_db.acme_cfg (\n'
     '    k text NOT NULL\n'
     ');\n'
     '--\n-- PostgreSQL database dump complete\n--\n',
     ["\\restrict", "testnonceforpgdumpnotreal", "PostgreSQL database dump",
      "SET statement_timeout", "set_config", "Dumped from database version",
      "row_security", "acme", "mothership_db"],
     ["shyrka", "<TENANT>"]),
]

_IDS = [m[0] for m in MUTANTS]


@pytest.mark.parametrize("mid,text,forbidden,expected", MUTANTS, ids=_IDS)
def test_scrub_cleans_mutant(mid, text, forbidden, expected):
    out = _scrub(text)
    for bad in forbidden:
        assert bad not in out, f"{mid}: residual leak {bad!r}:\n{out}"
    for good in expected:
        assert good in out, f"{mid}: missing expected {good!r}:\n{out}"


@pytest.mark.parametrize("mid,text,forbidden,expected", MUTANTS, ids=_IDS)
def test_gate_detects_raw_mutant(mid, text, forbidden, expected):
    """Defense in depth: the RAW mutant (before scrub) must be caught by the
    gate. If the scrub ever regresses, the gate still fails the release."""
    assert _gate(text), f"{mid}: gate failed to detect the raw leak"


def test_aggregate_scrub_then_gate_clean():
    """The global assertion: every non-secret class combined, scrubbed, passes
    the gate at 0 findings."""
    blob = "\n".join(text for _, text, _, _ in MUTANTS)
    clean = _scrub(blob)
    findings = _gate(clean)
    assert not findings, "aggregate leaked after scrub:\n" + report(findings)


# === SECRETS: never scrubbed; gate must flag + mask ==========================
SECRET_MUTANTS = [
    ("anthropic_key", 'PROD_KEY = "sk-ant-fakekey1234567890abcdefghijkl"'),
    ("openai_key",    'OPENAI = "sk-fakekey1234567890abcdefghijklmn"'),
    ("bearer",        'Authorization: "Bearer abcdefghij1234567890ABCDEFGHIJ12"'),
    ("conn_string",   'DB = "postgresql://user:supersecretpw1@db:5432/x"'),
    ("db_password_cli", 'cmd = "mysql -u root -pSuperSecret123"'),
    ("email",         'owner = "founder@example.com"'),
]


@pytest.mark.parametrize("sid,text", SECRET_MUTANTS, ids=[s[0] for s in SECRET_MUTANTS])
def test_secret_survives_scrub_and_is_flagged(sid, text):
    """The scrub must NOT touch secrets; the gate must catch them and mask the
    value (the detector must not itself leak)."""
    scrubbed = sy_scrub.scrub_text(
        text, NEUTRAL_DENYLIST,
        path_map=NEUTRAL_PATH_MAP, schema_tokens=NEUTRAL_SCHEMA_TOKENS,
    )
    findings = _gate(scrubbed)
    assert findings, f"{sid}: gate failed to flag the secret"
    for f in findings:
        assert f.snippet == "<SECRET>", f"{sid}: gate exposed the value: {f.snippet!r}"


# === INTEGRATION: real writer over the whitelisted files =====================
def test_integration_writer_whitelist_passes_gate(
    monolith_root, repo_root, release_dir, real_denylist, tmp_path,
):
    """Run the real writer on the whitelisted monolith files into a tmp OSS root,
    then assert the gate is clean AND no codename/path/header survived — by
    iterating the real denylist, never hardcoding a codename."""
    from sy_extract import parse_whitelist, write_release

    wl = (repo_root / "publish-whitelist.txt").read_text(encoding="utf-8")
    pairs = parse_whitelist(wl)
    written = write_release(Path(monolith_root), tmp_path, pairs, real_denylist)
    assert len(written) == len(pairs), f"wrote {len(written)} / {len(pairs)}"

    # 1. gate over the staged tree (defaults = real monolith vocab)
    findings = scan_root(tmp_path, real_denylist)
    assert not findings, "integration: leaks after scrub:\n" + report(findings)

    # 2. iterate the real denylist — never hardcode a codename in this file
    for f in tmp_path.rglob("*"):
        if not f.is_file():
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        low = content.lower()
        for token in real_denylist:
            assert token.lower() not in low, (
                f"codename {token!r} leaked in {f.relative_to(tmp_path)}")
        assert "@author" not in content, (
            f"@author header survived in {f.relative_to(tmp_path)}")
        assert "/home/ubuntu" not in content, (
            f"absolute path survived in {f.relative_to(tmp_path)}")
