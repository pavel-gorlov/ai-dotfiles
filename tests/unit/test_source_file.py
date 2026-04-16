"""Unit tests for ai_dotfiles.vendors.source_file."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_dotfiles.core.errors import ConfigError
from ai_dotfiles.vendors import source_file
from ai_dotfiles.vendors.base import SourceMeta


def _today() -> str:
    return datetime.now(tz=timezone.utc).date().isoformat()


# ── write ──────────────────────────────────────────────────────────────────


def test_write_happy_path(tmp_path: Path) -> None:
    source_file.write(
        tmp_path,
        vendor="github",
        origin="github:acme/tools/skills/x",
        tool="ai-dotfiles vendor",
        license="Apache-2.0",
    )

    written = (tmp_path / ".source").read_text(encoding="utf-8")
    assert "vendor: github\n" in written
    assert "origin: github:acme/tools/skills/x\n" in written
    assert "tool: ai-dotfiles vendor\n" in written
    assert f"fetched: {_today()}\n" in written
    assert "license: Apache-2.0\n" in written


def test_write_preserves_key_order(tmp_path: Path) -> None:
    source_file.write(
        tmp_path,
        vendor="github",
        origin="github:a/b",
        tool="ai-dotfiles vendor",
        license="MIT",
    )

    lines = (tmp_path / ".source").read_text(encoding="utf-8").splitlines()
    keys = [line.partition(":")[0] for line in lines if line]
    assert keys == ["vendor", "origin", "tool", "fetched", "license"]


def test_write_license_none_becomes_unknown(tmp_path: Path) -> None:
    source_file.write(
        tmp_path,
        vendor="github",
        origin="github:a/b",
        tool="ai-dotfiles vendor",
        license=None,
    )
    assert "license: unknown\n" in (tmp_path / ".source").read_text(encoding="utf-8")


def test_write_license_empty_string_becomes_unknown(tmp_path: Path) -> None:
    source_file.write(
        tmp_path,
        vendor="github",
        origin="github:a/b",
        tool="ai-dotfiles vendor",
        license="",
    )
    assert "license: unknown\n" in (tmp_path / ".source").read_text(encoding="utf-8")


def test_write_fetched_date_is_today(tmp_path: Path) -> None:
    source_file.write(
        tmp_path,
        vendor="github",
        origin="github:a/b",
        tool="ai-dotfiles vendor",
        license="MIT",
    )
    content = (tmp_path / ".source").read_text(encoding="utf-8")
    assert f"fetched: {_today()}" in content


def test_write_ends_with_newline(tmp_path: Path) -> None:
    source_file.write(
        tmp_path,
        vendor="github",
        origin="github:a/b",
        tool="ai-dotfiles vendor",
        license="MIT",
    )
    content = (tmp_path / ".source").read_text(encoding="utf-8")
    assert content.endswith("\n")


def test_write_empty_vendor_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="vendor"):
        source_file.write(
            tmp_path,
            vendor="",
            origin="github:a/b",
            tool="ai-dotfiles vendor",
            license="MIT",
        )


def test_write_empty_origin_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="origin"):
        source_file.write(
            tmp_path,
            vendor="github",
            origin="",
            tool="ai-dotfiles vendor",
            license="MIT",
        )


def test_write_empty_tool_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="tool"):
        source_file.write(
            tmp_path,
            vendor="github",
            origin="github:a/b",
            tool="",
            license="MIT",
        )


def test_write_overwrites_existing_file(tmp_path: Path) -> None:
    (tmp_path / ".source").write_text("stale content\n", encoding="utf-8")

    source_file.write(
        tmp_path,
        vendor="github",
        origin="github:a/b",
        tool="ai-dotfiles vendor",
        license="MIT",
    )

    content = (tmp_path / ".source").read_text(encoding="utf-8")
    assert "stale content" not in content
    assert "vendor: github" in content


# ── read ───────────────────────────────────────────────────────────────────


def test_read_missing_file_returns_none(tmp_path: Path) -> None:
    assert source_file.read(tmp_path) is None


def test_read_happy_path(tmp_path: Path) -> None:
    (tmp_path / ".source").write_text(
        "vendor: github\n"
        "origin: github:acme/tools\n"
        "tool: ai-dotfiles vendor\n"
        "fetched: 2026-04-15\n"
        "license: MIT\n",
        encoding="utf-8",
    )

    meta = source_file.read(tmp_path)

    assert meta == SourceMeta(
        vendor="github",
        origin="github:acme/tools",
        tool="ai-dotfiles vendor",
        fetched="2026-04-15",
        license="MIT",
    )


def test_read_tolerates_extra_whitespace(tmp_path: Path) -> None:
    (tmp_path / ".source").write_text(
        "  vendor:   github\n"
        "origin:github:a/b\n"
        "tool:  ai-dotfiles vendor  \n"
        "fetched:  2026-04-15\n"
        "license: MIT\n"
        "\n",
        encoding="utf-8",
    )

    meta = source_file.read(tmp_path)
    assert meta is not None
    assert meta.vendor == "github"
    assert meta.origin == "github:a/b"
    assert meta.tool == "ai-dotfiles vendor"


def test_read_malformed_missing_key_raises(tmp_path: Path) -> None:
    (tmp_path / ".source").write_text(
        "vendor: github\norigin: github:a/b\ntool: ai-dotfiles vendor\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="missing keys"):
        source_file.read(tmp_path)


def test_read_malformed_no_colon_raises(tmp_path: Path) -> None:
    (tmp_path / ".source").write_text(
        "vendor: github\nnot a kv line\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="key: value"):
        source_file.read(tmp_path)


def test_read_malformed_empty_value_raises(tmp_path: Path) -> None:
    (tmp_path / ".source").write_text(
        "vendor: github\n"
        "origin: \n"
        "tool: ai-dotfiles vendor\n"
        "fetched: 2026-04-15\n"
        "license: MIT\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="empty values"):
        source_file.read(tmp_path)


def test_round_trip_write_then_read(tmp_path: Path) -> None:
    source_file.write(
        tmp_path,
        vendor="github",
        origin="github:acme/tools/skills/x",
        tool="ai-dotfiles vendor",
        license="Apache-2.0",
    )

    meta = source_file.read(tmp_path)

    assert meta is not None
    assert meta.vendor == "github"
    assert meta.origin == "github:acme/tools/skills/x"
    assert meta.tool == "ai-dotfiles vendor"
    assert meta.fetched == _today()
    assert meta.license == "Apache-2.0"


def test_round_trip_with_none_license(tmp_path: Path) -> None:
    source_file.write(
        tmp_path,
        vendor="github",
        origin="github:a/b",
        tool="ai-dotfiles vendor",
        license=None,
    )

    meta = source_file.read(tmp_path)

    assert meta is not None
    assert meta.license == "unknown"
