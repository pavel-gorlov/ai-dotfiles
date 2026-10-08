"""Thin managed DSH command; native composition and process work live in core."""

from __future__ import annotations

import os
from pathlib import Path

import click

from ai_dotfiles import ui
from ai_dotfiles.commands._dsh_report import print_dsh_diagnostics
from ai_dotfiles.core.dsh_launch import (
    RESTART_NOTICE,
    execute_dsh_launch,
    prepare_dsh_launch,
)
from ai_dotfiles.core.errors import AiDotfilesError


@click.group()
def dsh() -> None:
    """Manage DeepSeek Harness activation."""


@dsh.command(
    context_settings={"ignore_unknown_options": True, "allow_interspersed_args": False}
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.option(
    "--strict",
    is_flag=True,
    help="Refuse skipped DSH elements; place this option before native flags.",
)
def launch(args: tuple[str, ...], strict: bool = False) -> None:
    """Launch an existing official DSH RC2 profile with audited managed patches.

    Put managed --strict first when needed, then native launcher flags:
    --profile NAME [--patch PATH ...],
    followed by verbatim application arguments. NAME is also accepted as the
    native profile shorthand. Profiles are not created or repaired. One process
    stays bound to the current project's MCP, hooks and agents; restart after
    managed updates or project changes. Web switching is not hard isolation.
    Native hot reload is disabled. RC2 headless requires a preset-free profile.

    Example: ai-dotfiles dsh launch --profile headless "run the tests"
    """
    try:
        env = dict(os.environ)
        plan = prepare_dsh_launch(args, cwd=Path.cwd(), process_env=env, strict=strict)
        print_dsh_diagnostics(plan.diagnostics, strict=strict)
        ui.info(RESTART_NOTICE, err=True)
        code = execute_dsh_launch(plan, process_env=env)
    except AiDotfilesError as exc:
        ui.error(str(exc))
        raise SystemExit(exc.exit_code) from exc
    raise SystemExit(code)
