"""Unit tests for the tab-completion data providers."""

from __future__ import annotations

import json
from pathlib import Path

import click
import pytest

from ai_dotfiles.core import completions


@pytest.fixture
def catalog(tmp_storage: Path) -> Path:
    """Return ``catalog/`` inside the temp storage, created empty."""
    root = tmp_storage / "catalog"
    root.mkdir()
    return root


def _mkskill(catalog: Path, name: str, *, domain: str | None = None) -> None:
    base = catalog / domain / "skills" if domain else catalog / "skills"
    (base / name).mkdir(parents=True)
    (base / name / "SKILL.md").write_text("---\nname: " + name + "\n---\n")


def _mkagent(catalog: Path, name: str, *, domain: str | None = None) -> None:
    base = catalog / domain / "agents" if domain else catalog / "agents"
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{name}.md").write_text("---\nname: " + name + "\n---\n")


def _mkrule(catalog: Path, name: str, *, domain: str | None = None) -> None:
    base = catalog / domain / "rules" if domain else catalog / "rules"
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{name}.md").write_text("# rule\n")


def _mkvendored(catalog: Path, kind: str, name: str) -> None:
    base = catalog / f"{kind}s" / name
    base.mkdir(parents=True)
    if kind == "skill":
        (base / "SKILL.md").write_text("---\nname: " + name + "\n---\n")
    (base / ".source").write_text('{"vendor": "test"}\n')


# ── Domains ──────────────────────────────────────────────────────────────────


def test_list_domain_names_skips_standalone_and_reserved(catalog: Path) -> None:
    (catalog / "python-backend").mkdir()
    (catalog / "gitflow").mkdir()
    (catalog / "skills").mkdir()
    (catalog / "agents").mkdir()
    (catalog / "rules").mkdir()
    (catalog / "_example").mkdir()

    assert completions.list_domain_names() == ["gitflow", "python-backend"]


def test_list_domain_names_include_reserved(catalog: Path) -> None:
    (catalog / "python-backend").mkdir()
    (catalog / "_example").mkdir()

    assert completions.list_domain_names(include_reserved=True) == [
        "_example",
        "python-backend",
    ]


def test_list_domain_names_empty_when_no_catalog(tmp_storage: Path) -> None:
    assert completions.list_domain_names() == []


# ── Standalone elements ──────────────────────────────────────────────────────


def test_list_standalone_skills(catalog: Path) -> None:
    _mkskill(catalog, "alpha")
    _mkskill(catalog, "beta")

    assert completions.list_standalone_elements("skill") == ["alpha", "beta"]


def test_list_standalone_agents(catalog: Path) -> None:
    _mkagent(catalog, "writer")
    _mkagent(catalog, "reviewer")

    assert completions.list_standalone_elements("agent") == ["reviewer", "writer"]


def test_list_standalone_unknown_type_returns_empty(catalog: Path) -> None:
    assert completions.list_standalone_elements("hook") == []


# ── Domain elements ──────────────────────────────────────────────────────────


def test_list_elements_in_domain(catalog: Path) -> None:
    _mkskill(catalog, "endpoint", domain="python-backend")
    _mkrule(catalog, "python-style", domain="python-backend")

    assert completions.list_elements_in_domain("python-backend", "skill") == [
        "endpoint"
    ]
    assert completions.list_elements_in_domain("python-backend", "rule") == [
        "python-style"
    ]
    assert completions.list_elements_in_domain("python-backend", "agent") == []


def test_list_elements_in_missing_domain(catalog: Path) -> None:
    assert completions.list_elements_in_domain("does-not-exist", "skill") == []


# ── Catalog specifiers (aggregate) ───────────────────────────────────────────


def test_list_catalog_specifiers_combines_everything(catalog: Path) -> None:
    (catalog / "python-backend").mkdir()
    _mkskill(catalog, "code-review")
    _mkagent(catalog, "doc-writer")
    _mkrule(catalog, "style-guide")

    specs = completions.list_catalog_specifiers()

    assert "@python-backend" in specs
    assert "skill:code-review" in specs
    assert "agent:doc-writer" in specs
    assert "rule:style-guide" in specs


# ── Vendored entries ─────────────────────────────────────────────────────────


