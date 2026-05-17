"""Assemble project ``AGENTS.md`` files from classified catalog rules.

Codex CLI has no ``.claude/rules/`` directory — instead it reads an
``AGENTS.md`` at the project root and, walking root->cwd, every nested
``<dir>/AGENTS.md``. A catalog rule renders into that surface as a
*managed block*:

* an :data:`~ai_dotfiles.core.rule_classify.RuleClass.ALWAYS_ON` rule ->
  a managed block in the project-root ``AGENTS.md``;
* a :data:`~ai_dotfiles.core.rule_classify.RuleClass.PATH_SCOPED` rule ->
  a managed block in ``<dir>/AGENTS.md`` for every directory listed in
  the rule's ``paths:`` frontmatter field. Those entries are guaranteed
  glob-free literal directories — a rule whose ``paths:`` carries any
  glob is classified ``DESCRIPTION_ONLY`` instead, so it never reaches
  this module.

(:data:`~ai_dotfiles.core.rule_classify.RuleClass.DESCRIPTION_ONLY`
rules are *not* handled here — they become Codex-only skills, wired in
ai-11.)

Ownership philosophy mirrors :mod:`ai_dotfiles.core.settings_merge`'s
``strip_owned``: user-authored text in an ``AGENTS.md`` is sacred. Only
regions delimited by ai-dotfiles markers are ever written or removed.
A managed block looks like::

    <!-- ai-dotfiles:rule:<name> START -->
    <!-- ai-dotfiles:rule:<name> sha256:<hex> -->
    <rule body>
    <!-- ai-dotfiles:rule:<name> END -->

The ``sha256`` line lets :func:`upsert_rule_block` detect that a block
is already present *and unchanged* and skip the rewrite — assembly is
idempotent: re-running it produces no duplicate blocks and no drift.

This module owns ``AGENTS.md`` files, so file I/O here is intentional
(unlike :mod:`ai_dotfiles.core.paths`). Functions stay composable so
the ai-11 command layer can call them from the apply path.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from ai_dotfiles.core.errors import ElementError
from ai_dotfiles.core.frontmatter import parse_frontmatter
from ai_dotfiles.core.rule_classify import GLOB_METACHARS, is_glob_free_dir

__all__ = [
    "AGENTS_FILENAME",
    "block_markers",
    "iter_rule_block_names",
    "rule_block_targets",
    "rule_name_of",
    "strip_rule_blocks",
    "upsert_rule_block",
]

AGENTS_FILENAME = "AGENTS.md"

# Leading ``---\n ... \n---\n`` frontmatter block — same shape the
# frontmatter parser matches; reused to split the rule body off.
_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)

# A rule name is the markdown stem; keep it marker-safe (no ``-->``).
_RULE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

_MARKER_START = "<!-- ai-dotfiles:rule:{name} START -->"
_MARKER_END = "<!-- ai-dotfiles:rule:{name} END -->"
_MARKER_SHA = "<!-- ai-dotfiles:rule:{name} sha256:{sha} -->"

# Matches a whole managed block (START line .. END line, inclusive),
# capturing the rule name. Non-greedy so adjacent blocks stay separate.
_BLOCK_RE = re.compile(
    r"<!-- ai-dotfiles:rule:(?P<name>[A-Za-z0-9._-]+) START -->\n"
    r".*?"
    r"<!-- ai-dotfiles:rule:(?P=name) END -->\n?",
    re.DOTALL,
)


def rule_name_of(md_path: Path) -> str:
    """Return the marker-safe rule name for a rule markdown file.

    The name is the file stem (``python.md`` -> ``python``). Raises
    :class:`ElementError` if the stem contains characters that would
    break the HTML-comment markers.
    """
    name = md_path.stem
    if not _RULE_NAME_RE.match(name):
        raise ElementError(f"Rule name not marker-safe: {name!r} (from {md_path})")
    return name


def block_markers(name: str) -> tuple[str, str]:
    """Return the ``(start, end)`` marker lines for a rule ``name``."""
    return _MARKER_START.format(name=name), _MARKER_END.format(name=name)


def _split_body(text: str) -> str:
    """Return the markdown body of a rule file (frontmatter stripped)."""
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return text.strip()
    return text[match.end() :].strip()


def _content_sha(body: str) -> str:
    """Return a stable SHA-256 of a rule block body."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _render_block(name: str, body: str) -> str:
    """Render a complete managed block (markers + sha line + body)."""
    start, end = block_markers(name)
    sha_line = _MARKER_SHA.format(name=name, sha=_content_sha(body))
    return f"{start}\n{sha_line}\n{body}\n{end}\n"


def _existing_block_sha(name: str, text: str) -> str | None:
    """Return the recorded sha of rule ``name``'s block in ``text``.

    ``None`` if the rule has no block, or a block without a sha line.
    """
    start, _ = block_markers(name)
    pattern = re.compile(
        re.escape(start)
        + r"\n<!-- ai-dotfiles:rule:"
        + re.escape(name)
        + r" sha256:(?P<sha>[0-9a-f]+) -->"
    )
    match = pattern.search(text)
    return match.group("sha") if match else None


def iter_rule_block_names(text: str) -> list[str]:
    """Return the names of every ai-dotfiles managed block in ``text``.

    Order follows first appearance. Duplicate names (a malformed file)
    are reported once.
    """
    seen: list[str] = []
    for match in _BLOCK_RE.finditer(text):
        name = match.group("name")
        if name not in seen:
            seen.append(name)
    return seen


