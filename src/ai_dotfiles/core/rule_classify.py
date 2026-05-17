"""Classify a catalog rule into a Codex activation mode.

Claude Code loads every ``.claude/rules/*.md`` and activates it by
``description``. Codex CLI has no single equivalent — a rule maps onto
one of three Codex surfaces depending on its frontmatter (epic ADR
ai-1-2):

* :data:`RuleClass.ALWAYS_ON` — a managed block in the project-root
  ``AGENTS.md`` (Codex always reads the root ``AGENTS.md``).
* :data:`RuleClass.PATH_SCOPED` — a managed block in ``<dir>/AGENTS.md``,
  activated by Codex's root->cwd walk; the scoping directories come from
  the rule's ``paths:`` frontmatter field.
* :data:`RuleClass.DESCRIPTION_ONLY` — a synthetic Codex-only skill
  (``rule-<name>``); Codex skills are the description-triggered,
  progressive-disclosure analogue of a Claude rule.

This module only *classifies* — it reads the rule's frontmatter and
returns a :class:`RuleClass`. Writing ``AGENTS.md`` blocks (ai-10) and
wiring the render into commands (ai-11) live elsewhere.

Two optional rule-frontmatter fields drive the classification:

* ``paths:`` — a list of directory globs the rule is scoped to.
* ``always_on:`` — a boolean; ``true`` marks an always-loaded rule.

Both are explicit: always-on is *never* inferred from prose such as
"Always-loaded baseline" in the rule body — explicit beats heuristic.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from ai_dotfiles.core.errors import ElementError
from ai_dotfiles.core.frontmatter import parse_frontmatter

__all__ = ["RuleClass", "classify_rule"]


class RuleClass(Enum):
    """How a catalog rule activates for the Codex target.

    ``ALWAYS_ON`` — always loaded; goes into the root ``AGENTS.md``.
    ``PATH_SCOPED`` — conditional on the working directory; goes into a
    nested ``<dir>/AGENTS.md``.
    ``DESCRIPTION_ONLY`` — description-triggered; rendered as a
    Codex-only ``rule-<name>`` skill.
    """

    ALWAYS_ON = "always_on"
    PATH_SCOPED = "path_scoped"
    DESCRIPTION_ONLY = "description_only"


def _truthy(value: Any) -> bool:
    """Interpret a frontmatter scalar as a boolean.

    The frontmatter parser yields scalars as strings, so ``always_on:
    true`` arrives as the string ``"true"``. Accept the common truthy
    spellings; anything else (including a missing field) is ``False``.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return False


def classify_rule(md_path: Path) -> RuleClass:
    """Classify the rule markdown file at ``md_path`` into a :class:`RuleClass`.

    Classification, in priority order:

    1. A non-empty ``paths:`` list ⇒ :data:`RuleClass.PATH_SCOPED`. A
       rule scoped to directories is inherently conditional, so ``paths:``
       wins even when ``always_on: true`` is also present.
    2. Otherwise ``always_on: true`` ⇒ :data:`RuleClass.ALWAYS_ON`.
    3. Otherwise ⇒ :data:`RuleClass.DESCRIPTION_ONLY` (the default — a
       rule with neither field, which is every un-migrated catalog rule).

    Raises :class:`ElementError` if ``md_path`` does not exist or is not
    a file.
    """
    if not md_path.is_file():
        raise ElementError(f"Rule file not found: {md_path}")

    frontmatter = parse_frontmatter(md_path.read_text(encoding="utf-8"))

    paths = frontmatter.get("paths")
    if isinstance(paths, list) and len(paths) > 0:
        return RuleClass.PATH_SCOPED

    if _truthy(frontmatter.get("always_on")):
        return RuleClass.ALWAYS_ON

    return RuleClass.DESCRIPTION_ONLY
