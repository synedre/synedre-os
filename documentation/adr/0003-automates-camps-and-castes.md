# ADR-0003: Automates, camps and castes

- **Status:** Accepted
- **Date:** 2026-07-23
- **Deciders:** Founder

## Context

The private monolith runs several hundred facades flat in one folder, scheduled by
a cron wrapper and a Nitro task layer. Two facts about that layer shape this
decision:

1. **The castes are database metadata, not folders.** Each automate carries a
   `kind` (technical nature) and a `caste` (owning group) as columns in
   `sy_automates`. The canonical classification lives in the DB, never in the file
   tree.
2. **The camp principle exists but was not materialized in the structure.** The
   system separates execution from validation and makes the roles reversible — but
   the folder layout did not reflect which pillar is which camp.

Before the runtime is extracted into the public distro, we need a placement
doctrine that (a) honors the camp principle physically, (b) keeps the caste as
data, and (c) draws the open-core line at generic runtime vs business-specific.

## Decision

1. **Camps map to pillars.** `02_atlas/` is the **West (Occident)** — validate,
   schedule, orchestrate. `03_sun_wukong/` is the **East (Orient)** — execute,
   think, transform. `core/shyrka/` is the neutral engine both camps run on.
2. **Automates live in `02_atlas/workers/`.** They are deterministic, reproducible
   routines (measure, audit, validate, schedule) — the nature of the West.
3. **Agents live in `03_sun_wukong/agents/`.** They are the LLM thinkers that
   decide and transform — the East.
4. **Castes stay in the database, never as directories.** The `caste` field ships
   as part of the schema (the mechanism is core), but the concrete caste values
   (e.g. *Vigies*, *Scribes*) are instance data that comes with a starter, never
   hardcoded into the folder tree.
5. **`workers/` is flat, or grouped by functional family** (`audit/`, `doc-auto/`,
   `sre/`, `browser/`, `memory/`) when volume justifies it — **never by caste**.

## Consequences

- **Positive:** The camp principle becomes legible from the folder layout — a
  reader knows where validators vs producers live. The caste stays a single source
  of truth (the DB); no drift between folders and data. The open-core line is
  physical: generic runtime facades in the public distro, business-specific ones
  left at the monolith.
- **Negative:** The West/East mapping is a commitment — moving an automate that
  grows LLM reasoning into an agent is a real refactor, not a relabel. Contributors
  must internalize that the camp is about *nature* (deterministic vs thinking),
  not about a provider.
- **Neutral:** The reversibility clause of the camp principle is preserved at the
  right level: which provider/team occupies each camp is reversible; the nature of
  a given automate is not.

## Alternatives considered

- **Castes as directories** (`workers/vigies/`, `workers/scribes/`…). Rejected: it
  duplicates the DB classification, hardcodes instance values meant to stay
  configurable, and collapses two orthogonal axes (camp = pillar, caste =
  ownership). An automate that changes owner would have to move files.
- **Flat scatter as in the monolith.** Rejected: several hundred facades in one
  folder is the non-discoverability we are correcting. Grouping by functional
  family is cheap and keeps the West navigable.
- **Automates in `core/shyrka/`.** Rejected: the core is the neutral engine (the
  agentic loop, the access facades). Automates are the West's scheduled layer, not
  the engine; placing them in `core/shyrka/` would blur the camp line this ADR
  draws.

## Links

- [`../automates-and-camps.md`](../automates-and-camps.md) — the full doctrine.
- [`../README.md`](../../README.md) §2 — the camp principle and the pillar table.
- [ADR-0002](0002-external-tools-placement.md) — the other half of placement
  (external tools).
- [`doc-doctrine.md`](../doc-doctrine.md) — the doc-auto loop the West's automates
  run.
