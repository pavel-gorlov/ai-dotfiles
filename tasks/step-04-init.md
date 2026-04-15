# Step 4: commands/init.py

## Goal

Implement `ai-dotfiles init`, `ai-dotfiles init -g`, and `ai-dotfiles init -g --from <url>`.

## File: `src/ai_dotfiles/commands/init.py`

### Command definition

```python
import click
from ai_dotfiles.core import paths, git_ops, symlinks
from ai_dotfiles.scaffold.generator import generate_storage_scaffold, generate_project_manifest
from ai_dotfiles import ui

@click.command()
@click.option("-g", "--global", "is_global", is_flag=True, help="Initialize global storage")
@click.option("--from", "from_url", default=None, help="Clone existing storage from git URL")
def init(is_global: bool, from_url: str | None) -> None:
```

### Behavior

#### `ai-dotfiles init` (project)

1. Call `paths.find_project_root()` — if not found, use cwd
2. Check if `ai-dotfiles.json` already exists — if yes, warn and abort
3. Call `generate_project_manifest(root)`
4. Print: `Created ai-dotfiles.json in <root>`

#### `ai-dotfiles init -g` (global, fresh)

1. Check if `storage_root()` already exists — if yes, warn and abort
2. Call `generate_storage_scaffold(storage_root())`
3. Call `symlinks.link_global_files(paths.global_dir(), paths.claude_global_dir(), paths.backup_dir())`
4. Print: `Created storage at <path>` + `Linked global/ -> ~/.claude/`

#### `ai-dotfiles init -g --from <url>` (global, clone)

1. Check if `storage_root()` already exists — if yes, warn and abort
2. Call `git_ops.git_clone(url, storage_root())`
3. Call `symlinks.link_global_files(paths.global_dir(), paths.claude_global_dir(), paths.backup_dir())`
4. Print: `Cloned <url> to <path>` + `Linked global/ -> ~/.claude/`

### Edge cases

- If `--from` is used without `-g`, error: `--from requires -g`
- If storage exists but is empty/broken, suggest `rm -rf` and retry
- If backup was created during linking, print backup location

## Register in cli.py

```python
from ai_dotfiles.commands.init import init
cli.add_command(init)
```

## File: `tests/test_init.py`

### Test cases

Use `click.testing.CliRunner` for all tests.

1. `test_init_project` — creates ai-dotfiles.json in cwd
2. `test_init_project_already_exists` — warns, doesn't overwrite
3. `test_init_global` — creates scaffold, links global files
4. `test_init_global_already_exists` — warns, aborts
5. `test_init_global_from_url` — calls git_clone (mocked), links
6. `test_init_from_without_global` — error message
7. `test_init_global_creates_backup` — existing files in ~/.claude/ get backed up

## Dependencies

- `core.paths`, `core.git_ops`, `core.symlinks`
- `scaffold.generator`
- `ui`

## Design note

Command is a thin wrapper. Business logic errors (`ConfigError`, etc.) are caught and converted to user-friendly output with exit code. No business logic in the command itself.

## Definition of Done

- [ ] `src/ai_dotfiles/commands/init.py` exists with init command
- [ ] Command registered in `cli.py`
- [ ] `tests/integration/test_init.py` exists with all 7 test cases
- [ ] `poetry run pytest tests/integration/test_init.py -v` — all tests pass
- [ ] `poetry run mypy src/ai_dotfiles/commands/init.py` — passes strict mode
- [ ] All public functions have type annotations
- [ ] `ai-dotfiles init` creates ai-dotfiles.json in cwd
- [ ] `ai-dotfiles init -g` creates full scaffold and links global/
- [ ] `--from` without `-g` produces error
- [ ] Errors produce user-friendly messages, not tracebacks

## Commit message

`feat: init command — project manifest and global storage setup`
