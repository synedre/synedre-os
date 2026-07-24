# 🛠️ External tools — inventory & conventions

> The wrappers that drive these tools live in
> [`core/shyrka/tools/`](../core/shyrka/tools/) (one subfolder per family). This
> page is the **inventory**: what is supported, where, and at which open-core
> tier. Placement rationale: [ADR-0002](adr/0002-external-tools-placement.md).

The meta-harness pilots external binaries and services (a browser, a 3D engine,
a design API) through **facades**, never directly. Every external coupling is
isolated behind a facade so the rest of the runtime stays tool-agnostic.

## Inventory

| Tool | Family | Wrapper | Skill(s) using it | Install | Tier |
|---|---|---|---|---|---|
| Chromium / CDP (generic driver) | `browser/` | `core/shyrka/tools/browser/` | QA-capture, browser automation | `02_atlas/infra/` | **free** (engine) |
| Chromium / CDP (dedicated host, profile isolation, monitoring) | — | [`addons/bucephale/`](../addons/bucephale/README.md) | same skills, hardened | `02_atlas/infra/` | **sold** (addon, [ADR-0005](adr/0005-bucephale-browser-addon.md)) |
| Blender | `three-d/` | `core/shyrka/tools/three-d/` | shape-report, character generation | `02_atlas/infra/` | **addon candidate** |
| Figma API | `figma/` | `core/shyrka/tools/figma/` | design intake | `02_atlas/infra/` | **free** (engine) |
| Headless capture | `screenshot/` | `core/shyrka/tools/screenshot/` | several | `02_atlas/infra/` | **free** (engine) |

> **Tier meaning.** *free* = part of the AGPL engine, ships in the public distro.
> *addon candidate* = domain-specific, may ship as a sold addon outside the AGPL
> core. *sold* = decided, addon-only (never ships in `core/`). The boundary is
> decided per family — and, since ADR-0005, can split WITHIN a family: the
> generic browser driver is free, the branded host/isolation/monitoring layer
> on top of it is sold.

## Conventions

1. **One facade per concern, one family per tool.** A wrapper belongs to exactly
   one family subfolder. If two tools share nothing but a name, they are two
   families.
2. **Version is pinned in `02_atlas/infra/`, not in code.** The facade reads the
   pinned version; it never hardcodes a download URL or image tag. This keeps
   upgrades in one place.
3. **Fail closed.** A missing or unreachable tool raises a clear error from the
   facade — never a silent no-op. See the facade contract in
   [`core/shyrka/tools/README.md`](../core/shyrka/tools/README.md).
4. **No internal names leak.** Wrappers in the public distro must be scrubbed of
   proprietary prefixes, tenant codenames and absolute paths — the same rule as
   everywhere (CLAUDE.md Rule 3). A wrapper that references an internal host or a
   tenant-specific endpoint does not ship.

## Adding a new tool

1. Create `core/shyrka/tools/<family>/` and the facade `sy_<tool>_<role>.py`.
2. Pin the install in `02_atlas/infra/`.
3. Add a row to the inventory table above (tool, family, wrapper, skills, install, tier).
4. If a skill will use it, write the skill in `03_sun_wukong/skills/` following
   the Golden Headband template.
5. Decide the tier honestly: is this generic engine, or domain addon? When unsure,
   leave it *free* and revisit — downgrading to addon later is easier than the
   reverse.

## Anti-patterns

- **Inlining the tool's SDK calls in a skill or automate.** Route through the
  facade; the coupling stays here.
- **Hardcoding the version in the facade.** Pin it in `02_atlas/infra/`.
- **Silent degradation when the tool is absent.** Fail closed.
- **A family that mixes two tools.** Split it; one family, one tool.
