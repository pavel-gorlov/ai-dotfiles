# Step 2a: core/paths.py

## Goal

Centralize all path resolution logic. Every other module imports paths from here.

## File: `src/ai_dotfiles/core/paths.py`

### Functions

```python
from pathlib import Path
import os

def storage_root() -> Path:
    """~/.ai-dotfiles/ or AI_DOTFILES_HOME env var."""
    return Path(os.environ.get("AI_DOTFILES_HOME", Path.home() / ".ai-dotfiles"))

def global_dir() -> Path:
    """storage_root() / "global" — physical files that get linked to ~/.claude/"""
    return storage_root() / "global"

def catalog_dir() -> Path:
    """storage_root() / "catalog" — all installable content."""
    return storage_root() / "catalog"

def stacks_dir() -> Path:
    """storage_root() / "stacks" — preset .conf files."""
    return storage_root() / "stacks"

def global_manifest_path() -> Path:
    """storage_root() / "global.json" — manifest of globally installed packages."""
    return storage_root() / "global.json"

def claude_global_dir() -> Path:
    """~/.claude/ — Claude Code's global config directory."""
    return Path.home() / ".claude"

def backup_dir() -> Path:
    """~/.dotfiles-backup/ — where conflicting files are moved."""
    return Path.home() / ".dotfiles-backup"

def find_project_root(start: Path | None = None) -> Path | None:
    """Walk upward from start (default: cwd) looking for ai-dotfiles.json.
    Fallback: look for .git directory.
    Return None if neither found (reached filesystem root)."""

def project_manifest_path(root: Path) -> Path:
    """root / "ai-dotfiles.json" """
    return root / "ai-dotfiles.json"

def project_claude_dir(root: Path) -> Path:
    """root / ".claude" — project-level Claude config."""
    return root / ".claude"
```

### Key behaviors

- `find_project_root()`: walk up from `start or Path.cwd()`. Check for `ai-dotfiles.json` first (exact match), then `.git`. Stop at filesystem root (`path.parent == path`). Return `None` if nothing found.
- All functions return `Path` objects, never strings.
- No directory creation — these just compute paths.

## File: `tests/test_paths.py`

### Test cases

1. `test_storage_root_default` — without env var, returns `~/.ai-dotfiles`
2. `test_storage_root_env_override` — with `AI_DOTFILES_HOME=/custom`, returns `/custom`
3. `test_global_dir` — is `storage_root() / "global"`
4. `test_catalog_dir` — is `storage_root() / "catalog"`
5. `test_stacks_dir` — is `storage_root() / "stacks"`
6. `test_global_manifest_path` — is `storage_root() / "global.json"`
7. `test_find_project_root_with_manifest` — create `ai-dotfiles.json` in parent, start from child dir, should find parent
8. `test_find_project_root_with_git` — no manifest but `.git/` exists, should find that dir
9. `test_find_project_root_manifest_priority` — both exist, manifest wins (closer)
10. `test_find_project_root_none` — isolated tmp dir with neither, returns `None`
11. `test_project_manifest_path` — returns `root / "ai-dotfiles.json"`
12. `test_project_claude_dir` — returns `root / ".claude"`

## Dependencies

None (uses only stdlib + pathlib).

## Definition of Done

- [ ] `src/ai_dotfiles/core/paths.py` exists with all functions listed above
- [ ] `tests/unit/test_paths.py` exists with all 12 test cases
- [ ] `poetry run pytest tests/unit/test_paths.py -v` — all tests pass
- [ ] `poetry run mypy src/ai_dotfiles/core/paths.py` — passes strict mode
- [ ] `poetry run ruff check src/ai_dotfiles/core/paths.py` — no errors
- [ ] All public functions have type annotations (params + return)
- [ ] No test uses real `~/.ai-dotfiles/` or `~/.claude/` — all paths via fixtures

## Commit

Part of batch commit after all Step 2 sub-tasks complete.
