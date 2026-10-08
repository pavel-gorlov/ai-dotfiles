---
id: ai-grmp6
kind: task
status: done
created_at: '2026-10-07T14:30:04+00:00'
parent: null
dependencies: []
status_history:
- at: '2026-10-07T14:30:04+00:00'
  status: to_do
- at: '2026-10-07T14:36:46+00:00'
  status: wip
  session:
    harness: codex
    id: 01a106d9-5bbd-71b3-88ff-699524937b7b
- at: '2026-10-07T16:01:49+00:00'
  status: done
  session:
    harness: codex
    id: 01a106d9-5bbd-71b3-88ff-699524937b7b
---

# Support native DSH permission mode

## Intake

Owner approved adding an explicit native DSH permission choice while preserving
Claude auto mode, and asked to make managed launch work, verify the commands,
and repeat the publication workflow.

## Context

Released 0.4.1 migrates the project but managed launch also reads the global
Claude source. The user's global settings contain permissions.defaultMode=auto
and skipAutoPermissionPrompt=true. defaultMode has no implemented equivalent
and blocks activation. Official DSH RC2 Auto is an experimental Web-only
integration, not a Headless default; it cannot be silently substituted.

The original checkout is dirty and behind trunk. Implementation uses a fresh
worktree from merged 0.4.1, preserving the original checkout and user settings.
This is one standalone implementation task, not a new decomposed epic.

## What to do

Add a strict per-scope manifest setting dsh_permission_mode with strict (default)
and native choices. An explicit native choice acknowledges only the recognized
Claude defaultMode=auto as a reported translation limitation. Preserve the raw
value and provenance. Keep deny/ask, unknown fields, invalid types and unsupported
defaultMode values blocking. Project acknowledgement cannot waive a global source.

Apply the choice consistently before source merging in install/add/remove,
migrate, status, reconcile and managed launch. Do not select a native preset,
change sandbox/approval defaults or generate access grants. Update required
renderer generators and the guide plus shipped builtin skill. Verify source
custody and drift when the choice changes.

Run meaningful permission/lifecycle/CLI and native acceptance tests, quality
gates, and the full source CI. Publish a patch release with verified wheel/sdist,
annotated tag and Homebrew formula CI. Install the released package, set only
the user's authorized DSH manifest choice, and verify actual migrate and managed
Headless launch while preserving Claude auto, existing DSH provider/model choices
and existing profiles. If Headless is absent, prepare it with official DSH tools
and reuse the existing Web account/model selection without copying credentials.

## Acceptance criteria

- [x] Both manifests validate strict/native choices, default to strict, and fail loudly on malformed values.
- [x] Native acknowledgement is per original scope; only defaultMode=auto is nonblocking and retains source bytes/value/provenance.
- [x] Deny/ask, malformed and unknown permission fields/values still block; no new native grants, preset or sandbox/approval changes occur.
- [x] Lifecycle, migration, status, reconciliation and fresh managed launch consistently use the selection, including drift after changing it.
- [x] Meaningful isolated tests and native RC2 acceptance plus quality gates pass; the guide and builtin skill document the exact contract.
- [x] Published release assets/tag and Homebrew formula are public and verified; source CI and both Homebrew platform installation checks pass.
- [x] Installed release runs the user's migrate and managed Headless launch; Claude auto, model/providers and native profiles remain preserved.

## Execution notes

- 2026-10-07: Owner approved native DSH permission selection and autonomous
  publication/command verification. Official RC2 package and current upstream
  documentation both confirm Auto is absent from Headless and defaults.
- Planning evidence: read-only lifecycle design lookup recommends a per-scope
  manifest setting rather than a launch-only bypass.
- Implementation frozen after 935 unique focused scenarios, including 24 native
  RC2 cases; all initial failures corrected and rechecked. Ruff/Black/mypy pass.
  Permission/config/bridge generators are 2, audit is 3; schema remains 1.
  Source custody includes manifest revocation before writes and native Ready.
- Added only the approved native mode field to both user manifests. Created the
  absent Headless profile through official DSH config dumping. Existing profiles
  and Claude original settings remain intact. Actual editable migrate passes.
- Actual editable launch passes the former defaultMode gate, then reports missing
  credentials for its stock deepseek-official route. Existing Web selection is
  deepseek-account/deepseek-v4-pro/high. Reused only this model-selection row in
  the new Headless patch; the existing Web patch and credential storage were
  preserved. A real Headless turn completed with an actual bash call and matching
  version-command result. Release installation verification remains pending.
- Feature commit 2cfa7d948b30b121526c1ca68dfdd0d2d10f82b6 carries Task-Id.
  Configured hooks accepted one formatter-only trailing comma and passed.
  Commitizen files-only bumped 0.4.2; frozen wheel/sdist match all 112 package
  files, and an isolated installed wheel reports metadata/runtime 0.4.2.
- Source PR: https://github.com/pavel-gorlov/ai-dotfiles/pull/26 . Exact-head
  full CI 37643167418 passed: 2516 tests, including 24 native cases, zero
  skips/failures/xfails, coverage 92.12%. Three SSH pushes returned GitHub HTTP
  500; the same frozen candidate
  was pushed normally through HTTPS, without changing remote configuration.
- PR26 merged to 232ec7fe3a6a28d0e535bfb72496b8edf26c75f7; tested/candidate/
  merged/tagged trees match. Annotated v0.4.2 and frozen wheel/sdist are public:
  https://github.com/pavel-gorlov/ai-dotfiles/releases/tag/v0.4.2 . Both assets
  downloaded HTTP200 with matching local hashes and GitHub digests. Tagged
  archive matches all 353 committed files and executable modes.
- Homebrew PR6 updates only formula URL/SHA; macOS/Linux installation matrix
  37645727441 passed all install/test/audit/smoke checks with actual version
  0.4.2. PR6 merged to 0f9d6c2dcafd5fec9ddfaa66242314c43ad0a112.
- Homebrew upgraded only ai-dotfiles to 0.4.2. All 112 installed package files
  match the public wheel. Installed CLI version/update/migrate/Headless commands
  all exit0; the real model called bash with ai-dotfiles --version and received
  the exact 0.4.2 result, then completed. Builtin skill matches the shipped
  template and documents the native choice.
- Final protected-file verification: 47 checked files, 35 catalog and 8 existing
  profile files, zero mismatches; Claude auto and both native mode choices intact.
  Evidence: /private/tmp/dsh-native-permission-policy-20261007/owner/final-live-proof.json
  and publication/final-publication-report.json. Publication and all owned
  installer/model processes are END; acceptance is complete.
