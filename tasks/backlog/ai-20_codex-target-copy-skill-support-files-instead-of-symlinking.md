---
id: ai-20
kind: task
status: backlog
created_at: '2026-05-17T19:19:20+00:00'
parent: ai-1
dependencies: []
---

# Codex target: copy skill support files instead of symlinking

## Context

A Codex skill is installed as `.agents/skills/<name>/` = a real directory
with a generated `SKILL.md` + a `.ai-dotfiles-meta` sidecar, but its
support sub-dirs (`scripts/`, `references/`, `assets/`) are **symlinked**
into the catalog (`~/.ai-dotfiles/catalog/...`).

On a project that lives on a different filesystem from the catalog —
e.g. a Windows project (`/mnt/c/...`) while the catalog is in WSL — the
symlink targets WSL paths a native-Windows Codex cannot resolve. The
support dirs appear broken.

Everything else the Codex target writes is a real, self-contained file.
The support-file symlink is the lone inconsistency. The Codex target
should be **fully self-contained**.

## What to do

The Codex target **copies** skill support files instead of symlinking
them — unconditionally (no flag, no detection). The Codex target's
design is "generated, self-contained artefacts"; copying support files
makes `.agents/skills/<name>/` entirely real files.

- `core/codex_install.py` — where it currently symlinks the skill's
  support items (`scripts/`, `references/`, `assets/`, any non-`SKILL.md`
  entry), `shutil.copytree` / `copy2` them instead. Preserve executable
  bits on scripts.
- `remove` / `install --prune` — a managed skill dir is already
  identified by the `.ai-dotfiles-meta` sidecar and removed wholesale;
  confirm copied support files are covered (they are, the whole dir
  goes).
- Re-install must refresh copied support files (overwrite cleanly).
- Factor the copy helper so ai-21 (Claude copy mode) can reuse it if
  practical — coordinate via this task's notes.

## Acceptance criteria

- [ ] Codex skill support files (`scripts/`, `references/`, `assets/`) are copied into `.agents/skills/<name>/`, not symlinked.
- [ ] After install there are no symlinks anywhere under `.agents/skills/`.
- [ ] Executable bits on copied `scripts/` are preserved.
- [ ] Re-install refreshes copied support files; `remove` deletes them with the skill dir.
- [ ] A test asserts `.agents/skills/` contains no symlinks after install.
- [ ] `poetry run pytest`, `mypy src/`, `ruff check`, `black --check` all green.
- [ ] PR opened against `main`.

## Anti-patterns

- Adding a flag / detection — the Codex target always copies; keep it
  unconditional and simple.
