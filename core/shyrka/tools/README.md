# `tools/` — wrappers for external tools

This directory holds the **wrappers and facades that drive external tools** — the
binaries and services the meta-harness does not own but must pilot: a browser
(Chromium), a 3D engine (Blender), a design API (Figma), a screenshot pipeline.

The runtime never talks to these tools directly. It talks to a facade in this
folder, and the facade is the only thing that knows how the tool is invoked,
where it is installed, and what version is pinned. **All external coupling is
isolated here.**

## Structure — one subfolder per family

```
core/shyrka/tools/
  browser/      # Chromium / CDP — automation, screenshots, QA capture
  three-d/      # Blender — shape reporting, character generation
  figma/        # Figma API — design intake
  screenshot/   # headless capture primitives
```

A family groups everything needed to pilot one tool. Inside a family, facades
follow the public naming convention `sy_<tool>_<role>.py` (e.g.
`sy_browser_control.py`, `sy_blender_shape.py`).

## The contract of a tool facade

1. **Isolate the coupling.** The rest of the runtime imports the facade, never
   the tool's SDK or binary path. If the tool's API changes, only this folder
   moves.
2. **Pin the version, elsewhere.** The exact tool version (Docker image tag, apt
   package, download URL) lives in `02_atlas/infra/`, not here. The facade reads
   it; it does not encode it.
3. **Fail closed.** If the tool is not installed or not reachable, the facade
   raises a clear, actionable error — it never silently no-ops. A hidden failure
   in a tool facade is worse than a crash, because the caller proceeds on a lie.
4. **No business logic.** The facade pilots the tool; it does not decide *what*
   to do with it. That decision lives in a skill (`03_sun_wukong/skills/`) or an
   automate (`02_atlas/workers/`).

## What does NOT belong here

| If you are adding… | It belongs in… |
|---|---|
| A skill (agent instructions to *use* the tool) | `03_sun_wukong/skills/<skill>/` |
| Install / version / Dockerfile for the binary | `02_atlas/infra/` |
| Inventory of supported tools, versions, prereqs | [`documentation/external-tools.md`](../../documentation/external-tools.md) |
| Business logic on top of the tool | an automate or a skill, not a facade |

## Open-core boundary

Most tool families are **engine** (free, part of the AGPL core): browser, screenshot,
figma — generic harness capabilities. Some are **addon candidates** (sold, outside
the AGPL core) when they are domain-specific rather than generic; the 3D families
are the clearest example. When unsure, see the tier column of
[`documentation/external-tools.md`](../../documentation/external-tools.md).

> Placement decision: [ADR-0002](../../documentation/adr/0002-external-tools-placement.md).
