# #623 M4 — retention, reset и restore

Approved [slice spec](automatic_snapshots_slice_spec.md), Class A;
ASR-REL-3 / ASR-DEP-2 / ASR-SEC-1. M3 #746 review requested on frozen165a97a.
M4 is stacked separately. No personal data/services/live activation.

Keep last snapshot per 14 nonempty UTC days, 8 nonempty ISO weeks, latest and
unexpired reset pins. Existing namespace lock covers check/pin/retention. Validate
entire recognized catalog before deletion; unknown/manual/foreign artifacts stay.
Corrupt catalog or uncertain pins prohibits pruning. A ready snapshot remains
ready with maintenance reason_code backup_retention_failed/reset_pins_unknown.

Full product reset is Database.clear_all_data (Streamlit admin and demo services;
web has no full-reset endpoint). Enabled selected real store: BEGIN IMMEDIATE
before pre-reset check + durable14-day pin; no concurrent writer commit before
DELETE. Separate WAL reader takes snapshot. Failure before DELETE blocks reset;
post-reset copy failure preserves committed reset and warns. Disabled/demo/
acceptance keep existing isolation. Retry never repeats the reset/business write.

No new engine/schema/dependency/scheduler or pin-repair endpoint. Lost pins stay
fail-closed until explicit operator investigation. Existing stopped-service
restore/rollback reused on automatic snapshot, verified in fresh process using
#624 domain fixture (checkpoint/coach/match/feedback/readiness/provider identity).

RED/GREEN matrix: daily/weekly union, same-day versions, unchanged reuse, pins
extension/expiry, lost/corrupt state, bad artifacts, deletion failure/retry,
namespace concurrency, failed pre-check/pin, writer exclusion, pre/post reset,
post-copy failure and exact restore/rollback. Guarded tests only; no credentials.
Target tests/smoke/test_snapshot_retention.py plus core/runtime/guard/restore,
then full contributor-safe, contracts, lint/build and isolated browser checks.
Actual results go to ExecPlan/PR; planned matrix is not evidence. Windows/ACL
and live activation NOT RUN. Native review/owner merge remain separate.


Review round1 disposition is recorded in ExecPlan: atomic retirement leaves the
active snapshot-ID catalog before deleting files. Its original manifest is kept
until data removal ends, so interrupted discards resume without treating corrupt
active artifacts as cleanup permission. Unknown/foreign/corrupt retired entries
are preserved. Empty shells without ownership proof are not adopted or deleted.
The pre-reset eligibility decision also controls post-reset: removing a demo
marker cannot turn the same reset into a real-store backup operation.
