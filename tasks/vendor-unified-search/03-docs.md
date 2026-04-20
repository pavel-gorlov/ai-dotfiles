# Subtask 03: docs + scaffolded skill sync

Depends on subtasks 01 and 02 being landed on disk (docs describe the
final CLI surface).

## Goal

Document the two new features in the user-facing materials and keep the
scaffolded `ai-dotfiles` skill in sync (CLAUDE.md mandates syncing
`src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md` on
every user-visible CLI change).

## File scope (exclusive)

- `README.md`
- `ai-dotfiles-blueprint.md`
- `src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md`

## Do NOT touch

- Any code or test file
- Any other doc

## `README.md`

In the Vendoring section:

1. Find the command table (search for the row
   `vendor list`). Add two new rows right after the existing meta rows:

   ```
   | `vendor search <query> [-v NAME ...] [--limit N]` | Aggregated search across every vendor whose deps are installed; results grouped by vendor. |
   ```

2. In the same section, update the `vendor list` row to mention install
   URLs:

   ```
   | `vendor list`                              | Registered vendors + dependency status (with install URL for any missing dep). |
   ```

3. Add an "Example: aggregated search" block after the other vendor
   examples:

   ```markdown
   #### Example: aggregated search

   ```bash
   ai-dotfiles vendor list              # see which vendors are ready
   ai-dotfiles vendor search git        # query every active vendor
   ai-dotfiles vendor search git --limit 5
   ai-dotfiles vendor search git -v buildwithclaude -v tonsofskills
   ```

   Vendors with missing deps are shown as `skipped (deps missing: ...)`
   with the install URL. Vendors without a `search` capability (e.g.
   `github`) are omitted silently.
   ```

## `ai-dotfiles-blueprint.md`

In the `### Команды` block (the Russian command listing near the top):

1. Update the `vendor list` line to note URL surfacing:

   ```
   ai-dotfiles vendor list                           Список vendor-плагинов + статус зависимостей (с URL для отсутствующих)
   ```

2. Add a new line immediately after `vendor installed` (or wherever the
   meta commands sit):

   ```
   ai-dotfiles vendor search <query>                 Агрегированный поиск по всем vendor-плагинам с группировкой
   ```

No changes elsewhere in the blueprint.

## `src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md`

Locate the vendor cheat-sheet section. Add the two bullets:

- `ai-dotfiles vendor list` — shows install URL for any missing dep
  (useful before running `deps install`).
- `ai-dotfiles vendor search <query> [-v NAME ...] [--limit N]` — one
  shot across every vendor whose deps are installed; results grouped by
  vendor.

Keep the surrounding table / formatting style consistent with the rest
of the file.

## Hard rules

- No code changes.
- Keep README / blueprint examples runnable (command syntax must match
  actual CLI landed by subtask 02).
- Do NOT fabricate vendors or flags that don't exist.

## Definition of Done

1. `poetry run pytest -q` — full suite still green (no test regressions
   from rewritten scaffold template; template is loaded by `init -g`
   tests)
2. `poetry run pre-commit run --all-files` — clean
3. Manual eyeball: render `README.md` and `ai-dotfiles-blueprint.md`,
   verify tables align and new examples are readable
4. Manual: `poetry run ai-dotfiles init -g` against a throwaway
   `AI_DOTFILES_HOME` and verify the shipped skill contains the new
   commands

Do NOT commit. Orchestrator runs final gates and commits the entire
feature with one message.
