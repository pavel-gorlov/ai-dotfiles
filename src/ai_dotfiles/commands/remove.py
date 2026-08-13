"""``ai-dotfiles remove`` — drop packages from manifest and unlink them."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ai_dotfiles import ui
from ai_dotfiles.core import (
    claude_copy,
    codex_config,
    codex_hooks,
    codex_install,
    codex_rules,
    manifest,
    symlinks,
)
from ai_dotfiles.core.codex_layout import CodexLayout, global_layout, project_layout
from ai_dotfiles.core.codex_targets import iter_codex_pairs, iter_codex_rule_plans
from ai_dotfiles.core.completions import (
    complete_installed_specifiers,
    make_completer,
)
from ai_dotfiles.core.dependencies import find_reverse_deps
from ai_dotfiles.core.elements import (
    Element,
    ElementType,
    parse_element,
    parse_elements,
    resolve_source_path,
    resolve_target_paths,
)
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError
from ai_dotfiles.core.gitignore import collect_managed_paths, sync_gitignore
from ai_dotfiles.core.mcp_apply import rebuild_claude_config
from ai_dotfiles.core.mcp_merge import collect_mcp_fragments
from ai_dotfiles.core.paths import (
    backup_dir,
    bin_dir,
    catalog_dir,
    claude_global_dir,
    find_project_root,
    global_manifest_path,
    project_claude_dir,
    project_manifest_path,
    storage_root,
)
from ai_dotfiles.core.runtime import tear_down_domain_runtime
from ai_dotfiles.core.settings_merge import (
    assemble_settings,
    collect_domain_fragments,
    collect_fragment_contributions,
    load_fragment,
    strip_owned,
    write_settings,
)
from ai_dotfiles.core.settings_ownership import (
    delete_settings_ownership,
    load_settings_ownership,
    save_settings_ownership,
)
from ai_dotfiles.core.settings_ownership import (
    is_empty as settings_ownership_is_empty,
)


def _check_reverse_deps(
    manifest_path: Path,
    catalog: Path,
    targets: list[Element],
) -> None:
    """Refuse to remove ``targets`` if other manifest entries depend on them.

    A target is exempt from the check when it is itself one of the
    other targets in the same call (removing the dependent and the dep
    together is fine).
    """
    raw_packages = manifest.get_packages(manifest_path)
    if not raw_packages:
        return
    target_set = {el.raw for el in targets}
    parsed_packages: list[Element] = []
    for spec in raw_packages:
        try:
            parsed_packages.append(parse_element(spec))
        except Exception:  # noqa: BLE001 - skip malformed manifest entries
            continue
    blockers: dict[str, list[str]] = {}
    for target in targets:
        dependents = find_reverse_deps(catalog, parsed_packages, target)
        # An entry that the user is also removing in the same call doesn't
        # block — they're tearing down the whole subtree intentionally.
        outstanding = [d for d in dependents if d.raw not in target_set]
        if outstanding:
            blockers[target.raw] = [d.raw for d in outstanding]
    if not blockers:
        return
    lines = ["Cannot remove the following entries — other packages depend on them:"]
    for target_raw, dependents_raw in blockers.items():
        joined = ", ".join(dependents_raw)
        lines.append(f"  {target_raw}  <-  required by {joined}")
    lines.append("Remove the dependents too, or pass --force to override.")
    raise ConfigError("\n".join(lines))


def _resolve_scope(is_global: bool) -> tuple[Path, Path, Path | None]:
    """Return ``(manifest_path, claude_dir, project_root)`` for the scope.

    ``project_root`` is ``None`` for the global scope.
    """
    if is_global:
        return global_manifest_path(), claude_global_dir(), None

    root = find_project_root()
    if root is None:
        raise ConfigError(
            "No project found. Run 'ai-dotfiles init' first or pass -g for global."
        )
    return project_manifest_path(root), project_claude_dir(root), root


def _unlink_element(
    element: Element, claude_dir: Path, catalog: Path, link_mode: str
) -> None:
    """Remove the Claude-target artefacts created for ``element``.

    In ``copy`` mode the recorded managed copies are deleted (user files
    are never touched — only sidecar-recorded entries); in ``symlink``
    mode the symlinks into the catalog are unlinked.
    """
    if link_mode == "copy":
        claude_copy.remove_copied_element(element, claude_dir, catalog)
        return
    if element.type is ElementType.DOMAIN:
        source = resolve_source_path(element, catalog)
        if source.exists():
            symlinks.unlink_domain(source, claude_dir)
            return
        # Catalog entry missing — best-effort: walk known target paths.
        for _, target in resolve_target_paths(element, claude_dir, catalog):
            symlinks.unlink_standalone(target)
        return

    for _, target in resolve_target_paths(element, claude_dir, catalog):
        symlinks.unlink_standalone(target)


def _unlink_codex_element(element: Element, layout: CodexLayout, catalog: Path) -> None:
    """Remove managed Codex artefacts created for ``element``.

    Only ai-dotfiles-managed content is removed — a user-authored
    skill/agent of the same name and user-authored ``AGENTS.md`` text are
    left untouched. Skills/agents drop their generated file (at global
    scope a skill may instead be a symlink into the catalog — dropped by
    the link check); a rule's managed ``AGENTS.md`` block is stripped
    (and a now-empty ``AGENTS.md`` deleted); a description-only rule's
    synthetic ``rule-<name>`` skill is removed. Domain ``hooks/`` members
    yield nothing to remove.
    """
    from ai_dotfiles.core.agents_md import rule_name_of

    for pair in iter_codex_pairs(element, layout, catalog):
        if pair.element_type is ElementType.AGENT:
            codex_install.remove_codex_agent(pair.target)
        elif pair.target.is_symlink():  # global gated-symlink skill
            codex_install.remove_codex_skill_link(pair.target, catalog_dir())
        else:  # SKILL or synthetic RULE skill
            codex_install.remove_codex_skill(pair.target)
    for plan in iter_codex_rule_plans(element, layout, catalog):
        name = rule_name_of(plan.source)
        for agents_md_path in plan.agents_md_paths:
            codex_install.remove_codex_rule_blocks(agents_md_path, name)


def _rebuild_codex_config(manifest_path: Path, codex_dir: Path, catalog: Path) -> None:
    """Reassemble ``.codex/config.toml`` from the remaining domain fragments.

    The Codex analogue of :func:`_rebuild_settings` — after a removal the
    managed ``[ai_dotfiles]`` region is rebuilt from whatever domains
    are still in the manifest, so a sibling domain's permissions / sandbox
    survive. Unrelated tables (``[mcp_servers]`` …) and user content are
    left intact. When no domain remains, the managed region is stripped.
    """
    packages = manifest.get_packages(manifest_path)
    fragments = collect_domain_fragments(packages, catalog)
    fragment_pairs = [(path.parent.name, path) for path in fragments]
    result = codex_config.write_codex_config(codex_dir, fragment_pairs)
    if result.status == "removed":
        ui.info("Codex: stripped managed region from config.toml")
    elif result.status in ("created", "updated"):
        ui.info("Codex: rebuilt config.toml managed region")

    # The exec policy is derived from the same fragments — rebuild it from
    # whatever domains survive, so a removed domain's prefix rules go away.
    rules_status, _ = codex_rules.write_codex_rules(codex_dir, fragment_pairs)
    if rules_status == "removed":
        ui.info(f"Codex: removed rules/{codex_rules.RULES_FILENAME}")
    elif rules_status in ("created", "updated"):
        ui.info(f"Codex: rebuilt rules/{codex_rules.RULES_FILENAME}")

    mcp_result = codex_config.write_codex_mcp(
        codex_dir, collect_mcp_fragments(packages, catalog)
    )
    if mcp_result.status == "removed":
        ui.info("Codex: stripped [mcp_servers] from config.toml")
    elif mcp_result.status in ("created", "updated"):
        ui.info("Codex: rebuilt config.toml [mcp_servers]")

    hooks_result = codex_hooks.write_codex_hooks(codex_dir, fragment_pairs)
    if hooks_result.status == "removed":
        ui.info("Codex: stripped managed hooks from hooks.json")
    elif hooks_result.status in ("created", "updated"):
        ui.info("Codex: rebuilt hooks.json managed hooks")


def _rebuild_settings(manifest_path: Path, claude_dir: Path, catalog: Path) -> None:
    """Reassemble ``settings.json`` while preserving user edits.

    Strips previously-owned entries from existing settings, then merges
    remaining fragments into the user-only base, and records new
    ownership (delete if empty).
    """
    packages = manifest.get_packages(manifest_path)
    fragments = collect_domain_fragments(packages, catalog)
    settings_path = claude_dir / "settings.json"

    existing = (
        load_fragment(settings_path)
        if settings_path.is_file() and not settings_path.is_symlink()
        else {}
    )
    prev_ownership = load_settings_ownership(claude_dir)
    user_base = strip_owned(existing, prev_ownership)
    settings = assemble_settings(fragments, base=user_base)
    new_ownership = collect_fragment_contributions(fragments)

    if settings:
        if settings_path.is_symlink():
            settings_path.unlink()
        write_settings(settings, settings_path)
    elif settings_path.exists() or settings_path.is_symlink():
        settings_path.unlink()

    if settings_ownership_is_empty(new_ownership):
        delete_settings_ownership(claude_dir)
    else:
        save_settings_ownership(claude_dir, new_ownership)


def _domain_still_installed_globally(domain_name: str) -> bool:
    """True if ``@<domain_name>`` is still listed in the global manifest."""
    spec = f"@{domain_name}"
    try:
        return spec in manifest.get_packages(global_manifest_path())
    except AiDotfilesError:
        return False
    except OSError:
        return False


def _maybe_tear_down_runtimes(
    elements: list[Element], removed_set: set[str], catalog: Path
) -> None:
    """Drop venv + shims for domains that are no longer installed anywhere.

    A project-scope remove keeps the runtime around when the domain still
    appears in the global manifest (a parallel global install would
    rely on it). A global-scope remove always tears down — local projects
    will re-provision on their next ``install``.
    """
    for el in elements:
        if el.type is not ElementType.DOMAIN or el.raw not in removed_set:
            continue
        if _domain_still_installed_globally(el.name):
            continue
        removed = tear_down_domain_runtime(catalog, el.name)
        if not removed:
            continue
        for name in removed:
            ui.info(f"  - bin/{name} (shim removed)")
        joined = ", ".join(removed)
        catalog_bin = catalog / el.name / "bin"
        ui.warn(
            f"@{el.name}: removed shim(s) {joined} from {bin_dir()}. "
            f"If another project still uses this CLI, either re-add @{el.name} "
            f"globally, or add the catalog bin dir to PATH:\n"
            f'    export PATH="{catalog_bin}:$PATH"'
        )


def _maybe_sync_gitignore(
    *,
    project_root: Path | None,
    claude_dir: Path,
    manifest_path: Path,
    no_gitignore: bool,
) -> None:
    """Regenerate the managed .gitignore block unless opted out."""
    if project_root is None or no_gitignore:
        return
    if not manifest.get_flag(manifest_path, "manage_gitignore", True):
        return
    if not manifest.get_flag(global_manifest_path(), "manage_gitignore", True):
        return
    paths = collect_managed_paths(claude_dir, storage_root())
    sync_gitignore(project_root, paths)


@click.command()
@click.argument(
    "packages",
    nargs=-1,
    required=True,
    shell_complete=make_completer(complete_installed_specifiers),
)
@click.option(
    "-g", "--global", "is_global", is_flag=True, help="Operate on global manifest."
)
@click.option(
    "--no-gitignore",
    is_flag=True,
    help="Do not touch .gitignore even if the project manages vendored "
    "symlink paths.",
)
@click.option(
    "--force",
    is_flag=True,
    help=(
        "Remove even if other manifest entries declare a dependency on "
        "the target. The dependents stay installed but their declared "
        "dependency will become missing."
    ),
)
def remove(
    packages: tuple[str, ...],
    is_global: bool,
    no_gitignore: bool,
    force: bool,
) -> None:
    """Remove PACKAGES from the manifest and unlink their elements."""
    try:
        elements = parse_elements(list(packages))

        catalog = catalog_dir()
        manifest_path, claude_dir, project_root = _resolve_scope(is_global)
        # Both scopes honour the manifest's `targets` (the global Codex
        # target superseded ADR ai-1-3's project-only restriction); the
        # global scope is always symlink-mode (its `.claude/` sits next
        # to the catalog).
        targets = manifest.get_targets(manifest_path)
        link_mode = "symlink" if is_global else manifest.get_link_mode(manifest_path)
        codex_layout = (
            (
                project_layout(project_root)
                if project_root is not None
                else global_layout()
            )
            if "codex" in targets
            else None
        )

        if not force:
            _check_reverse_deps(manifest_path, catalog, elements)

        raw_items = [element.raw for element in elements]
        removed = manifest.remove_packages(manifest_path, raw_items)
        removed_set = set(removed)

        manifest_name = manifest_path.name

        if not removed:
            ui.warn(f"None of these packages were installed in {manifest_name}")
            return

        ui.info(f"Removed from {manifest_name}:")
        for element in elements:
            if element.raw in removed_set:
                if "claude" in targets:
                    _unlink_element(element, claude_dir, catalog, link_mode)
                if codex_layout is not None:
                    _unlink_codex_element(element, codex_layout, catalog)
                ui.info(f"  - {element.raw}")
            else:
                ui.info(f"  ~ {element.raw} (not installed)")

        had_domain = any(
            el.type is ElementType.DOMAIN for el in elements if el.raw in removed_set
        )
        if codex_layout is not None:
            _rebuild_codex_config(manifest_path, codex_layout.codex_dir, catalog)
        if "claude" in targets:
            if project_root is not None:
                rebuild_claude_config(
                    manifest_path=manifest_path,
                    claude_dir=claude_dir,
                    catalog=catalog,
                    project_root=project_root,
                    backup_root=backup_dir(),
                    warn=ui.warn,
                )
            else:
                _rebuild_settings(manifest_path, claude_dir, catalog)
            if had_domain:
                ui.info(f"Settings: rebuilt {claude_dir.name}/settings.json")
        # Domain runtimes (venv + bin shims) are target-agnostic — they
        # are provisioned for any target, so tear them down regardless.
        if had_domain:
            _maybe_tear_down_runtimes(elements, removed_set, catalog)

        _maybe_sync_gitignore(
            project_root=project_root,
            claude_dir=claude_dir,
            manifest_path=manifest_path,
            no_gitignore=no_gitignore,
        )

    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)
