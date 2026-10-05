---
id: ai-6w1qz
kind: subtask
status: done
created_at: '2026-10-04T11:57:44+00:00'
parent: ai-f2pvj
context_files:
- src/ai_dotfiles/scaffold/templates/global_readme.md
- src/ai_dotfiles/scaffold/templates/root_readme.md
- src/ai_dotfiles/scaffold/templates/example_dsh_fragment.json
dependencies:
- ai-7xrwf
executor_agent: claude
size: S
mode: write
phase: 7
status_history:
- at: '2026-10-04T11:57:44+00:00'
  status: backlog
- at: '2026-10-05T06:19:54+00:00'
  status: to_do
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-05T06:20:18+00:00'
  status: wip
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-05T06:39:29+00:00'
  status: done
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
---

# Sync scaffold references and native fragment example

## Goal

Keep shipped scaffold references aligned and provide a documentation example of the native fragment contract.

Size driver: Two reference templates and one JSON-data example; no onboarding behaviour changes.

## Scope and ownership

Mode: write. Phase 4 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 4, 14; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- src/ai_dotfiles/scaffold/templates/global_readme.md
- src/ai_dotfiles/scaffold/templates/root_readme.md
- src/ai_dotfiles/scaffold/templates/example_dsh_fragment.json

## Definition of done

- [x] Shipped reference templates describe applicable DSH target/lifecycle and point to managed launcher guidance.
- [x] The example is a valid JSON patch array using the pinned native contract without executable expressions or secrets.
- [x] No default target, init flag or automatic profile/runtime installation is added.
- [x] Template examples are checked against the implemented collector and documentation.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.

## Execution notes

**backlog → to_do.** Previous docs ai-rr48w atomic a438dd1 is independently
verified with exact7 rawpaths/all6 live+HEAD SHA, done4/4 and normal Git gates0.
Queue only this ordered phase7 three-template owner; actual ready/next must
confirm eligibility before dispatch. Four criteria remain open, no onboarding
behaviour/runtime/profile installation or extra owned file.

**to_do → wip.** Actual tm ready/next selects sole modewriteS phase7 row.
Dispatch current-model owner with complete generated context plus whole approved
epic/current journal and exact three-template ownership. Four criteria remain
open until complete diff and actual collector/scaffold/native evidence reviewed.

**wip → done (atomic acceptance prepared).** Root reviewed whole175-line
owned diff/all3 frozen SHA, all36 actual command outputs/exits and complete
probe/collector/archive scripts. Existing scaffold/init18/18, actual helps9,
rendered shell snippet/domain create/resource copy, finite JSON/source binding,
public RC2 patch/boot/settled audit and12 wheel/sdist bytes comparisons pass;
whitespace empty. Two temporary evidence-harness assertions were corrected with
unchanged source and failed attempts retained. Root independent scaffold/default/
links/JSON-guide/resource binding/three launch parse proof0 matches same3 SHA.
All4 criteria demonstrated; source/ticks/move/usage/journal must share one commit.
Proof /private/tmp/dsh-6w1qz-root-reviewed.json, final worker report
/private/tmp/dsh-6w1qz-report.json. Final broad quality remains ai-pwjnx.