def strip_rule_blocks(text: str, names: set[str] | None = None) -> str:
    """Return ``text`` with ai-dotfiles managed rule blocks removed.

    The ``strip_owned`` analogue for ``AGENTS.md``. Only regions between
    matching markers are dropped — every other line (user-authored text,
    blank lines, other blocks) is preserved. If ``names`` is given, only
    those rules' blocks are stripped; otherwise *all* managed blocks go.

    Blank lines that the original file placed directly around a managed
    block are collapsed so repeated strip/insert cycles do not pile up
    empty lines (no drift).
    """

    def _replace(match: re.Match[str]) -> str:
        if names is not None and match.group("name") not in names:
            return match.group(0)
        return "\0"  # sentinel — collapsed below

    stripped = _BLOCK_RE.sub(_replace, text)
    # Collapse the sentinel plus any surrounding blank lines into a
    # single newline so user paragraphs keep their spacing.
    stripped = re.sub(r"\n*\0\n*", "\n", stripped)
    stripped = stripped.replace("\0", "")
    # Guard against runaway blank runs introduced by adjacent removals.
    stripped = re.sub(r"\n{3,}", "\n\n", stripped)
    return stripped


def upsert_rule_block(agents_md: Path, name: str, body: str) -> bool:
    """Insert or update rule ``name``'s managed block in ``agents_md``.

    Idempotent: if a block for ``name`` already exists with a matching
    content sha, the file is left untouched and ``False`` is returned.
    Otherwise the block is rewritten (or appended for a new rule) and
    ``True`` is returned. The parent directory is created if missing;
    user-authored text in an existing file is preserved.

    Returns ``True`` if the file was written, ``False`` on a no-op.
    """
    body = body.strip()
    new_sha = _content_sha(body)

    existing = agents_md.read_text(encoding="utf-8") if agents_md.is_file() else ""

    if _existing_block_sha(name, existing) == new_sha:
        return False

    # Defence in depth: a glob metacharacter anywhere in the directory
    # chain means a caller mis-resolved a file glob into an AGENTS.md
    # path. Refuse rather than ``mkdir`` a literal-glob directory tree
    # (the ai-18 bug). Classification keeps such rules off this path;
    # this guard ensures it can never regress silently.
    for part in agents_md.parent.parts:
        if any(ch in GLOB_METACHARS for ch in part):
            raise ElementError(
                f"refusing to create glob-named directory {part!r} "
                f"for AGENTS.md target {agents_md}"
            )

    block = _render_block(name, body)

    if name in iter_rule_block_names(existing):
        # Replace the stale block in place — keep surrounding user text.
        updated = strip_rule_blocks(existing, {name})
        updated = _append_block(updated, block)
    elif existing:
        updated = _append_block(existing, block)
    else:
        updated = block

    agents_md.parent.mkdir(parents=True, exist_ok=True)
    agents_md.write_text(updated, encoding="utf-8")
    return True


def _append_block(text: str, block: str) -> str:
    """Append ``block`` to ``text`` with exactly one blank-line separator."""
    if not text.strip():
        return block
    return f"{text.rstrip()}\n\n{block}"


def rule_block_targets(
    md_path: Path,
    project_root: Path,
    rule_class: str,
) -> list[Path]:
    """Return the ``AGENTS.md`` paths a rule's managed block must land in.

    For an ``ALWAYS_ON`` rule this is ``[<project_root>/AGENTS.md]``.
    For a ``PATH_SCOPED`` rule it is one ``<project_root>/<dir>/AGENTS.md``
    per directory listed in the rule's ``paths:`` frontmatter field.

    ``rule_class`` is the :class:`~ai_dotfiles.core.rule_classify.RuleClass`
    *value* string (``"always_on"`` / ``"path_scoped"``) — passed as a
    plain string to keep this module free of an import cycle with the
    classifier. ``DESCRIPTION_ONLY`` is rejected: it has no ``AGENTS.md``
    surface.

    A ``path_scoped`` rule's ``paths:`` entries must every one be a
    *literal, glob-free directory path*. The classifier
    (:func:`~ai_dotfiles.core.rule_classify.classify_rule`) already
    enforces this — a rule with any glob entry is demoted to
    ``description_only`` and never reaches here — but this function
    re-checks defensively: a glob entry raises :class:`ElementError`
    rather than being silently turned into a literal-glob directory name
    (the ai-18 bug).

    Raises :class:`ElementError` for an unknown class, for
    ``description_only``, for a ``path_scoped`` rule whose ``paths:``
    field is missing or empty, or for any ``paths:`` entry that contains
    a glob metacharacter.
    """
    if rule_class == "always_on":
        return [project_root / AGENTS_FILENAME]

    if rule_class == "path_scoped":
        text = md_path.read_text(encoding="utf-8")
        paths = parse_frontmatter(text).get("paths")
        if not isinstance(paths, list) or not paths:
            raise ElementError(
                f"path-scoped rule {md_path} has no 'paths:' frontmatter"
            )
        targets: list[Path] = []
        for raw in paths:
            entry = str(raw).strip()
            if not is_glob_free_dir(entry):
                raise ElementError(
                    f"path-scoped rule {md_path} has a non-directory "
                    f"'paths:' entry {entry!r}: a glob has no AGENTS.md "
                    f"surface (it should classify as description_only)"
                )
            directory = (project_root / entry).resolve()
            target = directory / AGENTS_FILENAME
            if target not in targets:
                targets.append(target)
        return targets

    raise ElementError(
        f"rule class {rule_class!r} has no AGENTS.md surface (rule {md_path})"
    )
