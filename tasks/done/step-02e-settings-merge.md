# Step 2e: core/settings_merge.py

## Goal

Assemble a single `settings.json` by deep-merging `settings.fragment.json` files from all connected domains. Hook arrays are concatenated by event key, not replaced.

## File: `src/ai_dotfiles/core/settings_merge.py`

### Functions

```python
import json
from pathlib import Path

def load_fragment(path: Path) -> dict:
    """Load a settings.fragment.json file.
    Return empty dict if file doesn't exist."""

def strip_meta(fragment: dict) -> dict:
    """Remove _domain and _description keys from a fragment.
    Returns a new dict (doesn't mutate input)."""

def deep_merge_hooks(base: dict, overlay: dict) -> dict:
    """Deep merge two settings dicts, concatenating hook arrays.
    
    For "hooks" key: each event (e.g. "PostToolUse", "PreToolUse") 
    contains a list of hook entries. Overlay entries are appended 
    to base entries for the same event.
    
    For other top-level keys: overlay overwrites base.
    
    Returns new dict.
    """

def assemble_settings(fragments: list[Path], base: dict | None = None) -> dict:
    """Load all fragments, strip meta fields, merge in sorted order.
    
    Sorting by fragment path ensures deterministic output regardless
    of filesystem ordering.
    
    If base is provided, start from base. Otherwise start from {}.
    """

def write_settings(settings: dict, target: Path) -> None:
    """Write assembled settings.json to target path.
    indent=2, trailing newline. Creates parent dirs if needed."""

def collect_domain_fragments(packages: list[str], catalog: Path) -> list[Path]:
    """Given a list of package specifiers, find all settings.fragment.json
    files from domains (@domain items). Returns list of paths.
    Standalone items (skill:, agent:, rule:) don't have fragments."""
```

### Merge example

Fragment 1 (`catalog/python/settings.fragment.json`):
```json
{
  "_domain": "python",
  "_description": "Ruff format for .py files",
  "hooks": {
    "PostToolUse": [{
      "matcher": "Edit|Write",
      "hooks": [{"type": "command", "command": "ruff-lint.sh"}]
    }]
  }
}
```

Fragment 2 (`catalog/go/settings.fragment.json`):
```json
{
  "_domain": "go",
  "_description": "Go format on save",
  "hooks": {
    "PostToolUse": [{
      "matcher": "Edit|Write",
      "hooks": [{"type": "command", "command": "gofmt.sh"}]
    }],
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{"type": "command", "command": "go-vet.sh"}]
    }]
  }
}
```

Result:
```json
{
  "hooks": {
    "PostToolUse": [
      {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "gofmt.sh"}]},
      {"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "ruff-lint.sh"}]}
    ],
    "PreToolUse": [
      {"matcher": "Bash", "hooks": [{"type": "command", "command": "go-vet.sh"}]}
    ]
  }
}
```

Note: `_domain` and `_description` stripped. PostToolUse arrays concatenated. Order is deterministic (sorted by domain name: "go" before "python").

## File: `tests/test_settings_merge.py`

### Test cases

1. `test_load_fragment_existing` — returns parsed JSON
2. `test_load_fragment_missing` — returns `{}`
3. `test_strip_meta` — removes `_domain`, `_description`, keeps rest
4. `test_strip_meta_no_meta` — dict without meta keys unchanged
5. `test_deep_merge_hooks_disjoint_events` — different events merged
6. `test_deep_merge_hooks_same_event` — same event arrays concatenated
7. `test_deep_merge_hooks_non_hook_keys` — overlay overwrites base
8. `test_deep_merge_hooks_empty_base` — overlay is result
9. `test_deep_merge_hooks_empty_overlay` — base is result
10. `test_assemble_single_fragment` — single fragment, meta stripped
11. `test_assemble_multiple_fragments` — arrays merged, deterministic order
12. `test_assemble_with_base` — base settings preserved, fragments merged on top
13. `test_assemble_empty_list` — returns base or `{}`
14. `test_write_settings` — correct JSON format written
15. `test_collect_domain_fragments` — finds fragment files from domain packages only

## Dependencies

- `json` (stdlib)
- `core.elements` — for parsing package specifiers in `collect_domain_fragments`

## Definition of Done

- [ ] `src/ai_dotfiles/core/settings_merge.py` exists with all functions
- [ ] `tests/unit/test_settings_merge.py` exists with all 15 test cases
- [ ] `poetry run pytest tests/unit/test_settings_merge.py -v` — all tests pass
- [ ] `poetry run mypy src/ai_dotfiles/core/settings_merge.py` — passes strict mode
- [ ] All public functions have type annotations (params + return)
- [ ] Merge output is deterministic (sorted by domain name)
- [ ] `_domain` and `_description` are stripped from output
- [ ] Hook arrays are concatenated, not replaced

## Commit

Part of batch commit after all Step 2 sub-tasks complete.
