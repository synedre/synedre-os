# ⚙️ The Atlas Matrix (Configurations & Templates)

> *"Order is not negotiated with agents — it is imposed through infrastructure."*

This directory (`/02_atlas/config/`) is the sanctuary of Synedre OS configuration
files. It holds the purified DNA of the tools that make up our system (Claude Code,
Kimi, Git, PM2, etc.).

## 1. The "Junk DNA" and Absolute-Path Problem

Many modern tools use JSON or YAML configuration files (e.g. `settings.json`). For
a sound architecture, these formats raise two major problems:
1. **They are dead:** they do not support dynamic environment variables (such as
   `$PWD` or `$SYNEDRE_ROOT`).
2. **They get dirty:** tools like Claude Code constantly rewrite their own
   configuration (executed commands, history). Versioning these raw files
   accumulates "junk DNA" in our Git repository.

## 2. The Solution: Template Compilation

To guarantee **Zero Drift** (no infrastructure divergence between prod, preprod and
local), Atlas does not use static files. It uses **Templates**.

Every file in this directory carries the `.tpl.*` extension
(e.g. `claude_settings.tpl.json`).

### Authorized Variables
In these templates we use universal substitution tags. The main one is:
*   `__SYNEDRE_ROOT__`: the absolute path of the project at deploy time.

*Example in a template:*
```json
"command": "__SYNEDRE_ROOT__/02_atlas/hooks/claude/doctrine-hook.sh"
```
