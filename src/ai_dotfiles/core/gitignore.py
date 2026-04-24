"""Auto-managed ``.gitignore`` block for vendored symlinks.

``ai-dotfiles add`` creates absolute-path symlinks from a project's
``.claude/`` into ``~/.ai-dotfiles/catalog/``. Those symlinks must not
be committed — they're per-machine and dangling for everyone else.
This module keeps a managed block inside the project's ``.gitignore``
listing every such symlink, so teammates / CI / Docker never inherit
broken paths.

The block is regenerated from scratch on every ``add`` / ``remove`` /
``install`` by rescanning ``.claude/``; no state file is needed. User-
authored lines outside the block are preserved verbatim; a literal
path already ignored by a user-authored line is NOT duplicated in the
block, and on ``remove`` we never touch such lines (we didn't place
them).
"""

from __future__ import annotations

from pathlib import Path

from ai_dotfiles.core.symlinks import is_managed_symlink

MANAGED_START = "# >>> ai-dotfiles managed — do not edit manually <<<"
MANAGED_END = "# >>> end ai-dotfiles managed <<<"

# Directories under .claude/ whose children are individually linked.
_SCAN_SUBDIRS: tuple[str, ...] = (
    "skills",
    "agents",
    "rules",
    "hooks",
    "output-styles",
)

# Top-level files that may be symlinked from global scope.
_SCAN_TOP_FILES: tuple[str, ...] = ("CLAUDE.md", "settings.json")


def collect_managed_paths(claude_dir: Path, storage: Path) -> list[str]:
    """Return sorted ``/.claude/...`` paths for every managed symlink.

    A managed symlink is one pointing into ``storage`` — i.e. created by
    ai-dotfiles itself. Real files and user-authored symlinks pointing
    elsewhere are ignored.
    """
    results: list[str] = []
    if not claude_dir.is_dir():
        return results
    rel_base = claude_dir.name
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
    """Split ``text`` into ``(before, managed, after)``.

    ``managed`` excludes the marker lines themselves. If no block exists,
    returns ``(all_lines, [], [])``.
    """
    lines = text.splitlines()
    try:
        start = lines.index(MANAGED_START)
    except ValueError:
        return lines, [], []
    try:
        end = lines.index(MANAGED_END, start + 1)
    except ValueError:
        # Malformed file — treat as no block so we don't corrupt user edits.
        return lines, [], []
    return lines[:start], lines[start + 1 : end], lines[end + 1 :]


def render(before: list[str], managed: list[str], after: list[str]) -> str:
    """Join the three segments back, wrapping ``managed`` in markers.

    If ``managed`` is empty, the markers are omitted entirely.
    """
    pieces: list[str] = list(before)
    if managed:
        pieces.append(MANAGED_START)
        pieces.extend(managed)
        pieces.append(MANAGED_END)
    pieces.extend(after)
    if not pieces or all(not p.strip() for p in pieces):
        return ""
    return "\n".join(pieces).rstrip() + "\n"


def sync_gitignore(project_root: Path, managed_paths: list[str]) -> bool:
    """Rewrite the managed block in ``project_root/.gitignore``.

    Returns True if the file was actually written. Silent no-op when the
    project is clearly not under git AND no ``.gitignore`` exists yet.
    Paths already literal-matched by a user-authored line are skipped so
    the block stays minimal.
    """
    gitignore = project_root / ".gitignore"
    git_dir = project_root / ".git"
    if not git_dir.exists() and not gitignore.exists():
        return False

    text = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    before, _current_managed, after = parse_blocks(text)

    # Drop paths that a user-authored line already ignores verbatim.
    user_authored_literals = {line.strip() for line in before + after}
    managed = [p for p in managed_paths if p not in user_authored_literals]

    rendered = render(before, managed, after)

    if not rendered and not gitignore.exists():
        return False
    if gitignore.exists() and gitignore.read_text(encoding="utf-8") == rendered:
        return False

    gitignore.write_text(rendered, encoding="utf-8")
    return True
