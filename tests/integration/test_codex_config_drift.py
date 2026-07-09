"""Drift detection for the managed ``.codex/config.toml`` regions.

Covers :func:`ai_dotfiles.core.codex_config.config_state` — the config.toml
analogue of ``is_stale``. config.toml carries no source-sha header, so drift
is found by recomputing the expected managed content from the current domain
fragments and comparing it to what is on disk.
"""

import json
from pathlib import Path

import pytest

from ai_dotfiles.core import codex_config

pytestmark = pytest.mark.integration


def _settings_fragment(path: Path, allow: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"permissions": {"allow": allow}}), encoding="utf-8")


def test_config_state_absent_when_nothing_managed(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()

    assert codex_config.config_state(root, [], []) == "absent"


def test_config_state_ok_then_stale_on_fragment_change(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    frag = tmp_path / "dom" / "settings.fragment.json"
    _settings_fragment(frag, ["Bash(ls:*)"])
    pairs = [("dom", frag)]

    codex_config.write_codex_config(root, pairs)
    assert codex_config.config_state(root, pairs, []) == "ok"

    # A fragment gained a permission — the on-disk managed table is now stale.
    _settings_fragment(frag, ["Bash(ls:*)", "Bash(cat:*)"])
    assert codex_config.config_state(root, pairs, []) == "stale"

    # Regenerating brings it back in sync.
    codex_config.write_codex_config(root, pairs)
    assert codex_config.config_state(root, pairs, []) == "ok"


def test_config_state_stale_when_domain_dropped(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    frag = tmp_path / "dom" / "settings.fragment.json"
    _settings_fragment(frag, ["Bash(ls:*)"])
    codex_config.write_codex_config(root, [("dom", frag)])

    # The domain is gone from the manifest (no fragments), but its managed
    # table still sits in config.toml -> stale until a regenerating install.
    assert codex_config.config_state(root, [], []) == "stale"
