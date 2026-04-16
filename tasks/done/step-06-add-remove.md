# Step 6: commands/add.py + commands/remove.py

## Goal

Implement `ai-dotfiles add` and `ai-dotfiles remove` for both project and global scope. These modify the manifest AND create/remove symlinks in one step.

## File: `src/ai_dotfiles/commands/add.py`

### Command definition

```python
@click.command()
@click.argument("items", nargs=-1, required=True)
@click.option("-g", "--global", "is_global", is_flag=True)
def add(items: tuple[str, ...], is_global: bool) -> None:
```

### Behavior: `ai-dotfiles add @python skill:code-review`

1. Parse items via `elements.parse_elements(list(items))`
2. Validate all exist in catalog
3. Determine manifest path (project or global)
4. Add to manifest: `manifest.add_packages(path, list(items))`
5. If `added` is empty (all duplicates), print "All packages already installed" and return
6. Determine claude_dir (project `.claude/` or global `~/.claude/`)
7. For each newly added element, create symlinks (same as install logic)
8. Reassemble settings.json from ALL packages in manifest (not just new ones)
9. Print what was added

### Behavior: `ai-dotfiles add -g skill:web-research`

Same logic but:
- Manifest: `global.json`
- Claude dir: `~/.claude/`

### Output example

```
Added to ai-dotfiles.json:
  + @python
  + skill:code-review
  ~ agent:researcher (already installed)
Settings: rebuilt .claude/settings.json
```

## File: `src/ai_dotfiles/commands/remove.py`

### Command definition

```python
@click.command()
@click.argument("items", nargs=-1, required=True)
@click.option("-g", "--global", "is_global", is_flag=True)
def remove(items: tuple[str, ...], is_global: bool) -> None:
```

### Behavior: `ai-dotfiles remove @python`

1. Parse items
2. Determine manifest path
3. Remove from manifest: `manifest.remove_packages(path, list(items))`
4. If `removed` is empty, print "None of these packages were installed" and return
5. For each removed element, unlink symlinks:
   - DOMAIN: `symlinks.unlink_domain(source, claude_dir)`
   - Standalone: `symlinks.unlink_standalone(target)`
6. Reassemble settings.json from remaining packages
7. If no domains remain, remove settings.json (if it was only from fragments)
8. Print what was removed

### Output example

```
Removed from ai-dotfiles.json:
  - @python
  Settings: rebuilt .claude/settings.json
```

## Register in cli.py

```python
from ai_dotfiles.commands.add import add
from ai_dotfiles.commands.remove import remove
cli.add_command(add)
cli.add_command(remove)
```

## File: `tests/test_add_remove.py`

### Setup

Create tmp storage with catalog containing:
- Domain `testdomain` with skills/test-skill/, agents/test-agent.md, settings.fragment.json
- Standalone skill:test-standalone (catalog/skills/test-standalone/SKILL.md)

### Test cases — add

1. `test_add_project_domain` — updates manifest + creates symlinks
2. `test_add_project_standalone` — updates manifest + creates symlink
3. `test_add_project_multiple` — adds several items at once
4. `test_add_project_duplicate` — already installed item skipped
5. `test_add_project_rebuilds_settings` — settings.json updated after add
6. `test_add_project_missing_package` — error for non-existent
7. `test_add_global` — updates global.json + links to ~/.claude/

### Test cases — remove

8. `test_remove_project` — updates manifest + removes symlinks
9. `test_remove_project_multiple` — removes several
10. `test_remove_project_not_installed` — prints warning, no error
11. `test_remove_project_rebuilds_settings` — settings.json updated after remove
12. `test_remove_global` — updates global.json + unlinks from ~/.claude/

### Integration

13. `test_add_then_remove_roundtrip` — add, verify linked, remove, verify clean

## Dependencies

- `core.paths`, `core.elements`, `core.manifest`, `core.symlinks`, `core.settings_merge`
- `ui`

## Definition of Done

- [ ] `src/ai_dotfiles/commands/add.py` and `remove.py` exist
- [ ] Commands registered in `cli.py`
- [ ] `tests/integration/test_add_remove.py` exists with all 13 test cases
- [ ] `poetry run pytest tests/integration/test_add_remove.py -v` — all tests pass
- [ ] `poetry run mypy src/ai_dotfiles/commands/add.py src/ai_dotfiles/commands/remove.py` — passes strict mode
- [ ] All public functions have type annotations
- [ ] add updates manifest AND creates symlinks in one step
- [ ] remove updates manifest AND removes symlinks in one step
- [ ] settings.json rebuilt after each add/remove
- [ ] add+remove roundtrip leaves clean state (test 13)
- [ ] Errors produce user-friendly messages, not tracebacks

## Commit message

`feat: add and remove commands with manifest + symlink management`
