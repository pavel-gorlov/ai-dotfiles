# Global Claude Config

This directory holds files symlinked into `~/.claude/`. They are loaded in
**every** Claude Code session.

| File / Dir          | Purpose                                                     |
| ------------------- | ----------------------------------------------------------- |
| `CLAUDE.md`         | Global memory — instructions loaded in every session        |
| `settings.json`     | Global settings: permissions, env vars, hooks               |
| `hooks/`            | Executable hook scripts referenced from `settings.json`     |
| `output-styles/`    | Reusable output-style markdown files                        |

## Selected global targets

The sibling `global.json` controls catalog packages and their targets. Without
`targets`, the default is `["claude"]`. To also render Codex and DeepSeek Harness,
edit that manifest to include `"targets": ["claude", "codex", "dsh"]`, then use:

```bash
ai-dotfiles install -g
ai-dotfiles status -g
ai-dotfiles reconcile -g --check
```

`add -g`, `remove -g` and `reconcile -g` use the same selected targets;
`install -g --prune` retires proven owned stale outputs. This directory remains
the Claude configuration source. Codex outputs go to `$CODEX_HOME` (default
`~/.codex`); DSH skills and managed resources go to `$DSH_HOME` (default `~/.dsh`).
These native homes are independent of catalog storage (`AI_DOTFILES_HOME`).
Native DSH profiles and home patches remain user-owned.

For DSH, install official `@deepseek-ai/dsh@0.2.0-rc.2` and Node separately and
prepare an existing native profile. From the consuming project, activate the
fresh global and selected project contributions with:

```bash
ai-dotfiles dsh launch --profile headless "review the changes"
```

Use an existing preset-free profile for headless operation. RC2 preset-managed
headless composition is refused with `COMPOSITION_NOT_SELECTED`; preset-aware
Web is supported. The launcher audits the selected native tree before Ready or
turns. It never installs a runtime or creates/repairs profiles. Restart after
source changes: managed overlays are immutable and native HMR is disabled.
One process binds to its launching project; Web project switching is not hard
isolation.

See the [storage reference](../README.md),
[CLI reference](../catalog/skills/ai-dotfiles/SKILL.md) and the
[DSH guide](https://github.com/pavel-gorlov/ai-dotfiles/blob/main/docs/dsh-target.md)
for native precedence, compatibility limits and migration (project-only).

## Docs

- https://docs.anthropic.com/en/docs/claude-code/settings#claude-directory
- https://docs.anthropic.com/en/docs/claude-code/settings
- https://docs.anthropic.com/en/docs/claude-code/hooks
- https://docs.anthropic.com/en/docs/claude-code/memory
- https://docs.anthropic.com/en/docs/claude-code/best-practices
- https://docs.anthropic.com/en/docs/claude-code/settings#output-styles
