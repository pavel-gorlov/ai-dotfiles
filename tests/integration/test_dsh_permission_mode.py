"""Per-original-scope acknowledgement, source custody and manifest revocation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ai_dotfiles.core import manifest
from ai_dotfiles.core.dsh_config import (
    DshConfigSource,
    attach_dsh_config_outputs,
    collect_dsh_configuration,
    compose_dsh_configuration,
)
from ai_dotfiles.core.dsh_install import apply_dsh_install, plan_dsh_install
from ai_dotfiles.core.dsh_layout import project_layout
from ai_dotfiles.core.errors import ConfigError

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("name", ["ai-dotfiles.json", "global.json"])
@pytest.mark.parametrize("value", [None, True, 1, [], {}, "", "auto", "Native"])
def test_manifest_mode_rejects_every_malformed_choice(
    tmp_path: Path, name: str, value: object
) -> None:
    path = tmp_path / name
    manifest.write_manifest(path, {"dsh_permission_mode": value})
    with pytest.raises(ConfigError, match="dsh_permission_mode"):
        manifest.get_dsh_permission_mode(path)


@pytest.mark.parametrize("name", ["ai-dotfiles.json", "global.json"])
def test_manifest_mode_missing_defaults_and_explicit_choices(
    tmp_path: Path, name: str
) -> None:
    path = tmp_path / name
    assert manifest.get_dsh_permission_mode(path) == "strict"
    manifest.write_manifest(path, {})
    assert manifest.get_dsh_permission_mode(path) == "strict"
    for mode in ("strict", "native"):
        manifest.write_manifest(path, {"dsh_permission_mode": mode})
        assert manifest.get_dsh_permission_mode(path) == mode


@pytest.mark.parametrize("global_mode", [None, "strict", "native"])
@pytest.mark.parametrize("project_mode", [None, "strict", "native"])
def test_each_original_scope_requires_its_own_acknowledgement_before_merge(
    tmp_path: Path, tmp_storage: Path, global_mode: str | None, project_mode: str | None
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    for path, mode in (
        (tmp_storage / "global.json", global_mode),
        (project / "ai-dotfiles.json", project_mode),
    ):
        manifest.write_manifest(
            path, {} if mode is None else {"dsh_permission_mode": mode}
        )
    raw = (
        b'{ "permissions": {"defaultMode":"auto", "deny":["Write"]},\r\n'
        b' "skipAutoPermissionPrompt": true }\r\n'
    )
    sources = []
    for scope, directory in (("global", tmp_storage), ("project", project)):
        path = directory / "settings.json"
        path.write_bytes(raw)
        sources.append(
            DshConfigSource(path, "settings", scope, scope, str(path), directory)
        )
    plan = collect_dsh_configuration(reversed(sources), project_layout(project))
    assert plan.permissions.deny == ("write",) and not plan.permissions.ask
    assert [item.blocking for item in plan.permissions.diagnostics] == [
        global_mode != "native",
        project_mode != "native",
    ]
    assert plan.blocked == (global_mode != "native" or project_mode != "native")
    assert all(
        item.code == "SETTINGS_FIELD_UNMAPPED" and not item.blocking
        for item in plan.diagnostics
    )
    for source, record, gap in zip(
        sources, plan.sources, plan.permissions.gaps, strict=True
    ):
        assert source.path.read_bytes() == raw
        assert record["value"] == json.loads(raw)
        assert gap.value == "auto" and gap.provenance.source == source.path
        assert (
            record["source_sha256"]
            == gap.provenance.source_sha256
            == hashlib.sha256(raw).hexdigest()
        )


def test_unused_global_manifest_does_not_affect_project_source(
    tmp_path: Path, tmp_storage: Path
) -> None:
    (tmp_storage / "global.json").write_text("malformed unrelated manifest")
    path = tmp_path / "settings.json"
    path.write_text('{"permissions":{"deny":["Write"]}}')
    source = DshConfigSource(path, "settings", "project", "local", str(path), tmp_path)
    assert not collect_dsh_configuration([source], project_layout(tmp_path)).blocked


def test_revoking_acknowledgement_refuses_prepared_install_before_any_write(
    tmp_path: Path, tmp_storage: Path
) -> None:
    selected = tmp_path / "ai-dotfiles.json"
    manifest.write_manifest(selected, {"dsh_permission_mode": "native"})
    path = tmp_path / "settings.json"
    path.write_text('{"permissions":{"defaultMode":"auto"}}')
    source = DshConfigSource(path, "settings", "project", "local", str(path), tmp_path)
    layout = project_layout(tmp_path)
    config = compose_dsh_configuration(collect_dsh_configuration([source], layout))
    install = attach_dsh_config_outputs(plan_dsh_install(layout), config)
    manifest.write_manifest(selected, {"dsh_permission_mode": "strict"})
    with pytest.raises(ConfigError, match="permission mode changed after planning"):
        apply_dsh_install(install)
    assert not layout.dsh_dir.exists()
    assert collect_dsh_configuration([source], layout).blocked


def test_manifest_mode_and_hash_share_one_read_even_if_source_is_revoked(
    tmp_path: Path, tmp_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = tmp_path / "ai-dotfiles.json"
    manifest.write_manifest(selected, {"dsh_permission_mode": "native"})
    expected = hashlib.sha256(selected.read_bytes()).hexdigest()
    path = tmp_path / "settings.json"
    path.write_text('{"permissions":{"defaultMode":"auto"}}')
    source = DshConfigSource(path, "settings", "project", "local", str(path), tmp_path)
    read = Path.read_bytes

    def revoke_after_read(current: Path) -> bytes:
        raw = read(current)
        if current == selected:
            manifest.write_manifest(selected, {"dsh_permission_mode": "strict"})
        return raw

    monkeypatch.setattr(Path, "read_bytes", revoke_after_read)
    layout = project_layout(tmp_path)
    config = collect_dsh_configuration([source], layout)
    assert config.permission_modes == ((selected, "native", expected),)
    install = attach_dsh_config_outputs(
        plan_dsh_install(layout), compose_dsh_configuration(config)
    )
    with pytest.raises(ConfigError, match="permission mode changed after planning"):
        apply_dsh_install(install)
    assert not layout.dsh_dir.exists()
