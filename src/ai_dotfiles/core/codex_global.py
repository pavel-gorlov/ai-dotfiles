"""Global (user-scope) Codex helpers: the instructions bridge.

The global Claude instructions file (``~/.claude/CLAUDE.md``) has no
Codex twin — Codex reads ``$CODEX_HOME/AGENTS.md`` as its global
instructions. This module bridges the former into the latter as a
managed block named :data:`GLOBAL_INSTRUCTIONS_NAME`, reusing the
rule-block machinery of :mod:`ai_dotfiles.core.agents_md`:

* the block's embedded ``sha256`` marker line gives drift detection
  (``status -g`` reports STALE when the user edits ``CLAUDE.md``);
* user-authored paragraphs around the block — and catalog rule blocks
  sharing the same file — are preserved by the marker discipline.

A symlink bridge was rejected at planning: it would monopolise the file
(no rule blocks) and clobber a user-authored global ``AGENTS.md``.

Because the bridge shares the rule-block marker namespace, its name is
**reserved**: a catalog rule with the same stem would collide with the
bridge on prune/strip — :func:`ensure_not_reserved` guards the global
install/add paths against that.
"""

from __future__ import annotations

from pathlib import Path

from ai_dotfiles.core import agents_md, paths
from ai_dotfiles.core.errors import ElementError

__all__ = [
    "GLOBAL_INSTRUCTIONS_NAME",
    "bridge_source",
    "bridge_state",
    "ensure_not_reserved",
    "upsert_bridge",
]

# The managed-block name of the global instructions bridge. Reserved —
# see :func:`ensure_not_reserved`.
GLOBAL_INSTRUCTIONS_NAME = "claude-global-instructions"


def bridge_source() -> Path:
    """Return the bridge's source file (``~/.claude/CLAUDE.md``)."""
    return paths.claude_global_dir() / "CLAUDE.md"


def bridge_state(agents_md_path: Path) -> str:
    """Return the drift state of the instructions bridge block.

    One of:

    * ``"absent"``  — there is no ``~/.claude/CLAUDE.md`` to bridge
      (nothing expected, nothing to report);
    * ``"missing"`` — the source exists but ``agents_md_path`` holds no
      bridge block (never installed, or stripped);
    * ``"stale"``   — a block exists but its recorded sha no longer
      matches the current ``CLAUDE.md`` content;
    * ``"ok"``      — the block matches the current source.
    """
    source = bridge_source()
    if not source.is_file():
        return "absent"
    if not agents_md_path.is_file():
        return "missing"
    try:
        text = agents_md_path.read_text(encoding="utf-8")
    except OSError:
        return "missing"
    if GLOBAL_INSTRUCTIONS_NAME not in agents_md.iter_rule_block_names(text):
        return "missing"
    body = source.read_text(encoding="utf-8")
    if agents_md.block_matches(GLOBAL_INSTRUCTIONS_NAME, body, text):
        return "ok"
    return "stale"


def upsert_bridge(agents_md_path: Path) -> str:
    """Bridge ``~/.claude/CLAUDE.md`` into ``agents_md_path`` idempotently.

    Returns ``"absent"`` when there is no source ``CLAUDE.md``,
    ``"unchanged"`` when the block is already current, ``"written"``
    when the block was created or refreshed.
    """
    source = bridge_source()
    if not source.is_file():
        return "absent"
    body = source.read_text(encoding="utf-8")
    if agents_md.upsert_rule_block(agents_md_path, GLOBAL_INSTRUCTIONS_NAME, body):
        return "written"
    return "unchanged"


def ensure_not_reserved(rule_md: Path) -> None:
    """Raise :class:`ElementError` if ``rule_md`` claims the bridge's name.

    Called on the global install/add paths before a rule's managed block
    is written: a catalog rule whose stem equals
    :data:`GLOBAL_INSTRUCTIONS_NAME` would be indistinguishable from the
    bridge block in ``$CODEX_HOME/AGENTS.md``.
    """
    if rule_md.stem == GLOBAL_INSTRUCTIONS_NAME:
        raise ElementError(
            f"rule name {GLOBAL_INSTRUCTIONS_NAME!r} is reserved for the "
            "global instructions bridge in $CODEX_HOME/AGENTS.md"
        )
