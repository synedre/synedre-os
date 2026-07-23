#!/usr/bin/env python3
"""
sy_db_schema_doc.py — Layer 2 doc generator (ADR-0001 doc-doctrine).

Reads ``core/shyrka/bootstrap.sql`` and emits ``documentation/db-schema.md``.
The output is AUTO-GENERATED — never hand-edit; regenerate after bootstrap.sql
changes:

    python3 02_atlas/workers/release/sy_db_schema_doc.py \
        --bootstrap core/shyrka/bootstrap.sql \
        --out documentation/db-schema.md

The doc-doctrine (ADR-0001) is three layers:
  Layer 1 — docstrings in-code (the source of truth, lives with the code).
  Layer 2 — THIS file. Auto-generated reference (tables/columns/COMMENTs),
            derived from bootstrap.sql. Never authored by hand. If it drifts
            from bootstrap.sql, bootstrap.sql wins — regenerate.
  Layer 3 — ADRs (immutable rationale, documentation/adr/).

Parsing is regex over the pg_dump'd DDL: CREATE TABLE blocks, COMMENT ON
TABLE/COLUMN statements, and CREATE OR REPLACE FUNCTION signatures. No DB
connection needed — the bootstrap.sql is the single input, so the doc and the
schema can never disagree (idempotent: same bootstrap.sql -> same doc).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

AUTO_MARKER = (
    "<!-- AUTO-GENERATED from core/shyrka/bootstrap.sql by sy_db_schema_doc.py "
    "-- DO NOT EDIT. Regenerate after bootstrap.sql changes. -->"
)

# Category -> ordered table list. Mirrors the bootstrap whitelist (see
# /tmp/sy_bootstrap_gen.py TABLES). A table not listed here lands in
# "Other" — that is a signal the generator and the whitelist drifted.
CATEGORIES: list[tuple[str, list[str]]] = [
    ("Sessions & runtime", [
        "sy_user", "sy_claude_session", "sy_run", "sy_job_queue",
        "sy_task_run", "sy_autonomy_window",
    ]),
    ("Chantier, travail & tâche", [
        "sy_chantier", "sy_chantier_travail", "sy_chantier_agent",
        "sy_chantier_claude_session", "sy_chantier_lock", "sy_chantier_readiness",
        "sy_chantier_qa_run", "sy_chantier_relevance", "sy_chantier_tache",
        "sy_chantier_tool", "sy_tache_dep", "sy_tache_iteration",
        "sy_tache_skill", "sy_tache_tool", "sy_travail_agent",
        "sy_travail_dep", "sy_travail_review",
    ]),
    ("Agents", [
        "sy_agents", "sy_agent_activity", "sy_agent_event",
        "sy_agent_heartbeat", "sy_agent_relations", "sy_agent_skill",
        "sy_agent_tool", "sy_agent_xp", "sy_agent_xp_history", "sy_ai_routing",
    ]),
    ("Automates", [
        "sy_automates", "sy_automate_agents", "sy_automate_conduites",
        "sy_automate_llm_run", "sy_automate_logs",
    ]),
    ("Cron", ["sy_cron_heartbeat"]),
    ("Doctrine, cicatrices & introspection", [
        "sy_conscience_health", "sy_doc_coverage", "sy_doc_drift",
        "sy_doc_external_review", "sy_doc_gap", "sy_doc_public_mirror",
        "sy_cicatrices", "sy_header_shell_health_history", "sy_reflex",
        "sy_reflex_audit", "sy_reflex_proposal",
    ]),
    ("Lexicon & LLM pricing", ["sy_lexicon", "sy_llm_pricing", "sy_ai_usage"]),
    ("Pentest", ["sy_pentest_finding", "sy_pentest_run"]),
    ("SEO engine (technical)", [
        "sy_canary_target", "sy_seo_authority_cache", "sy_seo_brand_brief",
        "sy_seo_bulk_queue", "sy_seo_coverage_snapshot", "sy_seo_health_history",
        "sy_seo_i18n_audit", "sy_seo_keyword_position", "sy_seo_page_backup",
        "sy_seo_page_status", "sy_seo_remediation_log", "sy_seo_sentinel_target",
        "sy_seo_stopwords", "sy_seo_tracked_keyword",
    ]),
]

# The 2 columns whose FK was dropped in the OSS distro (their target tables —
# sy_atlas_email, sy_backlog — are comm/borderline, excluded from the core).
# The generator flags them so a reader is not surprised the column has no FK.
DROPPED_FK_COLUMNS: set[tuple[str, str]] = {
    ("sy_agent_event", "id_atlas_email"),
    ("sy_doc_gap", "backlog_id"),
}

# Constraint clauses inside a CREATE TABLE that are NOT column definitions.
_CONSTRAINT_LEAD = (
    "CONSTRAINT", "PRIMARY KEY", "UNIQUE", "CHECK", "FOREIGN KEY", "EXCLUDE",
)

# CREATE TABLE shyrka.<name> ( ... ); — DOTALL captures the body across lines.
_CREATE_RE = re.compile(
    r"CREATE TABLE shyrka\.(\w+)\s*\((.*?)\n\);", re.DOTALL,
)
# COMMENT ON TABLE/COLUMN shyrka.x[.y] IS '...'; — '' inside is a literal quote.
_COMMENT_TABLE_RE = re.compile(
    r"COMMENT ON TABLE shyrka\.(\w+) IS '((?:[^']|'')*)';", re.DOTALL,
)
_COMMENT_COL_RE = re.compile(
    r"COMMENT ON COLUMN shyrka\.(\w+)\.(\w+) IS '((?:[^']|'')*)';", re.DOTALL,
)
# CREATE OR REPLACE FUNCTION shyrka.<name>(<args>) RETURNS <type>.
_FUNC_RE = re.compile(
    r"CREATE OR REPLACE FUNCTION shyrka\.(\w+)\s*\(([^)]*)\)\s*\n\s*RETURNS\s+([^\n]+)",
)


def _unescape(s: str) -> str:
    """Turn SQL doubled-quote '' back into a single '."""
    return s.replace("''", "'")


