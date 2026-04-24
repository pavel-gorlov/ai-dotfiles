# Subtask 01: `core/gitignore.py` + unit tests

Pure, I/O-light module that parses and rewrites the managed block in a
project's `.gitignore`. No click, no ui — commands wire it up in 02.

## Goal

Export a small API:

```python
MANAGED_START = "# >>> ai-dotfiles managed — do not edit manually <<<"
MANAGED_END = "# >>> end ai-dotfiles managed <<<"

def collect_managed_paths(claude_dir: Path, storage: Path) -> list[str]: ...
def sync_gitignore(project_root: Path, managed_paths: list[str]) -> bool: ...
def parse_blocks(text: str) -> tuple[list[str], list[str], list[str]]: ...
def render(before: list[str], managed: list[str], after: list[str]) -> str: ...
```

`sync_gitignore` is the single entry point; the rest are internal helpers
exported for testing.

## File scope (exclusive)

- `src/ai_dotfiles/core/gitignore.py`          (new)
- `tests/unit/test_gitignore.py`               (new)

## Do NOT touch

- Any command module (`commands/*.py`) — subtask 02.
- `core/symlinks.py` — reuse `is_managed_symlink` as-is; add no new
  exports.

## Hard rules

- mypy `--strict`; absolute imports from `ai_dotfiles.core.*`.
- No `print`, no `ui` import — pure module.
- Skip silently if `project_root/.git` is missing AND
  `project_root/.gitignore` is also missing. Otherwise always manage.
- Path format inside the block: `/.claude/skills/foo` (root-anchored
  POSIX paths — gitignore uses `/` even on Windows). No backslashes.
- Deterministic output: sort the managed paths asciibetically so that
  re-runs produce byte-identical files.
- When a user-authored line (outside the block) already ignores a path
  verbatim, drop that path from the managed block (do NOT duplicate).
  Only simple literal match — do not interpret wildcards.
- On empty managed-paths list AND no existing block: no-op, don't
  create an empty `.gitignore`.
- On empty managed-paths list AND existing block: strip the block;
  preserve the rest of the file verbatim including surrounding blank
  lines.

## Implementation sketch

```python
# src/ai_dotfiles/core/gitignore.py
from __future__ import annotations

from pathlib import Path

from ai_dotfiles.core.symlinks import is_managed_symlink

MANAGED_START = "# >>> ai-dotfiles managed — do not edit manually <<<"
MANAGED_END = "# >>> end ai-dotfiles managed <<<"

# Directories under .claude/ whose children are individually linked.
_SCAN_SUBDIRS: tuple[str, ...] = (
    "skills", "agents", "rules", "hooks", "output-styles",
)

# Top-level files that may be symlinked from global scope.
_SCAN_TOP_FILES: tuple[str, ...] = ("CLAUDE.md", "settings.json")


def collect_managed_paths(claude_dir: Path, storage: Path) -> list[str]:
    """Return sorted `/.claude/...` paths for every managed symlink."""
    results: list[str] = []
    if not claude_dir.is_dir():
        return results
    rel_base = claude_dir.name  # ".claude"
    for sub in _SCAN_SUBDIRS:
        sub_dir = claude_dir / sub
        if not sub_dir.is_dir():
            continue
        for child in sub_dir.iterdir():
            if is_managed_symlink(child, storage):
                results.append(f"/{rel_base}/{sub}/{child.name}")
    for top in _SCAN_TOP_FILES:
        entry = claude_dir / top
        if is_managed_symlink(entry, storage):
            results.append(f"/{rel_base}/{top}")
    results.sort()
    return results


def parse_blocks(text: str) -> tuple[list[str], list[str], list[str]]:
    """Split text into (before, managed, after). managed excludes markers.
    If no block exists, managed=[] and after=[]."""
    lines = text.splitlines()
    try:
        start = lines.index(MANAGED_START)
        end = lines.index(MANAGED_END, start + 1)
    except ValueError:
        return lines, [], []
    return lines[:start], lines[start + 1 : end], lines[end + 1 :]


def render(before: list[str], managed: list[str], after: list[str]) -> str:
    """Join lines back, wrapping the managed block in its markers. If
    managed is empty, omit the markers entirely."""
    pieces: list[str] = list(before)
    if managed:
        pieces.append(MANAGED_START)
        pieces.extend(managed)
        pieces.append(MANAGED_END)
    pieces.extend(after)
    # Trailing newline, collapse 3+ blanks to 2 (cosmetic).
    out = "\n".join(pieces).rstrip() + "\n" if pieces else ""
    return out


def sync_gitignore(project_root: Path, managed_paths: list[str]) -> bool:
    """Rewrite the managed block. Return True if the file was written.

    Silent no-op when the project is clearly not under git AND no
    .gitignore exists yet.
    """
    gitignore = project_root / ".gitignore"
    git_dir = project_root / ".git"
    if not git_dir.exists() and not gitignore.exists():
        return False

    text = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    before, _current_managed, after = parse_blocks(text)

    # Filter out paths that are already literal entries in user-authored lines.
    user_authored_literals = {
        line.strip() for line in before + after if line.strip().startswith("/")
    }
    managed = [p for p in managed_paths if p not in user_authored_literals]

    rendered = render(before, managed, after)

    # Nothing to do — don't create an empty file.
    if not rendered and not gitignore.exists():
        return False

    # Skip write if nothing changed (keeps mtime stable, avoids noisy diffs).
    if gitignore.exists() and gitignore.read_text(encoding="utf-8") == rendered:
        return False

    if rendered:
        gitignore.write_text(rendered, encoding="utf-8")
    elif gitignore.exists():
        # Block collapsed AND no surrounding content. Leave the empty
        # .gitignore in place rather than deleting it — user may have
        # tooling that expects the file.
        gitignore.write_text("", encoding="utf-8")
    return True
```

## Acceptance tests (`tests/unit/test_gitignore.py`)

- `test_collect_managed_paths_empty_claude_dir`
- `test_collect_managed_paths_ignores_real_files`
- `test_collect_managed_paths_ignores_symlinks_outside_storage`
- `test_collect_managed_paths_returns_sorted_absolute_paths`
- `test_collect_managed_paths_picks_up_top_level_CLAUDE_md_symlink`
- `test_parse_blocks_no_markers` — returns (all_lines, [], [])
- `test_parse_blocks_round_trip` — parse then render equals input (mod
  trailing newline)
- `test_render_omits_markers_when_managed_empty`
- `test_sync_creates_gitignore_when_git_dir_present`
- `test_sync_skips_when_no_git_and_no_gitignore`
- `test_sync_preserves_user_authored_lines_outside_block`
- `test_sync_replaces_existing_block` — seed .gitignore with an old
  block, call sync with a new path list, verify only the block changed
- `test_sync_removes_block_when_managed_empty_but_keeps_user_lines`
- `test_sync_skips_paths_already_in_user_authored_lines`
- `test_sync_idempotent` — call twice in a row, second call returns
  False (no write) and file bytes are identical
- `test_sync_writes_posix_slashes_even_on_windows_paths` (simulate with
  a constructed input; no actual Windows required)

Use `tmp_path` and `monkeypatch` only. No fixture touches real `~/`.

## Definition of Done

1. `poetry run pytest tests/unit/test_gitignore.py -q` — green
2. `poetry run pytest -q` — full suite green
3. `poetry run mypy src/` — clean
4. `poetry run ruff check src/ tests/` — clean
5. `poetry run black --check src/ tests/` — clean
6. `poetry run pre-commit run --all-files` — clean

Do NOT commit.
