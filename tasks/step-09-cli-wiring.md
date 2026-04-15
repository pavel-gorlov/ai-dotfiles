# Step 9: CLI wiring

## Goal

Register all commands in `cli.py`, ensure `ai-dotfiles --help` shows everything correctly, and run full smoke tests.

## File: `src/ai_dotfiles/cli.py`

### Final structure

```python
import click
from ai_dotfiles import __version__

@click.group()
@click.version_option(version=__version__)
def cli():
    """ai-dotfiles — package manager for Claude Code configuration."""
    pass

# Top-level commands
from ai_dotfiles.commands.init import init
from ai_dotfiles.commands.install import install
from ai_dotfiles.commands.add import add
from ai_dotfiles.commands.remove import remove
from ai_dotfiles.commands.list_cmd import list_cmd
from ai_dotfiles.commands.status import status
from ai_dotfiles.commands.vendor import vendor
from ai_dotfiles.commands.create_delete import create, delete

cli.add_command(init)
cli.add_command(install)
cli.add_command(add)
cli.add_command(remove)
cli.add_command(list_cmd, "list")
cli.add_command(status)
cli.add_command(vendor)
cli.add_command(create)
cli.add_command(delete)

# Subcommand groups
from ai_dotfiles.commands.domain import domain
from ai_dotfiles.commands.stack import stack

cli.add_command(domain)
cli.add_command(stack)
```

### Expected `ai-dotfiles --help` output

```
Usage: ai-dotfiles [OPTIONS] COMMAND [ARGS]...

  ai-dotfiles — package manager for Claude Code configuration.

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  add       Add packages to manifest and create symlinks.
  create    Create a standalone element in catalog/.
  delete    Delete a standalone element from catalog/.
  domain    Manage domains in catalog/.
  init      Initialize project manifest or global storage.
  install   Install packages from manifest.
  list      List installed or available packages.
  remove    Remove packages from manifest and delete symlinks.
  stack     Manage configuration stacks.
  status    Validate symlinks and show hook summary.
  vendor    Download external content into catalog/.
```

### Expected `ai-dotfiles domain --help`

```
Commands:
  add     Add an element to a domain.
  create  Create a new domain.
  delete  Delete a domain.
  list    List domain contents.
  remove  Remove an element from a domain.
```

### Expected `ai-dotfiles stack --help`

```
Commands:
  add     Add elements to a stack.
  apply   Apply a stack to the current project.
  create  Create a new stack.
  delete  Delete a stack.
  list    List stack contents.
  remove  Remove elements from a stack.
```

## File: `tests/test_cli.py`

Smoke tests using CliRunner:

1. `test_version` — `--version` shows version
2. `test_help` — `--help` lists all commands
3. `test_help_domain` — `domain --help` lists subcommands
4. `test_help_stack` — `stack --help` lists subcommands
5. `test_all_commands_have_help` — iterate all commands, each has `--help`
6. `test_init_help` — `init --help` shows -g and --from options
7. `test_add_help` — `add --help` shows -g option and ITEMS argument

## Definition of Done

- [ ] All commands registered in `cli.py`
- [ ] `tests/e2e/test_cli.py` exists with all 7 test cases
- [ ] `poetry run pytest tests/e2e/test_cli.py -v` — all tests pass
- [ ] `ai-dotfiles --help` lists all commands
- [ ] `ai-dotfiles domain --help` lists subcommands
- [ ] `ai-dotfiles stack --help` lists subcommands
- [ ] `poetry run pytest` — full test suite passes
- [ ] `poetry run mypy src/` — entire src passes strict mode
- [ ] `poetry run ruff check src/ tests/` — no lint errors
- [ ] `poetry run black --check src/ tests/` — all formatted

## Commit message

`feat: wire all commands into CLI entry point`