def parse_bootstrap(sql: str):
    """Return (tables, table_comments, col_comments, funcs).

    tables: {name: [(col, type_str, nullable, default)]}
    table_comments: {name: str}
    col_comments: {(table, col): str}
    funcs: [(name, args, returns)]
    """
    tables: dict[str, list[tuple[str, str, str, str]]] = {}
    for m in _CREATE_RE.finditer(sql):
        name, body = m.group(1), m.group(2)
        cols = []
        # split body into clause lines; a trailing comma separates clauses.
        for raw in body.split(",\n"):
            line = raw.strip()
            if not line or line.split()[0].upper() in _CONSTRAINT_LEAD:
                continue
            parts = line.split(None, 1)
            if len(parts) == 1:
                cols.append((parts[0], "", "", ""))  # degenerate; keep faithful
                continue
            col_name = parts[0]
            rest = parts[1].strip()
            nullable = "NOT NULL" if "NOT NULL" in rest.upper() else ""
            default = ""
            dm = re.search(r"DEFAULT\s+(.*?)(?:\s+NOT NULL\s*$|\s*$)", rest, re.IGNORECASE)
            if dm:
                default = dm.group(1).strip()
            # type = rest minus the modifiers we surfaced separately.
            type_str = rest
            if default:
                type_str = type_str.replace("DEFAULT " + dm.group(1), "")
            type_str = re.sub(r"\s+NOT NULL\b", "", type_str, flags=re.IGNORECASE).strip()
            cols.append((col_name, type_str, nullable, default))
        tables[name] = cols

    table_comments = {m.group(1): _unescape(m.group(2)) for m in _COMMENT_TABLE_RE.finditer(sql)}
    col_comments = {
        (m.group(1), m.group(2)): _unescape(m.group(3))
        for m in _COMMENT_COL_RE.finditer(sql)
    }
    funcs = [(m.group(1), m.group(2).strip(), m.group(3).strip()) for m in _FUNC_RE.finditer(sql)]
    return tables, table_comments, col_comments, funcs


