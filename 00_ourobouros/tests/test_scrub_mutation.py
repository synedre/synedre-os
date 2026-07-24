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
    # lexicon — FR building-trade vocabulary -> EN (decided 2026-07-24). The FR
    # words are the PUBLIC rename contract (documented in the release README),
    # not a codename/path/schema — naming them here does not violate the
    # fictional-literals invariant above.
    ("lexicon_vocab",
     'table = sy_chantier_travail\n'
     '# audit des taches du chantier : cicatrice liee, conduite_slug, travaux\n',
     ["chantier", "travail", "travaux", "tache", "cicatrice", "conduite"],
     ["sy_jobsite_work_order", "tasks", "jobsite", "scar", "playbook_slug",
      "work_orders"]),
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


# === LEXICON: boundaries + curated overlays ==================================
def test_lexicon_boundaries_no_false_positive():
    """Mid-word hits must NOT fire: plain-language words containing a lexicon
    token ('moustache', 'detache', 'travailler') and accent-adjacent forms
    ('détache') stay intact. Not a MUTANTS entry: this text contains no leak,
    so the raw-gate layer would (rightly) find nothing."""
    text = "la moustache se detache, il faut travailler, on détache tout\n"
    assert sy_scrub.translate_lexicon(text) == text
    assert not [f for f in _gate(text) if f.category == "lexicon"]


def test_lexicon_case_variants():
    out = sy_scrub.translate_lexicon("Chantier: CHANTIER du chantier\n")
    assert "hantier" not in out
    assert "Jobsite" in out and "JOBSITE" in out and "jobsite" in out


_NEUTRAL_COMMENT_MAP = {
    "tables": {"sy_widget": "A widget's registry."},
    "columns": {"sy_widget.position": "Order in the widget list."},
    "constraints": {"chk_widget_safe": "Guards the widget pattern."},
    "indexes": {"sy_widget_ix": "Speeds up widget lookups."},
}


def test_comment_overlay_replaces_known_and_escapes():
    """A mapped comment is swapped for its curated EN text; an apostrophe in
    the EN text is SQL-escaped by DOUBLING, never a backslash (PostgreSQL
    standard_conforming_strings — the antislash scar)."""
    sql = "COMMENT ON TABLE shyrka.sy_widget IS 'ancien texte français';\n"
    out = sy_scrub.translate_db_comments(sql, _NEUTRAL_COMMENT_MAP)
    assert out == "COMMENT ON TABLE shyrka.sy_widget IS 'A widget''s registry.';\n"
    assert "\\'" not in out


def test_comment_overlay_drops_unknown_fail_closed():
    """MUTATION PROOF of fail-closed: a comment ABSENT from the overlay is
    dropped entirely — unreviewed prose never ships, in any language."""
    sql = (
        "COMMENT ON TABLE shyrka.sy_widget IS 'known';\n"
        "COMMENT ON TABLE shyrka.sy_rogue IS 'texte non relu qui fuirait';\n"
    )
    out = sy_scrub.translate_db_comments(sql, _NEUTRAL_COMMENT_MAP)
    assert "sy_rogue" not in out and "non relu" not in out
    assert "sy_widget" in out


def test_comment_overlay_quoted_column_constraint_index():
    """The three non-plain shapes: a quoted column name ('\"position\"' is a
    reserved word), CONSTRAINT ... ON, and INDEX."""
    sql = (
        'COMMENT ON COLUMN shyrka.sy_widget."position" IS \'ordre fr\';\n'
        "COMMENT ON CONSTRAINT chk_widget_safe ON shyrka.sy_widget IS 'fr';\n"
        "COMMENT ON INDEX shyrka.sy_widget_ix IS 'fr';\n"
    )
    out = sy_scrub.translate_db_comments(sql, _NEUTRAL_COMMENT_MAP)
    assert "Order in the widget list." in out
    assert "Guards the widget pattern." in out
    assert "Speeds up widget lookups." in out
    assert "fr" not in out.replace("from", "")  # no FR body survived


