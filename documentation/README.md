# Documentation

Documentation for the Synedre OS harness — camp mechanics, facades, installation,
doctrine. To be filled in the following workstreams (extraction + harness docs).

## Index

- **[`doc-doctrine.md`](doc-doctrine.md)** — the documentation doctrine. Three
  layers (code is truth / the how is generated / the why is immutable), how drift
  is bounded honestly, and the anti-leak rule that the regen runs on *scrubbed*
  code.
- **[`external-tools.md`](external-tools.md)** — inventory and conventions for the
  external tools the harness pilots (browser, 3D, Figma…), where their wrappers
  live and at which open-core tier.
- **[`automates-and-camps.md`](automates-and-camps.md)** — the execution layer:
  agent vs automate, how the camps map to the pillars (Atlas = West, Wukong =
  East), and why castes live in the DB, not in folders.
- **[`adr/`](adr/)** — Architecture Decision Records, the *why* layer. Start at
  [`adr/0000-index.md`](adr/0000-index.md); copy
  [`adr/0000-template.md`](adr/0000-template.md) to write a new one.