def render(tables, table_comments, col_comments, funcs) -> str:
    out: list[str] = [AUTO_MARKER, ""]
    out.append("# Database schema — `shyrka`")
    out.append("")
    out.append(
        "The Synedre OS orchestrator core schema. DDL-only (no data), generated "
        f"from `core/shyrka/bootstrap.sql` over a {len(tables)}-table whitelist "
        f"+ {len(funcs)} engine functions. This page is reference (Layer 2 of the "
        "doc-doctrine, ADR-0001) — for *why* a table exists, see its COMMENT and "
        "the ADRs; for *how* to use it, see the in-code docstrings (Layer 1)."
    )
    out.append("")
    n_table_cmt = len(table_comments)
    n_col_cmt = len(col_comments)
    out.append(
        f"_Legend: {n_table_cmt}/{len(tables)} tables and {n_col_cmt} columns carry "
        "a COMMENT (the engine's doctrine, kept verbatim). "
        "`NOT NULL` and `DEFAULT` are surfaced; constraint clauses (PK/FK/CHECK) "
        "are in bootstrap.sql, not repeated here._"
    )
    out.append("")

    seen: set[str] = set()
    for title, members in CATEGORIES:
        present = [t for t in members if t in tables]
        if not present:
            continue
        out.append(f"## {title}")
        out.append("")
        for tname in present:
            seen.add(tname)
            _render_table(out, tname, tables[tname], table_comments.get(tname), col_comments)
        out.append("")

    other = sorted(set(tables) - seen)
    if other:
        out.append("## Other (uncategorised)")
        out.append("")
        out.append(
            "> A table here means the generator's category map and the bootstrap "
            "whitelist drifted — align them."
        )
        out.append("")
        for tname in other:
            _render_table(out, tname, tables[tname], table_comments.get(tname), col_comments)
        out.append("")

    if funcs:
        out.append("## Engine functions")
        out.append("")
        out.append(
            "PL/pgSQL guards that encode the orchestrator's runtime doctrine "
            "(chantier gates, append-only audit, updated_at). Kept auto-contained "
            "in the distro: one function that coupled to a comm-only table was "
            "dropped with its trigger."
        )
        out.append("")
        out.append("| Function | Args | Returns | Role |")
        out.append("|---|---|---|---|")
        for fname, args, returns in funcs:
            out.append(f"| `{fname}` | {args or '—'} | {returns} | {_func_role(fname)} |")
        out.append("")

    out.append("---")
    out.append(
        f"_Generated by `02_atlas/workers/release/sy_db_schema_doc.py` from "
        f"{len(tables)} tables + {len(funcs)} functions. Edit bootstrap.sql, "
        "then regenerate — never edit this page._"
    )
    out.append("")
    return "\n".join(out)


def _render_table(out, tname, cols, table_comment, col_comments):
    out.append(f"### `{tname}`")
    if table_comment:
        out.append("")
        out.append(f"> {table_comment}")
    out.append("")
    out.append("| Column | Type | Nullable | Default |")
    out.append("|---|---|---|---|")
    for col_name, type_str, nullable, default in cols:
        note = ""
        if (tname, col_name) in DROPPED_FK_COLUMNS:
            note = " *(FK to external table dropped in OSS distro)*"
        # type may carry the note for the 2 dropped-FK columns — append there.
        out.append(
            f"| `{col_name}`{note} | {type_str or '—'} | "
            f"{nullable or '—'} | {default or '—'} |"
        )
    table_col_comments = {c: v for (tbl, c), v in col_comments.items() if tbl == tname}
    if table_col_comments:
        out.append("")
        out.append("Column notes:")
        for col_name in [c for c, *_ in cols if (tname, c) in col_comments]:
            out.append(f"- **`{col_name}`** — {col_comments[(tname, col_name)]}")
    out.append("")


def _func_role(name: str) -> str:
    """One-line role from the function name (no COMMENT on functions in DDL)."""
    roles = {
        "is_safe_regex": "validates a stored regex pattern (CHECK on sy_reflex).",
        "fn_set_updated_at": "trigger: bumps updated_at on row change.",
        "fn_chantier_done_requires_tasks_complete": "gate: a chantier may not go `done` with open tasks.",
        "fn_travail_depends_on_readonly": "guard: deprecated depends_on column is read-only (use sy_travail_dep).",
        "guard_chantier_archive_requires_kpi_reached": "gate: a chantier with an outcome_kpi cannot archive until the KPI is reached.",
        "guard_chantier_done_requires_guardrail": "gate: a chantier must transition through status, never INSERT as done/archived.",
        "guard_chantier_done_requires_outcome_proof": "gate: closing a chantier requires an outcome proof.",
        "set_cicatrice_guardrail_default": "trigger: defaults a cicatrice's guardrail at INSERT.",
    }
    return roles.get(name, "—")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1].strip())
    p.add_argument("--bootstrap", default="core/shyrka/bootstrap.sql",
                   help="path to bootstrap.sql (default: core/shyrka/bootstrap.sql)")
    p.add_argument("--out", default="documentation/db-schema.md",
                   help="output markdown path (default: documentation/db-schema.md)")
    p.add_argument("--check", action="store_true",
                   help="exit non-zero if the output would differ (CI guard)")
    args = p.parse_args()

    sql = Path(args.bootstrap).read_text(encoding="utf-8")
    rendered = render(*parse_bootstrap(sql))

    out_path = Path(args.out)
    if args.check:
        existing = out_path.read_text(encoding="utf-8") if out_path.is_file() else ""
        if existing != rendered:
            print(f"sy_db_schema_doc: {out_path} is stale — regenerate", file=sys.stderr)
            return 1
        print(f"sy_db_schema_doc: {out_path} up to date")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(f"sy_db_schema_doc: wrote {out_path} ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
