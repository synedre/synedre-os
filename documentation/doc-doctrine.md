# 📝 Documentation doctrine

> **Status:** active. This is the public doctrine for anyone (human or AI agent)
> writing or generating documentation in Synedre OS. The condensed machine
> version lives in `CLAUDE.md` (local); this is the full version.

Documentation rots. A schema written in Markdown drifts in silence; a signature
described in prose becomes a lie the day the function changes and nobody updates
the page. This doctrine exists to make drift **loud, bounded, and mostly
mechanical to repair** — by separating what documentation *is* into three layers
that must never be confused.

---

## 1. The three layers

Every piece of documentation belongs to exactly one of three layers. Each layer
answers a different question, derives its truth from a different source, and has
a different lifecycle. **Confusing the layers is the root cause of drift.**

| Layer | Answers | Source of truth | Lifecycle | Lives in |
|---|---|---|---|---|
| **1. Code** | *What is* | Itself — absolute | Permanent | source files |
| **2. How (generated)** | *How it works* | Derived from code | Ephemeral, regenerable | `documentation/` |
| **3. Why (ADR)** | *Why we chose this* | A human decision | Immutable, dated | `documentation/adr/` |

### Layer 1 — Code is the truth

The code is the only absolute source of truth for *what the system is*. Types,
function signatures, data models, table schemas, route paths — these live in
code, not in prose. If a docstring and the code disagree, **the code is right by
definition** and the doc is debt.

