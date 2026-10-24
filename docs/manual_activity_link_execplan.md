# Persist explicit manual activity links (#720)

This living ExecPlan follows `.agent/PLANS.md`.

## Purpose / Big Picture

An operator can confirm that one original Intervals activity and one manually imported Garmin activity are the same physical ride. An offline CLI previews the decision without writing, applies an exact identity association, and can undo it. Lists and load calculations then see one activity even after provider replay. The selected original Intervals canonical id and its authored history survive. This is Class A because persistent identity and deduplication semantics change.

## Progress

- [x] (2026-10-24) Read-only reproduction: two local canonicals for one owner-confirmed FIT; equal UTC start and duration; original has no Garmin external coordinate.
- [x] Issue #720 created; clean isolated worktree from ae557d4; existing ingest/schema baseline: 47 passed.
- [x] Independent design checker identified deterministic payload selection, reference guards, cache cleanup, dry-run and reset boundaries.
- [x] Write spec and behavioral tests: initial RED missing service; first implementation exposed six replay failures, then GREEN.
- [x] Exact link/replay/unlink/stale protection/reset implemented; 24 new tests passed. Duration-boundary regression: RED 2 failed / 2 passed, then GREEN 4 passed.
- [x] Focused baseline and related suites passed; global ruff and independent consolidated review plus scoped fix verification passed.
- [x] Final corrected contributor-safe run: 3992 passed, 39 skipped, 116 deselected in 239.19s. Related focused suite: 88 passed. Ruff and diff whitespace check passed.
- [x] Consistent SQLite analysis copy rehearsed: link 2→1, replay in both orders stays 1, unlink 1→2, relink 2→1, integrity ok, zero orphan links. Draft PR #721 published.

## Surprises & Discoveries

Observed: the original Intervals link has no external Garmin coordinate, while the Garmin copy has its own id. Inferred: the current exact-coordinate algorithm cannot join them. Verified by: read-only local SQL and inspection of `services/activity_ingest.py` and `data/database.py` agree. This is a missing operator capability, not a violation of the existing ADR.

Observed: `Database(path)` runs schema and legacy repairs. Inferred: using it in a default preview could mutate a database. Verified by: constructor inspection. Use a raw read-only SQLite connection for preview.

## Decision Log

Decision: scope is an offline operator command and shared persistence, with no API/UI or automatic similarity matching. Rationale: one explicitly confirmed pair is sufficient. Date/author: 2026-10-24, owner scope and Codex.

Decision: keep the original standalone Intervals canonical identity and select its payload explicitly, regardless of primary-source configuration. The manual association is separate from provider facts and remains until unlink or full reset. No credentials, real identifiers or personal payloads enter tracked evidence.

Decision: refuse authored references on disappearing identities; delete only rebuildable interval/power-curve/bike-pair caches transactionally. Never migrate immutable ledgers. Preserve references attached to the surviving identity. Unlink recomputes normal exact-coordinate grouping from current source facts. One Garmin-returned Intervals claimant is allowed; multiple claimants abort the ingest transaction visibly.

## Outcomes & Retrospective

Implementation is in commit 064d1689a9336699d08a9543361da26510cdc88d and draft PR https://github.com/rbctmz/ai_trainer/pull/721. Independent code review found one P2 at the one-second normalization boundary; reproduced, fixed-in 064d168, and scoped verification returned 24 passed. The copied-data acceptance passed without live database mutation or provider writes. Final broad evidence: 3992 passed, 39 skipped, 116 deselected; related focused suite 88 passed; ruff and diff whitespace checks passed. Merge and live apply remain human decisions.

## Context and Orientation

`services/activity_ingest.py` normalizes provider identities; `data/database.py` persists each source payload and projects canonical rows. A canonical is the one row consumers count. `activity_provider_links` retains provider identities and payloads. Ordinary matching uses an exact Garmin external coordinate, not timestamps. The original Blocks record lacks that coordinate. `data/activity_store.py` resolves Intervals ids for enrichment and must honor the manually selected original when another Intervals copy arrives. Full reset lives in `Database._clear_all_data`.

## Plan of Work

Add `data/activity_manual_links.py` for an additive exact-pair table, read-only inspection, reference/cache guards and reassignment inside existing transactions. Extend Database initialization, ingest and reset, preserving unlinked behavior. Add `services/activity_manual_links.py` and `scripts/link_activities.py` for the offline preview/apply/unlink contract. Preview must not initialize Database. An optional constructor initialization switch permits the explicit write path to enter one locked transaction before any schema change. Record a reason with each manual association. Add synthetic smoke coverage and document the CLI and ADR-0008 exception.

