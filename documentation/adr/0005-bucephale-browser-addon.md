# ADR-0005: Bucéphale — the browser addon

- **Status:** Accepted
- **Date:** 2026-07-24
- **Deciders:** Founder

## Context

ADR-0002 placed browser tooling as **free** engine tier (generic CDP driving,
same bucket as screenshot/Figma). Extraction work on the monolith's browser
facades surfaced a real product baked into that "generic" tooling: a
dedicated, isolated automation host with per-context profile isolation
(a separate venture's browsing profile must never touch the operator's
personal one — a real confidentiality invariant, not a naming detail)
and health monitoring of that host.

That is not generic CDP driving — it is a distinct capability with real
product value, sitting on top of the generic driver. Naming it after the
generic family ("browser") would bury the value; naming it after its own
identity gives it a home and a story, matching how every other pillar of
this distro is named (Ourobouros, Atlas, Sun Wukong, Shyrka) rather than
described functionally.

## Decision

**Bucéphale — Bucephalus, Alexander's horse — is the mount that carries
automates and agents across the web.** It is a first-class addon at
`addons/bucephale/`, not a subfolder of `core/shyrka/tools/browser/`.

The split, decided explicitly (not a default):

- **`core/shyrka/tools/browser/`** (free, per ADR-0002) — the generic CDP
  driver: connect, navigate, click, read console, screenshot. Talks to *any*
  reachable Chrome instance. No product value in isolation — table stakes
  for an agentic browser skill.
- **`addons/bucephale/`** (sold) — the product: a dedicated, named automation
  host, per-context profile isolation (the confidentiality invariant above),
  health monitoring of that host. Depends on `core/shyrka/tools/browser/`
  for the wire protocol; adds the operational and safety layer around it.

The lore matters here, not as decoration: **Bucéphale carries, it does not
drive.** The engine (Shyrka) provides the CDP wire protocol; the addon
provides the horse — a dedicated place to stand, isolated per rider, that
does not throw you when it is tired (health monitoring).

## Consequences

- **Positive:** the free/sold boundary tracks real product value instead of
  a tool-family line. A contributor gets a working (if bare) browser skill
  from the free core; the addon is what makes it trustworthy multi-tenant
  infrastructure.
- **Negative:** two folders to maintain for one conceptual capability; the
  addon's docs must be explicit about the dependency direction (addon depends
  on core, never the reverse) so contributors do not accidentally couple the
  core driver to Bucéphale-specific profile concepts.
- **Neutral:** this is the first populated entry in `addons/` — it sets the
  precedent other addons (the 3D/Blender pipeline, flagged addon-candidate in
  `documentation/external-tools.md`) will follow: a named identity, a README
  stating what it adds over the free core capability it depends on.

## Alternatives considered

- **All of it free, in `core/shyrka/tools/browser/`.** Rejected: gives away
  the product-value layer (profile isolation, dedicated host, monitoring) for
  free, undermining the addon revenue this pillar exists to support.
- **All of it sold, nothing free.** Rejected: a bare CDP driver has no
  standalone product value and gatekeeping it behind a sale makes the free
  core distro unable to demonstrate a working browser skill at all — bad for
  adoption, and inconsistent with ADR-0002's existing free-tier ruling on the
  generic driving capability.
- **Named after the function ("browser-pro" / "isolated-browser").**
  Rejected: breaks the naming convention every other pillar follows, and a
  functional name describes what it does without saying why it is trustworthy
  (isolation is a promise, not just a feature).

## Links

- [ADR-0002](0002-external-tools-placement.md) — the free-tier ruling this
  ADR refines for the browser family specifically.
- [`../external-tools.md`](../external-tools.md) — inventory, updated with the
  core/addon split.
- [`../../addons/bucephale/README.md`](../../addons/bucephale/README.md) — the
  addon's own contract.
