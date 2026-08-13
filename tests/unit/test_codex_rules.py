"""Unit tests for ai_dotfiles.core.codex_rules.

The load-bearing property under test is the *narrowness* guarantee: a
Claude permission entry may only become a Codex ``prefix_rule`` when the
rule grants exactly what the entry granted. ``prefix_rule`` matches a
token prefix, so approximating an exact command would hand out
permissions the user never wrote down — that must never happen silently.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_dotfiles.core.codex_rules import (
    RULES_FILENAME,
    PrefixRule,
    SkippedPermission,
    render_rules,
    rules_path,
    rules_state,
    strip_codex_rules,
    translate_entry,
    translate_permissions,
    write_codex_rules,
)


def _write_fragment(directory: Path, name: str, data: dict[str, object]) -> Path:
    domain_dir = directory / name
    domain_dir.mkdir(parents=True, exist_ok=True)
    path = domain_dir / "settings.fragment.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ── translate_entry: what becomes a rule ──────────────────────────────


@pytest.mark.parametrize(
    ("entry", "pattern"),
    [
        ("Bash(tm:*)", ("tm",)),
        ("Bash(git fetch:*)", ("git", "fetch")),
        ("Bash(gh pr create:*)", ("gh", "pr", "create")),
        ("Bash(alembic *)", ("alembic",)),
        ("Bash(npx @elgato/cli *)", ("npx", "@elgato/cli")),
        # A colon inside a token is part of the command, not the marker.
        ("Bash(pnpm test:e2e:*)", ("pnpm", "test:e2e")),
    ],
)
def test_trailing_wildcard_becomes_a_prefix_rule(
    entry: str, pattern: tuple[str, ...]
) -> None:
    result = translate_entry(entry, "allow")
    assert isinstance(result, PrefixRule)
    assert result.pattern == pattern
    assert result.decision == "allow"
    assert result.source == entry


# ── translate_entry: what must NOT become a rule ──────────────────────


@pytest.mark.parametrize(
    ("entry", "expected_in_reason"),
    [
        # The widening case this whole module exists to prevent.
        ("Bash(pg_isready)", "exact command"),
        ("Bash(pnpm db:migrate)", "exact command"),
        # Dropping the quoting would turn "this one curl" into "any curl".
        ("Bash(curl -s -X POST http://h/x -d '{\"a\":1}')", "shell syntax"),
        ("Bash(sh -c 'rm -rf /')", "shell syntax"),
        ("Bash(git log | head)", "shell syntax"),
        # No token equivalent for a wildcard in the middle.
        ("Bash(npm run * --watch)", "wildcard inside"),
        # The exec policy governs commands, nothing else.
        ("Read(/etc/passwd)", "not Read()"),
        ("WebFetch(domain:example.com)", "not WebFetch()"),
        ("mcp__playwright__*", "not a Tool(argument) permission entry"),
        # Would match literally every command.
        ("Bash(*)", "matches every command"),
        ("Bash()", "empty command"),
    ],
)
def test_unrepresentable_entries_are_skipped(
    entry: str, expected_in_reason: str
) -> None:
    result = translate_entry(entry, "allow")
    assert isinstance(result, SkippedPermission)
    assert result.entry == entry
    assert expected_in_reason in result.reason


def test_exact_command_never_widens_into_a_prefix() -> None:
    """The security-critical invariant, stated directly.

    ``Bash(pg_isready)`` authorises that command alone. A rule of
    ``pattern = ["pg_isready"]`` would authorise ``pg_isready`` with any
    arguments — strictly more than the user granted.
    """
    rules, skipped = translate_permissions({"allow": ["Bash(pg_isready)"]})
    assert rules == []
    assert [s.entry for s in skipped] == ["Bash(pg_isready)"]


# ── decisions ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("list_name", "decision"),
    [("allow", "allow"), ("deny", "forbidden"), ("ask", "prompt")],
)
def test_each_claude_list_maps_to_its_codex_decision(
    list_name: str, decision: str
) -> None:
    rules, _ = translate_permissions({list_name: ["Bash(git push:*)"]})
    assert [r.decision for r in rules] == [decision]


# ── translate_permissions: dedup + ordering ───────────────────────────


def test_duplicate_entries_collapse_to_one_rule() -> None:
    rules, _ = translate_permissions(
        {"allow": ["Bash(git fetch:*)", "Bash(git fetch:*)", "Bash(git fetch *)"]}
    )
    assert len(rules) == 1


def test_rules_are_deterministically_ordered() -> None:
    first, _ = translate_permissions({"allow": ["Bash(z:*)", "Bash(a:*)"]})
    second, _ = translate_permissions({"allow": ["Bash(a:*)", "Bash(z:*)"]})
    assert [r.pattern for r in first] == [r.pattern for r in second]


def test_non_string_and_non_list_values_are_ignored() -> None:
    rules, skipped = translate_permissions(
        {"allow": ["Bash(ls:*)", 42], "deny": "nope"}
    )
    assert [r.pattern for r in rules] == [("ls",)]
    assert skipped == []


# ── render_rules ──────────────────────────────────────────────────────


def test_render_emits_starlark_prefix_rule() -> None:
    text = render_rules([PrefixRule(("git", "fetch"), "allow", "Bash(git fetch:*)")])
    assert "# managed-by: ai-dotfiles" in text
    assert 'pattern = ["git", "fetch"],' in text
    assert 'decision = "allow",' in text
    # Codex echoes the justification when it blocks a command, so the
    # originating entry has to survive into the file.
    assert 'justification = "ai-dotfiles: Bash(git fetch:*)",' in text


def test_render_of_nothing_is_empty() -> None:
    assert render_rules([]) == ""


# ── write / state / strip ─────────────────────────────────────────────


def test_write_creates_updates_and_removes(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    codex_dir = tmp_path / ".codex"
    fragment = _write_fragment(
        catalog, "gitflow", {"permissions": {"allow": ["Bash(git push:*)"]}}
    )
    pairs = [("gitflow", fragment)]

    status, skipped = write_codex_rules(codex_dir, pairs)
    assert status == "created"
    assert skipped == []
    assert 'pattern = ["git", "push"],' in rules_path(codex_dir).read_text()

    assert write_codex_rules(codex_dir, pairs)[0] == "unchanged"

    fragment.write_text(
        json.dumps({"permissions": {"allow": ["Bash(git pull:*)"]}}), encoding="utf-8"
    )
    assert write_codex_rules(codex_dir, pairs)[0] == "updated"

    # No domains left -> the file goes away rather than lingering empty.
    assert write_codex_rules(codex_dir, [])[0] == "removed"
    assert not rules_path(codex_dir).exists()


def test_state_tracks_permission_drift(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    codex_dir = tmp_path / ".codex"
    fragment = _write_fragment(
        catalog, "gitflow", {"permissions": {"allow": ["Bash(git push:*)"]}}
    )
    pairs = [("gitflow", fragment)]

    assert rules_state(codex_dir, pairs) == "missing"
    write_codex_rules(codex_dir, pairs)
    assert rules_state(codex_dir, pairs) == "ok"

    fragment.write_text(
        json.dumps({"permissions": {"allow": ["Bash(git push:*)", "Bash(gh pr:*)"]}}),
        encoding="utf-8",
    )
    assert rules_state(codex_dir, pairs) == "stale"

    write_codex_rules(codex_dir, pairs)
    assert rules_state(codex_dir, pairs) == "ok"


def test_state_absent_when_no_permissions_anywhere(tmp_path: Path) -> None:
    assert rules_state(tmp_path / ".codex", []) == "absent"


def test_hand_edit_counts_as_drift(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    codex_dir = tmp_path / ".codex"
    fragment = _write_fragment(
        catalog, "gitflow", {"permissions": {"allow": ["Bash(git push:*)"]}}
    )
    pairs = [("gitflow", fragment)]
    write_codex_rules(codex_dir, pairs)

    path = rules_path(codex_dir)
    path.write_text(path.read_text() + '\nprefix_rule(pattern = ["rm"])\n')
    assert rules_state(codex_dir, pairs) == "stale"


def test_strip_leaves_codex_own_rules_file_alone(tmp_path: Path) -> None:
    """``default.rules`` is Codex's — it records the user's TUI approvals."""
    catalog = tmp_path / "catalog"
    codex_dir = tmp_path / ".codex"
    fragment = _write_fragment(
        catalog, "gitflow", {"permissions": {"allow": ["Bash(git push:*)"]}}
    )
    write_codex_rules(codex_dir, [("gitflow", fragment)])

    default = rules_path(codex_dir).parent / "default.rules"
    default.write_text('prefix_rule(pattern = ["ls"], decision = "allow")\n')

    assert strip_codex_rules(codex_dir) is True
    assert not rules_path(codex_dir).exists()
    assert default.is_file()

    # Nothing of ours left to remove.
    assert strip_codex_rules(codex_dir) is False


def test_strip_removes_the_directory_when_it_empties(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    codex_dir = tmp_path / ".codex"
    fragment = _write_fragment(
        catalog, "gitflow", {"permissions": {"allow": ["Bash(git push:*)"]}}
    )
    write_codex_rules(codex_dir, [("gitflow", fragment)])
    rules_dir = rules_path(codex_dir).parent

    assert strip_codex_rules(codex_dir) is True
    assert not rules_dir.exists()


def test_skipped_entries_reach_the_caller(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog"
    codex_dir = tmp_path / ".codex"
    fragment = _write_fragment(
        catalog,
        "postgres",
        {"permissions": {"allow": ["Bash(psql:*)", "Bash(pg_isready)"]}},
    )
    _, skipped = write_codex_rules(codex_dir, [("postgres", fragment)])
    assert [s.entry for s in skipped] == ["Bash(pg_isready)"]
    assert RULES_FILENAME in str(rules_path(codex_dir))