## Milestones

First establish the exact operator contract and failing behavioral tests against synthetic source payloads. Review the design independently before implementation. Then implement persistence and ingest integration together, so apply and future replay share the same rule. Finally prove restart, replay, stale preview, ambiguity, authored-reference rejection, rollback, unlink and reset; rehearse only on a consistent analysis copy and provide a reviewable patch/PR.

## Concrete Steps

Run commands from the task worktree using `/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python` as Python. Baseline: `python -m pytest tests/smoke/test_activity_ingest.py tests/smoke/test_activity_provider_links_schema.py -q` returned 47 passed. New suite: `python -m pytest tests/smoke/test_manual_activity_links.py -q`. Final checks: `python -m ruff check .`, focused related smoke modules, `python -m pytest -m "not live and not debug and not e2e" tests/`. Use an external pytest cache directory if needed.

CLI contract: `python scripts/link_activities.py --database /path/to/offline.db --intervals-id i_original --garmin-id 123` returns JSON preview with `allowed`, `blockers`, `token`, and `before`/`after` totals. Explicit mutation additionally requires `--apply --expected-token TOKEN --confirm-stopped`; linking also requires `--reason TEXT`. `--unlink` previews or reverses the decision. A failed precondition returns an error and no partial state. No provider I/O occurs.

## Validation and Acceptance

Link two synthetic rows into one with the original canonical identity and one contribution to totals; preserve all provider payloads. Replay providers in either order and reopen Database: still one. Select the original for enrichment and projection even with a Garmin-returned Intervals claimant and either primary source. Refuse multiple claimants, conflicting pair, incompatible sport/time/duration, stale token and authored disappearing references. Verify transactional failure restores the prior state. Unlink must reconstruct ordinary canonicals from current facts, and repeat operations must be safe. Full reset clears introduced state. Existing normal matching suites remain green. Observe the same before/after count and load change on the copied owner dataset, without publishing its contents.

## Idempotence and Recovery

The exact pair has unique Intervals and Garmin keys; no chains or groups are introduced. Preview is read-only. Apply obtains BEGIN IMMEDIATE, re-reads state and checks the preview token before adding schema or data. A stale token refuses the operation. A transaction exception rolls back reassignment and decision together. Unlink removes the explicit decision and reprojects from preserved current source facts; derived caches can be refetched. Full reset removes decisions in its existing transaction. Before any separately authorized live apply, stop writers and create a validated backup through `scripts/sqlite_backup_restore.py`; do not claim writers are stopped while merely making an online analysis copy.

## Artifacts and Notes

Reviewed implementation SHA: 064d1689a9336699d08a9543361da26510cdc88d. Initial broad run: 3987 passed, 39 skipped, 116 deselected, one environment failure because a child run_web.sh lacked python in PATH. Activating the existing venv made the preflight module pass 3/3; the final corrected full run passed: 3992 passed, 39 skipped, 116 deselected in 239.19s. Optional skips include absent local TypeScript dependencies, garth and deliberately disabled fixture/diagnostic data. No dependencies were installed for this backend-only change.

Tracked evidence uses synthetic fixtures only. Personal rehearsal paths and identifiers remain outside Git. The source checkout stays unchanged and the original personal database stays untouched. PR closes #720 only after human merge.

## Interfaces and Dependencies

Use existing sqlite3, json, hashlib and pytest; no new dependencies. `manage_manual_link(path, intervals_id, garmin_id, *, apply=False, unlink=False, expected_token=None, reason=None, confirm_stopped=False)` is the service boundary returning a JSON-safe preview/result. Database write operations reuse `_resolve_garmin_coordinate` and `_project_canonical` inside one transaction. Public HTTP and TypeScript contracts are unchanged. ASR-REL-3 and ASR-MOD-3 and ADR-0008 cover atomic identity persistence and additive schema compatibility.

Duration precision clarification (2026-10-24 review): the one-second allowance is represented as 0.017 minutes, matching the existing three-decimal minute normalization; a two-second source difference is refused.

2026-10-24 progress update: recorded RED/GREEN, independent review disposition, copied-data acceptance and publication of draft PR #721. Final corrected broad result recorded; all local acceptance and independent checker gates passed. Native PR review, human merge and live apply remain separate gates.