def test_comment_overlay_noop_without_map():
    """comment_map=None is the facade path: COMMENT ON untouched."""
    sql = "COMMENT ON TABLE shyrka.sy_widget IS 'x';\n"
    assert sy_scrub.translate_db_comments(sql, None) == sql


# === PROSE overlay + accents gate (anglicization, decided 2026-07-24) ========
# Neutral FR->EN pairs: the mechanism is exercised without lifting any real
# curated block from prose-en.json into a committed test file.
_NEUTRAL_PROSE_PAIRS = [
    ["# garde-fou : bloque l'écriture si la vérification échoue\n",
     "# guardrail: blocks the write when the check fails\n"],
    ["echo \"opération refusée\"\n", "echo \"operation refused\"\n"],
]


def test_prose_overlay_exact_replace_idempotent_noop():
    """A known FR block is swapped for its curated EN text (exact-string);
    running the pass again is a no-op (idempotence); pairs=None is a no-op."""
    fr = _NEUTRAL_PROSE_PAIRS[0][0] + "do_thing()\n" + _NEUTRAL_PROSE_PAIRS[1][0]
    out = sy_scrub.translate_prose(fr, _NEUTRAL_PROSE_PAIRS)
    assert "guardrail: blocks the write" in out and "operation refused" in out
    assert "garde-fou" not in out and "refusée" not in out
    assert "do_thing()" in out
    assert sy_scrub.translate_prose(out, _NEUTRAL_PROSE_PAIRS) == out
    assert sy_scrub.translate_prose(fr, None) == fr


def test_prose_unknown_fr_survives_scrub_and_dies_at_gate():
    """MUTATION PROOF of the fail-closed contract: a FR comment the curated
    map does not know (added/edited in the monolith after curation) survives
    the scrub — inline prose cannot be dropped without dropping code — and
    MUST be caught by the gate's accents category, forcing curation."""
    rogue = "# commentaire arrivé après la curation, jamais relu\n"
    out = sy_scrub.scrub_text(
        rogue, NEUTRAL_DENYLIST,
        path_map=NEUTRAL_PATH_MAP, schema_tokens=NEUTRAL_SCHEMA_TOKENS,
        prose_pairs=_NEUTRAL_PROSE_PAIRS,
    )
    assert "arrivé" in out  # the scrub did NOT silently drop or mangle it
    hits = [f for f in _gate(out) if f.category == "accents"]
    assert hits, "gate missed the accented FR residue"
    assert "arrivé" in {f.snippet for f in hits}  # whole-word snippet, not 'é'


def test_accents_gate_off_for_history_and_clean_on_english():
    """accent_check=False (the history-audit path) silences the category; a
    plain-English text with an em-dash yields zero accents findings."""
    fr = "# sécurité du système\n"
    on = scan_text(fr, NEUTRAL_DENYLIST, path_literals=NEUTRAL_PATH_LITERALS,
                   schema_tokens=NEUTRAL_SCHEMA_TOKENS)
    off = scan_text(fr, NEUTRAL_DENYLIST, path_literals=NEUTRAL_PATH_LITERALS,
                    schema_tokens=NEUTRAL_SCHEMA_TOKENS, accent_check=False)
    assert [f for f in on if f.category == "accents"]
    assert not [f for f in off if f.category == "accents"]
    en = "# guardrail — blocks the write when the check fails\n"
    assert not [f for f in _gate(en) if f.category == "accents"]


def test_prose_map_keys_match_staged_tree(repo_root, release_dir):
    """Every FR key of the committed prose-en.json must still match the staged
    tree BY CONSTRUCTION — a key orphaned by a monolith edit means the map is
    stale (the gate would catch the FR residue, but this points at the pair)."""
    prose_path = release_dir / "prose-en.json"
    if not prose_path.is_file():
        pytest.skip("prose-en.json not curated yet")
    pairs = sy_scrub.load_prose_pairs(prose_path)
    staged = "\n===\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted((repo_root / "core").rglob("*"))
        + sorted((repo_root / "02_atlas" / "hooks").rglob("*"))
        + sorted((repo_root / "02_atlas" / "workers").rglob("*"))
        if p.is_file() and p.suffix in (".py", ".sh")
        and "release" not in p.parts
    )
    for fr, en in pairs:
        assert fr in staged or en in staged, (
            f"stale prose pair — neither FR nor EN found in the staged tree:\n{fr!r}")


