---
id: ai-6
kind: subtask
status: wip
created_at: '2026-05-17T07:09:43+00:00'
parent: ai-1
context_files:
- tests/integration/test_codex_target.py
- tests/e2e/test_codex_install.py
dependencies:
- ai-5
executor_agent: claude
---

# Codex target: Phase 1 tests

## Goal

Integration and e2e coverage for the Codex target — symlink + render
behaviour on a real temp filesystem, and the full CLI path via
`CliRunner`.

## Context files

- `tests/integration/test_codex_target.py` — **new.** Real `tmp_path`:
  `.agents/skills/<name>/` has a generated `SKILL.md` plus symlinked
  support files; `.codex/agents/<name>.toml` is generated; drift
  detection flips when a source agent changes; `remove` / `--prune`
  clean only managed files.
- `tests/e2e/test_codex_install.py` — **new.** Full CLI via
  `click.testing.CliRunner`: `install` / `add` / `remove` with
  `"targets": ["codex"]` and with `["claude", "codex"]`; a manifest
  without `targets` installs byte-identically (regression guard).

## Definition of done

- [ ] Integration test covers skill render+symlink, agent render, drift detection, remove/prune.
- [ ] e2e test covers `install`/`add`/`remove` for `codex` and `claude,codex` targets.
- [ ] Regression test: a manifest with no `targets` field installs identically to pre-change behaviour.
- [ ] Codex-target code coverage is at or above the project threshold (>= 80%).
- [ ] Full suite green: `pytest`, `mypy --strict`, `ruff`, `black`.

## Notes

- Use `tmp_path` and `conftest.py` fixtures — never touch the real `~/`.
- Tests encode the *contract* (ADR ai-1-1…ai-1-4 behaviour), not the
  shape of the implementation.
- Depends on ai-5 (the wired commands under test).