Consequence: structural facts (a function's name, its parameters, a model's
fields, a table's columns) are **never transcribed by hand** into documentation.
They are read from the code by the generator. A hand-typed parameter list in a
doc page is a lie waiting to happen.

### Layer 2 — The "how" is generated

The technical documentation — *how* the pieces fit, what each module does, how a
pipeline flows — is **generated from the code and regenerated as the code
changes.** It is a derived artifact, not a primary one.

- **Structural content is always generated.** Signatures, field tables, module
  inventories, route maps, cross-references. Marked `<!-- AUTO-GENERATED -->` so
  a human never edits them by hand and the generator can overwrite them whole.
- **Semantic content may be human-authored**, but lives *next to* the code as a
  docstring (see Layer 1's rule), not in a separate page that drifts away. The
  generator lifts the docstring into the page; it does not invent it.
- **Generated pages are ephemeral and reproducible.** Deleting all of
  `documentation/` and regenerating must produce an equivalent corpus. If it
  does not, the generator is broken or the docstrings are missing — both are
  bugs, not "lost work".

### Layer 3 — The "why" is immutable (ADR)

A decision *why* the architecture is shaped a certain way — why one database,
why camp-against-camp, why AGPL, why this boundary between engine and scars — is
not derivable from code. It is a human judgment, made on a date, by people who
weighed alternatives. These decisions are recorded as **Architecture Decision
Records (ADR)** and they are **immutable**:

- You do **not** edit an accepted ADR. If the decision changes, you write a new
  ADR that supersedes it and mark the old one `Superseded by ADR-0042`. The
  history of *why we changed our mind* is itself valuable.
- An ADR is dated and numbered (see `adr/0000-index.md`).
- ADRs answer *why*, never *what* or *how*. If a paragraph restates the code, it
  belongs in Layer 2.

---

## 2. Drift, honestly

> "Zero drift" is a real goal for **structural** drift and a myth for
> **semantic** drift. Say which one you mean.

| Drift type | Example | Mechanically detectable? | Bounded by |
|---|---|---|---|
| **Structural** | Doc cites a function renamed; field table missing a column; dead file path | **Yes** — the mirror compares code to doc | The regeneration pass |
| **Semantic** | Docstring says "sends the email" but the code silently drops it on error | **No** — the prose and the behaviour are both valid strings | Tests + scars + external review |

- **Structural drift tends to ~0 per generation**, because the generator reads
  the code fresh. The mirror (the drift watcher) catches what the generator
  missed — code newer than the doc, dead references, a published page lagging
  its internal source.
- **Semantic drift is never zero.** A regenerated page faithfully reproduces a
  misleading docstring; the lie propagates. The only honest filets are: tests
  that assert *behaviour* (not shape), scars (production lessons that recorded a
  time the doc misled someone), and the deliberate gaze of an outside reviewer.
- A doc that passes the mirror is **structurally faithful**, not **correct**.
  Treat the mirror as a guardrail, not as proof. (See: a guard that exists proves
  nothing — assert the effect, prove by mutation.)

---

## 3. Anti-leak: the regen runs on *scrubbed* code

> This is the single largest documentation risk for an open-core project. Read it
> twice.

The generator derives pages **from the code**. In a private monolith the code may
contain things that must never be public: proprietary prefixes, tenant codenames,
absolute paths, internal hostnames, scar references, secret-shaped strings. If
the generator reads that code directly and emits Markdown, **all of it lands in
the public documentation** — and a downstream scrub of the *prose* is too late,
because the generator already wove the leak into sentences.

**Rule:** documentation is generated from code that has **already been scrubbed
and renamed for the public distribution** (proprietary prefixes stripped, tenants
removed, paths relativized). The scrub is a property of the *source the generator
consumes*, not a filter bolted onto the *output the generator produces*.

Concretely, the generation pipeline is ordered:

```
source code (scrubbed for the distro)
        │
        ▼
   generate (derive the "how")
        │
        ▼
   stage (pending, never live)
        │
        ▼
   leak gate (automated check on everything staged)
        │
        ▼
   publish  ◀── human approval only
```

- The **leak gate** runs on every staged page and refuses to publish anything
  matching a secret pattern, an absolute home path, a proprietary prefix, or a
  known tenant codename. It is the last automated line.
- **Publishing is never autonomous.** A human activates the staged version. The
  machine prepares and sanitizes; the human decides.
- If you ever find yourself wanting to "just publish the generated pages
  directly", remember the ordering: **scrub the source, then generate.** Not the
  reverse.

---

## 4. Boundary: internal docs vs public docs

Two strata of documentation coexist, and the boundary between them is deliberate:

| Stratum | May contain | Audience | Example |
|---|---|---|---|
| **Internal** | Internal references, private context | The team / the private monolith | raw chapter drafts before sanitization |
| **Public** | Scrubbed, generalized content | Contributors and the world | what is published to the distro |

The same subject often exists in both strata: an internal page rich with private
context, and a public page scrubbed of it. They are **not** the same file kept in
sync by hand — the public page is *produced* from the internal one through the
scrub, exactly as Layer 2 is produced from Layer 1. Hand-syncing two copies is how
the public copy leaks.

---

## 5. When you change something, what do you update?

| You changed… | Update now |
|---|---|
| A signature, field, route, or schema (structural) | Nothing by hand — the next generation picks it up. The mirror will flag the gap until then. |
| A docstring (semantic) | The docstring *is* the update. It lives next to the code; the generator lifts it. |
| Behaviour in a way a docstring now misdescribes | The docstring (Layer 2) **and** check whether a scar is warranted. |
| An architectural decision or its rationale | Write or supersede an ADR (Layer 3). Never patch an old ADR in place. |
| Added a tenant/secret/proprietary symbol | Nothing in *this* repo — it must not be here. If it arrived via generation, the source was not scrubbed (§3). |

---

## 6. The anti-patterns

1. **Transcribing structural facts into prose by hand.** A typed parameter list
   is a lie the next refactor. Generate it.
2. **Editing an `<!-- AUTO-GENERATED -->` block by hand.** The next regen erases
   your edit and you will not notice. If the generated content is wrong, fix the
   *docstring* (the source), not the page.
3. **Editing an accepted ADR in place.** Supersede it. The history of decisions
   is part of the documentation.
4. **Generating before scrubbing.** The single most expensive mistake in
   open-core (§3). Scrub the source first.
5. **Trusting the mirror as proof of correctness.** It proves structural
   faithfulness, not semantic truth (§2).
6. **Keeping an internal and a public copy in sync by hand.** Produce the public
   from the internal; do not maintain two sources (§4).

---

## 7. Maintenance

- **Measure drift:** the mirror reports code-newer, dead-ref, and
  published-stale gaps. A clean mirror = structurally faithful, not correct.
- **Regenerate:** the deep regenerator rewrites a chapter to realign with the
  code, stages the scrubbed public version, and passes the leak gate.
- **Repair mechanically first:** dead references resolved by an unambiguous
  basename match are fixed deterministically; anything ambiguous is proposed for
  human review, never auto-rewritten.
- **A new scar that doc contributed to:** record it. Scars are how semantic drift
  gets noticed the second time it bites.

---

## 8. Links

- [`adr/0000-index.md`](adr/0000-index.md) — the Why layer: how to write and
  number an ADR.
- `CLAUDE.md` Rule 2 — the condensed machine version of this doctrine.
- The camp principle — *execution and validation are separated, and the roles are
  reversible*. The generator executes (derives), the mirror and the leak gate
  validate; neither validates its own work.
