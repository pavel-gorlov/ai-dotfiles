# Vendor Q3: docs + live smoke for buildwithclaude + tonsofskills

Document the two new vendors and prove them end-to-end against real
network + real git.

## File scope

- `README.md`
- `ai-dotfiles-blueprint.md`

## Do NOT touch

- Code / tests

## README updates

### Vendoring command table

Append two rows per vendor mirroring the existing `skills_sh`/`paks`
shape:

```
| `vendor buildwithclaude install <name> [--force]`    | ... |
| `vendor buildwithclaude list <name>`                 | ... |
| `vendor buildwithclaude search <query>`              | ... |
| `vendor buildwithclaude refresh [--force]`           | Re-fetch catalog cache |
| `vendor buildwithclaude deps check`                  | ... |
| `vendor tonsofskills install <name> [--force]`       | ... |
| ... (symmetric) ...
```

### Example block

Add after the existing `paks` example:

```markdown
#### Example: buildwithclaude

```bash
ai-dotfiles vendor buildwithclaude deps check
ai-dotfiles vendor buildwithclaude search typescript
ai-dotfiles vendor buildwithclaude install <name-from-search>
ai-dotfiles add skill:<name>
```

The catalog is cached under `~/.ai-dotfiles/.vendor-cache/` for 24h;
force a refresh with `vendor buildwithclaude refresh --force`.
```

Duplicate block for `tonsofskills`.

### Known limitations

Add bullets describing:
- Cache under `~/.ai-dotfiles/.vendor-cache/` grows on disk over time;
  `rm -rf ~/.ai-dotfiles/.vendor-cache/` is safe to free it
- Offline mode works against the last successful refresh
- Skills-only: plugin-level extras (hooks, agents bundled in plugins)
  are not imported; vendor installs only the `SKILL.md` directory

## Blueprint updates

`ai-dotfiles-blueprint.md` — extend the "Vendor plugins" section:

- Mention the two new vendors
- Note the `_repo_cache` shared layer (24h TTL, `refresh` subcommand)
- Add note that marketplace-backed vendors skip the upstream CLI and
  speak directly to the catalog repo (explaining why `ccpi` / `bwc-cli`
  aren't used)

## Live smoke (MUST run)

```bash
TMP=$(mktemp -d)
export AI_DOTFILES_HOME="$TMP/.ai-dotfiles"
mkdir -p "$AI_DOTFILES_HOME/catalog/skills"

echo '=== buildwithclaude ==='
ai-dotfiles vendor buildwithclaude deps check
ai-dotfiles vendor buildwithclaude refresh
# Pick some query likely to match
ai-dotfiles vendor buildwithclaude search git | head -15
# Grab first result name
FIRST=$(ai-dotfiles vendor buildwithclaude search git | head -1 | awk '{print $1}')
if [ -n "$FIRST" ]; then
  ai-dotfiles vendor buildwithclaude install "$FIRST"
  cat "$AI_DOTFILES_HOME/catalog/skills/$FIRST/.source"
fi

echo '=== tonsofskills ==='
ai-dotfiles vendor tonsofskills deps check
ai-dotfiles vendor tonsofskills refresh
ai-dotfiles vendor tonsofskills search typescript | head -15
FIRST=$(ai-dotfiles vendor tonsofskills search typescript | head -1 | awk '{print $1}')
if [ -n "$FIRST" ]; then
  ai-dotfiles vendor tonsofskills install "$FIRST"
  cat "$AI_DOTFILES_HOME/catalog/skills/$FIRST/.source"
fi

echo '=== installed ==='
ai-dotfiles vendor installed

rm -rf "$TMP"
```

Capture the output (paste in the commit message). Flag any surprises
as bullets under Known limitations.

## DoD

1. `poetry run pytest -q` — full suite green
2. `poetry run pre-commit run --all-files` — clean
3. Both live smokes complete end-to-end (or document the failure with
   root cause and add a Known-limitation bullet if an upstream repo
   quirk blocks it)
4. README + blueprint render cleanly (eyeball the diff)

Do NOT commit. Report files, smoke-run output, deviations.
