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
        # Codex injects no project-root variable; it runs hooks from the
        # session root, so the path is left relative. Substituting a
        # guessed variable expanded to "" and the hook died with 127.
        "command": ".claude/hooks/x.sh",
        "timeout": 30,  # kept
        # "if" dropped — Codex has no per-handler guard
    }


def test_no_codex_project_dir_variable_is_ever_emitted() -> None:
    """Regression guard: the guessed variable broke every hook it touched."""
    codex, _ = codex_hooks.translate_hooks(_CLAUDE_HOOKS)
    rendered = json.dumps(codex)
    assert "CODEX_PROJECT_DIR" not in rendered
    assert "CLAUDE_PROJECT_DIR" not in rendered


def test_bare_project_dir_becomes_dot() -> None:
    codex, _ = codex_hooks.translate_hooks(
        {
            "PreToolUse": [
                {"hooks": [{"type": "command", "command": "ls $CLAUDE_PROJECT_DIR"}]}
            ]
        }
    )
    assert codex["PreToolUse"][0]["hooks"][0]["command"] == "ls ."


def test_handlers_differing_only_by_the_dropped_guard_collapse() -> None:
    """Two Claude handlers can translate to the same Codex command.

    The ``if`` guard is Claude-only and dropped; without de-duplication
    Codex would run the same script twice on every matching tool call.
    """
    codex, _ = codex_hooks.translate_hooks(
        {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/x.sh",
                            "if": "Bash(git *)",
                        },
                        {
                            "type": "command",
                            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/x.sh",
                            "if": "Bash(gh *)",
                        },
                    ],
                }
            ]
        }
    )
    assert len(codex["PreToolUse"][0]["hooks"]) == 1


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


def test_hooks_state_tracks_drift(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    frag = tmp_path / "dom" / "settings.fragment.json"
    _fragment(frag, _CLAUDE_HOOKS)
    pairs = [("dom", frag)]

    assert codex_hooks.hooks_state(root, pairs) == "missing"
    codex_hooks.write_codex_hooks(root, pairs)
    assert codex_hooks.hooks_state(root, pairs) == "ok"
    assert codex_hooks.hooks_state(root, []) == "stale"  # domain went away


def test_a_file_holding_the_old_broken_command_is_stale(tmp_path: Path) -> None:
    """The delivery path for the exit-127 fix.

    Projects generated before the fix hold ``$CODEX_PROJECT_DIR/...``, which
    expands to nothing and makes every hook fail. Their fragments never
    changed, so this must be caught by comparing the translated group — not
    the source — or ``reconcile`` would leave them broken.
    """
    root = tmp_path / "proj"
    (root / ".codex").mkdir(parents=True)
    frag = tmp_path / "dom" / "settings.fragment.json"
    _fragment(frag, _CLAUDE_HOOKS)
    pairs = [("dom", frag)]

    # Reproduce the pre-fix state faithfully — file *and* ownership sidecar
    # both recording the broken group, which is what an upgraded project has.
    # (A fragment whose command already names the dead variable translates
    # through verbatim, since there is no $CLAUDE_PROJECT_DIR to rewrite.)
    _fragment(
        frag,
        {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "$CODEX_PROJECT_DIR/.claude/hooks/x.sh",
                            "timeout": 30,
                        }
                    ],
                }
            ]
        },
    )
    codex_hooks.write_codex_hooks(root, pairs)
    path = codex_hooks.hooks_path(root)
    assert "CODEX_PROJECT_DIR" in path.read_text(encoding="utf-8")

    # The real fragment comes back; the recorded group no longer matches it.
    _fragment(frag, _CLAUDE_HOOKS)
    assert codex_hooks.hooks_state(root, pairs) == "stale"

    codex_hooks.write_codex_hooks(root, pairs)
    assert codex_hooks.hooks_state(root, pairs) == "ok"
    assert "CODEX_PROJECT_DIR" not in path.read_text(encoding="utf-8")


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
