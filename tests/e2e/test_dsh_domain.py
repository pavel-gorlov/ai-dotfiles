"""Domain member edits refresh selected targets and retain reversible custody."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from ai_dotfiles.cli import cli
from ai_dotfiles.core import agents_md
from ai_dotfiles.core.codex_local_registry import save_local_registry
from ai_dotfiles.core.dsh_install import read_dsh_inventory
from ai_dotfiles.core.dsh_layout import DshLayout, global_layout, project_layout
from ai_dotfiles.core.dsh_migrate import stage_catalog_source_removal
from tests.e2e.test_dsh_install import (
    _domain,
    _json,
    _manifest,
    _project,
    _write,
    isolated_homes,
)
from tests.integration.test_dsh_reconcile import _snapshot

__all__ = ["isolated_homes"]


def _invoke(*args: str, exit_code: int = 0) -> Result:
    result = CliRunner().invoke(cli, list(args))
    assert result.exit_code == exit_code, (result.output, result.exception)
    return result


def _scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scope: str,
    targets: list[str],
    *,
    mode: str = "symlink",
) -> tuple[Path, DshLayout, tuple[str, ...]]:
    root = _project(tmp_path, monkeypatch)
    if scope == "global":
        _json(
            tmp_path / "storage/global.json",
            {"packages": ["@alpha"], "targets": targets},
        )
        return root, global_layout(), ("-g",)
    _manifest(root, ["@alpha"], targets, mode)
    return root, project_layout(root), ()


@pytest.mark.parametrize("scope", ["project", "global"])
@pytest.mark.parametrize(
    "targets",
    [["dsh"], ["claude", "dsh"], ["codex", "dsh"], ["claude", "codex", "dsh"]],
)
@pytest.mark.parametrize("kind", ["skill", "agent", "rule"])
def test_member_add_remove_selected_scopes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scope: str,
    targets: list[str],
    kind: str,
) -> None:
    catalog = tmp_path / "storage/catalog"
    _domain(catalog, "alpha")
    root, layout, args = _scope(tmp_path, monkeypatch, scope, targets)
    profile = _write(layout.dsh_dir / "profiles/user/cordis.yml", "User profile\n")
    foreign = _write(layout.skills_dir / "foreign/SKILL.md", "User skill\n")
    _write(layout.root_agents_md, "User instructions  \r\n")
    _invoke("install", *args)
    original = (catalog / "alpha/agents/alpha-agent.md").read_bytes()
    _invoke("domain", "add", "alpha", kind, "added")
    sub = Path(f"{kind}s") / ("added" if kind == "skill" else "added.md")
    source = catalog / "alpha" / sub
    instruction = source / "SKILL.md" if kind == "skill" else source
    records = read_dsh_inventory(layout).source_records.values()
    assert any(item["provenance"]["source"] == str(instruction) for item in records)
    copied = layout.resources_dir / "domains/alpha" / sub
    assert copied.exists()
    assert (
        copied / "SKILL.md" if kind == "skill" else copied
    ).read_bytes() == instruction.read_bytes()
    assert json.loads(layout.config_path.read_bytes())["environment"] == {
        "ALPHA": "alpha"
    }
    assert "mcp:alpha" in {
        item["name"]
        for item in json.loads(layout.config_path.read_bytes())["contributions"]
    }
    if kind == "skill":
        assert (layout.skills_dir / "added").is_symlink()
    _invoke("domain", "remove", "alpha", kind, "added")
    assert not source.exists()
    assert not copied.exists()
    assert all(
        item["provenance"]["source"] != str(instruction)
        for item in read_dsh_inventory(layout).source_records.values()
    )
    assert (layout.skills_dir / "alpha/SKILL.md").is_file()
    assert (catalog / "alpha/agents/alpha-agent.md").read_bytes() == original
    assert profile.read_bytes() == b"User profile\n"
    assert foreign.read_bytes() == b"User skill\n"
    if "claude" not in targets:
        assert not (root / ".claude").exists()
        assert not (tmp_path / "home/.claude").exists()
    if "codex" not in targets:
        assert not (root / ".codex").exists()
        assert not (tmp_path / "home/codex").exists()
    assert not list((tmp_path / "storage").glob("ai-dotfiles-retire-*"))


@pytest.mark.parametrize("scope", ["project", "global"])
@pytest.mark.parametrize(
    "targets", [["codex"], ["codex", "dsh"], ["claude", "codex", "dsh"]]
)
def test_saved_classification_retires_shared_rule_after_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: str, targets: list[str]
) -> None:
    catalog = tmp_path / "storage/catalog"
    _domain(catalog, "alpha")
    root, layout, args = _scope(tmp_path, monkeypatch, scope, targets)
    instructions = (
        root / "AGENTS.md" if scope == "project" else tmp_path / "home/codex/AGENTS.md"
    )
    _write(instructions, "User instructions  \r\n")
    _invoke("install", *args)
    assert "alpha-rule" in agents_md.iter_rule_block_names(instructions.read_text())
    _invoke("domain", "remove", "alpha", "rule", "alpha-rule")
    assert instructions.read_bytes() == b"User instructions  \r\n"
    if "dsh" in targets:
        assert not read_dsh_inventory(layout).rule_blocks


def test_fresh_local_union_keeps_shared_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = tmp_path / "storage/catalog"
    _domain(catalog, "alpha")
    root, _, _ = _scope(tmp_path, monkeypatch, "project", ["codex", "dsh"])
    _invoke("install")
    local = _write(
        root / ".claude/rules/alpha-rule.md", "---\nalways_on: true\n---\nBody\n"
    )
    save_local_registry(
        root, {"skills": {}, "agents": {}, "rule_blocks": {"AGENTS.md": ["alpha-rule"]}}
    )
    _invoke("domain", "remove", "alpha", "rule", "alpha-rule")
    assert local.read_bytes() == b"---\nalways_on: true\n---\nBody\n"
    assert "alpha-rule" in agents_md.iter_rule_block_names(
        (root / "AGENTS.md").read_text()
    )


@pytest.mark.parametrize("conflict", ["shared", "resource"])
@pytest.mark.parametrize("kind", ["rule", "skill"])
def test_later_scope_retirement_refusal_restores_source_before_any_target_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, conflict: str, kind: str
) -> None:
    catalog = tmp_path / "storage/catalog"
    _domain(catalog, "alpha")
    root, layout, _ = _scope(
        tmp_path, monkeypatch, "project", ["claude", "codex", "dsh"]
    )
    _json(
        tmp_path / "storage/global.json",
        {"packages": ["@alpha"], "targets": ["claude", "codex", "dsh"]},
    )
    _invoke("install", "-g")
    _invoke("install")
    source = catalog / (
        "alpha/rules/alpha-rule.md" if kind == "rule" else "alpha/skills/alpha"
    )
    original = (
        source.read_bytes() if source.is_file() else _snapshot(source),
        source.stat().st_mode,
        source.stat().st_mtime_ns,
    )
    if conflict == "shared":
        _write(
            root / "AGENTS.md",
            (root / "AGENTS.md").read_text().replace("Body", "Edited user body"),
        )
    else:
        _write(
            layout.resources_dir / "domains/alpha/fake.mjs", "Edited user resource\n"
        )
    project_before = _snapshot(root)
    global_before = _snapshot(tmp_path / "home")
    result = _invoke(
        "domain",
        "remove",
        "alpha",
        kind,
        "alpha-rule" if kind == "rule" else "alpha",
        exit_code=1,
    )
    assert "Foreign/modified" in result.output
    assert (
        source.read_bytes() if source.is_file() else _snapshot(source),
        source.stat().st_mode,
        source.stat().st_mtime_ns,
    ) == original
    assert _snapshot(root) == project_before
    assert _snapshot(tmp_path / "home") == global_before
    assert not list((tmp_path / "storage").glob("ai-dotfiles-retire-*"))


def test_later_scope_add_collision_keeps_all_targets_and_removes_new_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = tmp_path / "storage/catalog"
    _domain(catalog, "alpha")
    root, layout, _ = _scope(
        tmp_path, monkeypatch, "project", ["claude", "codex", "dsh"]
    )
    _json(
        tmp_path / "storage/global.json", {"packages": ["@alpha"], "targets": ["dsh"]}
    )
    _invoke("install", "-g")
    _invoke("install")
    foreign = _write(layout.skills_dir / "added/SKILL.md", "User original\n")
    project_before, global_before = _snapshot(root), _snapshot(tmp_path / "home")
    _invoke("domain", "add", "alpha", "skill", "added", exit_code=1)
    assert not (catalog / "alpha/skills/added").exists()
    assert foreign.read_bytes() == b"User original\n"
    assert _snapshot(root) == project_before
    assert _snapshot(tmp_path / "home") == global_before


def test_second_domain_dependency_order_native_rows_hooks_resources_and_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = tmp_path / "storage/catalog"
    for name in ("alpha", "beta"):
        _domain(catalog, name)
        _write(catalog / name / "native.mjs", "export function apply() {}\n")
        _json(
            catalog / name / "dsh.fragment.json",
            [
                {
                    "insert": [
                        {"id": f"native-{name}", "name": "./native.mjs", "config": {}}
                    ]
                }
            ],
        )
    _json(catalog / "beta/domain.json", {"depends": ["@alpha"]})
    hook = _write(catalog / "alpha/hooks/after.sh", "#!/bin/sh\nexit 0\n")
    _json(
        catalog / "alpha/settings.fragment.json",
        {
            "env": {"ALPHA": "alpha"},
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": str(hook)}],
                    }
                ]
            },
        },
    )
    root, layout, _ = _scope(tmp_path, monkeypatch, "project", ["dsh"], mode="copy")
    _manifest(root, ["@beta", "@alpha"], ["dsh"], "copy")
    _write(root / "AGENTS.md", "User instructions\n")
    user = _write(layout.dsh_dir / "cordis.yml", "User native root\n")
    bin_source = _write(catalog / "beta/bin/native-check", "#!/bin/sh\nexit 0\n")
    bin_source.chmod(0o755)
    _invoke("domain", "add", "beta", "skill", "added")
    snapshot = json.loads(layout.config_path.read_bytes())
    assert [part["insert"][0]["id"] for part in snapshot["domainPatches"]] == [
        "native-alpha",
        "native-beta",
    ]
    assert {"mcp:alpha", "mcp:beta"} <= {
        part["name"] for part in snapshot["contributions"]
    }
    assert layout.hooks_path.is_file()
    assert (
        layout.resources_dir / "domains/alpha/hooks/after.sh"
    ).read_bytes() == hook.read_bytes()
    assert (tmp_path / "storage/bin/native-check").is_file()
    _invoke("domain", "remove", "beta", "agent", "beta-agent")
    rows = json.loads(layout.config_path.read_bytes())["rows"]
    assert "ai-dotfiles-agent-beta-agent" not in {row["id"] for row in rows}
    assert "ai-dotfiles-agent-alpha-agent" in {row["id"] for row in rows}
    assert (layout.skills_dir / "alpha/SKILL.md").is_file()
    assert user.read_bytes() == b"User native root\n"
    assert not (root / ".claude").exists()
    _invoke("domain", "remove", "beta", "skill", "added")
    assert not (layout.resources_dir / "domains/beta/skills/added").exists()
    assert (layout.resources_dir / "domains/alpha/native.mjs").is_file()


@pytest.mark.parametrize("scope", ["project", "global"])
def test_removed_original_fragments_retire_rows_hooks_and_resources_keep_other_domain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scope: str
) -> None:
    catalog = tmp_path / "storage/catalog"
    for name in ("alpha", "beta"):
        _domain(catalog, name)
    hook = _write(catalog / "alpha/hooks/after.sh", "#!/bin/sh\nexit 0\n")
    _json(
        catalog / "alpha/settings.fragment.json",
        {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": str(hook)}],
                    }
                ]
            }
        },
    )
    fragment = _json(
        catalog / "alpha/dsh.fragment.json",
        [{"insert": [{"id": "native-alpha", "name": "./native.mjs", "config": {}}]}],
    )
    module = _write(catalog / "alpha/native.mjs", "export function apply() {}\n")
    root, layout, args = _scope(tmp_path, monkeypatch, scope, ["dsh"])
    _invoke("install", *args)
    _invoke("add", *args, "@beta")
    assert layout.hooks_path.is_file()
    assert json.loads(layout.config_path.read_bytes())["domainPatches"]
    for path in (
        fragment,
        module,
        hook,
        catalog / "alpha/settings.fragment.json",
        catalog / "alpha/mcp.fragment.json",
    ):
        path.unlink()
    _invoke("domain", "remove", "alpha", "agent", "alpha-agent")
    snapshot = json.loads(layout.config_path.read_bytes())
    assert snapshot["domainPatches"] == []
    assert {item["name"] for item in snapshot["contributions"]} == {"mcp:beta"}
    assert snapshot["environment"] == {"BETA": "beta"}
    assert "ai-dotfiles-agent-alpha-agent" not in {
        row["id"] for row in snapshot["rows"]
    }
    assert "ai-dotfiles-agent-beta-agent" in {row["id"] for row in snapshot["rows"]}
    hooks = json.loads(layout.hooks_path.read_bytes())
    assert hooks["hooks"] == {}
    assert all(item["origin"] != "@alpha" for item in hooks["aiDotfiles"]["sources"])
    assert not (layout.resources_dir / "domains/alpha/native.mjs").exists()
    assert (layout.resources_dir / "domains/beta/fake.mjs").is_file()
    assert not (root / ".claude").exists()


def test_source_staging_is_outside_catalog_and_restores_exact_original(
    tmp_path: Path,
) -> None:
    catalog = tmp_path / "catalog"
    source = _write(catalog / "alpha/rules/source.md", "Original\n")
    before = source.stat()
    with (
        pytest.raises(RuntimeError, match="refused"),
        stage_catalog_source_removal(source, catalog) as staged,
    ):
        assert not source.exists()
        assert not staged.is_relative_to(catalog)
        assert staged.read_bytes() == b"Original\n"
        raise RuntimeError("refused")
    assert source.read_bytes() == b"Original\n"
    assert source.stat().st_mode == before.st_mode
    assert source.stat().st_mtime_ns == before.st_mtime_ns
    assert not list(tmp_path.glob("ai-dotfiles-retire-*"))
