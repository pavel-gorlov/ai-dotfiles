"""Apply layer for the Codex CLI target.

The render layer (:mod:`ai_dotfiles.core.codex_render`) is a pure string
transform; this module is the *side-effecting* counterpart — it writes
generated files, symlinks support files, detects drift, and prunes
managed artefacts.

Two element types have a Phase-1 Codex surface:

* a **skill** materialises as a real ``.agents/skills/<name>/``
  directory holding a generated ``SKILL.md`` plus symlinks back to the
  catalog skill's support files (``scripts/``, ``references/``,
  ``assets/`` …);
* an **agent** materialises as a single generated
  ``.codex/agents/<name>.toml`` file.

Every generated file carries the two-line drift header emitted by the
render layer — line 1 ``# managed-by: ai-dotfiles``, line 2
``# source-sha256: <hex>``. Removal and staleness checks key off that
header so user-authored files in the same directories are never
touched.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from ai_dotfiles.core.codex_render import render_agent_toml, render_skill_md
from ai_dotfiles.core.errors import LinkError
from ai_dotfiles.core.symlinks import safe_symlink

__all__ = [
    "MANAGED_BY_HEADER",
    "install_codex_skill",
    "install_codex_agent",
    "is_managed",
    "is_stale",
    "remove_codex_skill",
    "remove_codex_agent",
]

# The marker line every generated Codex file starts with. Mirrors
# ``codex_render._MANAGED_BY`` — kept as a public constant here so the
# command layer can refer to "managed" files without importing a
# private name from the render module.
MANAGED_BY_HEADER = "# managed-by: ai-dotfiles"

# The skill SKILL.md filename. The support files/dirs that get
# symlinked are everything else in the catalog skill directory.
_SKILL_FILE = "SKILL.md"


def _read_header_lines(path: Path) -> list[str]:
    """Return the first two lines of ``path`` (empty list if unreadable)."""
    try:
        with path.open(encoding="utf-8") as handle:
            return [handle.readline().rstrip("\n"), handle.readline().rstrip("\n")]
    except OSError:
        return []


def is_managed(path: Path) -> bool:
    """Return True if ``path`` is a generated file ai-dotfiles owns.

    A file is "managed" when its first line is the
    :data:`MANAGED_BY_HEADER` marker. User-authored files in the same
    directory have no such header and are therefore left alone.
    """
    if not path.is_file():
        return False
    lines = _read_header_lines(path)
    return bool(lines) and lines[0] == MANAGED_BY_HEADER


def _source_sha256(text: str) -> str:
    """Return the hex SHA-256 of ``text`` encoded as UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_stale(generated_path: Path, source_path: Path) -> bool:
    """Return True if ``generated_path`` no longer matches its source.

    Reads the ``# source-sha256`` header line of the generated file and
    compares it to a fresh hash of ``source_path``'s current content
    (ADR ai-1-1 drift detection). A generated file with no readable
    header, or a missing source, counts as stale — the safe answer that
    nudges the user toward a regenerating ``install``.
    """
    if not generated_path.is_file():
        return True
    lines = _read_header_lines(generated_path)
    if len(lines) < 2 or not lines[1].startswith("# source-sha256: "):
        return True
    recorded = lines[1].removeprefix("# source-sha256: ").strip()

    try:
        source_text = source_path.read_text(encoding="utf-8")
    except OSError:
        return True
    return recorded != _source_sha256(source_text)


def install_codex_agent(source_md: Path, target_toml: Path) -> str:
    """Render ``source_md`` to Codex TOML and write it to ``target_toml``.

    The generated ``.toml`` is a committed project artefact (ADR
    ai-1-1), not a symlink. Returns ``"created"`` or ``"updated"``.

    Raises:
        ElementError: if the agent frontmatter lacks ``name`` /
            ``description`` (propagated from the render layer).
        LinkError: if the file cannot be written.
    """
    rendered = render_agent_toml(source_md)
    existed = target_toml.exists()
    try:
        target_toml.parent.mkdir(parents=True, exist_ok=True)
        target_toml.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        raise LinkError(f"Failed to write Codex agent {target_toml}: {exc}") from exc
    return "updated" if existed else "created"


def _skill_support_items(source_dir: Path) -> list[Path]:
    """Return the catalog skill's support files/dirs (everything but SKILL.md)."""
    items: list[Path] = []
    for child in sorted(source_dir.iterdir()):
        if child.name == _SKILL_FILE or child.name.startswith("."):
            continue
        items.append(child)
    return items


def install_codex_skill(source_dir: Path, target_dir: Path, backup: Path) -> str:
    """Install a catalog skill into ``target_dir`` for the Codex target.

    ``target_dir`` (``.agents/skills/<name>/``) is created as a real
    directory; ``SKILL.md`` is generated via
    :func:`~ai_dotfiles.core.codex_render.render_skill_md` with a
    trimmed description (ADR ai-1-4); every other catalog file/dir
    (``scripts/``, ``references/``, ``assets/`` …) is symlinked into it.

    Returns ``"created"`` or ``"updated"``.

    Raises:
        ElementError: if the catalog ``SKILL.md`` lacks ``description``.
        LinkError: if the skill directory cannot be materialised.
    """
    source_skill_md = source_dir / _SKILL_FILE
    rendered = render_skill_md(source_skill_md)

    existed = target_dir.exists()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / _SKILL_FILE).write_text(rendered, encoding="utf-8")
    except OSError as exc:
        raise LinkError(
            f"Failed to write Codex skill {target_dir / _SKILL_FILE}: {exc}"
        ) from exc

    for item in _skill_support_items(source_dir):
        safe_symlink(item, target_dir / item.name, backup)

    return "updated" if existed else "created"


def remove_codex_agent(target_toml: Path) -> bool:
    """Delete a managed Codex agent ``.toml``. Return True if removed.

    A file is removed only when it carries the :data:`MANAGED_BY_HEADER`
    marker; a user-authored ``.toml`` of the same name is left in place.
    """
    if not is_managed(target_toml):
        return False
    try:
        target_toml.unlink()
    except OSError as exc:
        raise LinkError(f"Failed to remove Codex agent {target_toml}: {exc}") from exc
    return True


def remove_codex_skill(target_dir: Path) -> bool:
    """Delete a managed Codex skill directory. Return True if removed.

    A skill directory is removed only when its ``SKILL.md`` is managed
    (carries the :data:`MANAGED_BY_HEADER`). The directory's symlinked
    support files point back into the read-only catalog, so removing the
    directory tree only drops the symlinks, never the catalog content.
    A user-authored ``.agents/skills/<name>/`` is left untouched.
    """
    skill_md = target_dir / _SKILL_FILE
    if not is_managed(skill_md):
        return False
    try:
        shutil.rmtree(target_dir)
    except OSError as exc:
        raise LinkError(f"Failed to remove Codex skill {target_dir}: {exc}") from exc
    return True
