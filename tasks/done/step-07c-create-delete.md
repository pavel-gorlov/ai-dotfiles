# Step 7c: commands/create_delete.py

## Goal

Implement `ai-dotfiles create skill|agent|rule <name>` and `ai-dotfiles delete skill|agent|rule <name>` for standalone elements in catalog/.

## File: `src/ai_dotfiles/commands/create_delete.py`

### Command definitions

```python
@click.command()
@click.argument("element_type", type=click.Choice(["skill", "agent", "rule"]))
@click.argument("name")
def create(element_type: str, name: str) -> None:
    """Create a standalone element in catalog/."""

@click.command()
@click.argument("element_type", type=click.Choice(["skill", "agent", "rule"]))
@click.argument("name")
def delete(element_type: str, name: str) -> None:
    """Delete a standalone element from catalog/."""
```

### Behavior: `ai-dotfiles create skill my-linter`

1. Determine destination:
   - skill: `catalog/skills/my-linter/` (create dir)
   - agent: `catalog/agents/my-linter.md` (single file)
   - rule: `catalog/rules/my-linter.md` (single file)
2. Check if already exists — error if yes
3. Call `scaffold.generator.generate_element_from_template(element_type, name, dest)`
4. Print: `Created catalog/skills/my-linter/SKILL.md`

### Behavior: `ai-dotfiles delete skill my-linter`

1. Determine path (same as create)
2. Check if exists — error if not
3. Check usage in manifests and stacks:
   - Scan `ai-dotfiles.json` in current project (if exists)
   - Scan `global.json`
   - Scan all `.conf` files in `stacks/`
   - If found anywhere, warn: "skill:my-linter is used in: ai-dotfiles.json, stacks/backend.conf"
4. Confirm deletion (unless --force)
5. Delete: `shutil.rmtree` for skill dirs, `Path.unlink` for agent/rule files
6. Print: `Deleted catalog/skills/my-linter/`

### Usage checking helper

```python
def find_usage(element_raw: str, storage: Path, project_root: Path | None) -> list[str]:
    """Find where an element is referenced.
    Returns list of file paths where it appears."""
```

This helper is also used by domain delete and stack delete.

## File: `tests/test_create_delete.py`

1. `test_create_skill` — creates dir with SKILL.md
2. `test_create_agent` — creates .md file
3. `test_create_rule` — creates .md file
4. `test_create_already_exists` — error message
5. `test_create_template_has_name` — {{name}} replaced in content
6. `test_delete_skill` — removes dir
7. `test_delete_agent` — removes file
8. `test_delete_not_found` — error message
9. `test_delete_warns_if_used` — prints warning about usage
10. `test_find_usage_in_manifest` — finds in ai-dotfiles.json
11. `test_find_usage_in_stack` — finds in .conf file
12. `test_find_usage_nowhere` — returns empty list

## Definition of Done

- [ ] `src/ai_dotfiles/commands/create_delete.py` exists with create and delete commands
- [ ] `tests/e2e/test_create_delete.py` exists with all 12 test cases
- [ ] `poetry run pytest tests/e2e/test_create_delete.py -v` — all tests pass
- [ ] `poetry run mypy src/ai_dotfiles/commands/create_delete.py` — passes strict mode
- [ ] All public functions have type annotations
- [ ] Templates have `{{name}}` replaced with actual name
- [ ] delete warns when element is used in manifests/stacks
- [ ] `find_usage` helper works for manifests and stack .conf files

## Commit

Part of batch commit after all Step 7 sub-tasks complete.
