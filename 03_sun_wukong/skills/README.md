# 📖 Wukong's Grimoire (Universal Skills)

> *"You don't die of thirst — you die of drinking from too many sources."*

This directory (`/03_sun_wukong/skills/`) is the single source of cognitive truth
for Synedre OS. It holds the Monkey King's "Seventy-two metamorphoses": the
instructions, doctrines and reasoning frames of our AI agents.

## 1. The Agnostic Philosophy

The skills held here are **strictly agnostic**.
Artificial intelligence is a commodity (Claude, Kimi, Codex, Mistral). The CLI tool
that drives it (`claude -p`, `kimi -y`) is interchangeable. What carries value is
**the business doctrine** (the Synedre doctrine, workstream management, the scars).

So that any LLM can understand this grimoire, **we reject proprietary formats**.
- No tool-specific tags like `<claude-only>`.
- No frozen JSON configuration bound to a single tool.
- Only **structured, semantic and explicit Markdown**.

## 2. The Standard Format (The Golden Headband)

Every new `SKILL.md` (or `system_*.md`) file added to this directory MUST follow
the semantic architecture below. This is what guarantees that a model like Kimi (2M
context) or Claude (Sonnet/Opus) understands the constraint the same way.

### 📝 Mandatory Template

```markdown
# [Name of the Metamorphosis / Skill] (e.g. Workstream Piloting)

## 1. Role and Identity
You are [Role/Agent]. Your objective is to [Main mission].
Never step out of this role.

## 2. The Golden Headband (Strict Rules)
- **RULE 1**: [Mandatory action, e.g. Always validate via Pydantic]
- **RULE 2**: [Access constraint, e.g. Never use absolute paths]
- **RULE 3**: [Workflow rule, e.g. Every mutation goes through Active Record]

## 3. Context & Data Sources
- [Explanation of the expected DB architecture]
- [Files or tables to read before acting]

## 4. Behavior & Arguments
- If the argument is X: Do this.
- If the argument is Y: Invoke the script `python3 -m ...`

## 5. Anti-Patterns & Scars (What NOT to do)
- ❌ Never do [Common mistake].
- ❌ Never ignore [Edge case].
```
