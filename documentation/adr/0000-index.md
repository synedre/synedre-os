# 🧭 ADR Index — Architecture Decision Records

> The **Why** layer of the [documentation doctrine](../doc-doctrine.md).
> Decisions live here; they are dated, numbered, and **immutable**.

An **ADR** records *why* an architectural choice was made, on what date, by whom,
and what alternatives were rejected. It is not a spec, not a how-to, and not a
restatement of the code — those belong in Layer 2. An ADR is the smallest unit of
*irreversible reasoning* the project wants to remember.

## The four pillars of a good ADR

1. **Irreversible-ish.** If the decision were trivial to undo, it does not need
   an ADR. ADRs are for choices that are expensive to reverse, or that shape many
   downstream decisions (one database; camp-against-camp; AGPL; engine-vs-scars
   boundary).
2. **Dated and signed.** A decision made in a context is only intelligible with
   its context. Record the date and the deciders.
3. **Immutable once accepted.** You do not edit an accepted ADR. If reality
   changes, you write a new one that *supersedes* it and mark the old one
   `Superseded by ADR-NNNN`. The history of changed minds is part of the record.
4. **Why, not what.** If a paragraph restates the code or the schema, cut it. The
   ADR earns its place by capturing the reasoning the code cannot express.

## Numbering

- `0000` is reserved for this index and the template (`0000-template.md`).
- Real decisions start at `0001`, strictly increasing, never reused.
- Filename: `NNNN-kebab-case-title.md`.

## Statuses

| Status | Meaning |
|---|---|
| `Proposed` | Drafted, not yet adopted. Open for challenge. |
| `Accepted` | Adopted and in force. Immutable from here. |
| `Deprecated` | No longer in force, not directly replaced. |
| `Superseded by ADR-NNNN` | Replaced by a later ADR. The link is mandatory. |

## When to write one

- A choice that constrains many future choices (data model, licensing, isolation
  model, provider coupling).
- A choice where a reasonable person would have picked differently, and you want
  the *why* on record so it is not relitigated blindly.
- A reversal of a previous ADR (the new ADR supersedes, the old one is annotated).

## When *not* to write one

- Bug fixes, refactors, feature work — these are code, not decisions.
- Anything fully reversible in one commit.
- Anything the code already says unambiguously.

## How to write one

Copy [`0000-template.md`](0000-template.md). Fill every section. Be honest about
the consequences you do not like — an ADR that lists only upside is marketing,
not a decision record.

---

## Records

| ID | Title | Status | Date |
|---|---|---|---|
| [0001](0001-three-layer-documentation-doctrine.md) | Three-layer documentation doctrine (code-truth / generated how / immutable why) | Accepted | 2026-07-23 |
| [0002](0002-external-tools-placement.md) | External tools placement (`core/shyrka/tools/<family>/`) | Accepted | 2026-07-23 |
| [0003](0003-automates-camps-and-castes.md) | Automates, camps and castes (camps ↔ pillars, castes in DB, not folders) | Accepted | 2026-07-23 |
| [0004](0004-engine-organs.md) | Engine organs live in the core (organ = called; worker = entry point) | Accepted | 2026-07-24 |
| [0005](0005-bucephale-browser-addon.md) | Bucéphale — the browser addon (free CDP driver in core, sold profile-isolation/host/monitoring as addon) | Accepted | 2026-07-24 |
| [0006](0006-skills-default-addon-tier.md) | Skills default to addon-tier (free only for harness-own-mechanics skills) | Accepted | 2026-07-24 |
