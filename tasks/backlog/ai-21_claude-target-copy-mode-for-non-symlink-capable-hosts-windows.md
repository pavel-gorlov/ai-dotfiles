---
id: ai-21
kind: task
status: backlog
created_at: '2026-05-17T19:19:20+00:00'
parent: ai-1
dependencies:
- ai-20
---

# Claude target: copy mode for non-symlink-capable hosts (Windows)

## Context

The Claude target installs `.claude/skills/`, `.claude/agents/`,
`.claude/rules/` as **symlinks** into the catalog
(`~/.ai-dotfiles/catalog/...`). On a Windows project whose catalog
lives in WSL, native Windows cannot resolve the WSL symlink targets —
all ~90 `.claude/` symlinks appear as broken / 0-byte files to a
native-Windows Claude Code.

Symlinks are the right default on Linux/WSL (a live view of the
catalog). The fix is an opt-in **copy mode** for hosts where symlinks
to the catalog won't resolve.

## What to do

Add a `link_mode` option to the project manifest:

- `ai-dotfiles.json` field `"link_mode": "symlink" | "copy"`, default
  `"symlink"` (every existing manifest unchanged). `core/manifest.py` —
  `get_link_mode(path)`.
- In `link_mode: "copy"`, `install` / `add` **copy** the catalog
  skill / agent / rule content into `.claude/` instead of symlinking.
  `remove` deletes the copies. Re-running `install` re-copies (a copy
  is a snapshot — it does not track the catalog live).
- Reuse the copy helper from ai-20 if one was factored.
- `status` — report copy-mode installs sensibly (a copy is not a
  symlink; the existing symlink-health check must not flag copies as
  broken / unmanaged).
- Optional, decide during implementation: auto-fall-back to copy when
  `os.symlink` raises `OSError` (Windows without Developer Mode). The
  explicit `link_mode` flag is the primary mechanism; auto-fallback is
  a safety net, not a replacement.
- Docs: `builtin_ai_dotfiles_skill.md` + `README.md` — document
  `link_mode`, when to use `copy` (Windows / cross-filesystem), and the
  snapshot (re-install to refresh) caveat.

## Acceptance criteria

- [ ] `manifest.get_link_mode()` returns `"symlink"` when the field is absent (backward compatible).
- [ ] With `link_mode: "copy"`, `install` / `add` copy skills/agents/rules into `.claude/`; no symlinks created.
- [ ] With `link_mode: "symlink"` (or absent), behaviour is byte-identical to today.
- [ ] `remove` cleans copy-mode installs; `status` does not misreport copies as broken.
- [ ] Docs (`builtin_ai_dotfiles_skill.md`, `README.md`) cover `link_mode`.
- [ ] `poetry run pytest`, `mypy src/`, `ruff check`, `black --check` all green.
- [ ] PR opened against `main`.

## Anti-patterns

- Making `copy` the default — symlink is the right Linux/WSL default;
  copy is opt-in.
- Forgetting that re-install must refresh copies — a copy is a
  snapshot, unlike a symlink.
