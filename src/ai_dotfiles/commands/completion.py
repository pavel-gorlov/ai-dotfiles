"""``ai-dotfiles completion`` — install shell tab completion.

Uses Click's built-in completion machinery. ``install`` writes the generated
script under ``~/.ai-dotfiles/completions/`` and patches the user's rc file
(``~/.bashrc`` / ``~/.zshrc``) with a marker-guarded source block so the
block can be removed cleanly by ``uninstall`` and is not duplicated on
re-run.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click
from click.shell_completion import BashComplete, ShellComplete, ZshComplete

from ai_dotfiles import ui
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError
from ai_dotfiles.core.paths import completion_dir

_SUPPORTED_SHELLS = ("bash", "zsh")
_MARKER_START = "# >>> ai-dotfiles completion >>>"
_MARKER_END = "# <<< ai-dotfiles completion <<<"
_COMPLETE_VAR = "_AI_DOTFILES_COMPLETE"
_PROG_NAME = "ai-dotfiles"


def _detect_shell() -> str:
    """Return the basename of ``$SHELL`` if supported, else raise."""
    shell_path = os.environ.get("SHELL", "")
    if not shell_path:
        raise ConfigError(
            "Cannot detect shell: $SHELL is not set. "
            "Pass --shell bash|zsh explicitly."
        )
    name = os.path.basename(shell_path)
    if name not in _SUPPORTED_SHELLS:
        raise ConfigError(
            f"Unsupported shell {name!r}. Supported: {', '.join(_SUPPORTED_SHELLS)}. "
            "Pass --shell bash|zsh to override."
        )
    return name


def _rc_path(shell: str) -> Path:
    if shell == "bash":
        return Path.home() / ".bashrc"
    if shell == "zsh":
        return Path.home() / ".zshrc"
    raise ConfigError(f"Unsupported shell: {shell!r}")


def _complete_class(shell: str) -> type[ShellComplete]:
    if shell == "bash":
        return BashComplete
    if shell == "zsh":
        return ZshComplete
    raise ConfigError(f"Unsupported shell: {shell!r}")


def _generate_script(shell: str) -> str:
    # Import here to avoid circular import (cli imports this module).
    from ai_dotfiles.cli import cli as root_cli

    cls = _complete_class(shell)
    complete = cls(root_cli, {}, _PROG_NAME, _COMPLETE_VAR)
    return complete.source()


def _script_path(shell: str) -> Path:
    return completion_dir() / f"ai-dotfiles.{shell}"


def _source_block(script_path: Path) -> str:
    quoted = str(script_path).replace('"', '\\"')
    return (
        f"{_MARKER_START}\n"
        f'[ -f "{quoted}" ] && source "{quoted}"\n'
        f"{_MARKER_END}\n"
    )


def _strip_existing_block(text: str) -> str:
    """Remove any existing ai-dotfiles completion block from ``text``."""
    if _MARKER_START not in text:
        return text
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    skipping = False
    for line in lines:
        stripped = line.rstrip("\n")
        if stripped == _MARKER_START:
            skipping = True
            continue
        if skipping:
            if stripped == _MARKER_END:
                skipping = False
            continue
        out.append(line)
    return "".join(out)


def _patch_rc(rc_path: Path, block: str) -> bool:
    """Write ``block`` to ``rc_path``, replacing any existing block.

    Returns True if a block was newly added, False if it was just refreshed.
    """
    existing = rc_path.read_text(encoding="utf-8") if rc_path.is_file() else ""
    had_block = _MARKER_START in existing
    cleaned = _strip_existing_block(existing)
    if cleaned and not cleaned.endswith("\n"):
        cleaned += "\n"
    new_text = cleaned + block
    rc_path.parent.mkdir(parents=True, exist_ok=True)
    rc_path.write_text(new_text, encoding="utf-8")
    return not had_block


def _remove_from_rc(rc_path: Path) -> bool:
    """Strip the marker block from ``rc_path``. Returns True if something changed."""
    if not rc_path.is_file():
        return False
    existing = rc_path.read_text(encoding="utf-8")
    if _MARKER_START not in existing:
        return False
    cleaned = _strip_existing_block(existing)
    rc_path.write_text(cleaned, encoding="utf-8")
    return True


@click.group("completion")
def completion() -> None:
    """Install or remove shell tab completion for ai-dotfiles."""


@completion.command("install")
@click.option(
    "--shell",
    "shell_name",
    type=click.Choice(list(_SUPPORTED_SHELLS)),
    default=None,
    help="Target shell (auto-detected from $SHELL if omitted).",
)
@click.option(
    "--print",
    "print_only",
    is_flag=True,
    help="Print the completion script to stdout without touching any files.",
)
def install(shell_name: str | None, print_only: bool) -> None:
    """Install tab completion into ~/.bashrc or ~/.zshrc."""
    try:
        shell = shell_name or _detect_shell()
        script = _generate_script(shell)

        if print_only:
            click.echo(script)
            return

        script_path = _script_path(shell)
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script, encoding="utf-8")
        ui.success(f"Wrote completion script to {script_path}")

        rc_path = _rc_path(shell)
        added = _patch_rc(rc_path, _source_block(script_path))
        verb = "Added" if added else "Refreshed"
        ui.success(f"{verb} completion block in {rc_path}")

        if shell == "zsh":
            ui.info(
                "  Note: zsh completion requires compinit. "
                "Ensure 'autoload -Uz compinit && compinit' runs before the block."
            )
        ui.info(f"  Restart your shell or run: source {rc_path}")
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)


@completion.command("uninstall")
@click.option(
    "--shell",
    "shell_name",
    type=click.Choice(list(_SUPPORTED_SHELLS)),
    default=None,
    help="Target shell (auto-detected from $SHELL if omitted).",
)
def uninstall(shell_name: str | None) -> None:
    """Remove tab completion from ~/.bashrc or ~/.zshrc."""
    try:
        shell = shell_name or _detect_shell()

        rc_path = _rc_path(shell)
        removed = _remove_from_rc(rc_path)
        if removed:
            ui.success(f"Removed completion block from {rc_path}")
        else:
            ui.warn(f"No completion block found in {rc_path}")

        script_path = _script_path(shell)
        if script_path.is_file():
            script_path.unlink()
            ui.success(f"Deleted {script_path}")
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)
