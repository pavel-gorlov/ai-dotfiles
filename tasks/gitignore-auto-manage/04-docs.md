# Subtask 04: docs — builtin skill + README

Last subtask. Freezes the user-visible contract.

## Goal

1. Update `src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md`
   to describe the auto-managed `.gitignore` block, the `--no-gitignore`
   flag, and the `manage_gitignore` manifest key.
2. Update `README.md` to mention the behavior in its Core Concepts
   section next to Symlinks / Settings merge / MCP servers.

## File scope (exclusive)

- `src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md`
- `README.md`

## Do NOT touch

- Any source. Any test. `ai-dotfiles-blueprint.md` (separate doc PR).

## Hard rules

- No emoji. No marketing tone. Match terse register of existing bullets.
- Every claim must reflect shipped behavior after 01–03 merge.

## `builtin_ai_dotfiles_skill.md` — insert bullet

Under the Notes section, next to the existing
`settings.fragment.json` / `mcp.fragment.json` bullets:

```
- `.gitignore` is auto-managed in a block delimited by
  `# >>> ai-dotfiles managed — do not edit manually <<<` markers. On
  every `add` / `remove` / `install` the block is regenerated to list
  every vendored symlink currently under `.claude/` (format:
  `/.claude/skills/<name>`). User-authored lines outside the block are
  never touched; a literal path already ignored by a user-authored line
  is not duplicated in the block. Opt out per-call with
  `--no-gitignore`, or globally by setting `"manage_gitignore": false`
  at the top level of `ai-dotfiles.json` (project) or
  `~/.ai-dotfiles/global.json` (global — project wins).
```

## `README.md` — add Core Concept bullet

Insert after the existing `MCP servers` bullet (around the Core
Concepts list):

```
- **Gitignore sync** — the CLI keeps a managed block inside
  `<project>/.gitignore` listing every vendored symlink under
  `.claude/`, so per-machine paths never land in git history. Opt out
  with `--no-gitignore` or `"manage_gitignore": false` in the manifest.
```

## Definition of Done

1. `poetry run pytest -q` — no regression.
2. `poetry run pre-commit run --all-files` — clean.
3. `grep -n 'ai-dotfiles managed'
   src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md`
   shows the new bullet.
4. `grep -n 'Gitignore sync' README.md` shows the new bullet.
5. No other file changed.

Orchestrator commits after this subtask passes:
`feat(cli): auto-manage .gitignore for vendored symlinks (#1)`.
