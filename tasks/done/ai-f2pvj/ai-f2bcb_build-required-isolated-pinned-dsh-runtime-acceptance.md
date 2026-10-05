---
id: ai-f2bcb
kind: subtask
status: done
created_at: '2026-10-04T11:57:43+00:00'
parent: ai-f2pvj
context_files:
- tests/integration/test_dsh_runtime.py
- tests/conftest.py
- pyproject.toml
dependencies:
- ai-7xrwf
executor_agent: claude
size: M
mode: write
phase: 7
status_history:
- at: '2026-10-04T11:57:43+00:00'
  status: backlog
- at: '2026-10-05T04:29:59+00:00'
  status: to_do
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-05T04:30:25+00:00'
  status: wip
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
- at: '2026-10-05T05:31:15+00:00'
  status: done
  session:
    harness: codex
    id: 01a10349-af5a-7b11-8503-9a19885a66b3
---

# Build required isolated pinned DSH runtime acceptance

## Goal

Own the pinned native runtime fixture, provider setup and shipped-helper packaging gate required by the epic.

Size driver: A real disposable runtime smoke suite, shared isolation fixtures and packaging/test marker configuration.

## Scope and ownership

Mode: write. Phase 4 of approved epic ai-47xpm.
Implement Pre-decided decisions 1, 2, 7, 8, 12, 13, 15; source contracts and limitations
are in the epic's Research and tooling / Surface matrix. No additional fork
or scope multiplier is introduced. The orchestrator enforces phase and serial
write order beyond the common layout dependency.

## Context files

- tests/integration/test_dsh_runtime.py
- tests/conftest.py
- pyproject.toml

## Definition of done

- [x] The exact @deepseek-ai/dsh@0.2.0-rc.2 baseline is installed/resolved only in a disposable fixture with isolated homes and local fake provider/MCP/hook programs.
- [x] Startup waits for managed required ids and invokes a real named child tool; retained parent services, current model route, literal bodies/descriptions and deny/ask including child approval are verified.
- [x] Native full-config precedence, MCP/hook activation and a failing optional managed plugin produce the expected audited behaviour.
- [x] No production credentials, external provider requests or real home files are used; unavailable runtime setup fails the required gate instead of skipping.
- [x] Generated ESM helpers are included in wheel/sdist; required markers/resources are configured and isolated installed-CLI verification passes.

## Notes

You are not alone in the codebase: preserve other owners' edits and accommodate their APIs. Only this task owns writes to its listed context files; coordinate any additional write with the orchestrator.
The orchestrator owns commits, acceptance ticks and lifecycle transitions.

## Execution notes

**ai-f2bcb backlog → to_do.** Previous ai-wkpk8 atomicdbb5f88d committed
and independently verified with full2411 green and source/ticks/move together.
Queue only this listed phase7 three-file native acceptance owner; actual
ready/next must establish modewrite eligibility before claim. Five criteria open.

**ai-f2bcb to_do → wip.** Actualready lists sole modewrite M phase7
row; tm next selects exact ai-f2bcb, actual tm move wip exit0. Dispatch one
current-model worker with complete generatedcontext, approvedepic/current
journal and exactthree paths. Five ticks open: pinned disposable runtime;
same-host audited actual namedchild/services/current route/literal/deny+ask;
config/MCP/hooks/optional-managed failure; no live credentials/homes/external
requests and missing-runtime hard failure; wheel/sdist plus truly installed CLI.
No other writer or Git operation. Existing public native fixtures/APIs provide
reference evidence, not substitute execution. Any production defect or extra
write boundary returns to coordinator before edits; no phantom skip/waiver.

**ai-f2bcb native child → remaining acceptance.** First exact same-host child
case passes after repeating the unchanged command with isolated permission for
macOS sandbox-exec. Production prepare/launch awaits audit before Ready with
zero tasks/sessions; stock spawn invokes the named child on parent-current/local.
Read and local stdio MCP execute; literal CRLF persona/descriptions and retained
llm/tools/systemPrompt/subagents are observed. Child Write is denied and Bash
fails with approval never without a callback; parent PTC Bash uses one allowed-once
callback, while Write remains denied under read-only/full enforcement. Initial
MCP failure was only a test fixture placed in settings.fragment instead of
mcp.fragment.json; no production files changed. All five ticks stay open until
frozen whole-diff and full-command review; scoped Web, HTTP/hooks, full-config,
optional-managed failure and wheel/sdist/installed CLI remain the same owner.

**Current-model capacity → same-owner resume.** Host ended the ai-f2bcb
worker turn with "Selected model is at capacity" before any frozen final result.
Same current-model owner resumes the same three files and WIP acceptance, using
fresh complete tm context/epic/journal at
/private/tmp/dsh-orchestration-contexts/ai-f2bcb-resume.md (2886 lines).
Saved source/logs survive; no production/Git/tracker ownership change or test
waiver. First reconcile actual command completion; no unchecked gate is assumed
successful and no duplicate still-running mutation/test is started. All five
criteria remain open until full final evidence and independent review.

**Frozen native15 → portable missing-runtime fixture.** Root read the whole
1045-line native test and complete conftest/pyproject diff, then independently
repeated all15 cases in a fresh /private/tmp/dsh-f2bcb-root-acceptance:15/15,
15.44s exit0. Actual selected standing tree at Ready and the same parent/child
tree, exact native deny/ask and installed wheel are proved on frozen source.
Missing-runtime negative PATH currently /usr/bin:/bin can contain dsh on another
host. Same three-file owner completes current unchanged full --cov first, then
replaces only that PATH with a guaranteed empty disposable bin and repeats final
own/static/full gates. Preserve before/final SHA and narrow diff; no production
change or silent transfer of a gate. All five DoD remain open until final frozen
evidence is inspected. Root initial review evidence is
/private/tmp/dsh-f2bcb-root-initial-reviewed.json.

**ai-f2bcb wip → done (atomic acceptance prepared).** Root reviewed the whole
three-file diff and final source SHA, actual command stdout/stderr/exits, all
15 native evidence records and wheel/sdist byte identity. Official RC2 remains
0.2.0-rc.2 with Cordis4.0.4 in disposable homes; nine same-host Ready/real-child
cases prove current parent route, literal persona/descriptions, retained services,
PTC deny/ask, child approval never, scoped standing-tree identity, native config
replacement, activated local MCP stdio/HTTP and hook context. Six negative cases
have zero Ready/turn, including real optional import/apply failures. Installed CLI
imports wheel site-packages without editable checkout/PYTHONPATH and all shipped
ESM parse. Final own15/15, affected272/272, full2426/2426 with92.04% coverage,
mypy87, Ruff and Black24/25 pass. Root independently repeated native15/15 before
the sole empty-bin PATH correction, then final changed negative1/1; all other
source bytes match, worker repeated full-final on the correction. Root proof:
/private/tmp/dsh-f2bcb-root-final-review.json; frozen worker report:
/private/tmp/dsh-f2bcb-report.json. Five ticks prepared only now; acceptance/move,
usage, this journal and three source files must share one successful commit.
No live homes/credentials/external providers, skipped gate or production edit.
