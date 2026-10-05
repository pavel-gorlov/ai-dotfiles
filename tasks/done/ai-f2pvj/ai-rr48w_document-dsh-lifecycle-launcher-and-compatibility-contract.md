---
id: ai-rr48w
kind: subtask
status: done
created_at: '2026-10-04T11:57:43+00:00'
parent: ai-f2pvj
context_files:
- README.md
- src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md
- docs/dsh-target.md
dependencies:
- ai-7xrwf
executor_agent: claude
size: S
mode: write
phase: 7
status_history:
- at: '2026-10-04T11:57:43+00:00'
  status: backlog
- at: '2026-10-05T05:38:38+00:00'
  status: to_do
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-05T05:39:00+00:00'
  status: wip
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-05T06:09:39+00:00'
  status: done
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
---

# Document DSH lifecycle launcher and compatibility contract

## Goal

Update the public CLI reference and document the complete approved DSH workflow and matrix boundaries.

Size driver: Three documentation files with already-decided CLI and native contracts.

## Scope and ownership

Mode: write. Phase 4 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 2, 3, 4, 6, 9, 14, 16; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- README.md
- src/ai_dotfiles/scaffold/templates/builtin_ai_dotfiles_skill.md
- docs/dsh-target.md

## Definition of done

- [x] README and builtin ai-dotfiles skill agree with new command/flags/targets/vendor and domain workflows in this PR.
- [x] The guide documents project/global roots, DSH_HOME, managed startup/restart/project binding, native JSON patch syntax and whole-config replacement.
- [x] Native UI override behaviour, current-model alias inheritance, collisions, provenance/reconcile and every matrix limitation are explicit.
- [x] Examples match actual help and finite native contract; no parity or security claim exceeds the pinned APIs.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.

## Execution notes

**ai-rr48w backlog → to_do.** Previous native acceptance child committed and
independently verified8df291590, all required native/runtime/packaging gates pass.
Queue exact three-file documentation concern, then actualready/next before claim.
Four criteria remain open; no production/source/CLI or onboarding changes.

**ai-rr48w to_do → wip.** Actualready/next selects sole modewriteS phase7
row; tm move wip0. Dispatch current-model worker, whole actualgeneratedcontext,
approvedepic/currentjournal and exact3 docs paths. Four ticks remain open until
whole diff, actual help/reference/examples and native boundary evidence reviewed.
No overlapping writer/read fanout or Git operation. Keep existing documentation
language and unchanged defaults/vendor catalog-only workflows; no invented flags.

**ai-rr48w wip → done (atomic acceptance prepared).** Root read the whole
910-line captured three-doc diff plus final editorial increment (final912),
verified all3 frozen source SHA, actual30 command outputs/exits/output SHA and
primary current/pinned comparison. README/builtin cover three scopes/targets,
actual lifecycle/help/defaults/domain/vendor flow; guide covers roots/binding,
whole-config/CLI-vs-UI precedence, current-parent aliases, all matrix/hook/MCP/
source-custody limits and no broadening. Narrow18helps/8JSON/11launchargv/
11links/7unchangedvendor flows and7events pass. Real published RC2 notice plugin
boot/public settled audit proves whole-config replacement and loaded Fiber config,
warnings empty; Node/whitespace0. Root independently verifies8JSON/11 production
launch parsings and native origin binding0 with unchanged docs, plus both vendor
list helps and published logger/helper path. Temporary probe mistakes in both
worker and root are retained; only probes were corrected, no product defect or
implementation edits. Final guide removes internal integration history. Evidence:
/private/tmp/dsh-rr48w-report.json and /private/tmp/dsh-rr48w-root-reviewed.json.
Four ticks now demonstrated; source/ticks/move/usage/journal must share one
successful commit. Broad final quality remains ai-pwjnx; next templates stay held.
