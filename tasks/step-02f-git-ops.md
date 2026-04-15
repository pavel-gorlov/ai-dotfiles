# Step 2f: core/git_ops.py

## Goal

Git operations for `init -g --from` (clone storage) and `vendor` (download external content).

## File: `src/ai_dotfiles/core/git_ops.py`

### Functions

```python
import subprocess
from pathlib import Path

def git_clone(url: str, dest: Path) -> None:
    """Clone a git repository to dest.
    
    Runs: git clone <url> <dest>
    Raises click.ClickException on failure with stderr output.
    """

def git_sparse_checkout(url: str, subpath: str, dest: Path) -> None:
    """Clone only a specific subdirectory from a repo.
    
    Strategy:
    1. git clone --filter=blob:none --no-checkout <url> <temp>
    2. cd <temp> && git sparse-checkout set <subpath>
    3. git checkout
    4. Copy <temp>/<subpath> to <dest>
    5. Clean up temp dir
    
    Fallback: if sparse checkout fails (old git), do full clone + copy.
    """

def parse_github_url(url: str) -> tuple[str, str, str, str] | None:
    """Parse GitHub tree URL into (repo_url, branch, subpath, name).
    
    Input:  https://github.com/user/repo/tree/main/skills/frontend-design
    Output: ("https://github.com/user/repo.git", "main", "skills/frontend-design", "frontend-design")
    
    Input:  https://github.com/user/repo/tree/main/path/to/skill
    Output: ("https://github.com/user/repo.git", "main", "path/to/skill", "skill")
    
    Returns None if URL doesn't match GitHub tree pattern.
    Also handles: github.com/user/repo (no tree — full clone).
    """

def detect_element_type(path: Path) -> str | None:
    """Detect what type of element is at path.
    
    - Has SKILL.md -> "skill"
    - Single .md file with agent frontmatter -> "agent"  
    - Single .md file with rule frontmatter -> "rule"
    - Otherwise -> None (unknown, put in skills/ by default)
    """
```

### Notes

- All git commands use `subprocess.run` with `check=True`, `capture_output=True`, `text=True`
- Error handling: catch `subprocess.CalledProcessError`, wrap in `click.ClickException` with stderr
- Temp directories use `tempfile.TemporaryDirectory`
- No external dependencies beyond git itself

## File: `tests/test_git_ops.py`

### Test cases

Use `unittest.mock.patch` for subprocess — don't actually clone repos.

1. `test_git_clone_success` — calls `git clone` with correct args
2. `test_git_clone_failure` — raises ClickException with stderr
3. `test_parse_github_url_tree` — full tree URL parsed correctly
4. `test_parse_github_url_root` — repo root URL (no tree) parsed
5. `test_parse_github_url_invalid` — non-GitHub URL returns None
6. `test_parse_github_url_ssh` — `git@github.com:user/repo` handled
7. `test_sparse_checkout_calls` — correct sequence of git commands

## Dependencies

- `subprocess`, `tempfile`, `shutil`, `re` (stdlib)
- `click` (for error types)

## Definition of Done

- [ ] `src/ai_dotfiles/core/git_ops.py` exists with all functions
- [ ] `tests/unit/test_git_ops.py` exists with all 7 test cases
- [ ] `poetry run pytest tests/unit/test_git_ops.py -v` — all tests pass
- [ ] `poetry run mypy src/ai_dotfiles/core/git_ops.py` — passes strict mode
- [ ] All public functions have type annotations (params + return)
- [ ] Git subprocess calls are mocked (no real network in tests)
- [ ] Errors raise `ExternalError` (from `core.errors`)

## Commit

Part of batch commit after all Step 2 sub-tasks complete.
