# Addons

The merchant frontier of Synedre OS: modules sold on the marketplace, outside
the AGPL core. Each addon gets a named identity (lore-consistent with the
pillars — Ourobouros, Atlas, Sun Wukong, Shyrka) and a README stating what it
adds over the free core capability it depends on; dependency direction is
always addon → core, never the reverse.

| Addon | Adds over the free core | Status |
|---|---|---|
| [`bucephale/`](bucephale/README.md) | Dedicated browser host, per-context profile isolation, health monitoring — on top of `core/shyrka/tools/browser/`'s generic CDP driver | Scaffold ([ADR-0005](../documentation/adr/0005-bucephale-browser-addon.md)) |

*(3D/character-generation is an addon candidate — see
[`documentation/external-tools.md`](../documentation/external-tools.md) —
not yet named or scaffolded.)*
