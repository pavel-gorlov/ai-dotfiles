---
id: ai-42cyj
kind: task
status: done
created_at: '2026-10-07T17:40:54+00:00'
parent: null
dependencies: []
status_history:
- at: '2026-10-07T17:40:54+00:00'
  status: to_do
- at: '2026-10-07T17:43:08+00:00'
  status: wip
  session:
    harness: codex
    id: 01a106d9-5bbd-71b3-88ff-699524937b7b
- at: '2026-10-07T19:15:56+00:00'
  status: done
  session:
    harness: codex
    id: 01a106d9-5bbd-71b3-88ff-699524937b7b
---

# Fix managed DSH Web settings

## Intake

Owner reported that the managed Web Preview Notice cannot be dismissed because
its acknowledgement API fails. Related native directory-picker dynamic entries
also fail. Owner authorized a bounded source fix and the next patch publication
and installation if a source change is required.

## Context

Released 0.4.2 provides managed DSH composition and native permission selection.
Managed Web must keep native user settings writable and persistent while the
managed policy and source provenance remain intact. Investigate the actual
WelcomeNotice acknowledgement write and the runtime Loader path used by native
directory-picker entries, using current RC2 behavior and concrete API failures.

The original checkout is dirty and behind trunk. Work starts from current public
main in a fresh worktree; the completed ai-grmp6 task and all retired worktrees
are preserved. This is one standalone task with one implementation writer.

## What to do

Correct the managed composition so native WelcomeNotice acknowledgement can be
written, refreshed and retained after a managed restart. Correct the associated
native directory-picker runtime Loader composition. Keep native writes separate
from managed policy and source provenance; do not introduce HMR or change the
permission mode, sandbox, approval, profile, provider or model defaults.

Add focused regression tests and meaningful native Web API proof. Preserve the
schema, ownership and source-custody guards, updating generator versions only
when emitted output changes. Synchronize the guide and shipped builtin skill.
If source changes are needed, publish and install the next patch through the
existing source CI, GitHub assets and Homebrew formula workflow, then verify
the installed managed Web behavior before closing the task.

## Acceptance criteria

- [x] Native WelcomeNotice acknowledgement writes successfully, survives refresh and remains acknowledged after a managed restart.
- [x] Native settings writes do not leak or overwrite managed overlay/policy state; the fix introduces no HMR or permission/profile/model default changes.
- [x] Native directory-picker dynamic entries work through the runtime Loader composition with meaningful regression coverage.
- [x] Schema, provenance, ownership and source-custody guards remain intact, including appropriate generated-output drift detection.
- [x] Focused isolated and native regressions plus actual Web API proof pass, with failures and corrective checks retained in evidence.
- [x] The user guide and shipped builtin ai-dotfiles skill describe the corrected managed Web workflow in the same source PR.
- [x] If source is changed, the next patch is publicly released and installed with successful source/Homebrew CI and installed managed Web verification.

## Execution notes

- 2026-10-07: Canonical tm create allocated this standalone task. Setup starts
  from verified public main 232ec7fe3a6a28d0e535bfb72496b8edf26c75f7 in a new
  isolated branch. No completed task is reopened or edited. Bootstrap uses an
  exact temporary catalog copy and preserves the live catalog and original
  dirty checkout. Implementation, commits and publication remain gated on
  focused review and frozen source evidence.

- 2026-10-07: COMPLETE. Installed 0.4.3 native Web HTTP proof exposes 19
  settings namespaces (before: 0), ACK mutate/read succeeds, valid revision
  conflict and invalid type are refused. All 12 managed entries and profile
  bytes remain unchanged; both browse picker entries are ACTIVE. Restart
  preserves the ACK and the profile SHA 75a1a25590e442ad0961a87199d7dcf046796eb600e5b1bb71aa6f1b913a28ac.
  The user's ACK was already stored before this fix: live proof is idempotent
  native API persistence, while all six isolated HTTP cases prove changed ACK
  durability, refusal and rollback. No physical UI click is claimed (CUA
  permissions unavailable). The same native API used by Continue is verified.
- Source PR27 merged e777c68663cef371d10624105aeca992cfc8847b and public
  v0.4.3 wheel/sdist/tag archive verified. Corrected full CI37669329254 passed
  2522 tests, including 30 native, zero skips, coverage92.11%; the earlier
  test-only platform-picker failure and correction remain in evidence.
  Tap PR7 merged 445e9b527e62222d0f32e7200190594ff94c5347; macOS/Linux
  install/test/audit/smoke passed. Homebrew CLI0.4.3 and all113 installed files
  match public assets, builtin skill matches the installed template.
- Live receipts: owner/after-0.4.3-receipt.json,
  owner/restart-after-0.4.3-receipt.json and owner/active-web-receipt.json under
  /private/tmp/dsh-web-settings-20261007. Consolidated installed proof SHA
  b7d35e16a50eaecacad0e46263fee91cc603877a141cfd12b6b4f94ff661136a;
  publication/final-publication-report.json SHA
  f1f55e62381147c2339dd8143f595c0e5bddcfaa2255492a8d00caa1ea4a2d0e.
  Protected16:15 byte/mode unchanged, qualified external Codex config drift
  retained. No profile/model changes. Owned managed Web pid84794 port54059
  remains running; old servers/Desktop/Docker were not stopped.
