# Bucéphale — the browser addon

*Bucephalus, Alexander's horse: the mount that carries automates and agents
across the web.* Placement rationale: [ADR-0005](../../documentation/adr/0005-bucephale-browser-addon.md).

## What this addon adds over the free core

[`core/shyrka/tools/browser/`](../../core/shyrka/tools/browser/) (free, AGPL)
is the generic CDP driver: connect, navigate, click, read console, screenshot.
It talks to *any* reachable Chrome instance and has no opinion about who is
riding.

Bucéphale is the product layer on top:

1. **A dedicated, named automation host.** Not a shared, anonymous headless
   instance — a host with an identity, monitored for health, that the rest
   of the runtime can depend on.
2. **Per-context profile isolation.** Separate riders never share a saddle:
   a confidentiality invariant, not a convenience feature. Two contexts
   (e.g. the Founder's personal browsing and a household venture's) must
   never resolve to the same cookie jar / session / history.
3. **Health monitoring of the host itself** — is the horse still standing,
   still fast enough to carry a rider, still pointed the right way.

## Dependency direction

Bucéphale depends on `core/shyrka/tools/browser/` for the wire protocol. The
core driver must never import or assume anything Bucéphale-specific (profile
names, host identity) — see the "no reverse coupling" rule in
[ADR-0002](../../documentation/adr/0002-external-tools-placement.md).

## Status

*(Scaffold — empty at seed. Extraction target for a future workstream; see
`publish-whitelist.txt` §NEXT-WAVE / project memory for the monolith source
candidates already surveyed: `ac_browser_control.py` carries the
profile-isolation invariant this addon needs to genericize before it ships.)*