# French markers that must never survive the curated SQL-message pass — verbs
# and tracker refs sampled from every mapped message.
_FR_MESSAGE_MARKERS = [
    "refuse", "terminees", "lecture seule", "Utiliser", "dépendances",
    "archiver", "atteint", "clôture", "garde-fou", "justifie", "clore",
    "renseigne", "naître", "catégorique", "bloque", "rattachées", "sûr",
    "#974", "#380", "#397", "#984", "#987", "#989",
]


def test_sql_messages_full_chain_no_french():
    """Every curated FR engine-function string, run through the FULL scrub
    chain, leaves no French marker, no tracker ref, and no lexicon residue.
    Proves both the map itself and its ordering before the lexicon pass."""
    for fr, _en in sy_scrub._DEFAULT_SQL_MESSAGES:
        out = _scrub(fr)
        for marker in _FR_MESSAGE_MARKERS:
            assert marker not in out, f"marker {marker!r} survived in:\n{out}"
        assert not [f for f in _gate(out) if f.category == "lexicon"], out


def test_bootstrap_and_schema_doc_lexicon_clean(repo_root):
    """The committed artifacts themselves: bootstrap.sql and the generated
    db-schema.md carry zero FR-lexicon residue."""
    from sy_leak_gate import _LEXICON_RE

    for rel in ("core/shyrka/bootstrap.sql", "documentation/db-schema.md"):
        text = (repo_root / rel).read_text(encoding="utf-8")
        hits = sorted({m.group(0) for m in _LEXICON_RE.finditer(text)})
        assert not hits, f"{rel}: FR lexicon residue {hits}"


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


def test_history_audit_diff_marker_not_content(tmp_path):
    """GUARD (whole class): the history audit scans diff CONTENT, never diff
    SYNTAX. A deleted line starting with 'process...' reads '-process...' in
    `git log -p`; with the marker kept it false-positives the '-p<password>'
    secret pattern. Build a real 2-commit repo (add then delete the line) and
    assert the audit stays clean."""
    import subprocess

    from sy_publish_audit import audit_history

    def g(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True,
                       capture_output=True,
                       env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                            "HOME": str(tmp_path), "PATH": "/usr/bin:/bin"})

    g("init", "-q")
    f = tmp_path / "sy_worker.py"
    f.write_text("x = 1\nprocess_environment_of_the_cron = True\n", encoding="utf-8")
    g("add", "sy_worker.py")
    g("commit", "-qm", "add")
    f.write_text("x = 1\n", encoding="utf-8")
    g("commit", "-qam", "delete the process line")
    findings = audit_history(tmp_path, ["acme"])
    assert not [x for x in findings if x.category == "db_password_cli"], findings


# === INTEGRATION: real writer over the whitelisted files =====================
def test_integration_writer_whitelist_passes_gate(
    monolith_root, repo_root, release_dir, real_denylist, tmp_path,
):
    """Run the real writer on the whitelisted monolith files into a tmp OSS root,
    then assert the gate is clean AND no codename/path/header survived — by
    iterating the real denylist, never hardcoding a codename. The real
    prose-en.json rides along, so 'gate clean' includes the accents category:
    the staged tree is proven anglicized end-to-end."""
    from sy_extract import parse_whitelist, write_release

    wl = (repo_root / "publish-whitelist.txt").read_text(encoding="utf-8")
    pairs = parse_whitelist(wl)
    prose_path = release_dir / "prose-en.json"
    prose = sy_scrub.load_prose_pairs(prose_path) if prose_path.is_file() else None
    written = write_release(Path(monolith_root), tmp_path, pairs, real_denylist, prose)
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
