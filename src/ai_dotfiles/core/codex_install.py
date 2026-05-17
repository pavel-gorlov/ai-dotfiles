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

Drift detection (ADR ai-1-1) records the SHA-256 of the catalog source.
The marker is carried differently by the two targets:

* an agent ``.toml`` keeps a two-line ``# managed-by`` / ``# source-sha256``
  comment header — ``#`` is a valid TOML comment;
* a skill ``SKILL.md`` must start with ``---`` on line 1 for Codex's
  frontmatter parser to recognise it (ai-19), so its marker lives in a
  per-skill ``.ai-dotfiles-meta`` JSON sidecar written next to it.

Removal and staleness checks key off the appropriate marker — the
header for an agent, the sidecar for a skill — so user-authored files
in the same directories are never touched. A skill directory with no
``.ai-dotfiles-meta`` sidecar is user-authored and never pruned.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from ai_dotfiles.core import agents_md
from ai_dotfiles.core.codex_render import (
    render_agent_toml,
    render_rule_skill_md,
    render_skill_md,
    source_sha256,
    split_body,
)
from ai_dotfiles.core.errors import LinkError
from ai_dotfiles.core.symlinks import safe_symlink

__all__ = [
    "MANAGED_BY_HEADER",
    "SKILL_META_FILENAME",
    "apply_codex_rule_blocks",
    "install_codex_agent",
    "install_codex_rule_skill",
    "install_codex_skill",
    "is_managed",
    "is_managed_skill",
    "is_stale",
    "remove_codex_agent",
    "remove_codex_rule_blocks",
    "remove_codex_skill",
]

# The marker line every generated Codex agent ``.toml`` starts with.
# Mirrors ``codex_render._MANAGED_BY`` — kept as a public constant here
# so the command layer can refer to "managed" agents without importing
# a private name from the render module.
MANAGED_BY_HEADER = "# managed-by: ai-dotfiles"

# The skill SKILL.md filename. The support files/dirs that get
# symlinked are everything else in the catalog skill directory.
_SKILL_FILE = "SKILL.md"

# Per-skill sidecar holding the drift/ownership marker (ai-19). A
# generated ``SKILL.md`` must start with ``---`` on line 1, so the
# ``# managed-by`` / ``# source-sha256`` marker that an agent ``.toml``
# keeps in a comment header instead lives in this JSON file next to the
# generated ``SKILL.md``. Its presence marks the skill dir as managed.
SKILL_META_FILENAME = ".ai-dotfiles-meta"

# Identifier stored in the sidecar's ``managed_by`` field.
_MANAGED_BY_VALUE = "ai-dotfiles"


def _skill_meta_path(target_dir: Path) -> Path:
    """Return the ``.ai-dotfiles-meta`` sidecar path for a skill directory."""
    return target_dir / SKILL_META_FILENAME


def _write_skill_meta(target_dir: Path, source_text: str) -> None:
    """Write the skill drift/ownership sidecar next to the generated SKILL.md.

    The sidecar is a small JSON object — ``{"managed_by": "ai-dotfiles",
    "source_sha256": "<hex>"}`` — recording the SHA-256 of the catalog
    source. ``remove`` / ``prune`` treat its presence as the
    ai-dotfiles-managed marker; :func:`is_stale` reads ``source_sha256``.
    """
    payload = {
        "managed_by": _MANAGED_BY_VALUE,
        "source_sha256": source_sha256(source_text),
    }
    meta_path = _skill_meta_path(target_dir)
    try:
        meta_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise LinkError(
            f"Failed to write Codex skill sidecar {meta_path}: {exc}"
        ) from exc


def _read_skill_meta(target_dir: Path) -> dict[str, str] | None:
    """Return the parsed skill sidecar, or ``None`` if absent/unreadable.

    A skill directory without a readable sidecar is treated as
    user-authored — never pruned, always considered stale.
    """
    meta_path = _skill_meta_path(target_dir)
    try:
        raw = meta_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return {str(k): str(v) for k, v in data.items()}


def _read_header_lines(path: Path) -> list[str]:
    """Return the first two lines of ``path`` (empty list if unreadable)."""
    try:
        with path.open(encoding="utf-8") as handle:
            return [handle.readline().rstrip("\n"), handle.readline().rstrip("\n")]
    except OSError:
        return []


def is_managed(path: Path) -> bool:
    """Return True if ``path`` is a generated agent ``.toml`` ai-dotfiles owns.

    An agent ``.toml`` is "managed" when its first line is the
    :data:`MANAGED_BY_HEADER` comment marker. User-authored ``.toml``
    files in the same directory have no such header and are left alone.

    Skills carry their marker in a ``.ai-dotfiles-meta`` sidecar, not an
    in-file header — use :func:`is_managed_skill` for a skill directory.
    """
    if not path.is_file():
        return False
    lines = _read_header_lines(path)
    return bool(lines) and lines[0] == MANAGED_BY_HEADER


