# Feature: `mcp.fragment.json` support for domains

## Goal

Let domains declare MCP servers alongside skills/agents/rules/hooks.
After `ai-dotfiles add @foo`, any `mcpServers` entries in
`catalog/foo/mcp.fragment.json` land in `<project>/.mcp.json`, and
corresponding `mcp__<server>__*` permissions land in `settings.json`.
`remove` reverses the operation, leaving user-authored `.mcp.json`
entries untouched.

## Why

Today a domain can bundle skills, agents, rules, hooks, and a settings
fragment — but MCP servers must be added manually to each project.
Adding the MCP dimension closes the loop: one `ai-dotfiles add
@playwright` installs the skill AND wires the server AND grants the
permissions.

Plan file (Claude Code pull): verified against MCP docs
(<https://code.claude.com/docs/en/mcp.md>,
<https://code.claude.com/docs/en/settings.md>,
<https://code.claude.com/docs/en/permissions.md>). Key-names and
env-var syntax match the real Claude Code surface.

## Plan

Five subtasks, run **sequentially** — they share files:

| # | Subtask | Details |
|---|---------|---------|
| 1 | `core/mcp_merge.py` + unit tests          | [mcp-fragments/01-core-merge.md](mcp-fragments/01-core-merge.md) |
| 2 | `core/mcp_ownership.py` + unit tests      | [mcp-fragments/02-ownership.md](mcp-fragments/02-ownership.md)  |
| 3 | Skip-list + add/remove/install wiring     | [mcp-fragments/03-wire-commands.md](mcp-fragments/03-wire-commands.md) |
| 4 | Integration + e2e tests                   | [mcp-fragments/04-tests.md](mcp-fragments/04-tests.md)          |
| 5 | Docs (builtin skill + README)             | [mcp-fragments/05-docs.md](mcp-fragments/05-docs.md)            |

### Execution

```
01 (mcp_merge.py)
   │
   v
02 (mcp_ownership.py)
   │
   v
03 (wire into add/remove/install)   <- imports 01+02
   │
   v
04 (integration + e2e)              <- exercises 03
   │
   v
05 (docs)                           <- final CLI surface frozen
```

## Orchestrator role

- Dispatch in order 01 → 02 → 03 → 04 → 05.
- After each subtask: run `poetry run pytest -q`,
  `poetry run mypy src/`, `poetry run ruff check src/ tests/`,
  `poetry run black --check src/ tests/`,
  `poetry run pre-commit run --all-files`. Halt on failure and report.
- Never run subtasks in parallel — 03 modifies `add.py`, `remove.py`,
  `install.py`, `elements.py`, `symlinks.py`, all of which 04's tests
  import transitively.
- Do NOT ask the subagents to commit. Commit once after 05 lands and
  all gates pass, using a single
  `feat(mcp): domain mcp.fragment.json -> .mcp.json` message.
- Solo-repo direct-to-main push is the accepted convention for this
  repo — no PR needed unless explicitly requested.

## Non-goals (MVP scope)

- No `ai-dotfiles mcp …` subcommand group (Phase 2).
- No `ai-dotfiles domain mcp …` scaffolding helpers (Phase 2).
- No `-g` / global scope for MCP (Phase 3; user-scope lives in
  `~/.claude.json` and mixes with session state).
- No subprocess to `claude` CLI.
- No `ai-dotfiles mcp import` from existing `.mcp.json` (Phase 3).
- No `--force` override flag on first-time name collision (Phase 2).
- No conflict-diff UI.
- No `mcp.fragment.json` stub written by `domain create` (Phase 2).
- No expansion of `${VAR}` / `${VAR:-default}` at write time — tokens
  written verbatim; Claude Code expands at runtime.

## Design decisions (approved)

| Question | Decision |
|----------|----------|
| Ownership file location | `<project>/.claude/.ai-dotfiles-mcp-ownership.json` |
| Name collision | Domain wins iff server is already in ownership; first collision → user keeps it, WARN |
| `_requires.npm` check | In MVP; reads project root `package.json` only |
| Settings allowlist key | `enabledMcpjsonServers: [<names>]` (precise); NOT `enableAllProjectMcpServers: true` |
| Env-var syntax | `${VAR}` / `${VAR:-default}` (Claude Code native) |

## Verification (after all subtasks land)

```bash
poetry run pytest -q
poetry run mypy src/
poetry run ruff check src/ tests/
poetry run black --check src/ tests/
poetry run pre-commit run --all-files

# Manual smoke (create a catalog domain with mcp.fragment.json first)
cd /tmp && rm -rf mcp-smoke && mkdir mcp-smoke && cd mcp-smoke
git init -q
ai-dotfiles init
ai-dotfiles add @mcp-smoke
cat .mcp.json                                         # contains server
jq '.permissions.allow' .claude/settings.json         # includes mcp__<name>__*
jq '.enabledMcpjsonServers' .claude/settings.json     # ["<name>"]
cat .claude/.ai-dotfiles-mcp-ownership.json           # server -> [@mcp-smoke]
ai-dotfiles remove @mcp-smoke
test ! -f .mcp.json                                    # removed
test ! -f .claude/.ai-dotfiles-mcp-ownership.json      # removed
```

## Files touched (cumulative across subtasks)

- `src/ai_dotfiles/core/mcp_merge.py`           (new, subtask 01)
- `src/ai_dotfiles/core/mcp_ownership.py`       (new, subtask 02)
- `src/ai_dotfiles/core/elements.py`            (skip-list, subtask 03)
- `src/ai_dotfiles/core/symlinks.py`            (skip-list, subtask 03)
- `src/ai_dotfiles/commands/add.py`             (subtask 03)
- `src/ai_dotfiles/commands/remove.py`          (subtask 03)
- `src/ai_dotfiles/commands/install.py`         (subtask 03)
- `src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md`  (subtask 05)
- `README.md`                                   (subtask 05)
- `tests/unit/test_mcp_merge.py`                (new, subtask 01)
- `tests/unit/test_mcp_ownership.py`            (new, subtask 02)
- `tests/integration/test_mcp_add_remove.py`    (new, subtask 04)
- `tests/e2e/test_mcp_cli.py`                   (new, subtask 04)
