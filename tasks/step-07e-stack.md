# Step 7e: commands/stack.py

## Goal

Implement `ai-dotfiles stack` subcommand group: create, delete, list, add, remove, apply.

## Stack format

File: `stacks/<name>.conf`

```bash
# Stack: <name>
# Apply with: ai-dotfiles stack apply <name>
# One element per line. Lines starting with # are comments.
@python
skill:code-review
agent:researcher
rule:security
```

- One element per line
- Lines starting with `#` are comments
- Empty lines ignored
- No duplicate entries

## File: `src/ai_dotfiles/commands/stack.py`

### Helper functions

```python
def _stack_path(name: str) -> Path:
    """Return stacks/<name>.conf path."""

def _read_stack(path: Path) -> list[str]:
    """Parse .conf file, return list of element specifiers (skip comments/blanks)."""

def _write_stack(path: Path, items: list[str], name: str) -> None:
    """Write .conf file with header comment and items."""
```

### Subcommands

#### `ai-dotfiles stack create <name>`

1. Check `stacks/<name>.conf` doesn't exist
2. Create with header comments only (empty stack)
3. Print: `Created stack <name> at stacks/<name>.conf`

#### `ai-dotfiles stack delete <name>`

1. Check exists
2. Delete file
3. Print: `Deleted stack <name>`

#### `ai-dotfiles stack list <name>`

1. Check exists
2. Parse and print elements, one per line
3. If empty: `Stack <name> is empty`

#### `ai-dotfiles stack add <name> <items...>`

```python
@stack.command("add")
@click.argument("name")
@click.argument("items", nargs=-1, required=True)
def add_to_stack(name: str, items: tuple[str, ...]) -> None:
```

1. Check stack exists
2. Read current items
3. Validate new items format (parse_elements to check syntax)
4. Append new items (skip duplicates)
5. Write back
6. Print added items

#### `ai-dotfiles stack remove <name> <items...>`

1. Read current items
2. Remove specified items
3. Write back
4. Print removed items

#### `ai-dotfiles stack apply <name>`

```python
@stack.command("apply")
@click.argument("name")
def apply_stack(name: str) -> None:
```

1. Read stack items
2. Call the add command logic for each item (to project manifest + create symlinks)
3. Set `"stack": "<name>"` in ai-dotfiles.json via `manifest.set_metadata()`
4. Print: `Applied stack <name>: N packages added`

### Register in cli.py

```python
from ai_dotfiles.commands.stack import stack
cli.add_command(stack)
```

## File: `tests/test_stack.py`

1. `test_stack_create` — creates .conf with header
2. `test_stack_create_already_exists` — error
3. `test_stack_delete` — removes file
4. `test_stack_delete_not_found` — error
5. `test_stack_list_populated` — shows items
6. `test_stack_list_empty` — "Stack is empty"
7. `test_stack_add_items` — appends to file
8. `test_stack_add_duplicate` — skips existing
9. `test_stack_add_invalid_format` — error for bad specifier
10. `test_stack_remove_items` — removes from file
11. `test_stack_remove_not_present` — warning, not error
12. `test_stack_apply` — creates symlinks + sets metadata in manifest
13. `test_stack_apply_sets_stack_key` — manifest has "stack" field
14. `test_read_stack_skips_comments` — # lines not included
15. `test_read_stack_skips_blank_lines` — empty lines not included

## Definition of Done

- [ ] `src/ai_dotfiles/commands/stack.py` exists with all 6 subcommands
- [ ] `tests/e2e/test_stack.py` exists with all 15 test cases
- [ ] `poetry run pytest tests/e2e/test_stack.py -v` — all tests pass
- [ ] `poetry run mypy src/ai_dotfiles/commands/stack.py` — passes strict mode
- [ ] All public functions have type annotations
- [ ] .conf parsing skips comments and blank lines
- [ ] stack add prevents duplicates
- [ ] stack apply creates symlinks + sets "stack" key in manifest

## Commit

Part of batch commit after all Step 7 sub-tasks complete.
