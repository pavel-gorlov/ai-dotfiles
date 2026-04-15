"""UI helpers wrapping click.secho (no print() allowed in src/)."""

from typing import Any

import click


def info(msg: str, **kwargs: Any) -> None:
    """Print an informational message (default color, to stdout)."""
    click.secho(msg, **kwargs)


def success(msg: str, **kwargs: Any) -> None:
    """Print a success message (green, prefix '+', to stdout)."""
    click.secho(f"+ {msg}", fg="green", **kwargs)


def warn(msg: str, **kwargs: Any) -> None:
    """Print a warning message (yellow, prefix '!', to stderr)."""
    click.secho(f"! {msg}", fg="yellow", err=True, **kwargs)


def error(msg: str, **kwargs: Any) -> None:
    """Print an error message (red, prefix 'x', to stderr)."""
    click.secho(f"x {msg}", fg="red", err=True, **kwargs)


def confirm(msg: str, default: bool = False) -> bool:
    """Prompt the user to confirm an action."""
    return click.confirm(msg, default=default)
