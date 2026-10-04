---
id: ai-4m4hj
kind: subtask
status: done
created_at: '2026-10-04T11:57:42+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/core/dsh_hooks.py
- tests/unit/test_dsh_hooks.py
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
mode: write
phase: 3
status_history:
- at: '2026-10-04T11:57:42+00:00'
  status: backlog
- at: '2026-10-04T21:10:12+00:00'
  status: to_do
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-04T21:10:54+00:00'
  status: wip
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-04T21:44:59+00:00'
  status: done
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
---

# Translate supported DSH command hooks and resource bindings

## Goal

Produce one combined native hooks configuration and origin-bound resource plan for the seven supported command events.

Size driver: One hooks collector with matcher, protocol and path-binding tests.

## Scope and ownership

Mode: write. Phase 2 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 6, 9, 11; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/core/dsh_hooks.py
- tests/unit/test_dsh_hooks.py

## Definition of done

- [x] The seven matrix events combine across domains/scopes into one hooks.json using the native compatibility plugin.
- [x] Known exact tool matchers translate; event, matcher, handler/async/once and output compatibility gaps are reported before native parsing ignores them.
- [x] Handlers/support resources bind to their source origin and the launcher project without depending on a Claude install.
- [x] Required unsupported handler semantics are MANUAL; supported exit-2/context/Stop behaviour has test coverage.
- [x] Tests cover multiple domains, global/project bindings and every listed unsupported hook field.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.

## Execution notes

**backlog → to_do.** Queue the next serial Phase 2 owner after ai-ckvng commit
99a7e5daa7415756601f62003a680b7b929c1c34 is independently verified, parent b34cf40,
Git gates exit 0 and worktree/index clean. Composition focused 140/140 and
relevant regressions 790/790 pass; audit generator is 2. This two-file owner
collects original hook sources and returns ONE combined hooks contribution,
resources and precise diagnostics. Native actual host/launcher remains ai-vv1t9.

**to_do → wip.** tm ready/tm next select ai-4m4hj, parent ai-f2pvj,
mode write, phase 3; no competing writer or read fan-out. One worker receives
the complete tm context, approved epic and current orchestrator. Write ownership
is exactly core/dsh_hooks.py and tests/unit/test_dsh_hooks.py. Required native
behaviour evidence uses isolated temporary fixtures/public pinned APIs; unit
tests remain pure/mocked, and required final runtime acceptance stays open.

**Collector review → bounded origin resources.** Initial collector creates a
DshResource for the source's whole parent even when hooks are absent. For an
implicit global ~/.claude/settings.json this inventories/copies unrelated
sessions/projects; an implicit project-root source can sweep the repository.
Limit implicit local/global origins to guarded original input plus known
handler/support roots; do not materialize a parent tree for no-hook inputs.
An explicitly bounded catalog domain may reuse its complete domain resource.
Same two-file owner implements decisions 6/11, without a shell/resource parser
or new flag; mock unit evidence must cover unrelated parent state and no hooks.


**Review → acceptance.** Final two-file owner implements collect_dsh_hooks,
DshHookPlan.contribution/output and attach_dsh_hook_outputs. All original
sources combine global-first into one native hooks-claude-code row; raw inputs,
origin SHA and known handler subtrees remain guarded. Explicit bounded domain
resources may reuse the whole domain; implicit settings never sweep their parent.
Unsupported fields/required semantics produce precise MANUAL diagnostics before
native parsing. All seven events, both origins, matcher translation, exit-2,
context and Stop-next-turn behaviour have actual pinned native evidence.
Worker unit gate: 206/206; combined hooks/config/render/policy/Codex/settings/
installer/native suites: 830/830 (14.46s), no skips/xfails. The first combined
sandbox run refused loopback HTTP listen; the entire same gate then passed
with isolated-loopback escalation. This is environment evidence, not a source
failure or a weakened test. mypy src/: 82 files; Ruff/Black owned2: exit 0.
Coordinator independently repeats 206/206, type/style/whitespace and the complete
/private/tmp/ai-4m4hj-hooks-probe-vt7i6epp/run.mjs pinned native probe: exit 0,
7 events x 2 origins, 32 observations, 9 immutable roots/66 sentinel files.
Actual named-child invocation and same-host launcher readiness remain with
ai-vv1t9/ai-f2bcb; this hook probe proves the native live-context carrier only.
The final edit corrects a stale docstring, with no logic/test changes.

**wip → done.** tm acceptance reports 5/5 checked, exit 0; tm move done
exits 0. Prepare the two source/test files, this tick/move/usage and orchestrator
journal for one subtask commit. Completion is verified only after Git gates and
that commit succeed; launcher remains queued until then.

**Git gate → pinned formatting.** Pinned Black25.1 adds twelve trailing
commas to multiline test function parameters only. Coordinator inspected every
hunk and accepted; core is unchanged. Git owner repeats all206 hook unit tests
and required pre-commit/commit-msg/whitespace gates before the same commit.
Combined830/native evidence remains valid for this formatting-only edit.
