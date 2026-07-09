"""``ai-dotfiles migrate`` — carry LOCAL project elements to the Codex target.

Thin wrapper: resolve the project, call
:func:`ai_dotfiles.core.codex_migrate.migrate_to_codex`, and format the
report. Local (hand-authored, non-catalog) skills/agents/rules are symlinked
where the format is unchanged and rendered where it changes; ``CLAUDE.md``
stays the canonical instruction file (Codex reads it via a fallback). Surfaces
with no Codex home (workflows, custom commands) are reported, not dropped
silently. ``--dry-run`` plans and classifies without writing.
"""

from __future__ import annotations

import click

from ai_dotfiles import ui
from ai_dotfiles.core import codex_migrate, manifest, paths
from ai_dotfiles.core.codex_migrate import MigrateReport
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError


@click.command("migrate")
@click.option(
    "--to",
    "target",
    type=click.Choice(["codex"]),
    default="codex",
    show_default=True,
    help="Target to migrate local elements to.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Plan and classify every action (and list Claude-only surfaces) "
    "without writing anything.",
)
def migrate(target: str, dry_run: bool) -> None:
    """Migrate local (non-catalog) .claude/ elements to the Codex target."""
    try:
        _run_migrate(dry_run=dry_run)
    except AiDotfilesError as exc:
        ui.error(str(exc))
        raise SystemExit(exc.exit_code) from exc


def _run_migrate(*, dry_run: bool) -> None:
    root = paths.find_project_root()
    if root is None or not paths.project_manifest_path(root).is_file():
        raise ConfigError("ai-dotfiles.json not found. Run 'ai-dotfiles init' first.")

    packages = manifest.get_packages(paths.project_manifest_path(root))
    report = codex_migrate.migrate_to_codex(
        root, manifest_packages=packages, dry_run=dry_run
    )
    _print_report(report)


def _print_report(report: MigrateReport) -> None:
    if not (
        report.actions
        or report.claude_only
        or report.fallback_changed
        or report.mcp_added
    ):
        ui.info("No local (non-catalog) elements to migrate to Codex.")
        return

    ui.info(
        "Dry run — local elements -> Codex:"
        if report.dry_run
        else "Local elements -> Codex:"
    )
    for action in report.actions:
        ui.success(
            f"  [{action.classification}] {action.strategy.ljust(12)} "
            f"{action.target_label}  ({action.note})"
        )
    if report.fallback_changed:
        ui.success(
            "  CLAUDE.md -> project_doc_fallback_filenames "
            "(Codex reads CLAUDE.md directly; trust the project once to enable)"
        )
    for name in report.mcp_added:
        ui.success(f"  MCP server '{name}' -> .codex/config.toml [mcp_servers]")

    if report.claude_only:
        ui.info("")
        ui.warn("Claude-only (no Codex target):")
        for label, reason in report.claude_only:
            ui.warn(f"  - {label}: {reason}")

    if report.dry_run:
        ui.info("")
        ui.info("Dry run: nothing written. Re-run without --dry-run to apply.")
