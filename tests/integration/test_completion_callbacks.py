"""Integration tests for shell-completion callbacks wired on CLI arguments.

These verify that:
1. Each targeted command declares a ``shell_complete`` callback on the right
   argument.
2. The callback returns the expected list of specifiers for a realistic
   catalog / manifest layout.
3. The ``is_global`` flag from ``ctx.params`` is honored.

Uses ``tmp_storage`` + ``tmp_project`` fixtures from ``conftest.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import click
import pytest

from ai_dotfiles.commands.add import add
from ai_dotfiles.commands.create_delete import delete as delete_standalone
from ai_dotfiles.commands.domain import (
    delete as domain_delete,
)
from ai_dotfiles.commands.domain import (
    list_domain,
)
from ai_dotfiles.commands.domain import (
    remove_element as domain_remove,
)
from ai_dotfiles.commands.remove import remove
from ai_dotfiles.commands.vendor import _meta_remove as vendor_remove

pytestmark = pytest.mark.integration


def _complete(
    command: click.Command, arg_name: str, ctx: click.Context, incomplete: str
) -> list[str]:
    """Invoke the shell_complete callback for ``arg_name`` and return raw values.

    Click's ``Parameter.shell_complete(ctx, incomplete)`` returns a list of
    ``CompletionItem``; we unwrap ``.value`` for assertion convenience.
    """
    for param in command.params:
        if param.name == arg_name:
            items = param.shell_complete(ctx, incomplete)
            return [getattr(item, "value", str(item)) for item in items]
    raise AssertionError(f"Parameter {arg_name!r} not found on {command.name}")


def _seed_catalog(catalog: Path) -> None:
    """Minimal realistic catalog: one domain + one standalone skill."""
    (catalog / "python-backend").mkdir(parents=True)
    (catalog / "skills" / "alpha").mkdir(parents=True)
    (catalog / "skills" / "alpha" / "SKILL.md").write_text("---\nname: alpha\n---\n")


# ── add: shell_complete on `packages` ────────────────────────────────────────


def test_add_completes_available_global_scope(tmp_storage: Path) -> None:
    _seed_catalog(tmp_storage / "catalog")
    (tmp_storage / "global.json").write_text(json.dumps({"packages": ["skill:alpha"]}))

    ctx = click.Context(add)
    ctx.params = {"is_global": True}

    # Prefix "" returns all; skill:alpha should be present but after @python-backend
    # (fresh-first ordering).
    result = _complete(add, "packages", ctx, "")
    assert "@python-backend" in result
    assert "skill:alpha" in result
    assert result.index("@python-backend") < result.index("skill:alpha")


def test_add_completes_filtered_by_prefix(tmp_storage: Path) -> None:
    _seed_catalog(tmp_storage / "catalog")

    ctx = click.Context(add)
    ctx.params = {"is_global": True}

    assert _complete(add, "packages", ctx, "@py") == ["@python-backend"]
    assert _complete(add, "packages", ctx, "skill:") == ["skill:alpha"]
    assert _complete(add, "packages", ctx, "zzz") == []


def test_add_completes_project_scope(
    tmp_storage: Path, tmp_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_catalog(tmp_storage / "catalog")
    monkeypatch.chdir(tmp_project)
    (tmp_project / "ai-dotfiles.json").write_text(
        json.dumps({"packages": ["@python-backend"]})
    )

    ctx = click.Context(add)
    ctx.params = {"is_global": False}

    result = _complete(add, "packages", ctx, "")
    # Project has @python-backend installed → skill:alpha is fresh; both still listed
    assert result.index("skill:alpha") < result.index("@python-backend")


# ── remove: shell_complete on `packages` ─────────────────────────────────────


def test_remove_completes_only_installed_global(tmp_storage: Path) -> None:
    _seed_catalog(tmp_storage / "catalog")
    (tmp_storage / "global.json").write_text(
        json.dumps({"packages": ["skill:alpha", "@python-backend"]})
    )

    ctx = click.Context(remove)
    ctx.params = {"is_global": True}

    result = _complete(remove, "packages", ctx, "")
    assert sorted(result) == ["@python-backend", "skill:alpha"]


def test_remove_returns_nothing_when_manifest_missing(tmp_storage: Path) -> None:
    _seed_catalog(tmp_storage / "catalog")

    ctx = click.Context(remove)
    ctx.params = {"is_global": True}

    # No global.json present → empty list, no crash
    assert _complete(remove, "packages", ctx, "") == []


def test_remove_prefix_filter(tmp_storage: Path) -> None:
    _seed_catalog(tmp_storage / "catalog")
    (tmp_storage / "global.json").write_text(
        json.dumps({"packages": ["skill:alpha", "@python-backend"]})
    )

    ctx = click.Context(remove)
    ctx.params = {"is_global": True}

    assert _complete(remove, "packages", ctx, "@") == ["@python-backend"]
    assert _complete(remove, "packages", ctx, "skill:") == ["skill:alpha"]


# ── domain delete / list: shell_complete on `name` ───────────────────────────


def test_domain_delete_and_list_complete_names(tmp_storage: Path) -> None:
    catalog = tmp_storage / "catalog"
    (catalog / "python-backend").mkdir(parents=True)
    (catalog / "gitflow").mkdir()
    (catalog / "skills").mkdir()  # pseudo-dir; must be skipped
    (catalog / "_example").mkdir()  # reserved; must be skipped

    for cmd in (domain_delete, list_domain):
        ctx = click.Context(cmd)
        ctx.params = {}
        assert _complete(cmd, "name", ctx, "") == ["gitflow", "python-backend"]


# ── domain remove: element_name → elements of type inside domain ─────────────


def test_domain_remove_completes_from_preceding_args(tmp_storage: Path) -> None:
    catalog = tmp_storage / "catalog"
    skill_dir = catalog / "python-backend" / "skills" / "fastapi-endpoint"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: fastapi-endpoint\n---\n")

    ctx = click.Context(domain_remove)
    ctx.params = {"name": "python-backend", "element_type": "skill"}

    assert _complete(domain_remove, "element_name", ctx, "") == ["fastapi-endpoint"]


# ── delete skill|agent|rule: name → standalone elements of that type ─────────


def test_delete_standalone_completes_by_element_type(tmp_storage: Path) -> None:
    catalog = tmp_storage / "catalog"
    (catalog / "agents").mkdir(parents=True)
    (catalog / "agents" / "writer.md").write_text("---\nname: writer\n---\n")

    ctx = click.Context(delete_standalone)
    ctx.params = {"element_type": "agent"}

    assert _complete(delete_standalone, "name", ctx, "") == ["writer"]


# ── vendor remove: name → vendored element names ─────────────────────────────


def test_vendor_remove_completes_vendored_names(tmp_storage: Path) -> None:
    catalog = tmp_storage / "catalog"
    vendored = catalog / "skills" / "vendored-skill"
    vendored.mkdir(parents=True)
    (vendored / "SKILL.md").write_text("---\nname: vendored-skill\n---\n")
    (vendored / ".source").write_text('{"vendor": "test"}\n')

    # And one local (non-vendored) skill that must be skipped
    local = catalog / "skills" / "local-skill"
    local.mkdir()
    (local / "SKILL.md").write_text("---\nname: local-skill\n---\n")

    ctx = click.Context(vendor_remove)
    ctx.params = {}

    assert _complete(vendor_remove, "name", ctx, "") == ["vendored-skill"]
