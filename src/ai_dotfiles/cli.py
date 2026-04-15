import click

from ai_dotfiles import __version__


@click.group()
@click.version_option(version=__version__, prog_name="ai-dotfiles")
def cli() -> None:
    """ai-dotfiles: package manager for Claude Code configuration."""
