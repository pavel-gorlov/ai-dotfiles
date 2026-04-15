# Step 5: commands/install.py

## Goal

Implement `ai-dotfiles install` (project) and `ai-dotfiles install -g` (global). Reads manifest, creates symlinks, assembles settings.json.

## File: `src/ai_dotfiles/commands/install.py`

### Command definition

```python
@click.command()
@click.option("-g", "--global", "is_global", is_flag=True)
def install(is_global: bool) -> None:
```

### Behavior: `ai-dotfiles install` (project)

1. Find project root via `paths.find_project_root()` — error if not found
2. Read manifest via `manifest.get_packages(paths.project_manifest_path(root))`
3. If packages empty, print "Nothing to install" and return
4. Parse all packages via `elements.parse_elements(packages)`
5. Validate all exist in catalog via `elements.validate_element_exists()`
6. Ensure `.claude/` dir exists in project root
7. For each element:
   - DOMAIN: call `symlinks.link_domain(source, project_claude_dir, backup_dir)`
   - SKILL/AGENT/RULE: call `symlinks.link_standalone(source, target, backup_dir)`
8. Collect settings fragments from domains: `settings_merge.collect_domain_fragments(packages, catalog)`
9. If fragments exist, assemble and write: `settings_merge.assemble_settings(fragments)` -> `.claude/settings.json`
10. Print summary: N packages installed, list of linked items

### Behavior: `ai-dotfiles install -g` (global)

1. Check storage exists — error if not
2. Link global files: `symlinks.link_global_files(global_dir, claude_global_dir, backup_dir)`
3. Read global manifest: `manifest.get_packages(global_manifest_path)`
4. For each package, parse and link into `~/.claude/`:
   - Same logic as project install but target is `claude_global_dir`
5. Print summary

### Output example

```
Installing from ai-dotfiles.json...
  + @python (3 skills, 1 agent, 2 hooks)
  + skill:code-review
  + agent:researcher
  + rule:security
  Settings: merged 1 domain fragment -> .claude/settings.json
Installed 4 packages.
```

### Edge cases

- Missing catalog entries: error with specific message "Package @foo not found in catalog"
- Broken symlinks from previous install: clean up and relink
- Empty hooks in fragment: don't create empty settings.json
- Project with no `.claude/` dir: create it

## File: `tests/test_install.py`

### Setup

Create a tmp catalog with test domain and standalone items. Use `tmp_storage` fixture.

### Test cases

1. `test_install_project_domain` — links skills/, agents/, rules/, hooks/ from domain
2. `test_install_project_standalone_skill` — links skill dir
3. `test_install_project_standalone_agent` — links agent .md
4. `test_install_project_standalone_rule` — links rule .md
5. `test_install_project_mixed` — domain + standalone together
6. `test_install_project_settings_merge` — settings.json assembled from domain fragment
7. `test_install_project_no_manifest` — error "ai-dotfiles.json not found"
8. `test_install_project_empty_packages` — "Nothing to install"
9. `test_install_project_missing_package` — error for missing catalog entry
10. `test_install_project_idempotent` — run twice, same result
11. `test_install_global` — links global files to ~/.claude/
12. `test_install_global_with_packages` — links global files + catalog items
13. `test_install_global_no_storage` — error "Storage not found"

## Dependencies

- `core.paths`, `core.elements`, `core.manifest`, `core.symlinks`, `core.settings_merge`
- `ui`

## Design note

Command is a thin wrapper. Catches `AiDotfilesError` subclasses and formats user-friendly output.

## Definition of Done

- [ ] `src/ai_dotfiles/commands/install.py` exists with install command
- [ ] Command registered in `cli.py`
- [ ] `tests/integration/test_install.py` exists with all 13 test cases
- [ ] `poetry run pytest tests/integration/test_install.py -v` — all tests pass
- [ ] `poetry run mypy src/ai_dotfiles/commands/install.py` — passes strict mode
- [ ] All public functions have type annotations
- [ ] Project install creates correct symlinks from manifest
- [ ] Global install links global/ files to ~/.claude/
- [ ] settings.json assembled from domain fragments
- [ ] Idempotent: running install twice = same result
- [ ] Errors produce user-friendly messages, not tracebacks

## Commit message

`feat: install command — symlink creation and settings assembly`
