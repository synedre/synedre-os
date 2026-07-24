# ADR-0006: Skills default to addon-tier

- **Status:** Accepted
- **Date:** 2026-07-24
- **Deciders:** Founder

## Context

ADR-0002 already separated *facade* (adapter code — how to talk to a tool)
from *skill* (agent instructions — how to use a tool for a goal) by nature,
placing them in different folders. It did not rule on the open-core tier of
skills themselves — only on where they live.

ADR-0005 (Bucéphale) surfaced the pattern this ADR generalizes: a "generic"
capability often hides real product value one layer up from the raw adapter.
A skill is, by construction, that layer — a **curated workflow**: which steps
to follow, in what order, to what quality bar, in what output format. That is
judgment and expertise, the same kind of thing normally sold rather than
given away. Treating every skill as free-by-default would give away that
layer wholesale, the same mistake ADR-0005 rejected for the browser addon.

## Decision

**Skills default to addon-tier (sold).** A skill only qualifies as free core
if it operates the meta-harness's **own generic constructs** (jobsite,
work_order, scar, doctrine, agent roster) rather than encoding a
domain-specific workflow applied to an external or business goal.

Test: does the skill's value come from *operating Synedre OS itself*, or from
*applying Synedre OS to a domain problem*? The former is core; the latter is
product.

Examples (illustrative, not exhaustive — each skill is still judged on the
test above, not looked up in a list):

- **Free (harness mechanics):** the jobsite/run lifecycle skills, memory
  recall, system status, the governance/audit skills that check the harness's
  own doctrine/lexicon/module consistency.
- **Addon (domain workflow):** a design-intake skill, a brand-research skill,
  an SEO-remediation skill, a 3D-character skill — each encodes curated
  domain expertise on top of one or more free-core facades.

## Placement corollary

Tier has a folder consequence, mirroring ADR-0005's core/addon split for
facades: **`03_sun_wukong/skills/` holds free, harness-mechanics skills
only.** An addon-tier skill lives inside its addon —
`addons/<addon-name>/skills/` — bundled with the domain capability it
serves, not in the shared free-skill namespace. `03_sun_wukong/skills/README.md`
(the format/template doctrine — "Wukong's Grimoire") still governs the
*authoring format* for every skill, free or sold; it does not mean every
skill lives in that folder.

## Consequences

- **Positive:** consistent with ADR-0005's reasoning — the same free/sold
  logic now applies uniformly across facades AND skills, so the boundary
  does not need re-litigating per skill encountered during extraction.
- **Negative:** most of the monolith's skill catalog ends up addon-tier, not
  free. The v0.1.0 free distro's "batteries included" skill surface stays
  thin — harness mechanics only. That thinness is an intentional trade:
  it favors the sold-addon revenue model over a feature-rich free demo.
- **Neutral:** a skill's tier can still be revisited individually later (a
  skill judged generic enough might split into a free facade + an addon
  skill around it) — the DEFAULT posture is addon, not an immutable per-skill
  ruling.

## Alternatives considered

- **All skills free, sell only bundled products (à la Bucéphale).** Rejected:
  gives away the curated-workflow layer for free — the same reasoning ADR-0005
  rejected for "all of Bucéphale free."
- **Tier decided ad hoc, no default.** Rejected: re-litigates the same
  judgment call roughly once per skill (dozens), slows extraction work, and
  produces an inconsistent boundary across skills that are structurally alike.

## Links

- [ADR-0002](0002-external-tools-placement.md) — facade vs skill placement
  (nature and folder), the split this ADR adds a tier ruling on top of.
- [ADR-0005](0005-bucephale-browser-addon.md) — the precedent: generic
  adapter free, curated value layer sold; also the folder-consequence pattern
  the placement corollary mirrors.
- [`../../03_sun_wukong/skills/README.md`](../../03_sun_wukong/skills/README.md)
  — the authoring format ("Wukong's Grimoire"), scoped to free skills by this
  ADR's placement corollary.
