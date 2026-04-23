# Subtask 05: docs — builtin skill + README

Last subtask. Freezes the user-visible contract. Only runs after 04
is green (so the described behavior matches what ships).

## Goal

Document `mcp.fragment.json` in:
1. `src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md`
   — the canonical reference bundled with `init -g`; per CLAUDE.md, it
   MUST be kept in sync on every user-visible change.
2. `README.md` — one-liner in the fragments paragraph.

## File scope (exclusive)

- `src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md`
- `README.md`

## Do NOT touch

- Any source under `src/ai_dotfiles/` (other than the skill template).
- Any test file.
- `ai-dotfiles-blueprint.md` — out of scope; update in a follow-up PR
  if desired.

## Hard rules

- No marketing fluff. Match the existing terse register of the skill
  file and README.
- No emoji. No code-block languages that aren't already used in the
  file (inspect first).
- Every claim in the docs must match shipped behavior — e.g. the env
  var syntax is `${VAR}` / `${VAR:-default}`, NOT `${env:VAR}`.

## `builtin_ai_dotfiles_skill.md` — insert after the existing
`settings.fragment.json` bullet (around line 199)

```
- `mcp.fragment.json` inside a domain declares `mcpServers` merged into
  `<project>/.mcp.json` on `add` / `install`. Permissions
  `mcp__<server>__*` are auto-added to `settings.json` and server
  names are appended to `enabledMcpjsonServers` (precise allowlist —
  user-added entries in `.mcp.json` keep Claude Code's default approval
  prompt). Env-var expansion uses Claude Code's native `${VAR}` /
  `${VAR:-default}` syntax. Ownership is tracked in
  `<project>/.claude/.ai-dotfiles-mcp-ownership.json`; user-authored
  entries in `.mcp.json` are preserved on remove. If you previously
  denied a server at Claude Code's approval prompt, run
  `claude mcp reset-project-choices` after `add`. Global scope (`-g`)
  does not yet support MCP.
```

Check the surrounding paragraph for line-length conventions and match
them (wrap at ~78 cols if the file does, otherwise leave long lines).

## `README.md` — add to the fragments paragraph

One sentence, directly after the sentence that explains
`settings.fragment.json`:

> Domains may also ship `mcp.fragment.json` to declare MCP servers;
> they are merged into `<project>/.mcp.json` on `ai-dotfiles add`
> with `mcp__<server>__*` permissions auto-wired into `settings.json`.

If the README has a feature-matrix table, add a `mcp.fragment.json`
row too; otherwise the paragraph addition alone is sufficient.

## Definition of Done

1. `poetry run pytest -q` — no regression
2. `poetry run pre-commit run --all-files` — clean
3. `grep -n 'mcp.fragment.json' src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md`
   shows the new paragraph
4. `grep -n 'mcp.fragment.json' README.md` shows the one-liner
5. No other file changed

Orchestrator commits after this subtask passes:
`feat(mcp): domain mcp.fragment.json -> .mcp.json`
