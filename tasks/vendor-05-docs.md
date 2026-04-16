# Vendor V5: docs + smoke

Document the new vendor framework and the two built-in vendors. Verify
end-to-end with a real-network smoke run against
`vercel-labs/skills`.

## File scope (exclusive)

- `README.md` — rewrite the "Vendoring" section
- `ai-dotfiles-blueprint.md` — add "Vendor plugins" section + note
  opt-in Node.js dependency

## Do NOT touch

- Any code file
- Any test file

## README changes

Replace the current `vendor URL` / `vendor -f URL` table with a
Vendoring section that documents:

### Command tree

- `vendor list` — registered vendors + dep status
- `vendor installed` — vendored items in catalog
- `vendor remove <name>` — remove a vendored item
- `vendor github install <url> [--force]`
- `vendor github list <url>`
- `vendor github deps check | install [--yes]`
- `vendor npx_skills install <source> [--force] [--select a,b]`
- `vendor npx_skills list <source>`
- `vendor npx_skills deps check | install [--yes]`

### Example (GitHub)

```bash
ai-dotfiles vendor github install \
  https://github.com/org/repo/tree/main/skills/my-skill
ai-dotfiles add skill:my-skill
```

### Example (npx skills)

```bash
# One-time: install Node.js
ai-dotfiles vendor npx_skills deps install

# Enumerate
ai-dotfiles vendor npx_skills list vercel-labs/skills

# Install one
ai-dotfiles vendor npx_skills install vercel-labs/skills --select document-skills
ai-dotfiles add skill:document-skills
```

### Known limitations

Update to reflect:
- `vendor github` requires `git` on PATH; `vendor npx_skills` requires
  Node.js/npx. Install-on-demand via `vendor <v> deps install`.
- No auto-update of vendored items yet.
- `vendor remove` is a no-op for symlinks in active projects — remove
  via `ai-dotfiles remove` first.

## ai-dotfiles-blueprint.md changes

Add a new section "Vendor plugins" describing:
- Registry-based architecture (`src/ai_dotfiles/vendors/`)
- `Vendor` protocol (name, display_name, description, deps,
  list_source, fetch)
- Shared services: `source_file`, `placement`, `deps`
- How to add a new vendor: create a module exposing a module-level
  `Vendor` instance, register in `vendors/__init__.py`
- Opt-in runtime deps: vendor-specific (git for github, Node.js for
  npx_skills). Core CLI has no external runtime deps.

## Smoke run (manual, after committing V4)

Requires Node.js on PATH. If absent: use `vendor npx_skills deps install`
first (run manually, not in the task spec).

```bash
TMP=$(mktemp -d)
export AI_DOTFILES_HOME="$TMP/.ai-dotfiles"

ai-dotfiles vendor list
ai-dotfiles init -g

# github
ai-dotfiles vendor github install \
  https://github.com/anthropics/skills/tree/main/document-skills \
  || echo "(may fail if anthropics/skills has no document-skills path)"

# npx skills
ai-dotfiles vendor npx_skills list vercel-labs/skills
ai-dotfiles vendor npx_skills install vercel-labs/skills --select <first-name>
cat "$AI_DOTFILES_HOME/catalog/skills/<first-name>/.source"

ai-dotfiles vendor installed

rm -rf "$TMP"
```

Document any surprises from the real run as "Known limitations" bullets.

## Definition of Done

1. `poetry run pytest -q` — full suite green
2. `poetry run pre-commit run --all-files` — clean
3. README renders correctly (manual eyeball)
4. Smoke run above produces no unexpected errors OR such errors are
   documented
5. `ai-dotfiles-blueprint.md` has "Vendor plugins" section

Do NOT commit.
