"""Scaffold generator.

Reads template files bundled as package data under
``ai_dotfiles.scaffold.templates`` and materializes them on disk, either as
the full storage tree (``ai-dotfiles init -g``) or as a single new element
(``ai-dotfiles create skill|agent|rule``).

Placeholder substitution is intentionally trivial: ``{{name}}`` is replaced
verbatim via :func:`str.replace`.
"""

from __future__ import annotations

import json
import stat
from importlib import resources
from pathlib import Path

_TEMPLATE_PKG = "ai_dotfiles.scaffold.templates"


def _read_template(name: str) -> str:
    """Read a template file from package data as text."""
    return resources.files(_TEMPLATE_PKG).joinpath(name).read_text(encoding="utf-8")


def _chmod_plus_x(path: Path) -> None:
    current = path.stat().st_mode
    path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _apply_replacements(text: str, replacements: dict[str, str] | None) -> str:
    if not replacements:
        return text
    for key, value in replacements.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def _write_template(
    name: str,
    dest: Path,
    replacements: dict[str, str] | None = None,
) -> None:
    """Read ``name`` from package data, apply replacements, write to ``dest``.

    Creates parent directories as needed. If ``dest`` ends in ``.sh``, sets
    the executable bit on the written file.
    """
    content = _apply_replacements(_read_template(name), replacements)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    if dest.suffix == ".sh":
        _chmod_plus_x(dest)


def generate_storage_scaffold(root: Path) -> None:
    """Create the full storage directory structure at ``root``.

    Idempotent with respect to directories (``mkdir(exist_ok=True)``) but
    **overwrites** any scaffold files already present.
    """
    root.mkdir(parents=True, exist_ok=True)

    # global/
    global_dir = root / "global"
    _write_template("global_readme.md", global_dir / "README.md")
    _write_template("global_claude.md", global_dir / "CLAUDE.md")
    _write_template("global_settings.json", global_dir / "settings.json")

    hooks_dir = global_dir / "hooks"
    _write_template("global_hooks_readme.md", hooks_dir / "README.md")
    _write_template("post_edit_lint.sh", hooks_dir / "post-edit-lint.sh")
    _write_template("pre_commit_check.sh", hooks_dir / "pre-commit-check.sh")

    styles_dir = global_dir / "output-styles"
    _write_template("output_styles_readme.md", styles_dir / "README.md")
    _write_template("concise_ru.md", styles_dir / "concise-ru.md")

    # global.json
    global_manifest = root / "global.json"
    if not global_manifest.exists():
        global_manifest.write_text(
            json.dumps({"packages": []}, indent=2) + "\n", encoding="utf-8"
        )

    # catalog/
    catalog_dir = root / "catalog"
    _write_template("catalog_readme.md", catalog_dir / "README.md")

    example_dir = catalog_dir / "_example"
    _write_template(
        "example_skill.md",
        example_dir / "skills" / "example-skill" / "SKILL.md",
    )
    _write_template(
        "example_agent.md",
        example_dir / "agents" / "example-agent.md",
    )
    _write_template(
        "example_rule.md",
        example_dir / "rules" / "example-style.md",
    )
    _write_template(
        "example_hook.sh",
        example_dir / "hooks" / "example-lint.sh",
    )
    _write_template(
        "example_settings_fragment.json",
        example_dir / "settings.fragment.json",
    )

    for sub in ("skills", "agents", "rules"):
        (catalog_dir / sub).mkdir(parents=True, exist_ok=True)

    # stacks/
    stacks_dir = root / "stacks"
    _write_template("stacks_readme.md", stacks_dir / "README.md")
    _write_template("example_stack.conf", stacks_dir / "_example.conf")

    # root-level files
    _write_template("root_readme.md", root / "README.md")
    _write_template("gitignore", root / ".gitignore")


def generate_project_manifest(root: Path) -> None:
    """Create ``<root>/ai-dotfiles.json`` with an empty packages list.

    Does nothing if the manifest already exists.
    """
    manifest = root / "ai-dotfiles.json"
    if manifest.exists():
        return
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"packages": []}, indent=2) + "\n", encoding="utf-8")


def generate_element_from_template(
    element_type: str,
    name: str,
    dest: Path,
) -> Path:
    """Create a new element file from its template.

    - ``skill`` — ``dest`` is treated as a directory; ``dest/SKILL.md`` is
      written.
    - ``agent`` / ``rule`` — ``dest`` is the target ``.md`` file itself.

    ``{{name}}`` is replaced with ``name`` in the template.
    """
    replacements = {"name": name}
    if element_type == "skill":
        out = dest / "SKILL.md"
        _write_template("skill_template.md", out, replacements)
        return out
    if element_type == "agent":
        _write_template("agent_template.md", dest, replacements)
        return dest
    if element_type == "rule":
        _write_template("rule_template.md", dest, replacements)
        return dest
    raise ValueError(f"Unknown element_type: {element_type!r}")
