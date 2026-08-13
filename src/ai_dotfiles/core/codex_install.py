"""Apply layer for the Codex CLI target.

The render layer (:mod:`ai_dotfiles.core.codex_render`) is a pure string
transform; this module is the *side-effecting* counterpart — it writes
generated files, symlinks support files, detects drift, and prunes
managed artefacts.

Two element types have a Phase-1 Codex surface:

* a **skill** materialises as a real ``.agents/skills/<name>/``
  directory holding a generated ``SKILL.md`` plus *copies* of the
  catalog skill's support files (``scripts/``, ``references/``,
  ``assets/`` …) — the Codex target is self-contained by design (ai-20),
  so a Windows project never sees a symlink into the WSL catalog;
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
import os
import shutil
from pathlib import Path

from ai_dotfiles.core import agents_md
from ai_dotfiles.core.codex_render import (
    AGENT_GENERATOR_VERSION,
    render_agent_toml,
    render_rule_skill_md,
    render_skill_md,
    source_sha256,
    split_body,
)
from ai_dotfiles.core.errors import LinkError
from ai_dotfiles.core.frontmatter import parse_frontmatter
from ai_dotfiles.core.fs_copy import copy_tree_into

__all__ = [
    "MANAGED_BY_HEADER",
    "SKILL_DESCRIPTION_MAX",
    "SKILL_META_FILENAME",
    "apply_codex_rule_blocks",
    "generator_is_outdated",
    "install_codex_agent",
    "install_codex_rule_skill",
    "install_codex_skill",
    "is_managed",
    "is_managed_skill",
    "is_stale",
    "remove_codex_agent",
    "remove_codex_rule_blocks",
    "remove_codex_skill",
    "remove_codex_skill_link",
    "rule_block_state",
    "skill_symlink_ok",
    "symlink_codex_skill",
]

# The marker line every generated Codex agent ``.toml`` starts with.
# Mirrors ``codex_render._MANAGED_BY`` — kept as a public constant here
# so the command layer can refer to "managed" agents without importing
# a private name from the render module.
MANAGED_BY_HEADER = "# managed-by: ai-dotfiles"

# The skill SKILL.md filename. The support files/dirs that get
# copied are everything else in the catalog skill directory.
_SKILL_FILE = "SKILL.md"

# Per-skill sidecar holding the drift/ownership marker (ai-19). A
# generated ``SKILL.md`` must start with ``---`` on line 1, so the
# ``# managed-by`` / ``# source-sha256`` marker that an agent ``.toml``
# keeps in a comment header instead lives in this JSON file next to the
# generated ``SKILL.md``. Its presence marks the skill dir as managed.
SKILL_META_FILENAME = ".ai-dotfiles-meta"

# Identifier stored in the sidecar's ``managed_by`` field.
_MANAGED_BY_VALUE = "ai-dotfiles"

# Codex enforces a hard cap on a skill's frontmatter ``description``; over the
# limit the whole skill fails to load (openai/codex issue #13941). A raw
# ``SKILL.md`` whose description exceeds it must be rendered with the
# first-sentence trim rather than symlinked.
SKILL_DESCRIPTION_MAX = 1024

# Codex skill ``name``: lowercase letters/digits/hyphens, <= 64 chars, and it
# must equal the parent folder name (always true for our sources, whose
# folder *is* the name).
_SKILL_NAME_MAX = 64


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
    """Return the first three lines of ``path`` (empty list if unreadable)."""
    try:
        with path.open(encoding="utf-8") as handle:
            return [handle.readline().rstrip("\n") for _ in range(3)]
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


def generator_is_outdated(generated_path: Path) -> bool:
    """Return True if an agent ``.toml`` came from an older renderer.

    Lets the status layer say *why* an artefact is stale: the source did
    not necessarily change — the renderer did. Returns False for any
    non-agent artefact, which carries no generator marker.
    """
    lines = _read_header_lines(generated_path)
    if len(lines) < 3 or lines[0] != MANAGED_BY_HEADER:
        return False
    if not lines[2].startswith("# generator: "):
        return True
    return lines[2].removeprefix("# generator: ").strip() != str(
        AGENT_GENERATOR_VERSION
    )


def _agent_is_stale(generated_path: Path, source_path: Path) -> bool:
    """Drift check for an agent ``.toml`` — header SHA *and* generator.

    Two independent reasons to regenerate: the catalog source changed, or
    the renderer that produced this file did. Without the second check a
    transform change (e.g. dropping the ``model`` pin) would never reach
    projects whose sources happen to be untouched.

    A file written before the generator line existed has no third header
    line and is therefore stale, which is the intended migration path.
    """
    lines = _read_header_lines(generated_path)
    if len(lines) < 2 or not lines[1].startswith("# source-sha256: "):
        return True
    if len(lines) < 3 or not lines[2].startswith("# generator: "):
        return True
    if lines[2].removeprefix("# generator: ").strip() != str(AGENT_GENERATOR_VERSION):
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


def _skill_support_names(source_dir: Path) -> list[str]:
    """Return the names of a catalog skill's support items (all but SKILL.md).

    Everything in the catalog skill directory other than ``SKILL.md`` and
    dotfiles is a support item — ``scripts/``, ``references/``,
    ``assets/`` and any sibling file.
    """
    return [
        child.name
        for child in sorted(source_dir.iterdir())
        if child.name != _SKILL_FILE and not child.name.startswith(".")
    ]


def _clear_stale_support(target_dir: Path, keep: set[str]) -> None:
    """Drop previously copied support items no longer present in the catalog.

    Re-install copies the current support items afresh; this removes any
    that a previous install left behind but the catalog source has since
    renamed or deleted. The generated ``SKILL.md`` and the
    ``.ai-dotfiles-meta`` sidecar (dotfiles) are always kept.
    """
    for child in target_dir.iterdir():
        if child.name == _SKILL_FILE or child.name.startswith("."):
            continue
        if child.name in keep:
            continue
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        except OSError as exc:
            raise LinkError(
                f"Failed to clear stale support item {child}: {exc}"
            ) from exc


def install_codex_skill(source_dir: Path, target_dir: Path) -> str:
    """Install a catalog skill into ``target_dir`` for the Codex target.

    ``target_dir`` (``.agents/skills/<name>/``) is created as a real
    directory; ``SKILL.md`` is generated via
    :func:`~ai_dotfiles.core.codex_render.render_skill_md` with a
    trimmed description (ADR ai-1-4); every other catalog file/dir
    (``scripts/``, ``references/``, ``assets/`` …) is *copied* into it
    (ai-20). The Codex target is self-contained by design — copying
    rather than symlinking means a Windows project never carries a
    symlink into the WSL-resident catalog. Executable bits on copied
    ``scripts/`` are preserved (:func:`shutil.copy2` keeps mode).

    The generated ``SKILL.md`` starts with ``---`` on line 1 (ai-19);
    the drift/ownership marker is written to a ``.ai-dotfiles-meta``
    sidecar next to it. Re-installing overwrites the ``SKILL.md`` and
    sidecar cleanly and refreshes the copied support items — a catalog
    file removed between installs does not linger.

    Returns ``"created"`` or ``"updated"``.

    Raises:
        ElementError: if the catalog ``SKILL.md`` lacks ``description``.
        LinkError: if the skill directory cannot be materialised.
    """
    source_skill_md = source_dir / _SKILL_FILE
    rendered = render_skill_md(source_skill_md)
    source_text = source_skill_md.read_text(encoding="utf-8")

    # A symlink at the target (a previous gated-symlink install, or a
    # migrate-created link) must be dropped first — ``mkdir`` /
    # ``write_text`` would otherwise follow it and write INTO the source.
    if target_dir.is_symlink():
        try:
            target_dir.unlink()
        except OSError as exc:
            raise LinkError(
                f"Failed to replace Codex skill symlink {target_dir}: {exc}"
            ) from exc

    existed = target_dir.exists()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / _SKILL_FILE).write_text(rendered, encoding="utf-8")
    except OSError as exc:
        raise LinkError(
            f"Failed to write Codex skill {target_dir / _SKILL_FILE}: {exc}"
        ) from exc
    _write_skill_meta(target_dir, source_text)

    support_names = _skill_support_names(source_dir)
    if existed:
        _clear_stale_support(target_dir, keep=set(support_names))
    for name in support_names:
        copy_tree_into(source_dir / name, target_dir / name)

    return "updated" if existed else "created"


def skill_symlink_ok(source_dir: Path, name: str) -> tuple[bool, str]:
    """Return ``(can_symlink, reason)`` for a raw skill directory.

    A raw ``SKILL.md`` may be symlinked (auto-fresh, no drift tracking)
    only when Codex will load it unchanged: the ``name`` must be valid
    hyphen-case and the frontmatter ``description`` must be within
    Codex's hard :data:`SKILL_DESCRIPTION_MAX` cap. Otherwise the skill
    must be rendered with the first-sentence description trim.
    """
    if not _valid_skill_name(name):
        return False, f"name {name!r} is not Codex hyphen-case — rendering instead"
    skill_md = source_dir / _SKILL_FILE
    try:
        frontmatter = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    except OSError:
        return False, "SKILL.md unreadable — rendering instead"
    description = frontmatter.get("description")
    if isinstance(description, str) and len(description) > SKILL_DESCRIPTION_MAX:
        return (
            False,
            f"description {len(description)} chars > {SKILL_DESCRIPTION_MAX} cap "
            "— rendering with first-sentence trim",
        )
    return True, "symlink (auto-fresh; raw SKILL.md within Codex limits)"


def _valid_skill_name(name: str) -> bool:
    if not name or len(name) > _SKILL_NAME_MAX:
        return False
    if name[0] == "-" or name[-1] == "-":
        return False
    return all(ch.islower() or ch.isdigit() or ch == "-" for ch in name)


def symlink_codex_skill(
    source_dir: Path, target_dir: Path, *, relative: bool = True
) -> str:
    """Create a symlink ``target_dir`` -> ``source_dir`` idempotently.

    With ``relative`` (the project-scope default) the link text is
    relative so it survives the repo being moved or cloned. The global
    scope passes ``relative=False``: ``$CODEX_HOME`` and the ai-dotfiles
    storage move independently (each has its own env override), so an
    absolute link — the same convention the global Claude symlinks use —
    is the robust choice there.

    A stale symlink is repointed; a previously *rendered* managed skill
    at the target is replaced by the link; a user-authored directory is
    refused. Returns ``"linked"`` or ``"already-linked"``.
    """
    try:
        target_dir.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise LinkError(f"Failed to create {target_dir.parent}: {exc}") from exc

    link_ref = (
        os.path.relpath(source_dir, target_dir.parent) if relative else str(source_dir)
    )

    if target_dir.is_symlink():
        if os.readlink(target_dir) == link_ref:
            return "already-linked"
        target_dir.unlink()
    elif target_dir.exists():
        if is_managed_skill(target_dir):
            shutil.rmtree(target_dir)
        else:
            raise LinkError(
                f"{target_dir} exists and is not ai-dotfiles-managed; "
                "refusing to overwrite a user-authored skill"
            )

    try:
        target_dir.symlink_to(link_ref)
    except OSError as exc:
        raise LinkError(f"Failed to symlink {target_dir} -> {link_ref}: {exc}") from exc
    return "linked"


def remove_codex_skill_link(link: Path, source_root: Path) -> bool:
    """Remove a skill symlink if it points under ``source_root``.

    The symlink analogue of :func:`remove_codex_skill` for prune: a link
    whose (non-strict) resolution lands inside ``source_root`` (e.g. the
    catalog) is ai-dotfiles-created and safe to drop — dangling links
    included. A symlink pointing anywhere else is user-authored and left
    alone. Returns ``True`` if the link was removed.
    """
    if not link.is_symlink():
        return False
    try:
        resolved = link.resolve()
        root = source_root.resolve()
    except OSError:
        return False
    if not resolved.is_relative_to(root):
        return False
    try:
        link.unlink()
    except OSError as exc:
        raise LinkError(f"Failed to remove Codex skill link {link}: {exc}") from exc
    return True


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
    (ai-19) — see :func:`is_managed_skill`. The directory's support
    files are copies (ai-20), so dropping the directory tree removes
    them with it and never touches the catalog source. A user-authored
    ``.agents/skills/<name>/`` (no sidecar) is left untouched.
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


def rule_block_state(rule_md: Path, agents_md_path: Path) -> str:
    """Return the drift state of a rule's managed block in one ``AGENTS.md``.

    The read-only counterpart of :func:`apply_codex_rule_blocks`, and the
    ``AGENTS.md`` analogue of :func:`is_stale` for skills/agents. One of:

    * ``"missing"`` — the file is absent/unreadable, or holds no managed
      block for the rule (never installed, or the block was removed);
    * ``"stale"``   — a block exists but its recorded ``sha256`` no longer
      matches the current rule body (the source changed since install);
    * ``"ok"``      — a block exists and matches the current rule body.

    The body is stripped exactly as the apply path strips it
    (:func:`~ai_dotfiles.core.codex_render.split_body`), so the comparison
    is byte-for-byte what :func:`~ai_dotfiles.core.agents_md.upsert_rule_block`
    would compute.
    """
    if not agents_md_path.is_file():
        return "missing"
    try:
        text = agents_md_path.read_text(encoding="utf-8")
    except OSError:
        return "missing"
    name = agents_md.rule_name_of(rule_md)
    if name not in agents_md.iter_rule_block_names(text):
        return "missing"
    try:
        body = split_body(rule_md.read_text(encoding="utf-8"))
    except OSError:
        return "stale"
    return "ok" if agents_md.block_matches(name, body, text) else "stale"


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