def is_managed_skill(target_dir: Path) -> bool:
    """Return True if ``target_dir`` is an ai-dotfiles-managed Codex skill.

    A skill directory is managed when it holds a ``.ai-dotfiles-meta``
    sidecar with ``managed_by == "ai-dotfiles"`` (ai-19). A skill
    directory without the sidecar is user-authored and must never be
    pruned or removed.
    """
    if not target_dir.is_dir():
        return False
    meta = _read_skill_meta(target_dir)
    return meta is not None and meta.get("managed_by") == _MANAGED_BY_VALUE


def _source_sha256(text: str) -> str:
    """Return the hex SHA-256 of ``text`` encoded as UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _agent_is_stale(generated_path: Path, source_path: Path) -> bool:
    """Drift check for an agent ``.toml`` — compares the header SHA line."""
    lines = _read_header_lines(generated_path)
    if len(lines) < 2 or not lines[1].startswith("# source-sha256: "):
        return True
    recorded = lines[1].removeprefix("# source-sha256: ").strip()
    try:
        source_text = source_path.read_text(encoding="utf-8")
    except OSError:
        return True
    return recorded != _source_sha256(source_text)


def _skill_is_stale(skill_md_path: Path, source_path: Path) -> bool:
    """Drift check for a skill — compares the sidecar SHA to the source."""
    meta = _read_skill_meta(skill_md_path.parent)
    if meta is None:
        return True
    recorded = meta.get("source_sha256")
    if not recorded:
        return True
    try:
        source_text = source_path.read_text(encoding="utf-8")
    except OSError:
        return True
    return recorded != _source_sha256(source_text)


def is_stale(generated_path: Path, source_path: Path) -> bool:
    """Return True if ``generated_path`` no longer matches its source.

    Drift detection (ADR ai-1-1). The recorded SHA-256 of the catalog
    source is compared to a fresh hash of ``source_path``'s current
    content. The recorded value lives in a different place per target,
    so this dispatches on the generated artefact:

    * an agent ``.toml`` — read the ``# source-sha256`` comment header;
    * a skill ``SKILL.md`` — read ``source_sha256`` from the sibling
      ``.ai-dotfiles-meta`` sidecar (ai-19).

    A missing generated file, an unreadable marker, or a missing source
    counts as stale — the safe answer that nudges the user toward a
    regenerating ``install``.
    """
    if not generated_path.is_file():
        return True
    if generated_path.name == _SKILL_FILE:
        return _skill_is_stale(generated_path, source_path)
    return _agent_is_stale(generated_path, source_path)


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

    The generated ``SKILL.md`` starts with ``---`` on line 1 (ai-19);
    the drift/ownership marker is written to a ``.ai-dotfiles-meta``
    sidecar next to it. Re-installing overwrites both cleanly.

    Returns ``"created"`` or ``"updated"``.

    Raises:
        ElementError: if the catalog ``SKILL.md`` lacks ``description``.
        LinkError: if the skill directory cannot be materialised.
    """
    source_skill_md = source_dir / _SKILL_FILE
    rendered = render_skill_md(source_skill_md)
    source_text = source_skill_md.read_text(encoding="utf-8")

    existed = target_dir.exists()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / _SKILL_FILE).write_text(rendered, encoding="utf-8")
    except OSError as exc:
        raise LinkError(
            f"Failed to write Codex skill {target_dir / _SKILL_FILE}: {exc}"
        ) from exc
    _write_skill_meta(target_dir, source_text)

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

    A skill directory is removed only when it carries the
    ``.ai-dotfiles-meta`` sidecar marking it ai-dotfiles-managed
    (ai-19) — see :func:`is_managed_skill`. The directory's symlinked
    support files point back into the read-only catalog, so removing the
    directory tree only drops the symlinks, never the catalog content.
    A user-authored ``.agents/skills/<name>/`` (no sidecar) is left
    untouched.
    """
    if not is_managed_skill(target_dir):
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
    The generated ``SKILL.md`` starts with ``---`` on line 1 (ai-19);
    the drift/ownership marker goes to a ``.ai-dotfiles-meta`` sidecar so
    :func:`remove_codex_skill` and drift detection key off it.

    Returns ``"created"`` or ``"updated"``.

    Raises:
        LinkError: if the skill directory cannot be materialised.
    """
    rendered = render_rule_skill_md(rule_md)
    source_text = rule_md.read_text(encoding="utf-8")
    existed = target_dir.exists()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / _SKILL_FILE).write_text(rendered, encoding="utf-8")
    except OSError as exc:
        raise LinkError(
            f"Failed to write Codex rule skill {target_dir / _SKILL_FILE}: {exc}"
        ) from exc
    _write_skill_meta(target_dir, source_text)
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
