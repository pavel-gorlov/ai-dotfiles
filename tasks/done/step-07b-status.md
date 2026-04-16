# Step 7b: commands/status.py

## Goal

Implement `ai-dotfiles status` — validate that installed symlinks are healthy and show merged hooks summary.

## File: `src/ai_dotfiles/commands/status.py`

### Command definition

```python
@click.command()
def status() -> None:
```

### Behavior

1. Find project root, read ai-dotfiles.json
2. For each package in manifest:
   a. Check source exists in catalog
   b. Resolve target paths
   c. Check each symlink: exists? points to correct source? broken?
3. Check settings.json: exists? up to date with current fragments?
4. Print status report

### Output example

```
ai-dotfiles status (my-project)

  @python
    + skills/py-lint         -> ~/.ai-dotfiles/catalog/python/skills/py-lint  OK
    + agents/py-debug.md     -> ~/.ai-dotfiles/catalog/python/agents/py-debug.md  OK
    ! hooks/ruff-on-save.sh  -> BROKEN (target missing)

  skill:code-review
    + skills/code-review     -> ~/.ai-dotfiles/catalog/skills/code-review  OK

  agent:researcher
    x agents/researcher.md   NOT LINKED

  Settings: .claude/settings.json
    Merged from: @python
    Hooks: PostToolUse (2 handlers)

Issues: 2 (run 'ai-dotfiles install' to fix)
```

### Status indicators

- `+` OK — symlink exists and points correctly
- `!` BROKEN — symlink exists but target is missing or wrong
- `x` NOT LINKED — expected symlink doesn't exist

### Settings summary

Show which domains contribute to settings.json and what hooks are defined (event name + handler count).

### Exit code

- 0 if all OK
- 1 if any issues found

## File: `tests/test_status.py`

1. `test_status_all_ok` — all symlinks valid, exit 0
2. `test_status_broken_symlink` — reports broken link, exit 1
3. `test_status_missing_symlink` — reports not linked, exit 1
4. `test_status_settings_summary` — shows merged hooks
5. `test_status_empty_manifest` — "No packages installed"
6. `test_status_no_manifest` — "ai-dotfiles.json not found"

## Definition of Done

- [ ] `src/ai_dotfiles/commands/status.py` exists
- [ ] `tests/e2e/test_list_status.py` includes all 6 status test cases
- [ ] `poetry run pytest tests/e2e/test_list_status.py -v` — all tests pass
- [ ] `poetry run mypy src/ai_dotfiles/commands/status.py` — passes strict mode
- [ ] All public functions have type annotations
- [ ] OK symlinks show `+`, broken show `!`, missing show `x`
- [ ] Exit code 0 when all OK, 1 when issues found
- [ ] Settings summary shows hook event names and handler counts

## Commit

Part of batch commit after all Step 7 sub-tasks complete.
