"""Real Claude MCP rebuilds prove only their generated allowlist contributions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from ai_dotfiles.cli import cli
from ai_dotfiles.core import mcp_apply
from ai_dotfiles.core.dsh_layout import project_layout
from ai_dotfiles.core.dsh_migrate import DshLocalSource, migrate_project_to_dsh
from ai_dotfiles.core.settings_ownership import ownership_path
from tests.integration.test_dsh_reconcile import _snapshot


def _json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def _invoke(*args: str, exit_code: int = 0) -> Result:
    result = CliRunner().invoke(cli, list(args))
    assert result.exit_code == exit_code, (result.output, result.exception)
    return result


def _settings_source(project: Path) -> DshLocalSource:
    report = migrate_project_to_dsh(
        project,
        ["@example"],
        project.parent / "storage/catalog",
        ["claude", "dsh"],
        dry_run=True,
    )
    return next(
        source
        for source in report.plan.inputs.raw_sources
        if source.path.name == "settings.json"
    )


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("DSH_HOME", str(home / "dsh"))
    monkeypatch.setenv("CODEX_HOME", str(home / "codex"))
    monkeypatch.setenv("AI_DOTFILES_HOME", str(tmp_path / "storage"))
    (tmp_path / "storage/global").mkdir(parents=True)
    domain = tmp_path / "storage/catalog/example"
    _json(domain / "domain.json", {"name": "example", "description": "MCP fixture"})
    _json(
        domain / "mcp.fragment.json",
        {"mcpServers": {"catalog": {"command": "fixture-catalog-mcp"}}},
    )
    root = tmp_path / "project"
    (root / ".git").mkdir(parents=True)
    _json(root / "ai-dotfiles.json", {"packages": [], "targets": ["claude", "dsh"]})
    monkeypatch.chdir(root)
    return root


@pytest.mark.integration
@pytest.mark.parametrize("initial_command", ["add", "install"])
@pytest.mark.parametrize("user_names", [[], ["user", "catalog"]])
def test_real_mcp_rebuild_migrates_once_and_keeps_user_residual_stable(
    project: Path, initial_command: str, user_names: list[str]
) -> None:
    if user_names:
        _json(project / ".claude/settings.json", {"enabledMcpjsonServers": user_names})
        _json(project / ".mcp.json", {"mcpServers": {"user": {"command": "user-mcp"}}})
    if initial_command == "install":
        _json(
            project / "ai-dotfiles.json",
            {"packages": ["@example"], "targets": ["claude", "dsh"]},
        )
    _invoke(initial_command, *(("@example",) if initial_command == "add" else ()))
    ledger = json.loads(ownership_path(project / ".claude").read_bytes())
    proof = ledger["enabled_mcpjson_servers"]
    assert proof["generated"] == ([] if "catalog" in user_names else ["catalog"])
    original = (project / ".claude/settings.json").read_bytes()
    before = _snapshot(project)
    dry = _invoke("migrate", "--to", "dsh", "--dry-run")
    assert "LOCAL_ORIGINAL_UNPROVEN" not in dry.output
    assert _snapshot(project) == before
    source = _settings_source(project)
    assert source.value.get("enabledMcpjsonServers", []) == user_names
    _invoke("migrate", "--to", "dsh")
    layout = project_layout(project)
    stable = _snapshot(layout.dsh_dir)
    config = json.loads(layout.config_path.read_bytes())
    names = [row["name"] for row in config["contributions"]]
    assert names.count("mcp:catalog") == 1
    assert names.count("mcp:user") == bool(user_names)
    for command in (
        ("install",),
        ("install",),
        ("reconcile", "--check"),
        ("reconcile",),
    ):
        _invoke(*command)
        assert _snapshot(layout.dsh_dir) == stable
        assert (project / ".claude/settings.json").read_bytes() == original
    _invoke("remove", "@example")
    settings = project / ".claude/settings.json"
    residual = json.loads(settings.read_bytes()) if settings.exists() else {}
    assert residual.get("enabledMcpjsonServers", []) == user_names


@pytest.mark.integration
@pytest.mark.parametrize("proof_state", ["legacy", "edited-list"])
def test_unproven_allowlist_refuses_without_writes_until_a_real_rebuild(
    project: Path, proof_state: str
) -> None:
    _invoke("add", "@example")
    ledger_path = ownership_path(project / ".claude")
    if proof_state == "legacy":
        ledger = json.loads(ledger_path.read_bytes())
        ledger.pop("enabled_mcpjson_servers")
        _json(ledger_path, ledger)
    else:
        settings_path = project / ".claude/settings.json"
        settings = json.loads(settings_path.read_bytes())
        settings["enabledMcpjsonServers"].append("new-user")
        _json(settings_path, settings)
    before = _snapshot(project)
    dry = _invoke("migrate", "--to", "dsh", "--dry-run")
    assert "LOCAL_ORIGINAL_UNPROVEN" in dry.output
    assert "enabledMcpjsonServers" in dry.output
    _invoke("migrate", "--to", "dsh", exit_code=1)
    assert _snapshot(project) == before
    _invoke("install")
    _invoke("migrate", "--to", "dsh")
    _invoke("reconcile", "--check")
    source = _settings_source(project)
    assert source.value.get("enabledMcpjsonServers", []) == (
        ["new-user"] if proof_state == "edited-list" else []
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "invalid",
    [None, [], {}, {"generated": [42], "value_sha256": "0" * 64}],
)
def test_malformed_mcp_proof_is_never_repaired_by_writing_over_it(
    project: Path, invalid: object
) -> None:
    _invoke("add", "@example")
    _invoke("migrate", "--to", "dsh")
    ledger_path = ownership_path(project / ".claude")
    ledger = json.loads(ledger_path.read_bytes())
    ledger["enabled_mcpjson_servers"] = invalid
    _json(ledger_path, ledger)
    before = _snapshot(project)
    for command in (("migrate", "--to", "dsh"), ("install",), ("reconcile",)):
        result = _invoke(*command, exit_code=1)
        assert "enabled_mcpjson_servers" in result.output
        assert _snapshot(project) == before


@pytest.mark.integration
@pytest.mark.parametrize("other_field", ["env", "enableAllProjectMcpServers"])
def test_generated_mcp_proof_cannot_prove_other_aggregate_fields(
    project: Path, other_field: str
) -> None:
    _invoke("add", "@example")
    settings_path = project / ".claude/settings.json"
    settings = json.loads(settings_path.read_bytes())
    settings[other_field] = {"UNPROVEN": "value"} if other_field == "env" else True
    _json(settings_path, settings)
    before = _snapshot(project)
    dry = _invoke("migrate", "--to", "dsh", "--dry-run")
    assert "LOCAL_ORIGINAL_UNPROVEN" in dry.output
    assert other_field in dry.output
    _invoke("migrate", "--to", "dsh", exit_code=1)
    assert _snapshot(project) == before


@pytest.mark.integration
def test_failed_remove_keeps_user_overlap_proof_for_install_recovery(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _json(project / ".claude/settings.json", {"enabledMcpjsonServers": ["catalog"]})
    _invoke("add", "@example")
    _invoke("migrate", "--to", "dsh")

    def fail_backup(path: Path, backup_root: Path, project_name: str) -> Path:
        raise OSError("simulated MCP failure")

    with monkeypatch.context() as patch:
        patch.setattr(mcp_apply, "backup_mcp_json", fail_backup)
        _invoke("remove", "@example", exit_code=1)

    ledger_path = ownership_path(project / ".claude")
    ledger = json.loads(ledger_path.read_bytes())
    assert ledger["enabled_mcpjson_servers"]["generated"] == []
    assert json.loads((project / ".mcp.json").read_bytes())["mcpServers"]
    _invoke("install")
    assert json.loads((project / ".claude/settings.json").read_bytes()) == {
        "enabledMcpjsonServers": ["catalog"]
    }
    assert not (project / ".mcp.json").exists()
    _invoke("migrate", "--to", "dsh")
    _invoke("reconcile", "--check")
