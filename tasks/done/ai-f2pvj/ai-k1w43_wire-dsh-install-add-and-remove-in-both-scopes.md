---
id: ai-k1w43
kind: subtask
status: done
created_at: '2026-10-04T11:57:43+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/commands/install.py
- src/ai_dotfiles/commands/add.py
- src/ai_dotfiles/commands/remove.py
- src/ai_dotfiles/core/dsh_migrate.py
- tests/e2e/test_dsh_install.py
dependencies:
- ai-7xrwf
- ai-nzmc8
executor_agent: claude
size: M
mode: write
phase: 4
status_history:
- at: '2026-10-04T11:57:43+00:00'
  status: backlog
- at: '2026-10-05T01:06:52+00:00'
  status: to_do
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-05T01:07:18+00:00'
  status: wip
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-05T01:30:44+00:00'
  status: done
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
---

# Wire DSH install add and remove in both scopes

## Goal

Connect existing catalog lifecycle commands and their applicable flags to DSH core services in project/global scope.

Size driver: Three command wrappers, the narrow registered-local producer selection and one project/global CLI suite share one catalog lifecycle concern.

## Scope and ownership

Mode: write. Phase 3 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 2, 5, 10, 11; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/commands/install.py
- src/ai_dotfiles/commands/add.py
- src/ai_dotfiles/commands/remove.py
- src/ai_dotfiles/core/dsh_migrate.py
- tests/e2e/test_dsh_install.py

## Definition of done

- [x] DSH-only and Claude+Codex+DSH install/add/remove work in project and -g scope with existing applicable flags.
- [x] Command wrappers delegate logic to core and format errors through ui; no new business logic is added to commands.
- [x] Catalog-only install does not silently migrate local elements; local provenance remains protected on remove/prune.
- [x] Codex and DSH shared project blocks use the coordinator before both existing Codex and new DSH destructive paths, including empty manifests.
- [x] User content, other domains and global shared configuration survive removal/prune and collisions.
- [x] CLI tests cover --prune, copy/link mode, target combinations and existing default/unknown-target regressions.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.

## Execution notes

**Concrete lifecycle probe → bounded producer selection.** ai-m4s7p's full
opted-in reconciliation correctly discovers new local sources, but catalog-only
install/add/remove must not silently adopt them. Selection must happen before
local rendering/collision and retain the complete observed original-source set
for guards: post-filtering inputs either fails source-set proof or leaves an
unregistered guarded projection active. This owner adds the narrow selection in
dsh_migrate.py, using fresh registered originals, no stored snapshot or user flag.
All project/global CLI cases consolidate in test_dsh_install.py, keeping exactly
five owned files and all six acceptance criteria. Existing migrate/reconcile
defaults remain full discovery. Fresh whole-cut critic must pass before dispatch.

**Shared refresh probe → target mutation ordering.** Coordinator disposable
probe exits0: after catalog shared rule body changes, Codex-first block mutation
causes DSH historical custody refusal; DSH-first refresh followed by Codex gives
clean check. The command owner must consume the union and preflight/current
originals in the correct order, including Claude settings/ledger rebuilds; prove
mixed-target repeated install and changed catalog rule refresh remain clean.
No historical guard may be relaxed to compensate for earlier target writes.


**backlog → to_do.** Prior lifecycle a3b3e3a verified against ebe655bb:
exact11paths +2495/-78, five frozen source SHA, done6/6, source/tracker/usage
same commit. Pinned pre-commit/msg/whitespace exit0 with no formatter changes;
clean tree/index and main baseline preserved. Queue bounded five-file CLI plus
registered-only fresh producer owner; fresh whole-cut critic BLOCKING0 and
cut-check/validate49 already pass. Guarded-value activation stays ai-wkpk8.


**to_do → wip.** tm ready/next select ai-k1w43 under ai-f2pvj, modewrite,
phase4. Sole current-model worker receives full generated five-file context,
whole approved epic and current orchestration journal. Six ticks remain open.
Producer must select registered originals before render/collision, guard the
observed source set and original registry; CLI must preserve default targets,
isolated global homes, user files, local provenance and shared refresh order.


**Frozen implementation → verified acceptance.** Coordinator reviewed the
whole five-file diff +1028/-58, SHAfdfd0494 and final five source/test SHA.
Own61/61 and affected364/364 exit0; unchanged whole gate2283/2283 in125.10s
exit0, stderr empty, including pinned native Web/HTTP MCP after isolated
loopback retry of the same command (initial sandbox-only EPERM, no exclusions).
Whole/364 precede one test-only refinement; four source SHA unchanged. Final
permanent unproven-env refusal test and all61 cases pass independently in9.43s;
root/worker mypy87, Ruff5, pinned Black25.1 five and whitespace all exit0.
Root independent6-case disposable probe also exits0: target/mode repeats change
zero bytes, shared-body refresh/remove and disabled-target local preservation;
default Claude ignores unchanged foreign/redirected DSH trees.
Namesake Codex catalog no longer hides recorded DSH local rule; complete
observed JSON/original/ledger/registry guards remain enforced before apply.
Thin wrappers preflight before Claude, fresh DSH apply before Codex; both local
registries and empty manifests survive shared removal/prune. Applicable flags,
project/global domain/MCP/env, user profiles/foreign skills and default/unknown
regressions are demonstrated. Supported projected permissions still return
precise zero-write LOCAL_VALUE_INPUT_PENDING, solely ai-wkpk8's named join hold;
they are not a permanent limitation contract. Evidence full report, stdout and
/private/tmp/dsh-k1w43-pending-evidence.json. Six CLI criteria now verified.


**wip → done.** Actual tm acceptance6/6 and tm move done exit0; usage
recorded. Commit source/test, six ticks, backlog relocation, usage and both
journals together. Next status/reconcile/migrate writer remains held until
parent/path/frozen SHA/clean-tree commit proof. No production home changes.
