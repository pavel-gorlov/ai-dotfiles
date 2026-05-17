"""Domain & element dependency resolution.

Domains declare their dependencies in ``catalog/<domain>/domain.json``
(``depends`` field). Standalone elements declare them in their YAML
frontmatter (``depends:`` key). Values are element specifiers in the
same syntax used in manifests: ``@domain``, ``skill:name``,
``agent:name``, ``rule:name``.

This module provides three pure-logic helpers:

* :func:`read_depends` — read declared dependencies of one element.
* :func:`resolve_transitive` — DFS expansion with cycle detection,
  returns elements in topological order (deps before dependents).
* :func:`find_reverse_deps` — given a manifest, find which entries
  transitively depend on a target element. Used by ``remove`` to block
  unsafe deletions.

No I/O happens here beyond reading catalog files — keep CLI concerns out.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ai_dotfiles.core.domain_meta import read_domain_meta
from ai_dotfiles.core.elements import (
    Element,
    ElementType,
    parse_element,
    resolve_source_path,
)
from ai_dotfiles.core.errors import (
    ConfigError,
    DependencyCycleError,
    MissingDependencyError,
)
from ai_dotfiles.core.frontmatter import parse_frontmatter

__all__ = [
    "read_depends",
    "resolve_transitive",
    "find_reverse_deps",
    "topological_sort",
]


def _read_domain_depends(catalog: Path, element: Element) -> list[str]:
    return read_domain_meta(catalog, element.name).depends


# --------------------------------------------------------------------------
# Standalone-element frontmatter parsing
# --------------------------------------------------------------------------
#
# The YAML-frontmatter parser is shared via ``core.frontmatter``. We only
# need the ``depends:`` key here; two shapes are supported by the parser:
#
#   depends: ["@python", "skill:x"]
#
#   depends:
#     - "@python"
#     - skill:x


def _read_standalone_depends(catalog: Path, element: Element) -> list[str]:
    source = resolve_source_path(element, catalog)
    md_path = source / "SKILL.md" if element.type is ElementType.SKILL else source
    if not md_path.is_file():
        return []
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read {md_path}: {exc}") from exc
    depends = parse_frontmatter(text).get("depends", [])
    if not isinstance(depends, list):
        raise ConfigError(
            f"Element {element.raw!r} ({md_path}): 'depends' must be a list."
        )
    return depends


def read_depends(catalog: Path, element: Element) -> list[Element]:
    """Return the elements ``element`` depends on, parsed from the catalog.

    Looks up ``_depends`` in ``settings.fragment.json`` for domains and
    ``depends:`` in YAML frontmatter for standalone elements.
    """
    if element.type is ElementType.DOMAIN:
        raw = _read_domain_depends(catalog, element)
    else:
        raw = _read_standalone_depends(catalog, element)

    parsed: list[Element] = []
    for spec in raw:
        parsed.append(parse_element(spec))
    return parsed


def _check_exists(catalog: Path, dep: Element, source: Element) -> None:
    target = resolve_source_path(dep, catalog)
    if not target.exists():
        raise MissingDependencyError(
            f"Element {source.raw!r} declares dependency {dep.raw!r}, "
            f"but {target} does not exist in the catalog."
        )


def resolve_transitive(
    catalog: Path,
    roots: Iterable[Element],
) -> list[Element]:
    """Return ``roots`` plus all transitive dependencies in topological order.

    Topological order = deps appear before their dependents. Roots
    preserve their relative order when independent. Duplicates are
    de-duplicated by ``Element.raw``.

    Raises :class:`DependencyCycleError` if a cycle is detected, or
    :class:`MissingDependencyError` if a referenced element is missing
    from the catalog.
    """
    visited: dict[str, Element] = {}
    on_stack: set[str] = set()
    order: list[Element] = []

    def visit(node: Element, stack_path: list[str]) -> None:
        if node.raw in visited:
            return
        if node.raw in on_stack:
            cycle = " -> ".join([*stack_path, node.raw])
            raise DependencyCycleError(f"Dependency cycle detected: {cycle}")
        on_stack.add(node.raw)
        stack_path.append(node.raw)
        for dep in read_depends(catalog, node):
            _check_exists(catalog, dep, node)
            visit(dep, stack_path)
        stack_path.pop()
        on_stack.discard(node.raw)
        visited[node.raw] = node
        order.append(node)

    for root in roots:
        visit(root, [])

    return order


def topological_sort(
    catalog: Path,
    elements: Iterable[Element],
) -> list[Element]:
    """Reorder ``elements`` topologically (deps first) without expanding.

    Unlike :func:`resolve_transitive`, this function does not pull in
    new dependencies — it only re-arranges the input. Items whose deps
    are not in the input are tolerated (treated as independent).

    Used by fragment merging so that a manually-edited manifest with
    the wrong order still produces a stable layered output.
    """
    inputs = list(elements)
    by_raw = {el.raw: el for el in inputs}
    order_index = {el.raw: i for i, el in enumerate(inputs)}
    visited: set[str] = set()
    on_stack: set[str] = set()
    order: list[Element] = []

    def visit(node: Element, stack_path: list[str]) -> None:
        if node.raw in visited:
            return
        if node.raw in on_stack:
            cycle = " -> ".join([*stack_path, node.raw])
            raise DependencyCycleError(f"Dependency cycle detected: {cycle}")
        on_stack.add(node.raw)
        stack_path.append(node.raw)
        deps_in_set = [dep for dep in read_depends(catalog, node) if dep.raw in by_raw]
        deps_in_set.sort(key=lambda d: order_index[d.raw])
        for dep in deps_in_set:
            visit(by_raw[dep.raw], stack_path)
        stack_path.pop()
        on_stack.discard(node.raw)
        visited.add(node.raw)
        order.append(node)

    for el in inputs:
        visit(el, [])

    return order


def find_reverse_deps(
    catalog: Path,
    manifest_packages: Iterable[Element],
    target: Element,
) -> list[Element]:
    """Return every element from ``manifest_packages`` whose transitive
    dependency closure includes ``target`` (excluding ``target`` itself).

    Used to block ``ai-dotfiles remove @x`` while another manifest entry
    still depends on ``@x``.
    """
    dependents: list[Element] = []
    for entry in manifest_packages:
        if entry.raw == target.raw:
            continue
        try:
            closure = resolve_transitive(catalog, [entry])
        except (MissingDependencyError, DependencyCycleError):
            # If the entry itself has bad metadata we cannot reason about
            # its deps; skip it rather than blowing up the unrelated remove.
            continue
        for el in closure:
            if el.raw == target.raw:
                dependents.append(entry)
                break
    return dependents
