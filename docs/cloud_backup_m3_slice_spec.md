# M3 cloud status and isolated drill — #757

Author: Domain/API Implementer, then explicit UI handoff. Independent checker:
read-only Class A checker. Merge owner: Greg. Date: 2026-11-15.
Base: 27e5405 (#755). Candidate/evidence SHA follows implementation checkpoints.

## Change Class

Class A: persistent drill receipt, remote recovery and public status boundary.
Native review is manual, 0/2 used; owner acceptance/merge remain pending.
The accepted parent contract is [cloud_backup_slice_spec.md](cloud_backup_slice_spec.md).

## Scope and public contracts

Add CloudBackupStatus to api/backup_contract.py and web/lib/types.ts, with the
five states, four nullable UTC timestamps, fixed reason codes and drill_warning
already specified in M1. GET /api/backup/cloud/status is read-only and accepts
only demo selection; it obtains selected paths from Settings, never a Database
dependency/constructor. Demo/acceptance short circuit before config access.
Existing local BackupStatus/check/envelopes and database schemas are unchanged.
Contract registry/extractor/inventory cover the additive endpoint.

CLI adds explicit drill. Existing run performs a drill when none succeeded or
30 days elapsed. Drill selects the latest remote snapshot for the fixed trainer
host, verifies repository ID, exact snapshot ID and restored manifest binding,
bytes/hash/integrity/schema/all typed table fingerprints in new owned temp.
It does not rely on local originals/status/receipt; an absent receipt is allowed,
but a corrupt/foreign receipt is refused. It never silently tries an older copy.
Recovered manifests cannot assert upload coverage: drill success changes only
last_drill_at/drill_failed, preserving prior upload dates/reason/evidence.
Drill failure preserves last successful dates and sets cloud_drill_failed.
Private receipt adds boolean drill_pending (absent means false), atomically
published with successful upload when a drill is due. Interrupted pending drill
shows failed warning; watchdog/failure writes preserve committed upload metadata.
Upload and drill share the repository lock and 600s process-group bound; cleanup
uses existing owned-inode checks. No init/unlock/prune/activation.

## UI handoff / design brief

Use the existing global BackupStatusBanner warning pattern and tokens. Local
and cloud facts stay separate; show coverage-check, remote verification and
drill times independently. Disabled/unknown/stale/degraded and API failure are
explicit. Drill due/failed is a separate warning even when upload is ready.
No browser upload/drill action or domain freshness arithmetic. UI work starts
after the API contract tests pass; implementer hands exact DTO/files/evidence
to UI role. Verify synthetic states at1280/390 light/dark, no overflow/secrets,
and no cloud POST. No new layout/CSS system or settings flow.

## Non-goals

Live Cloud.ru/Keychain/LaunchAgent, personal SQLite/.env/runtime changes,
retention, auto-restore, second trainer or backup engine. Existing reset keeps
cloud history/config/receipt. Owned temporary drill data is cleaned only by its
invocation, never by product reset. Rollback disables cloud config and reverts
code; all existing snapshots remain intact.

## Definition of Done and RED matrix

- [ ] API no-source/no-network/no-write probes and demo/config canaries.
- [ ] Missing/local-lost/foreign/corrupt/clock/failed-drill receipt matrix.
- [ ] Drill success/failure/retry/30-day cadence/lock/deadline/cleanup tests.
- [ ] Encrypted LOCAL restic domain fixture, removed local originals/receipt,
  fresh application readers prove cycle/checkpoint/decision/match/feedback/
  readiness/provider/manual identities and exact raw rows; measured RTO<=30min.
- [ ] Contract freshness/inventory, lint/build, focused and full isolated tests,
  browser fixtures/screenshots and independent checker evidence.
- [ ] Draft PR links #757; zero untriaged blockers; owner owns review/merge.

RED tests must first fail on absent endpoint/contract/drill/cadence/UI. Existing
M2 transport and guard tests characterize unchanged safety. Domain fixture uses
real persistence/readers, never substitutes a two-table synthetic DB for full
recovery acceptance. Native restic may skip when unavailable in CI, but local
native evidence is required before claiming this acceptance.

## State, identity and evidence boundaries

Config owns repository/source binding; remote manifest owns recovered generation.
Current/history/new namespace never cross-bind; unknown/partial metadata fail
closed. Missing local state gives unknown/stale/degraded upload health while successful
drill remains independently visible. Future or malformed timestamps refuse.
Last_drill_at changes only after complete validation. Failure/retry never updates
upload coverage; drill never invokes backup or replays a domain business mutation.
Reset/rollback retain cloud history; runtime drill has no production write path.

## ASR / ADR traceability

ASR-SEC-1: path/secret-free DTO, no network on GET. ASR-REL-1/3 and DEP-2:
recovery preserves domain identity and partial failures do not mutate source.
MOD-2: shared server-owned semantics. Reuse ADR-0001 web-primary and existing
snapshot/restic boundaries; no new architecture/service/dependency.

## Evidence / review

Observed: M2 current tree has read_cloud_status but no cloud HTTP contract,
drill command or remote snapshot discovery. Verified by current source reads.
Final evidence and owner gates are recorded in the PR when broad checks finish.
Full+scoped checker and native review follow repository two-round stop rule.

Independent implementation checker atd1e3d31: one blockingP2, zeroP1. Observed:
transient drill receipt error reverted newly committed upload evidence, and
combined-run timeout wrote upload cloud_timeout without drill_failed. Verified
by checker full-domain synthetic probes and author2RED regression tests.
Disposition: fixed-in aa1d61b; scoped checker READY,82PASS and four independent
pending/final/persistent-write/watchdog probes passed. Native review still0/2.

Author completion audit: hourly run with missing source/local snapshots/receipt
initially skipped the due drill (1RED). Corrected with pure selected-path
eligibility and remote-only branch before source-dependent upload binding;
upload remains degraded while successful drill is recorded independently.
Default/demo/local-disabled/foreign selected paths still refuse before network.
This implements the existing monthly/lost-local criterion; no new product scope.
