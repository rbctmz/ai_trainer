# Slice spec — persisted Planning handoff (#731 / #733)

- Author/implementer: inherited agent, then Codex via owner handoff 2026-10-26.
- Checker: independent scoped review pending; merge owner: rbctmz.
- ExecPlan: [persisted Planning handoff](issue_731_persisted_planning_execplan.md).
- Class A: persisted provenance/public response semantics. Initial Class B
  extraction is retained as history; no new feature scope is inferred.
- Review: one original local full-diff audit plus scoped verification passes.
  Native rounds remain separate; no new full-diff review requested here.

## Scope and observable contract

Choose the most recent prospective local_date not after the athlete anchor;
within that date choose the latest target revision, id breaks ties. Keep first
capture live fallback and keep saved numbers until another capture. Planning's
metrics, load interpretation, TSB-dependent recommendations/state and readiness
drivers use one selected capture. Captured freshness/intervention fields and
public required fields survive projection. Metrics identify source and capture.

Public API/TypeScript changes are additive: PlanningLoadMetrics and
PlanningReadinessSnapshot mirror existing/new fields; contract extraction and
real-router HTTP conformance verify the response. Database schema, rows, writer,
capture fingerprint, configuration and event contracts are unchanged.

## Non-goals and handoffs

No UI layout/style, provider calls, TSS-scale or threshold changes, A2, merge,
review acceptance or issue closure. #616 stays separate. Dashboard/Today
persisted-reading remains an owner/spec handoff; its transfer into #732 is not
represented as approved/completed by this slice. HRV diagnostics and ACWR keep
their existing distinct input histories; ACWR is not truncated to this window.

## Evidence boundary and RED matrix

| Boundary | Required check | Evidence |
| --- | --- | --- |
| 90/91 dates, report days vary | all live load paths agree | inherited boundary regression |
| yesterday revision 3 / today revision 1 | choose today's row | a84282e regression |
| prospective / backfilled / future rows | exclude wrong mode/future | targeted boundary tests |
| capture / changed inputs / new capture | one consistent HTTP response | 4e97b61 three-phase test |
| captured JSON / older row columns | preserve ReadinessSnapshot contract | HTTP conformance + legacy projection |
| absent capture | live values and source | inherited first-capture fallback |
| repeat HTTP reads | journal unchanged | idempotent read check |

RED at inherited 4e97b61: added real-router PlanningStatus validation fails on
missing readiness_snapshot.computed_at and reason. Additional assertions cover
captured drivers and intervention/freshness evidence. Final GREEN is recorded
below.

## State, failure, rollback and traceability

Source is the selected immutable prospective capture; before first capture,
live canonical metrics. Selection/read errors retain the existing live-fallback
policy; new fail-closed/error contracts are not silently introduced. No new
persistent state means no new reset/retention owner. Current HTTP calls never
append captures. Revert completion code to roll back its projections/TS fields;
synthetic tests prove stored row identities/content remain unchanged.

ASR-REL-2: incomplete evidence is explicit. ASR-MOD-2/3: server-owned semantics,
compatible response and mirrored TS. ADR-0001/0003: web consumes shared Python
facts and canonical snapshot presentation. No UI role handoff is needed to
implement the bounded Python/contract fix.

## Findings and dispositions

| Finding | Disposition |
| --- | --- |
| Standalone 91-day input | fixed-in 41c2f03; preserve fix |
| Global revision ordering | fixed-in a84282e; verify multidate case |
| Persisted numbers with live TSB interpretation | fixed-in 4e97b61; finish public shape/drivers/TS before publication |
| Public snapshot shape and captured drivers | fixed-in 69d62ff; HTTP conformance and capture phases GREEN |

## Evidence bundle and final gate

Code head 69d62ff includes inherited a84282e and 4e97b61. Isolated checks:
110 focused/conformance passed, the expanded boundary suite 9 passed,
extractor/inventory 24 passed, full contributor-safe 4172 passed / 39 skipped /
116 deselected in 289.74s. Ruff, web lint/build, contract freshness and diff-check
passed. All nine changed runtime/test/TS artifacts match the isolated source
tree used for verification. No user database was supplied to the tests.

Code publication verified at remote cb0cbe7 in PR #733; final documentation
is delivered on the same branch. Current-head CI remains a separate gate. The initial
archive/limited-PATH harness failures were investigated and excluded; final
verification used an isolated Git snapshot, project Python and installed Node.
Current screen values and personal backtest are untested. Owner acceptance,
independent checker and merge remain pending. This document does not authorize
another full-diff review, acceptance labels, closing #731/#660 or starting #732.
