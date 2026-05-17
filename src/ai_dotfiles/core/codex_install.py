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

from ai_dotfiles.core import agents_md
from ai_dotfiles.core.codex_render import (
    render_agent_toml,
    render_rule_skill_md,
    render_skill_md,
    split_body,
)
from ai_dotfiles.core.errors import LinkError
from ai_dotfiles.core.symlinks import safe_symlink

__all__ = [
    "MANAGED_BY_HEADER",
    "apply_codex_rule_blocks",
    "install_codex_agent",
    "install_codex_rule_skill",
    "install_codex_skill",
    "is_managed",
    "is_stale",
    "remove_codex_agent",
    "remove_codex_rule_blocks",
    "remove_codex_skill",
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


# ── Rules: AGENTS.md blocks + synthetic rule-<name> skills ─────────────
#
# Phase 2 (epic ai-1, ADR ai-1-2). A catalog rule has no single Codex
# artefact — it dispatches by :class:`~ai_dotfiles.core.rule_classify.RuleClass`:
#
# * ``ALWAYS_ON`` / ``PATH_SCOPED`` -> managed blocks in one or more
#   ``AGENTS.md`` files (assembled by :mod:`ai_dotfiles.core.agents_md`);
# * ``DESCRIPTION_ONLY`` -> a synthetic Codex-only skill ``rule-<name>``.
#
# These wrap the pure :mod:`agents_md` helpers with the side-effecting
# write/delete the command layer needs.


def install_codex_rule_skill(rule_md: Path, target_dir: Path) -> str:
    """Render a description-only rule into a synthetic Codex skill.

    ``target_dir`` (``.agents/skills/rule-<name>/``) is created as a real
    directory holding a single generated ``SKILL.md`` — the rule body
    wrapped in synthesised ``name`` / ``description`` frontmatter (ADR
    ai-1-2). Unlike a catalog skill it has no support files to symlink.
    The generated ``SKILL.md`` carries the managed-by + source-sha256
    header so :func:`remove_codex_skill` and drift detection key off it.

    Returns ``"created"`` or ``"updated"``.

    Raises:
        LinkError: if the skill directory cannot be materialised.
    """
    rendered = render_rule_skill_md(rule_md)
    existed = target_dir.exists()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / _SKILL_FILE).write_text(rendered, encoding="utf-8")
    except OSError as exc:
        raise LinkError(
            f"Failed to write Codex rule skill {target_dir / _SKILL_FILE}: {exc}"
        ) from exc
    return "updated" if existed else "created"


def apply_codex_rule_blocks(rule_md: Path, agents_md_paths: list[Path]) -> list[Path]:
    """Upsert a rule's managed block into each ``AGENTS.md`` in the list.

    The rule body (frontmatter stripped via
    :func:`~ai_dotfiles.core.codex_render.split_body`) is written as an
    ai-dotfiles managed block — idempotently — into every path in
    ``agents_md_paths`` (the project-root ``AGENTS.md`` for an always-on
    rule, one nested ``<dir>/AGENTS.md`` per ``paths:`` entry for a
    path-scoped rule). User-authored text in those files is preserved.

    Returns the subset of ``agents_md_paths`` that were actually written
    (a no-op on an unchanged block is excluded).
    """
    name = agents_md.rule_name_of(rule_md)
    body = split_body(rule_md.read_text(encoding="utf-8"))
    written: list[Path] = []
    for path in agents_md_paths:
        try:
            if agents_md.upsert_rule_block(path, name, body):
                written.append(path)
        except OSError as exc:
            raise LinkError(f"Failed to write rule block to {path}: {exc}") from exc
    return written


def remove_codex_rule_blocks(agents_md_path: Path, rule_name: str) -> bool:
    """Strip rule ``rule_name``'s managed block from one ``AGENTS.md``.

    Only the block delimited by the rule's ai-dotfiles markers is
    removed; surrounding user-authored text is preserved. An
    ``AGENTS.md`` left whitespace-only after the strip is deleted — it
    held nothing but ai-dotfiles content. Returns ``True`` if the file
    was rewritten or deleted, ``False`` if there was nothing to strip.
    """
    if not agents_md_path.is_file():
        return False
    text = agents_md_path.read_text(encoding="utf-8")
    if rule_name not in agents_md.iter_rule_block_names(text):
        return False

    stripped = agents_md.strip_rule_blocks(text, {rule_name})
    try:
        if stripped.strip():
            agents_md_path.write_text(stripped, encoding="utf-8")
        else:
            agents_md_path.unlink()
    except OSError as exc:
        raise LinkError(
            f"Failed to update {agents_md_path} while removing rule "
            f"{rule_name!r}: {exc}"
        ) from exc
    return True
