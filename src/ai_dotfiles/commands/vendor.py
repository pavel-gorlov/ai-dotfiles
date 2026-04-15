"""``ai-dotfiles vendor`` — download external content from a GitHub URL.

Clones (or sparse-checks-out) the given GitHub URL into ``catalog/<kind>s/<name>/``
and writes a ``.source`` tracking file inside it describing the origin.

The command does **not** auto-add the vendored element to any manifest —
callers still need to run ``ai-dotfiles add <element>`` themselves.
"""

from __future__ import annotations

import shutil
import sys
from datetime import date
from pathlib import Path

import click

from ai_dotfiles import ui
from ai_dotfiles.core import git_ops
from ai_dotfiles.core.errors import AiDotfilesError, ConfigError, ElementError
from ai_dotfiles.core.paths import catalog_dir


def _owner_repo_from_url(repo_url: str) -> tuple[str, str]:
    """Extract ``(owner, repo)`` from the normalized repo URL.

    ``parse_github_url`` returns either:

    * ``https://github.com/<owner>/<repo>.git``
    * ``git@github.com:<owner>/<repo>.git``
    """
    if repo_url.startswith("git@"):
        _, _, tail = repo_url.partition(":")
    else:
        tail = repo_url.rsplit("github.com/", 1)[-1]
    owner, _, repo = tail.partition("/")
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    return owner, repo


def _source_file_content(owner: str, repo: str, subpath: str, fetched_on: str) -> str:
    origin_suffix = f"/{subpath}" if subpath else ""
    return (
        f"origin: github:{owner}/{repo}{origin_suffix}\n"
        f"fetched: {fetched_on}\n"
        f"tool: ai-dotfiles vendor\n"
        f"license: unknown\n"
    )


def _resolve_kind(staging: Path) -> str:
    """Return ``"skill"`` / ``"agent"`` / ``"rule"``; default to ``"skill"``."""
    kind = git_ops.detect_element_type(staging)
    return kind if kind is not None else "skill"


@click.command()
@click.argument("url")
@click.option(
    "-f",
    "--force",
    is_flag=True,
    help="Overwrite the destination directory if it already exists.",
)
def vendor(url: str, force: bool) -> None:
    """Download external content from a GitHub URL into catalog/."""
    staging: Path | None = None
    try:
        parsed = git_ops.parse_github_url(url)
        if parsed is None:
            raise ElementError(
                "Unrecognized GitHub URL. Supported formats:\n"
                "  https://github.com/<owner>/<repo>\n"
                "  https://github.com/<owner>/<repo>/tree/<branch>/<subpath>\n"
                "  git@github.com:<owner>/<repo>.git"
            )

        repo_url, branch, subpath, name = parsed
        owner, repo = _owner_repo_from_url(repo_url)

        catalog = catalog_dir()
        catalog.mkdir(parents=True, exist_ok=True)

        # Stage download in a tmp path inside catalog/ so we can sniff its type
        # before choosing the final sub-directory.
        staging = catalog / f".vendor-staging-{name}"
        if staging.exists():
            shutil.rmtree(staging)

        git_ops.git_sparse_checkout(repo_url, subpath, staging, branch=branch)

        kind = _resolve_kind(staging)
        kind_subdir = f"{kind}s"
        kind_dir = catalog / kind_subdir
        kind_dir.mkdir(parents=True, exist_ok=True)

        final_dest = kind_dir / name
        if final_dest.exists():
            if not force:
                raise ConfigError(
                    f"Destination already exists: catalog/{kind_subdir}/{name}. "
                    "Use --force to overwrite."
                )
            if final_dest.is_dir():
                shutil.rmtree(final_dest)
            else:
                final_dest.unlink()

        shutil.move(str(staging), str(final_dest))
        staging = None  # moved — nothing to clean up in ``finally``

        fetched_on = date.today().isoformat()
        content = _source_file_content(owner, repo, subpath, fetched_on)

        source_target: Path
        if final_dest.is_dir():
            source_target = final_dest / ".source"
        else:
            source_target = final_dest.with_name(final_dest.name + ".source")
        source_target.write_text(content, encoding="utf-8")

        ui.success(f"Downloaded to catalog/{kind_subdir}/{name}/")
        ui.info("Source tracked in .source")
        ui.info("")
        ui.info("Ready to use:")
        ui.info(f"  ai-dotfiles add {kind}:{name}")
    except AiDotfilesError as exc:
        ui.error(str(exc))
        sys.exit(exc.exit_code)
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
