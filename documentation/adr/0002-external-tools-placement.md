# ADR-0002: External tools placement

- **Status:** Accepted
- **Date:** 2026-07-23
- **Deciders:** Founder

## Context

The meta-harness pilots external binaries and services — a browser (Chromium/CDP),
a 3D engine (Blender), a design API (Figma), screenshot pipelines. In the private
monolith these pilots are **scattered flat** among hundreds of top-level facades,
mixed with business logic, infra and one-shots. That makes the external coupling
hard to find, hard to upgrade (a version bump touches unknown files), and
impossible to reason about as a boundary.

Two forces demand a placement decision before the runtime is extracted into the
public distro:

1. **Isolation.** External tools are the most volatile dependency the runtime has
   (binary upgrades, API churn, install differences across hosts). The coupling
   must live behind a single, discoverable frontier so the rest of the runtime
   stays tool-agnostic.
2. **Open-core boundary.** Some tool families are generic engine capabilities
   (browser, screenshot) and belong in the free AGPL core; others are
   domain-specific (3D) and are addon candidates. A physical frontier makes that
   tier decision visible and reversible.

## Decision

We gather every wrapper that drives an external tool under
**`core/shirka/tools/`**, organized **one subfolder per family**
(`browser/`, `three-d/`, `figma/`, `screenshot/`), with facades named
`sy_<tool>_<role>.py`.

Three rules frame the folder:

1. **Isolate the coupling.** The rest of the runtime imports a facade, never the
   tool's SDK or binary. A tool change ripples only here.
2. **Pin the version outside the code.** Exact tool versions (image tags, packages,
   URLs) live in `02_atlas/infra/`; the facade reads them.
3. **Fail closed.** A missing/unreachable tool raises a clear error, never a silent
   no-op.

And a strict separation of concerns: **skills** that *use* a tool live in
`03_sun_wukong/skills/`; **install** lives in `02_atlas/infra/`; the **inventory**
of supported tools lives in [`documentation/external-tools.md`](../external-tools.md).

## Consequences

- **Positive:** External coupling is behind one discoverable frontier — upgrades,
  swaps and security review happen in one place. The open-core tier of each tool
  is visible from the folder structure. New contributors find "how do we drive a
  browser?" in one location.
- **Negative:** A level of indirection is added — a skill that wants a screenshot
  goes through a facade, not straight to the tool. Maintaining the version pin in
  `02_atlas/infra/` is ongoing discipline.
- **Neutral:** Contributors must learn the facade contract (isolate, pin outside,
  fail closed). Mild overhead in exchange for a stable runtime.

## Alternatives considered

- **Flat in `core/shirka/`, as the monolith does in its facade folder.** Rejected:
  the monolith's flat scatter of pilots among business facades is exactly the
  non-discoverability we are correcting. Grouping by family is cheap and clear.
- **A single `tools.py` module.** Rejected: the tools are heterogeneous (a CLI
  binary, an HTTP API, a library), each with several facades. One file becomes a
  grab-bag; one folder per family stays navigable.
- **Co-located with the skills that use them.** Rejected: a skill is *agent
  instructions* (how to use a tool for a goal); a facade is *adapter code* (how to
  talk to the tool). Different natures, different lifecycles, different homes —
  see the camp principle and [ADR-0003](0003-automates-camps-and-castes.md).

## Links

- [`../external-tools.md`](../external-tools.md) — the inventory.
- [`../../core/shirka/tools/README.md`](../../core/shirka/tools/README.md) — the
  facade contract.
- [ADR-0003](0003-automates-camps-and-castes.md) — automates, camps and castes
  (the other half of the placement doctrine).
