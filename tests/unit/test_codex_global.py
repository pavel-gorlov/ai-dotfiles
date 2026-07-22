"""Unit tests for ai_dotfiles.core.codex_global (the instructions bridge)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_dotfiles.core import codex_global
from ai_dotfiles.core.agents_md import iter_rule_block_names
from ai_dotfiles.core.errors import ElementError

_CLAUDE_MD = "# Personal prefs\n\nAlways answer in Russian.\n"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _write_claude_md(home: Path, text: str = _CLAUDE_MD) -> Path:
    path = home / ".claude" / "CLAUDE.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_bridge_absent_without_source(home: Path, tmp_path: Path) -> None:
    agents_md = tmp_path / "codex" / "AGENTS.md"
    assert codex_global.bridge_state(agents_md) == "absent"
    assert codex_global.upsert_bridge(agents_md) == "absent"
    assert not agents_md.exists()


def test_upsert_bridge_writes_managed_block(home: Path, tmp_path: Path) -> None:
    _write_claude_md(home)
    agents_md = tmp_path / "codex" / "AGENTS.md"

    assert codex_global.bridge_state(agents_md) == "missing"
    assert codex_global.upsert_bridge(agents_md) == "written"

    text = agents_md.read_text(encoding="utf-8")
    assert codex_global.GLOBAL_INSTRUCTIONS_NAME in iter_rule_block_names(text)
    assert "Always answer in Russian." in text
    assert codex_global.bridge_state(agents_md) == "ok"
    # Idempotent — a second upsert is a no-op.
    assert codex_global.upsert_bridge(agents_md) == "unchanged"


def test_bridge_goes_stale_when_source_edited(home: Path, tmp_path: Path) -> None:
    source = _write_claude_md(home)
    agents_md = tmp_path / "codex" / "AGENTS.md"
    codex_global.upsert_bridge(agents_md)

    source.write_text(_CLAUDE_MD + "\nNew paragraph.\n", encoding="utf-8")

    assert codex_global.bridge_state(agents_md) == "stale"
    assert codex_global.upsert_bridge(agents_md) == "written"
    assert codex_global.bridge_state(agents_md) == "ok"


def test_upsert_bridge_preserves_user_text(home: Path, tmp_path: Path) -> None:
    _write_claude_md(home)
    agents_md = tmp_path / "codex" / "AGENTS.md"
    agents_md.parent.mkdir(parents=True)
    agents_md.write_text("My own global notes.\n", encoding="utf-8")

    codex_global.upsert_bridge(agents_md)

    text = agents_md.read_text(encoding="utf-8")
    assert "My own global notes." in text
    assert "Always answer in Russian." in text


def test_ensure_not_reserved_rejects_bridge_name(tmp_path: Path) -> None:
    rule = tmp_path / f"{codex_global.GLOBAL_INSTRUCTIONS_NAME}.md"
    rule.write_text("---\nalways_on: true\n---\n\nbody\n", encoding="utf-8")
    with pytest.raises(ElementError, match="reserved"):
        codex_global.ensure_not_reserved(rule)
    # Any other stem passes.
    codex_global.ensure_not_reserved(tmp_path / "python.md")
