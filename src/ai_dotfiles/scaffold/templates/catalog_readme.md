# Catalog

All installable content lives here. Two layouts are supported.

## Domain layout

A domain bundles multiple related elements:

```
catalog/<domain>/
├── skills/
├── agents/
├── rules/
├── hooks/
└── settings.fragment.json
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

## `settings.fragment.json`

Merged into `~/.claude/settings.json` when the domain is installed. Example:

```json
{
  "_domain": "_example",
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
