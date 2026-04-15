# Step 2b: core/elements.py

## Goal

Parse element specifiers (`@domain`, `skill:name`, `agent:name`, `rule:name`) and resolve them to filesystem paths in the catalog.

## File: `src/ai_dotfiles/core/elements.py`

### Data structures

```python
from enum import Enum
from dataclasses import dataclass
from pathlib import Path

class ElementType(Enum):
    DOMAIN = "domain"
    SKILL = "skill"
    AGENT = "agent"
    RULE = "rule"

@dataclass(frozen=True)
class Element:
    type: ElementType
    name: str
    raw: str  # original string, e.g. "@python" or "skill:code-review"
```

### Functions

```python
def parse_element(s: str) -> Element:
    """Parse element specifier string.
    
    Formats:
      @domain     -> Element(DOMAIN, "domain", "@domain")
      skill:name  -> Element(SKILL, "name", "skill:name")
      agent:name  -> Element(AGENT, "name", "agent:name")
      rule:name   -> Element(RULE, "name", "rule:name")
    
    Raises click.ElementError on invalid format.
    """

def parse_elements(items: list[str]) -> list[Element]:
    """Parse multiple specifiers. Convenience wrapper."""

def resolve_source_path(element: Element, catalog: Path) -> Path:
    """Return the source path in catalog/ for an element.
    
    DOMAIN  -> catalog/<name>/
    SKILL   -> catalog/skills/<name>/
    AGENT   -> catalog/agents/<name>.md
    RULE    -> catalog/rules/<name>.md
    """

def resolve_target_paths(element: Element, claude_dir: Path, catalog: Path) -> list[tuple[Path, Path]]:
    """Return list of (source, target) pairs for symlinking.
    
    For DOMAIN: iterate subdirs skills/, agents/, rules/, hooks/ inside
    catalog/<domain>/. For each item found, create a pair:
      - skills/foo/  -> claude_dir/skills/foo
      - agents/bar.md -> claude_dir/agents/bar.md
      - rules/baz.md -> claude_dir/rules/baz.md
      - hooks/qux.sh -> claude_dir/hooks/qux.sh
    Skip README.md files. Skip settings.fragment.json (handled separately).
    
    For SKILL:  [(catalog/skills/<name>, claude_dir/skills/<name>)]
    For AGENT:  [(catalog/agents/<name>.md, claude_dir/agents/<name>.md)]
    For RULE:   [(catalog/rules/<name>.md, claude_dir/rules/<name>.md)]
    """

def validate_element_exists(element: Element, catalog: Path) -> None:
    """Check that the source path exists. Raise click.UsageError if not."""
```

### Edge cases

- Domain name must not start with `_` when used in manifests (reserved for `_example`)
- Element names: allow alphanumeric, hyphens, underscores. No slashes or dots.
- `skill:name` resolves to a directory (`catalog/skills/<name>/`), not a file
- `agent:name` and `rule:name` resolve to `.md` files

## File: `tests/test_elements.py`

### Test cases

1. `test_parse_domain` — `@python` -> Element(DOMAIN, "python", "@python")
2. `test_parse_skill` — `skill:code-review` -> Element(SKILL, "code-review", ...)
3. `test_parse_agent` — `agent:researcher` -> Element(AGENT, "researcher", ...)
4. `test_parse_rule` — `rule:security` -> Element(RULE, "security", ...)
5. `test_parse_invalid_no_prefix` — `"foobar"` raises ElementError
6. `test_parse_invalid_unknown_type` — `"hook:foo"` raises ElementError
7. `test_parse_elements_multiple` — list of mixed types
8. `test_resolve_source_domain` — returns `catalog/<name>/`
9. `test_resolve_source_skill` — returns `catalog/skills/<name>/`
10. `test_resolve_source_agent` — returns `catalog/agents/<name>.md`
11. `test_resolve_source_rule` — returns `catalog/rules/<name>.md`
12. `test_resolve_target_domain` — creates pairs for skills/, agents/, rules/, hooks/ contents
13. `test_resolve_target_domain_skips_readme` — README.md not in output
14. `test_resolve_target_domain_skips_settings_fragment` — settings.fragment.json not in output
15. `test_resolve_target_standalone` — single pair for skill/agent/rule
16. `test_validate_exists_ok` — existing element passes
17. `test_validate_exists_missing` — missing element raises UsageError

## Dependencies

- `click` (for error types)
- `pathlib` (stdlib)

## Definition of Done

- [ ] `src/ai_dotfiles/core/elements.py` exists with all classes and functions
- [ ] `tests/unit/test_elements.py` exists with all 17 test cases
- [ ] `poetry run pytest tests/unit/test_elements.py -v` — all tests pass
- [ ] `poetry run mypy src/ai_dotfiles/core/elements.py` — passes strict mode
- [ ] All public functions have type annotations (params + return)
- [ ] Invalid inputs raise `ElementError` (from `core.errors`), not unhandled exceptions

## Commit

Part of batch commit after all Step 2 sub-tasks complete.
