# Catalog

All installable content lives here. Two layouts are supported.

## Domain layout

A domain bundles multiple related elements:

```
catalog/<domain>/
├── domain.json              # metadata (name, description, depends, requires)
├── settings.fragment.json   # Claude Code config merged into settings.json
├── mcp.fragment.json        # optional — MCP servers merged into .mcp.json
├── skills/
├── agents/
├── rules/
└── hooks/
```

Reference the whole domain with `@<domain>`.

## Standalone layout

Single elements without a domain:

```
catalog/skills/<name>/SKILL.md
catalog/agents/<name>.md
catalog/rules/<name>.md
```

Reference them with `skill:<name>`, `agent:<name>`, `rule:<name>`.

## `domain.json`

Canonical metadata manifest for a domain:

```json
{
  "name": "python-backend",
  "description": "FastAPI + async SQLAlchemy backend domain",
  "depends": ["@python"],
  "requires": {
    "npm": ["@playwright/mcp"]
  }
}
```

All fields are optional. `depends` lists other elements (`@domain`, `skill:x`, `agent:y`, `rule:z`) that must be installed alongside this one — `ai-dotfiles add` pulls them in transitively. `requires.npm` lists host npm packages that should be present in `package.json` (warns if missing).

## `settings.fragment.json`

Pure Claude Code config — merged into `~/.claude/settings.json` when the domain is installed:

```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Edit|Write",
      "hooks": [{"type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/example-lint.sh"}]
    }]
  }
}
```

## Vendoring

Pull external content in with `ai-dotfiles vendor <url>`.