def test_list_vendored_scans_source_sidecars(catalog: Path) -> None:
    _mkvendored(catalog, "skill", "vendored-a")
    _mkvendored(catalog, "agent", "vendored-b")
    _mkskill(catalog, "local-only")  # no .source — should be skipped

    assert completions.list_vendored_element_names() == ["vendored-a", "vendored-b"]


# ── Manifests ────────────────────────────────────────────────────────────────


def test_list_installed_global(tmp_storage: Path) -> None:
    (tmp_storage / "global.json").write_text(
        json.dumps({"packages": ["skill:a", "@python-backend"]})
    )

    assert completions.list_installed_specifiers(is_global=True) == [
        "skill:a",
        "@python-backend",
    ]


def test_list_installed_global_missing(tmp_storage: Path) -> None:
    assert completions.list_installed_specifiers(is_global=True) == []


def test_list_installed_project(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_project)
    (tmp_project / "ai-dotfiles.json").write_text(
        json.dumps({"packages": ["skill:proj"]})
    )

    assert completions.list_installed_specifiers(is_global=False) == ["skill:proj"]


def test_list_installed_project_no_manifest(
    tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_project)
    assert completions.list_installed_specifiers(is_global=False) == []


def test_list_installed_malformed_returns_empty(tmp_storage: Path) -> None:
    (tmp_storage / "global.json").write_text("not json")
    assert completions.list_installed_specifiers(is_global=True) == []


# ── Available (catalog − installed) ──────────────────────────────────────────


def test_list_available_fresh_then_installed(catalog: Path, tmp_storage: Path) -> None:
    _mkskill(catalog, "a")
    _mkskill(catalog, "b")
    (tmp_storage / "global.json").write_text(json.dumps({"packages": ["skill:a"]}))

    result = completions.list_available_specifiers(is_global=True)

    # Fresh first, installed second — both still listed.
    assert result == ["skill:b", "skill:a"]


# ── Completer wrapper ────────────────────────────────────────────────────────


def test_make_completer_filters_by_prefix() -> None:
    completer = completions.make_completer(lambda ctx: ["alpha", "beta", "alp"])
    ctx = click.Context(click.Command("x"))
    param = click.Argument(["name"])

    assert completer(ctx, param, "") == ["alpha", "beta", "alp"]
    assert completer(ctx, param, "al") == ["alpha", "alp"]
    assert completer(ctx, param, "zzz") == []


def test_make_completer_swallows_exceptions() -> None:
    def broken(_ctx: click.Context) -> list[str]:
        raise RuntimeError("boom")

    completer = completions.make_completer(broken)
    ctx = click.Context(click.Command("x"))
    param = click.Argument(["name"])

    assert completer(ctx, param, "") == []


# ── Pre-built contextual completers ──────────────────────────────────────────


def test_complete_installed_uses_ctx_scope(
    tmp_storage: Path, tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_storage / "global.json").write_text(
        json.dumps({"packages": ["skill:global-only"]})
    )
    monkeypatch.chdir(tmp_project)
    (tmp_project / "ai-dotfiles.json").write_text(
        json.dumps({"packages": ["skill:project-only"]})
    )

    ctx_global = click.Context(click.Command("add"))
    ctx_global.params = {"is_global": True}
    ctx_project = click.Context(click.Command("add"))
    ctx_project.params = {"is_global": False}

    assert completions.complete_installed_specifiers(ctx_global) == [
        "skill:global-only"
    ]
    assert completions.complete_installed_specifiers(ctx_project) == [
        "skill:project-only"
    ]


def test_complete_domain_elements_reads_preceding_args(catalog: Path) -> None:
    _mkskill(catalog, "endpoint", domain="python-backend")

    ctx = click.Context(click.Command("remove"))
    ctx.params = {"name": "python-backend", "element_type": "skill"}

    assert completions.complete_domain_elements(ctx) == ["endpoint"]


def test_complete_standalone_elements_reads_element_type(catalog: Path) -> None:
    _mkagent(catalog, "writer")

    ctx = click.Context(click.Command("delete"))
    ctx.params = {"element_type": "agent"}

    assert completions.complete_standalone_elements(ctx) == ["writer"]
