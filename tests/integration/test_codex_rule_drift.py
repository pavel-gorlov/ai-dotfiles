"""Drift detection for a rule's managed ``AGENTS.md`` block.

Covers :func:`ai_dotfiles.core.agents_md.block_matches` (pure) and
:func:`ai_dotfiles.core.codex_install.rule_block_state` (filesystem) — the
``AGENTS.md`` analogue of ``is_stale`` for skills/agents. Before this,
``status`` reported a present-but-outdated rule block as OK; these lock in the
ok / stale / missing distinction.
"""

from pathlib import Path

import pytest

from ai_dotfiles.core import agents_md, codex_install

pytestmark = pytest.mark.integration


def _rule(tmp_path: Path, body: str = "# Rule\n\nOriginal content.") -> Path:
    md = tmp_path / "myrule.md"
    md.write_text(f"---\nalways_on: true\n---\n{body}\n", encoding="utf-8")
    return md


def test_block_matches_current_stale_and_absent(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents_md.upsert_rule_block(agents, "myrule", "the body")
    text = agents.read_text(encoding="utf-8")

    assert agents_md.block_matches("myrule", "the body", text) is True
    assert agents_md.block_matches("myrule", "a different body", text) is False
    assert agents_md.block_matches("absent-rule", "the body", text) is False


def test_rule_block_state_transitions(tmp_path: Path) -> None:
    rule_md = _rule(tmp_path)
    agents = tmp_path / "AGENTS.md"

    # Nothing installed yet.
    assert codex_install.rule_block_state(rule_md, agents) == "missing"

    # Install the managed block -> OK.
    codex_install.apply_codex_rule_blocks(rule_md, [agents])
    assert codex_install.rule_block_state(rule_md, agents) == "ok"

    # Edit the rule source -> the on-disk block is now stale.
    rule_md.write_text(
        "---\nalways_on: true\n---\n# Rule\n\nCHANGED content.\n", encoding="utf-8"
    )
    assert codex_install.rule_block_state(rule_md, agents) == "stale"

    # Re-apply regenerates the block -> OK again.
    codex_install.apply_codex_rule_blocks(rule_md, [agents])
    assert codex_install.rule_block_state(rule_md, agents) == "ok"


def test_rule_block_state_missing_for_unmanaged_file(tmp_path: Path) -> None:
    rule_md = _rule(tmp_path)
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# Hand-written AGENTS.md\n\nNo managed block here.\n")

    assert codex_install.rule_block_state(rule_md, agents) == "missing"


def test_rule_block_state_detects_block_among_user_text(tmp_path: Path) -> None:
    rule_md = _rule(tmp_path)
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# Project AGENTS.md\n\nUser-authored preamble.\n")

    codex_install.apply_codex_rule_blocks(rule_md, [agents])

    text = agents.read_text(encoding="utf-8")
    assert "User-authored preamble." in text  # user text preserved
    assert codex_install.rule_block_state(rule_md, agents) == "ok"
