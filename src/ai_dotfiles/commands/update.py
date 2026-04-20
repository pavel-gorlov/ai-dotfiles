"""``ai-dotfiles update`` — refresh CLI-managed files in storage.

Currently resyncs the built-in ``ai-dotfiles`` skill under
``~/.ai-dotfiles/catalog/skills/ai-dotfiles/SKILL.md`` from the template
shipped with the installed CLI. User-authored content (domain files,
custom skills/agents/rules, ``global/CLAUDE.md``, manifests) is never
touched.

Future extension point: a ``--self`` flag that upgrades the CLI itself
(pipx / pip). Not implemented yet — the immediate need is syncing the
built-in skill when the CLI version brings new frontmatter or command
docs.
"""

from __future__ import annotations

import sys

import click

from ai_dotfiles import ui
from ai_dotfiles.core import paths
from ai_dotfiles.core.errors import AiDotfilesError
from ai_dotfiles.scaffold.generator import sync_builtin_skill


@click.command()
def update() -> None:
    """Refresh CLI-managed files inside the global storage."""
    try:
        root = paths.storage_root()
        if not root.is_dir():
            ui.error(
                f"Storage not found at {root}. Run 'ai-dotfiles init -g' first."
            )
            sys.exit(1)
        dest = sync_builtin_skill(root)
        ui.success(f"Updated {dest}")
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)
