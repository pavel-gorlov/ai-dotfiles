"""Bounded stock gitflow fallback and source/ownership guards."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ai_dotfiles.core.dsh_config import collect_dsh_config_sources
from ai_dotfiles.core.dsh_hooks import attach_dsh_hook_outputs, collect_dsh_hooks
from ai_dotfiles.core.dsh_install import collect_dsh_elements
from ai_dotfiles.core.dsh_layout import global_layout, project_layout
from ai_dotfiles.core.elements import parse_elements
from ai_dotfiles.core.errors import ConfigError

pytestmark = pytest.mark.integration
STOCK = Path(__file__).resolve().parents[1] / "fixtures/dsh-stock-gitflow"


def copy_stock_catalog(catalog: Path) -> None:
    """Copy reviewed originals only into the caller's disposable catalog."""
    for name in ("gitflow", "python"):
        shutil.copytree(STOCK / name, catalog / name)


@pytest.mark.parametrize("scope", ["project", "global"])
def test_fallback_requires_original_catalog_plan_and_guards_all_three_sources(
    tmp_path: Path, scope: str
) -> None:
    catalog = tmp_path / "catalog"
    copy_stock_catalog(catalog)
    layout = (
        project_layout(tmp_path / "project")
        if scope == "project"
        else global_layout(tmp_path / "native-home")
    )
    selected = parse_elements(["@gitflow", "@python"])
    install = collect_dsh_elements(selected, layout, catalog)
    sources = collect_dsh_config_sources(selected, catalog, layout)
    unproven = collect_dsh_hooks(sources, layout)
    assert unproven.blocked and not unproven.hooks
    assert any("catalog resource is unproven" in d.reason for d in unproven.diagnostics)
    hooks = collect_dsh_hooks(sources, layout, install_plans=(install,))
    assert not hooks.blocked and hooks.contribution() is None
    assert hooks.hooks == {}
    assert (
        len([d for d in hooks.diagnostics if d.code == "HOOK_GITFLOW_POLICY_FALLBACK"])
        == 2
    )
    assert all(not d.blocking for d in hooks.diagnostics)
    output = json.loads(hooks.output().content)
    assert (
        len(
            output["aiDotfiles"]["sources"][0]["value"]["hooks"]["PreToolUse"][0][
                "hooks"
            ]
        )
        == 2
    )
    assert {p.source for p in hooks.provenance} >= {
        catalog / "gitflow/hooks/route-to-agent.sh",
        catalog / "gitflow/rules/gitflow.md",
        catalog / "gitflow/agents/git-workflow-assistant.md",
    }
    script = catalog / "gitflow/hooks/route-to-agent.sh"
    script.write_bytes(script.read_bytes() + b"# concurrent change\n")
    with pytest.raises(ConfigError, match="source changed after planning"):
        attach_dsh_hook_outputs(install, hooks)


@pytest.mark.parametrize("kind", ["rule", "agent"])
def test_project_override_cannot_prove_delivery_of_global_stock_policy(
    tmp_path: Path,
    kind: str,
) -> None:
    catalog = tmp_path / "catalog"
    copy_stock_catalog(catalog)
    selected = parse_elements(["@gitflow"])
    global_scope = global_layout(tmp_path / "native-home")
    project_scope = project_layout(tmp_path / "project")
    global_install = collect_dsh_elements(selected, global_scope, catalog)
    other_catalog = tmp_path / "other-catalog"
    name = "gitflow" if kind == "rule" else "git-workflow-assistant"
    source = other_catalog / f"{kind}s/{name}.md"
    source.parent.mkdir(parents=True)
    original = catalog / f"gitflow/{kind}s/{name}.md"
    source.write_text(original.read_text() + "\nChanged policy; do not delegate.\n")
    override = collect_dsh_elements(
        parse_elements([f"{kind}:{name}"]), project_scope, other_catalog
    )
    sources = collect_dsh_config_sources(selected, catalog, global_scope)
    hooks = collect_dsh_hooks(
        sources, project_scope, install_plans=(global_install, override)
    )
    assert hooks.blocked and not hooks.hooks
    label = (
        "always-on routing rule" if kind == "rule" else "callable inherited-model agent"
    )
    assert any("effective stock " + label in d.reason for d in hooks.diagnostics)


def test_stock_retirement_preserves_supported_handler_order_timeout_and_origin(
    tmp_path: Path,
) -> None:
    catalog = tmp_path / "catalog"
    copy_stock_catalog(catalog)
    settings = catalog / "gitflow/settings.fragment.json"
    value = json.loads(settings.read_text())
    handlers = value["hooks"]["PreToolUse"][0]["hooks"]
    handlers.insert(0, {"type": "command", "command": "echo first", "timeout": 1})
    handlers.insert(2, {"type": "command", "command": "echo second", "timeout": 2})
    settings.write_text(json.dumps(value))
    selected = parse_elements(["@gitflow"])
    layout = project_layout(tmp_path / "project")
    install = collect_dsh_elements(selected, layout, catalog)
    hooks = collect_dsh_hooks(
        collect_dsh_config_sources(selected, catalog, layout),
        layout,
        install_plans=(install,),
    )
    assert not hooks.blocked
    assert hooks.hooks["PreToolUse"] == [
        {
            "matcher": "bash",
            "hooks": [
                {"type": "command", "command": "echo first", "timeout": 1},
                {"type": "command", "command": "echo second", "timeout": 2},
            ],
        }
    ]
    assert hooks.contribution().provenance[0].source == settings
