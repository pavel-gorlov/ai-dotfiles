"""Emit domain hooks to Codex ``.codex/hooks.json`` (translate/write/strip)."""

import json
from pathlib import Path

import pytest

from ai_dotfiles.core import codex_hooks

pytestmark = pytest.mark.integration

_CLAUDE_HOOKS = {
    "PreToolUse": [
        {
            "matcher": "Bash",
            "hooks": [
                {
                    "type": "command",
                    "if": "Bash(git *)",
                    "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/x.sh",
                    "timeout": 30,
                }
            ],
        }
    ],
    "Notification": [{"hooks": [{"type": "command", "command": "y"}]}],
}


def _fragment(path: Path, hooks: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"hooks": hooks}), encoding="utf-8")


def test_translate_drops_if_rewrites_var_keeps_matcher_and_timeout() -> None:
    codex, skipped = codex_hooks.translate_hooks(_CLAUDE_HOOKS)

    assert skipped == ["Notification"]  # no Codex twin
    group = codex["PreToolUse"][0]
    assert group["matcher"] == "Bash"
    assert group["hooks"][0] == {
        "type": "command",
        "command": "$CODEX_PROJECT_DIR/.claude/hooks/x.sh",  # var rewritten
        "timeout": 30,  # kept
        # "if" dropped — Codex has no per-handler guard
    }


def test_write_creates_reports_skips_and_strips(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    frag = tmp_path / "dom" / "settings.fragment.json"
    _fragment(frag, _CLAUDE_HOOKS)

    result = codex_hooks.write_codex_hooks(root, [("dom", frag)])
    assert result.status == "created"
    assert result.skipped_events == {"dom": ["Notification"]}

    data = json.loads(codex_hooks.hooks_path(root).read_text(encoding="utf-8"))
    assert "PreToolUse" in data["hooks"]
    assert "Notification" not in data["hooks"]

    assert codex_hooks.strip_codex_hooks(root) is True
    assert not codex_hooks.hooks_path(root).is_file()


def test_write_preserves_user_authored_hooks(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / ".codex").mkdir(parents=True)
    codex_hooks.hooks_path(root).write_text(
        json.dumps(
            {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "user"}]}]}}
        ),
        encoding="utf-8",
    )
    frag = tmp_path / "dom" / "settings.fragment.json"
    _fragment(
        frag,
        {"PreToolUse": [{"hooks": [{"type": "command", "command": "domain"}]}]},
    )

    codex_hooks.write_codex_hooks(root, [("dom", frag)])
    data = json.loads(codex_hooks.hooks_path(root).read_text(encoding="utf-8"))
    assert data["hooks"]["Stop"][0]["hooks"][0]["command"] == "user"
    assert "PreToolUse" in data["hooks"]

    # Strip removes only the domain groups; the user's survive.
    codex_hooks.strip_codex_hooks(root)
    after = json.loads(codex_hooks.hooks_path(root).read_text(encoding="utf-8"))
    assert "Stop" in after["hooks"]
    assert "PreToolUse" not in after["hooks"]
