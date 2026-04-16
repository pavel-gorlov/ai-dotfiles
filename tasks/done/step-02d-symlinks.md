# Step 2d: core/symlinks.py

## Goal

Safe symlink management with backup, idempotency, README skipping, and chmod +x for shell scripts. This is the most critical module — every install/add/remove operation depends on it.

## File: `src/ai_dotfiles/core/symlinks.py`

### Functions

```python
from pathlib import Path

def safe_symlink(source: Path, target: Path, backup: Path) -> str:
    """Create symlink: target -> source.
    
    Cases:
    1. target doesn't exist -> create symlink, return "linked"
    2. target is symlink pointing to source -> no-op, return "already-linked"
    3. target is symlink pointing elsewhere -> remove, create new, return "relinked"
    4. target is regular file/dir -> move to backup dir preserving 
       relative path structure, create symlink, return "backed-up"
    
    Creates parent directories of target if needed.
    Sets chmod +x on source if it ends with .sh.
    
    backup: root of backup directory (~/.dotfiles-backup/).
    Backup preserves relative structure: if target is ~/.claude/hooks/lint.sh,
    backup goes to ~/.dotfiles-backup/.claude/hooks/lint.sh
    """

def remove_symlink(target: Path) -> bool:
    """Remove target if it's a symlink. Return True if removed."""

def is_managed_symlink(target: Path, storage: Path) -> bool:
    """Check if target is a symlink pointing into our storage directory."""

def link_domain(domain_path: Path, claude_dir: Path, backup: Path) -> list[str]:
    """Link all elements from a domain directory to claude_dir.
    
    Iterates subdirs: skills/, agents/, rules/, hooks/.
    For each item inside (file or directory):
      - Skip README.md files
      - Skip settings.fragment.json
      - Call safe_symlink(item, claude_dir/<subdir>/<item.name>, backup)
      - chmod +x on .sh files
    
    Returns list of status messages like:
      ["linked skills/py-lint", "backed-up hooks/old-hook.sh", ...]
    """

def link_standalone(source: Path, target: Path, backup: Path) -> str:
    """Link a single standalone element. Wrapper around safe_symlink.
    Creates target parent dir (e.g. claude_dir/skills/) if needed."""

def unlink_domain(domain_path: Path, claude_dir: Path) -> list[str]:
    """Remove all symlinks in claude_dir that point into domain_path.
    Returns list of removed items."""

def unlink_standalone(target: Path) -> bool:
    """Remove a single standalone symlink."""

def link_global_files(global_dir: Path, claude_dir: Path, backup: Path) -> list[str]:
    """Link global/ contents to ~/.claude/ file-by-file.
    
    Links:
      global/CLAUDE.md       -> claude_dir/CLAUDE.md
      global/settings.json   -> claude_dir/settings.json
      global/hooks/*         -> claude_dir/hooks/*  (each file, not dir symlink)
      global/output-styles/* -> claude_dir/output-styles/*  (each file)
    
    Skips README.md in hooks/ and output-styles/.
    Does NOT link global/README.md itself.
    Returns status messages.
    """
```

### Key behaviors

- **Idempotency**: running twice produces the same result, no errors
- **Backup**: real files/dirs are moved, not deleted. Backup path mirrors the original location relative to home
- **No directory symlinks**: we symlink individual files/entries, not whole directories. This prevents clobbering ~/.claude/ which has its own content (sessions, projects, etc.)
- **chmod +x**: any `.sh` file in source gets `chmod +x` before linking
- **Skip README.md**: never link README.md files from catalog — they're documentation, not config

## File: `tests/test_symlinks.py`

### Test cases

1. `test_safe_symlink_new` — creates symlink, returns "linked"
2. `test_safe_symlink_idempotent` — same source+target twice, second returns "already-linked"
3. `test_safe_symlink_relink` — different source at same target, relinks
4. `test_safe_symlink_backup_file` — existing regular file gets moved to backup
5. `test_safe_symlink_backup_preserves_structure` — backup path mirrors original
6. `test_safe_symlink_creates_parent_dirs` — target parent dirs created
7. `test_safe_symlink_chmod_sh` — .sh files get +x
8. `test_remove_symlink_exists` — removes, returns True
9. `test_remove_symlink_not_symlink` — regular file, returns False (doesn't delete)
10. `test_remove_symlink_missing` — doesn't exist, returns False
11. `test_is_managed_symlink_yes` — points into storage
12. `test_is_managed_symlink_no` — points elsewhere
13. `test_link_domain_full` — domain with skills/, agents/, rules/, hooks/ — all linked
14. `test_link_domain_skips_readme` — README.md in subdirs not linked
15. `test_link_domain_skips_settings_fragment` — settings.fragment.json not linked
16. `test_link_standalone_skill` — links skill dir
17. `test_link_standalone_agent` — links agent .md file
18. `test_unlink_domain` — removes all domain symlinks
19. `test_unlink_standalone` — removes single symlink
20. `test_link_global_files` — CLAUDE.md, settings.json, hooks/*, output-styles/* linked
21. `test_link_global_skips_readme` — README.md in global/ not linked

## Dependencies

- `pathlib`, `shutil`, `os`, `stat` (stdlib)

## Definition of Done

- [ ] `src/ai_dotfiles/core/symlinks.py` exists with all functions
- [ ] `tests/integration/test_symlinks.py` exists with all 21 test cases
- [ ] `poetry run pytest tests/integration/test_symlinks.py -v` — all tests pass
- [ ] `poetry run mypy src/ai_dotfiles/core/symlinks.py` — passes strict mode
- [ ] All public functions have type annotations (params + return)
- [ ] Errors raise `LinkError` (from `core.errors`)
- [ ] safe_symlink is idempotent (run twice = same result)
- [ ] Backup files land in correct relative path structure
- [ ] .sh files get chmod +x
- [ ] README.md files are never linked

## Commit

Part of batch commit after all Step 2 sub-tasks complete.
