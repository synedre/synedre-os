#!/bin/bash
# Synedre OS - Bootstrap and infrastructure initialization script

echo "🧱 Deploying Atlas: Initializing the Synedre OS architecture..."

# 1. Create the founding pillars
echo "🏗️ Creating the structural pillars..."
mkdir -p 00_ourobouros/{logs,tmp,backups,.chaos,tests}
mkdir -p 01_founder/{docs,customers,leads}
mkdir -p 02_atlas/{infra,devops,secrets}
mkdir -p 03_sun_wukong/{apps,workers,skills,ia_agents}
mkdir -p core/
mkdir -p addons/

# 2. Secure the .chaos directory
# Chaos must exist, but we make sure it is ready to receive uncertainty
touch 00_ourobouros/.chaos/.gitkeep

# 3. Unify the AI skills (Wukong's Grimoire)
echo "🔮 Configuring the Unified Grimoire for AI agents..."

# For Claude Code
mkdir -p .claude
rm -rf .claude/skills # Remove the default folder if it exists
ln -sf $(pwd)/03_sun_wukong/skills .claude/skills
echo "  ↳ Claude Code symlink activated."

# For Cursor / Kimi (future example)
# ln -sf $(pwd)/03_sun_wukong/skills/.cursorrules .cursorrules
# echo "  ↳ Cursor symlink activated."

# 4. Initialize the environment
if [ ! -f .env ]; then
    echo "⚙️ Generating the .env file from the example..."
    # cp .env.example .env (if you have an example)
    touch .env
    echo "SYNEDRE_ROOT=$(pwd)" >> .env
fi

# 5. Lock down permissions
echo "🔒 Locking permissions..."
chmod +x install.sh
# Make future automations executable by default
# chmod +x 03_sun_wukong/workers/*.sh 2>/dev/null

echo "✅ Synedre OS is ready. The Golden Headband is in place."


# 🔗 Configure Atlas reflexes (Hooks per domain)
echo "🔗 Activating hooks..."

# 1. Git Hooks (Standard)
chmod +x 02_atlas/hooks/git/*
ln -sf $(pwd)/02_atlas/hooks/git/pre-commit .git/hooks/pre-commit
echo "  ↳ Git hooks installed."

# 2. Hooks for AI agents
# Make scripts executable if they exist
chmod +x 02_atlas/hooks/claude/* 2>/dev/null
chmod +x 02_atlas/hooks/kimi/* 2>/dev/null
chmod +x 02_atlas/hooks/codex/* 2>/dev/null
echo "  ↳ Agent hooks/wrappers prepared."



# 🔗 Configure Sun Wukong transformations (Skills per domain)
echo "🔗 Activating skills..."
ln -sf $(pwd)/03_sun_wukong/skills .claude/skills

# For Kimi Code (example)
ln -sf $(pwd)/03_sun_wukong/skills/system_chantier.md .kimirules



echo "🔗 Configuring the DNA of AI agents..."

# Create the hidden folder if it does not exist
mkdir -p ~/.claude

# Symlink the full settings file
ln -sf $(pwd)/02_atlas/config/claude/claude_settings.json ~/.claude/settings.json

echo "  ↳ Claude Code brain (Permissions, Hooks, Status) locked onto Atlas."

echo "🔗 Compiling the DNA of Kimi Code..."

# Create the target folder (Kimi often uses ~/.kimi-code)
mkdir -p ~/.kimi-code

# Compile the TOML template with sed
sed "s|__SYNEDRE_ROOT__|$PWD|g" 02_atlas/config/kimi/kimi_config.tpl.toml > ~/.kimi-code/config.toml

echo "  ↳ config.toml generated successfully for Kimi."
