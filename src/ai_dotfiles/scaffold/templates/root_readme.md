# ~/.ai-dotfiles

Storage for `ai-dotfiles` — a package manager for Claude Code configuration.

## Quick start

1. `ai-dotfiles init` — initialize a project manifest
2. `ai-dotfiles add skill:my-skill` — add an element
3. `ai-dotfiles install` — symlink into `~/.claude/` or `<project>/.claude/`

## Layout

```
~/.ai-dotfiles/
├── global/          # files symlinked into ~/.claude/
├── global.json      # global package manifest
├── catalog/         # installable content (domains + standalone)
├── stacks/          # preset .conf bundles
└── README.md
```

## Shell alias

Shorter invocation:

```bash
alias adf='ai-dotfiles'
```
