import click

from ai_dotfiles import __version__
from ai_dotfiles.commands.add import add
from ai_dotfiles.commands.create_delete import create, delete
from ai_dotfiles.commands.domain import domain
from ai_dotfiles.commands.init import init
from ai_dotfiles.commands.install import install
from ai_dotfiles.commands.list_cmd import list_cmd
from ai_dotfiles.commands.remove import remove
from ai_dotfiles.commands.stack import stack
from ai_dotfiles.commands.status import status
from ai_dotfiles.commands.vendor import vendor


@click.group()
@click.version_option(version=__version__, prog_name="ai-dotfiles")
def cli() -> None:
    """ai-dotfiles: package manager for Claude Code configuration."""


cli.add_command(init)
cli.add_command(install)
cli.add_command(add)
cli.add_command(remove)
cli.add_command(list_cmd)
cli.add_command(status)
cli.add_command(vendor)
cli.add_command(create)
cli.add_command(delete)
cli.add_command(domain)
cli.add_command(stack)
