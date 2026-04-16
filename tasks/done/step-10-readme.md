# Step 10: README.md

## Goal

Write project README with installation, quick start, full command reference, and examples.

## File: `README.md`

### Structure

```markdown
# ai-dotfiles

Package manager for Claude Code configuration. Like npm for your AI coding setup.

Manifest file in your project + `install` on another machine = everything restored.

## Install

\`\`\`bash
pipx install ai-dotfiles
\`\`\`

## Quick Start

\`\`\`bash
# 1. Create global storage
ai-dotfiles init -g

# 2. Set up a project
cd ~/projects/my-api
ai-dotfiles init
ai-dotfiles add @python skill:code-review

# 3. On another machine
ai-dotfiles init -g --from git@github.com:you/my-ai-config.git
cd ~/projects/my-api
ai-dotfiles install
\`\`\`

## How It Works

[Brief: manifest (ai-dotfiles.json) + storage (~/.ai-dotfiles/) + symlinks into .claude/]

## Element Format

| Format        | Resolves to                    |
|---------------|--------------------------------|
| @domain       | catalog/<domain>/              |
| skill:name    | catalog/skills/<name>/         |
| agent:name    | catalog/agents/<name>.md       |
| rule:name     | catalog/rules/<name>.md        |

## Commands

### Project / Global
[Table or list of all commands with one-line descriptions]

### Elements
[create, delete]

### Domains
[domain create|delete|list|add|remove]

### Stacks
[stack create|delete|list|add|remove|apply]

### Vendoring
[vendor]

## Storage Structure

[Directory tree of ~/.ai-dotfiles/]

## Configuration

| Setting          | Value              |
|------------------|--------------------|
| Storage path     | ~/.ai-dotfiles/    |
| Override         | AI_DOTFILES_HOME   |
| Project manifest | ai-dotfiles.json   |
| Global manifest  | global.json        |

## License

MIT
```

### Key points

- Keep concise — not a spec document, a user guide
- Show don't tell — real command examples
- Link to blueprint for full details
- English (this is a public repo)

## Definition of Done

- [ ] `README.md` updated with full content (not just header)
- [ ] Includes: install, quick start, all commands, element format, env vars
- [ ] Includes: development section (poetry install, pre-commit, pytest, mypy)
- [ ] `poetry run pytest --cov` — full test suite passes, coverage >= 80%
- [ ] `poetry run pre-commit run --all-files` — all checks pass
- [ ] `ai-dotfiles --help` matches command list in README

## Commit message

`docs: README with installation, quick start, and command reference`
