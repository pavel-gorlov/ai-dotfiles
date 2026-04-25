"""Unit tests for ai_dotfiles.core.dependencies."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_dotfiles.core.dependencies import (
    find_reverse_deps,
    read_depends,
    resolve_transitive,
    topological_sort,
)
from ai_dotfiles.core.elements import parse_element
from ai_dotfiles.core.errors import (
    ConfigError,
    DependencyCycleError,
    MissingDependencyError,
)


def _mkdomain(catalog: Path, name: str, depends: list[str] | None = None) -> None:
    """Materialize a minimal domain with the given depends in domain.json."""
    root = catalog / name
    root.mkdir(parents=True, exist_ok=True)
    meta: dict[str, object] = {"name": name}
    if depends is not None:
        meta["depends"] = depends
    (root / "domain.json").write_text(json.dumps(meta))


def _mkskill(catalog: Path, name: str, depends: list[str] | None = None) -> None:
    skill_dir = catalog / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    body = "---\nname: " + name + "\n"
    if depends is not None:
        body += "depends:\n"
        for dep in depends:
            body += f'  - "{dep}"\n'
    body += "---\n\n# " + name + "\n"
    (skill_dir / "SKILL.md").write_text(body)


# ── read_depends ──────────────────────────────────────────────────────────


def test_read_depends_domain_no_field(tmp_path: Path) -> None:
    _mkdomain(tmp_path, "a")
    assert read_depends(tmp_path, parse_element("@a")) == []


def test_read_depends_domain_explicit(tmp_path: Path) -> None:
    _mkdomain(tmp_path, "a")
    _mkdomain(tmp_path, "b", depends=["@a"])
    deps = read_depends(tmp_path, parse_element("@b"))
    assert [d.raw for d in deps] == ["@a"]


def test_read_depends_domain_invalid_type(tmp_path: Path) -> None:
    _mkdomain(tmp_path, "x")
    meta = tmp_path / "x" / "domain.json"
    meta.write_text(json.dumps({"name": "x", "depends": "not-a-list"}))
    with pytest.raises(ConfigError):
        read_depends(tmp_path, parse_element("@x"))


def test_read_depends_skill_block_list(tmp_path: Path) -> None:
    _mkdomain(tmp_path, "py")
    _mkskill(tmp_path, "my-skill", depends=["@py"])
    deps = read_depends(tmp_path, parse_element("skill:my-skill"))
    assert [d.raw for d in deps] == ["@py"]


def test_read_depends_skill_inline_list(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "inline"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        '---\nname: inline\ndepends: ["@py", "skill:other"]\n---\n# x\n'
    )
    _mkdomain(tmp_path, "py")
    _mkskill(tmp_path, "other")
    deps = read_depends(tmp_path, parse_element("skill:inline"))
    assert [d.raw for d in deps] == ["@py", "skill:other"]


def test_read_depends_skill_no_frontmatter(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "nofm"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# no frontmatter\n")
    assert read_depends(tmp_path, parse_element("skill:nofm")) == []


# ── resolve_transitive ────────────────────────────────────────────────────


def test_resolve_transitive_linear(tmp_path: Path) -> None:
    _mkdomain(tmp_path, "a")
    _mkdomain(tmp_path, "b", depends=["@a"])
    _mkdomain(tmp_path, "c", depends=["@b"])
    order = resolve_transitive(tmp_path, [parse_element("@c")])
    assert [el.raw for el in order] == ["@a", "@b", "@c"]


def test_resolve_transitive_diamond(tmp_path: Path) -> None:
    _mkdomain(tmp_path, "a")
    _mkdomain(tmp_path, "b", depends=["@a"])
    _mkdomain(tmp_path, "c", depends=["@a"])
    _mkdomain(tmp_path, "d", depends=["@b", "@c"])
    order = resolve_transitive(tmp_path, [parse_element("@d")])
    raws = [el.raw for el in order]
    # @a appears once.
    assert raws.count("@a") == 1
    # @a is before @b and @c, both before @d.
    assert raws.index("@a") < raws.index("@b") < raws.index("@d")
    assert raws.index("@a") < raws.index("@c") < raws.index("@d")


def test_resolve_transitive_cycle(tmp_path: Path) -> None:
    _mkdomain(tmp_path, "a", depends=["@b"])
    _mkdomain(tmp_path, "b", depends=["@a"])
    with pytest.raises(DependencyCycleError):
        resolve_transitive(tmp_path, [parse_element("@a")])


def test_resolve_transitive_self_cycle(tmp_path: Path) -> None:
    _mkdomain(tmp_path, "a", depends=["@a"])
    with pytest.raises(DependencyCycleError):
        resolve_transitive(tmp_path, [parse_element("@a")])


def test_resolve_transitive_missing_dep(tmp_path: Path) -> None:
    _mkdomain(tmp_path, "a", depends=["@b"])
    with pytest.raises(MissingDependencyError):
        resolve_transitive(tmp_path, [parse_element("@a")])


def test_resolve_transitive_multiple_roots(tmp_path: Path) -> None:
    _mkdomain(tmp_path, "shared")
    _mkdomain(tmp_path, "a", depends=["@shared"])
    _mkdomain(tmp_path, "b", depends=["@shared"])
    order = resolve_transitive(tmp_path, [parse_element("@a"), parse_element("@b")])
    raws = [el.raw for el in order]
    # @shared appears once.
    assert raws.count("@shared") == 1
    assert raws.index("@shared") < raws.index("@a")
    assert raws.index("@shared") < raws.index("@b")


def test_resolve_transitive_skill_depends_on_domain(tmp_path: Path) -> None:
    _mkdomain(tmp_path, "py")
    _mkskill(tmp_path, "my", depends=["@py"])
    order = resolve_transitive(tmp_path, [parse_element("skill:my")])
    assert [el.raw for el in order] == ["@py", "skill:my"]


# ── topological_sort ──────────────────────────────────────────────────────


def test_topological_sort_reorders(tmp_path: Path) -> None:
    _mkdomain(tmp_path, "a")
    _mkdomain(tmp_path, "b", depends=["@a"])
    inputs = [parse_element("@b"), parse_element("@a")]  # wrong order
    out = topological_sort(tmp_path, inputs)
    assert [el.raw for el in out] == ["@a", "@b"]


def test_topological_sort_does_not_pull_in_extras(tmp_path: Path) -> None:
    _mkdomain(tmp_path, "a")
    _mkdomain(tmp_path, "b", depends=["@a"])
    # Only @b in the input; @a is NOT pulled in by topological_sort.
    out = topological_sort(tmp_path, [parse_element("@b")])
    assert [el.raw for el in out] == ["@b"]


# ── find_reverse_deps ─────────────────────────────────────────────────────


def test_find_reverse_deps_direct(tmp_path: Path) -> None:
    _mkdomain(tmp_path, "a")
    _mkdomain(tmp_path, "b", depends=["@a"])
    manifest = [parse_element("@a"), parse_element("@b")]
    dependents = find_reverse_deps(tmp_path, manifest, parse_element("@a"))
    assert [d.raw for d in dependents] == ["@b"]


def test_find_reverse_deps_transitive(tmp_path: Path) -> None:
    _mkdomain(tmp_path, "a")
    _mkdomain(tmp_path, "b", depends=["@a"])
    _mkdomain(tmp_path, "c", depends=["@b"])
    manifest = [parse_element("@a"), parse_element("@b"), parse_element("@c")]
    dependents = find_reverse_deps(tmp_path, manifest, parse_element("@a"))
    raws = sorted(d.raw for d in dependents)
    assert raws == ["@b", "@c"]


def test_find_reverse_deps_none(tmp_path: Path) -> None:
    _mkdomain(tmp_path, "a")
    _mkdomain(tmp_path, "b")
    manifest = [parse_element("@a"), parse_element("@b")]
    dependents = find_reverse_deps(tmp_path, manifest, parse_element("@a"))
    assert dependents == []
