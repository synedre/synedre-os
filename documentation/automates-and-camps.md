# ⚙️ Automates, camps & castes

> How the non-conversational execution layer is organized, and why the camps map
> to the pillars. Placement rationale: [ADR-0003](adr/0003-automates-camps-and-castes.md).

The harness has two registers of execution. Keeping them distinct — and knowing
which pillar each belongs to — is what makes the system legible.

## 1. Two registers: agent vs automate

| | **Agent** | **Automate** |
|---|---|---|
| Does | Thinks, decides, delegates (ReAct) | Runs a deterministic routine |
| Built on | An LLM persona | Coded control flow (it may *call* an LLM, but the flow is fixed) |
| Triggered by | A spawn, a task, a chat | A schedule (cron), a CLI, a queue |
| Lives in | `03_sun_wukong/agents/` | `02_atlas/workers/` |

An automate does not "think." Even one that invokes an LLM (to generate text, to
classify) has its control flow hardcoded — the LLM is a step, not the driver. The
*reasoning* lives in the agents; the *repeatable execution* lives in the automates.

## 2. The camps map to the pillars

The camp principle — *execution and validation are separated, and the roles are
reversible* — is not abstract. It maps onto the pillars:

| Pillar | Camp | Role |
|---|---|---|
| `02_atlas/` | **West (Occident)** | Validate, schedule, orchestrate. The titan that holds the world and sees everything. |
| `03_sun_wukong/` | **East (Orient)** | Execute, think, transform. The monkey that acts. |
| `core/shyrka/` | neutral | The engine both camps run on (the agentic loop, the access facades). |
| `00_ourobouros/`, `01_founder/`, `addons/` | neutral | Memory, business, the merchant frontier. |

- The **automates** are deterministic, reproducible routines — measuring, auditing,
  validating, scheduling. That is the nature of the **West**, so they live in
  `02_atlas/workers/`.
- The **agents** are the LLM thinkers that decide and transform — the **East**, so
  they live in `03_sun_wukong/agents/`.

What is reversible is **which provider/team occupies each camp**, not the nature of
a given automate. An automate that validates is a validator; the camp principle
says a different camp must validate *the automate's* work — it does not turn the
validator into a producer.

## 3. Classification: `kind` (mechanism) vs `caste` (ownership)

Each automate is classified on two axes, and they have different statuses in the
open-core distro:

| Axis | Values | Status in OSS |
|---|---|---|
| **`kind`** | `recurring`, `oneshot`, `tool`, `lib`, `meta` | **Core.** The runtime must know how an automate is triggered. |
| **`caste`** | ownership group (e.g. *Vigies*, *Scribes*…) | **Mechanism = core; concrete values = starter.** |

- `kind` is a technical mechanism — it belongs in the schema and ships in the
  public core.
- `caste` is an organizational label: *which group of agents owns this automate*.
  The **mechanism** (the field exists, it is queryable) is core; the **concrete
  caste values** are instance data that comes with a starter, never hardcoded.

### Castes are metadata, not directories

Classification lives **in the database** (`sy_automates.caste`), not in the file
tree. There are no `workers/vigies/` or `workers/scribes/` folders. Materializing
castes as directories would (a) duplicate the DB, (b) hardcode instance values we
mean to keep configurable, and (c) mix two axes — the camp (already captured by
the pillar) and the caste (ownership). They are orthogonal; do not collapse them.

## 4. Structure of `workers/`

`02_atlas/workers/` is flat by default. If volume justifies grouping (after
extraction), group by **functional family** — never by caste:

```
02_atlas/workers/
  audit/       # drift detection, findings
  doc-auto/    # the doc↔code mirror, regeneration, publishing
  sre/         # cost/runaway guards, alerting
  browser/     # browser-job queue workers
  memory/      # RAG index, embedding sync, consolidation
```

A functional family answers *what this automate does*; a caste answers *who owns
it*. Only the former is a sensible file-tree axis.

## 5. Open-core boundary

Only **generic runtime facades** migrate into the public distro: the cron wrapper,
the conscience tick, the task worker, the DB and logger facades, the SRE guards,
the doc-auto loop. The hundreds of business-specific facades of the private
monolith (tenant billing, client-specific scrapers, vertical integrations) **stay
at the monolith** — they are experience, not engine.

The public distro ships the **mechanism** of scheduling, classification and camps.
The concrete caste roster, the persona instances and the business automates come
with a starter or are sold as addons. That is the open-core line, made physical.

## Links

- [ADR-0003](adr/0003-automates-camps-and-castes.md) — the placement decision.
- [`doc-doctrine.md`](doc-doctrine.md) — the doc-auto loop these automates run.
- [ADR-0002](adr/0002-external-tools-placement.md) — the other half of placement
  (external tools).
- The camp principle in [`../README.md`](../README.md) §2.
