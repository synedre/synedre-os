# Release pipeline

This folder is the **release pipeline** that turns the private monolith into a
publish-safe open-core snapshot. Two camps (doctrine: the East builds, the West
judges) — the writers here are the producers, the gates here are the validators,
and no camp ever validates its own work.

```
publish-whitelist.txt ──▶ sy_extract ──▶ sy_scrub ──▶ stage ──▶ sy_leak_gate ──▶ sy_publish_audit
        (what)            (copy only)   (transform)  (tree)    (must be clean)    (tree + history)
                                                                      │
                                              bootstrap.sql ──────────┘  (exception: dump-driven, see below)
```

## Contract

The pipeline is **whitelist-driven** and **scrub-before-write**:

- **Whitelist-driven** (`publish-whitelist.txt`). The writer copies ONLY the
  files listed, mapping monolith path → OSS path. Never `cp -r` a directory then
  scrub it — the whitelist drives inclusion (cicatrice #618).
- **Scrub-before-write**. `sy_scrub` transforms the SOURCE, then the writer
  writes the dest. The output is never scrubbed after the fact.
- **Defense in depth**. A leak gate checks the staged output regardless of the
  scrub, and publishing is never autonomous (no remote is configured until an
  explicit human opt-in).
- **Secrets fail, never redacted**. Secrets are out of scope for `sy_scrub` —
  they must FAIL at the gate and demand human action, never be silently rewritten
  into a publish.

## Modules

| Module | Role | Camp |
|---|---|---|
| `sy_extract.py` | Writer: copies the whitelisted files, scrubbing each before write. | East (producer) |
| `sy_scrub.py` | 7 ordered, idempotent transforms (headers, codenames, paths, schema, prefixes, pg_dump artifacts). Pure functions. | East |
| `sy_leak_gate.py` | Detector: FAILs on residual leak (codename / path / schema / secret). Secrets are masked `<SECRET>` so the detector never leaks the value. | West (validator) |
| `sy_publish_audit.py` | Tree + git-history audit: a leak removed from the working tree still lives in history. | West |
| `sy_db_schema_doc.py` | Layer 2 doc generator: `bootstrap.sql` → `documentation/db-schema.md` (auto, never hand-edited). | — |

The denylist (`sy_codename_denylist.txt`) holds YOUR tenant codenames and is
**gitignored** — only the `.example` (neutral placeholders) ships. The real file
is local-only (CLAUDE.md Rule 3).

## Standard workflow (whitelist-driven)

```bash
SY_SRC_ROOT=/path/to/monolith \
SY_DEST_ROOT=/path/to/oss \
python3 02_atlas/workers/release/sy_extract.py

# gate + audit the staged tree
python3 02_atlas/workers/release/sy_leak_gate.py --root .
python3 02_atlas/workers/release/sy_publish_audit.py --root .
```

Add a file: append `monolith/path -> oss/path` to `publish-whitelist.txt`,
re-run. The pipeline is reusable across T3.x without code changes.

## Exception: `bootstrap.sql` (dump-driven)

`core/shyrka/bootstrap.sql` is the ONE artifact that is **not** whitelist-driven.
Its source is not a file in the monolith — it is a runtime `pg_dump` of the live
orchestrator schema, filtered to a 69-table core whitelist + 8 referenced engine
functions, then scrubbed. It is generated and committed directly here, outside
`publish-whitelist.txt` (which is not modified).

**Why a dump, not the migrations.** The schema grew across 157 migrations that
ALTER columns incrementally and interleave DDL with seeds (lore, codenames). The
dump is the clean **final state**: the columns as they exist today, no seeds, no
incremental noise.

**Why a whitelist, not the whole schema.** The live schema (`vaisseau_mere_ac`)
mixes 354 tables — Synedre OS engine, CodeMyShop enterprise, PrestaShop
ecommerce, tenant specifics. The schema name filters nothing. The 69-table
whitelist is the **orchestrator heart** only: sessions, chantier/task, agents,
automates, cron, doctrine/cicatrices, doc-drift, lexicon, llm-pricing, pentest,
seo-engine, reflex. `ps_ac_*` / `cs_*` ecommerce is excluded by construction
(except 3 `ps_ac_*` engine concepts the scrub renames to `sy_*`).

### Regenerating `bootstrap.sql`

The generator is a one-off script (kept out of the repo — it embeds the private
DB address). To regenerate, reproduce its 9 steps:

1. `pg_dump --schema-only --no-owner --no-privileges -t vaisseau_mere_ac.<t>` over
   the 69 core tables (see the `TABLES` list; it mirrors the categories in
   `documentation/db-schema.md`).
2. `pg_get_functiondef` over the schema's functions, scrubbed.
3. Scrub both via `sy_scrub.scrub_text()` (7 transforms; `vaisseau_mere_ac`→
   `shyrka`, `ps_ac_`→`sy_`, codenames→`<TENANT>`, pg_dump artifacts stripped).
4. Keep only the functions the 69 tables reference (CHECK / trigger / default);
   drop the two that break auto-containment:
   - `cascade_resolved_inbox_on_chantier_done` — its body references
     `sy_inbox_emails` (a comm table, not dumped); its trigger is dropped too.
   - `_audit_log_immutable` — orphan (its table is not in the 69).
5. Drop the 2 orphan FKs (`sy_agent_event.id_atlas_email → sy_atlas_email`,
   `sy_doc_gap.backlog_id → sy_backlog`): keep the columns, drop the constraint.
6. Assemble: header (`CREATE SCHEMA shyrka; SET search_path`) + functions
   (BEFORE tables, so CHECK constraints resolve) + tables.
7. Sanity: 0 INSERT, 0 `vaisseau_mere`/`ps_ac_`, 69 CREATE TABLE, 0 orphan FK,
   0 cascade residue.
8. Restore test: `psql -f bootstrap.sql` on a fresh `postgres:16` → exit 0.
9. Regenerate `documentation/db-schema.md` (below), then re-run gate + audit.

After editing `bootstrap.sql`, regenerate the doc:

```bash
python3 02_atlas/workers/release/sy_db_schema_doc.py
python3 02_atlas/workers/release/sy_db_schema_doc.py --check   # CI: fails if stale
```

## Testing

`00_ourobouros/tests/test_scrub_mutation.py` — mutation + integration. Four
layers, each verifying a separate concern (scrub cleans a mutant; the gate still
catches the RAW mutant if the scrub regressed; secrets survive scrub and are
flagged; the real writer over the whitelisted files passes the gate). Run:

```bash
SY_SRC_ROOT=/path/to/monolith python3 -m pytest 00_ourobouros/tests/ -v
```
