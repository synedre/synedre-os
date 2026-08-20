# 🧬 Synedre OS

> *"We give away the engine. We keep the experience."*

**Synedre OS** is the open-core **agentic meta-harness** (AGPL-3.0): the substrate
that orchestrates a fleet of AI agents — camp against camp — around a **single
database**. It is the shared engine behind our two public verticals,
**[CodeMyShop](https://github.com/synedre/codemyshop)** (commerce) and
**[Corbie](https://github.com/synedre/corbie)** (household).

> ⚠️ **Status: scaffold.** This repository lays down the structure and the legal
> foundation. The runtime code (harness extraction, `ac_` → `sy_` rename,
> `bootstrap.sql`, the Shirka chassis) lands in the following workstreams — see
> `documentation/`.

## 1. The open-core doctrine

| Free (AGPL-3.0) | Sold (marketplace) |
|---|---|
| Camp mechanics, harness, facades | Scars (production lessons) |
| Multi-brain (Claude Code + Kimi Code) | Addons & domain skills |
| Structure, `.tpl.*` templates | Data & experience |

The moat is what the system *knows* — not what it *is*.

> 🛑 No scar, no customer data, no secret must ever appear in this repository. The
> `core/shyrka/brain/` directory is gitignored **by design**.

## 2. The architecture — four pillars

| Pillar | Role |
|---|---|
| `00_ourobouros/` | **Technical memory** — logs, tests, backups, chaos. The self-devouring serpent: live state. |
| `01_founder/` | **The Founder** — docs, customers, leads. The business layer. |
| `02_atlas/` | **The Orchestrator** — infra, devops, secrets, hooks, configs (`.tpl.*` templates). |
| `03_sun_wukong/` | **The Executor** — apps, workers, skills, AI agents. The Monkey King's metamorphoses. |
| `core/shyrka/` | **The Core** — the meta-harness runtime (`brain/` is private). |
| `addons/` | **The merchant frontier** — sold modules, outside the AGPL core. |

Guiding principle: **execution and validation are separated — and the roles are
reversible.** Whichever camp produces, the other validates; never does a camp
validate its own work, in either direction.

The camps map to the pillars: **`02_atlas/` is the West (Occident)** — the titan
that validates, schedules and orchestrates; the deterministic automates live in
its `workers/`. **`03_sun_wukong/` is the East (Orient)** — the monkey that
executes, thinks and transforms; the LLM agents live in its `agents/`.
`core/shyrka/` is the neutral engine both camps run on. What is reversible is
*which provider occupies each camp*, not the nature of a given routine — see
[`documentation/automates-and-camps.md`](documentation/automates-and-camps.md).

## 3. Multi-brain

Synedre OS is not tied to one LLM. The skills (`03_sun_wukong/skills/`) are
provider-agnostic: semantic Markdown, never a proprietary format. The installer
wires Claude Code **and** Kimi Code to the same grimoire (see
[`03_sun_wukong/skills/README.md`](03_sun_wukong/skills/README.md)).

## 4. Install

```bash
git clone https://github.com/synedre/synedre-os.git
cd synedre-os
./install.sh
```

> `install.sh` is a **stub** (hook directories and the runtime are not extracted
> yet). It will serve as the bootstrap once extraction is complete.

## 5. Contributing

External contributions will be welcomed **after** signing the CLA — see
[`CLA.md`](CLA.md). The project does not accept external PRs yet.

## License

[AGPL-3.0](LICENSE) — © 2026 Alexandre Carette.

**The code is free. The name is not.** *Synedre* and *CodeMyShop* are
trademarks held by Alexandre Carette; the AGPL-3.0 grants you the code, not
the name. Section 7(e) of the licence expressly allows this — see
[`TRADEMARK.md`](TRADEMARK.md), which is deliberately permissive: almost
everything you are likely to want to do needs no permission at all.

Part of the **Synedre** ecosystem — a sovereign agentic engine.
