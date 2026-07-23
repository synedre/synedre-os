# ADR-0001: Three-layer documentation doctrine

- **Status:** Accepted
- **Date:** 2026-07-23
- **Deciders:** Founder

## Context

Documentation in an agentic system rots faster than the code it describes: the
code changes every session, the agents rewrite it continuously, and a Markdown
page describing "how it works" becomes a lie within days. Past experience shows
two failure modes that repeat:

1. **Structural drift.** A page hand-types a function signature or a table schema.
   The code changes; the page does not; the page now describes a system that no
   longer exists. The drift is silent — nothing alarms until someone is misled.
2. **Semantic drift.** A docstring or page *describes* behaviour accurately in
   shape but the underlying behaviour diverges subtly (an error path silently
   dropped, a side effect added). The prose and the code are both valid strings;
   nothing mechanical can detect the disagreement.

Two bad reactions to this are common: (a) give up and let docs rot, or (b) chase
"zero drift" as if it were achievable for both kinds. Neither holds. We need a
doctrine that treats the two drifts differently, derives as much documentation as
possible from the code so structural drift self-heals, and is honest that
semantic drift is never zero and must be bounded by other means.

A second force: this is an **open-core** distribution. Documentation is *generated
from the code*, and the private monolith the engine is extracted from contains
proprietary prefixes, tenant codenames, absolute paths and internal references
that must never reach the public. The generation step is therefore also a leak
surface, and the ordering of scrub-vs-generate is a load-bearing decision.

## Decision

We adopt a **three-layer documentation doctrine** (see
[`../doc-doctrine.md`](../doc-doctrine.md)):

- **Layer 1 — Code is truth.** Types, signatures, schemas, routes are absolute
  and live only in code. They are never transcribed into prose by hand.
- **Layer 2 — The "how" is generated.** Technical pages are derived from the code
  and regenerated as it changes. Structural content carries `<!-- AUTO-GENERATED -->`
  markers and is never hand-edited; semantic content is authored as docstrings
  next to the code and lifted by the generator.
- **Layer 3 — The "why" is immutable (ADR).** Architectural decisions are
  recorded as dated, numbered, immutable ADRs. Reversals supersede, never edit
  in place.

And two ordering rules that follow:

- **Generation runs on scrubbed code.** Proprietary prefixes are stripped and the
  source is sanitized *before* the generator consumes it — the scrub is a
  property of the input, not a filter on the output. A leak gate checks the
  staged output regardless.
- **Publishing is never autonomous.** The machine scrubs, generates, stages and
  gates; a human activates.

## Consequences

- **Positive:** Structural drift self-heals on each regeneration; the mirror only
  has to catch the gaps between regens, not re-derive the whole corpus.
  Documentation becomes reproducible — deleting and regenerating `documentation/`
  yields an equivalent corpus, so pages are cheap to lose. The leak surface is
  bounded by a deterministic, ordered pipeline rather than by human diligence.
- **Negative:** The generator and the mirror become critical infrastructure — if
  they break, drift accumulates invisibly until they are fixed. Docstrings now
  carry real weight (they feed generation), so missing or misleading docstrings
  propagate into the public docs. Maintaining the scrub rules is ongoing work as
  new leak shapes appear.
- **Neutral:** Contributors must learn which layer a change touches (code,
  docstring, or ADR) and follow the matching update path. This is mild overhead
  in exchange for not hand-syncing copies.

## Alternatives considered

- **Single-layer "docs as code", no generation.** Hand-write everything, keep it
  in sync by discipline. Rejected: structural drift is silent and inevitable at
  our change velocity; discipline does not scale against continuous agent-driven
  rewrites.
- **Generate everything, including the why.** Derive even the rationale from
  code/comments. Rejected: *why* a decision was made is not recoverable from the
  code that resulted from it; generating it fabricates plausible-but-untrue
  reasoning. The why must be human-authored and immutable.
- **Scrub the output instead of the input.** Generate first, then filter the
  Markdown for leaks. Rejected (the load-bearing one): by the time prose exists,
  a proprietary symbol has already been woven into sentences the scrub cannot
  reliably detect. The leak must be prevented at the source the generator reads.
- **"Zero drift" as the goal, undifferentiated.** Rejected as dishonest: it is
  achievable for structural drift and a myth for semantic drift. Conflating them
  leads to either false confidence or fatalism.

## Links

- [`../doc-doctrine.md`](../doc-doctrine.md) — the full doctrine this ADR adopts.
- `CLAUDE.md` Rule 2 — the condensed machine version.
- The camp principle — the generator (execution) and the mirror + leak gate
  (validation) are separate camps; neither validates its own work.
