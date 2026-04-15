# Global Claude Config

This directory holds files symlinked into `~/.claude/`. They are loaded in
**every** Claude Code session.

| File / Dir          | Purpose                                                     |
| ------------------- | ----------------------------------------------------------- |
| `CLAUDE.md`         | Global memory — instructions loaded in every session        |
| `settings.json`     | Global settings: permissions, env vars, hooks               |
| `hooks/`            | Executable hook scripts referenced from `settings.json`     |
| `output-styles/`    | Reusable output-style markdown files                        |

## Docs

- https://docs.anthropic.com/en/docs/claude-code/settings#claude-directory
- https://docs.anthropic.com/en/docs/claude-code/settings
- https://docs.anthropic.com/en/docs/claude-code/hooks
- https://docs.anthropic.com/en/docs/claude-code/memory
- https://docs.anthropic.com/en/docs/claude-code/best-practices
- https://docs.anthropic.com/en/docs/claude-code/settings#output-styles
