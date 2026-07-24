# ADR-0004: Engine organs live in the core

- **Status:** Accepted
- **Date:** 2026-07-24
- **Deciders:** Founder

## Context

ADR-0003 rejected placing automates in `core/shyrka/` — the core is the neutral
engine, the West is the scheduled layer. Extracting the second facade batch
surfaced a category that ADR-0003 did not name: modules that instrument the
engine itself and are never entry points that orchestrate work. Three shipped
with that batch:

- `sy_reflex` — the **reflexes**: invoked by the harness hooks on every tool
  event, decides deny/warn/allow from DB rules.
- `sy_cron_beat` — the **pulse**: a `beat()` primitive each supervised job
  calls from inside its own script.
- `sy_conscience_health` — the **proprioception**: the engine's self health
  snapshot, aggregating the existing audit facades into one verdict.

Calling these "automates" and filing them under `02_atlas/workers/` would have
been a category error: nothing about them validates or orchestrates work, and
two of the three are not even schedulable — they are *called*.

## Decision

**A module that instruments the engine itself is an organ, and organs live in
`core/shyrka/`.** The placement test:

> An **organ** is *called* — by the harness (hooks, session lifecycle) or by
> other modules (a primitive, an access facade). A **West worker** is an
> *entry point* that orchestrates work on a schedule or on demand.

This refines, and does not contradict, ADR-0003's rejection of "automates in
`core/shyrka/`": that rejection stands — organs are not automates. A module
that starts as an organ and grows into a scheduled orchestrator moves to the
West (a real refactor, per ADR-0003's camp-commitment consequence, not a
relabel).

Applied to the batch: `sy_reflex`, `sy_cron_beat`, `sy_conscience_health` →
`core/shyrka/`; `sy_session_start` (an orchestrator of checks that *consumes*
the organs) → `02_atlas/workers/sre/`; `sy_agent_runner` (the LLM execution
contract) → `03_sun_wukong/`.

## Consequences

- **Positive:** the core reads as an anatomy — reflexes, pulse, proprioception
  next to the data and env facades. Contributors get a one-line test instead of
  a judgment call.
- **Negative:** the organ/worker line requires reading how a module is invoked,
  not just what it does. The whitelist comments carry the classification so the
  next extractor does not re-litigate it.

## Links

- [ADR-0003](0003-automates-camps-and-castes.md) — camps, castes, and the
  rejection this ADR refines.
- [`../../publish-whitelist.txt`](../../publish-whitelist.txt) — the organ
  section of the release map.
