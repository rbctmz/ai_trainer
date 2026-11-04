# Verify TSS duration semantics before changing formulas (#731)

This living plan follows `.agent/PLANS.md`. The owner accepted the seven-case
experiment on 2026-11-04 and explicitly requested a separate branch.

## Purpose / Big Picture

Today must explain training load from trustworthy inputs. A2 paired 69 local
activities with Intervals without finding a universal scale factor. This slice
checks whether the largest differences come from duration semantics: elapsed
time includes stops, moving time excludes some nonmovement, and summed heart
rate zone times are a third quantity. Agreement with Intervals is a comparison,
not a requirement to copy its physiology model.

## Progress

- [x] 2026-11-04: verify #731/#732 and create
  `codex/issue-731-tss-pause-evidence` from fresh origin/main `e98b138`.
- [ ] Freeze four problematic runs, one swim and one low-pause control per sport.
- [ ] Complete one diagnostic pass within one hour; record confirmed rules/gaps.
- [ ] If a violated accepted invariant and correct input semantics are proved,
  escalate the slice to Class A and prepare a separate RED/GREEN fix. Otherwise
  preserve production math and identify the exact follow-up evidence needed.
- [ ] Repeat TSB/ACWR threshold backtest on frozen history; distinguish current
  local baseline from any hypothetical external comparison.
- [ ] Publish a bounded evidence PR and B0 handoff; no merge or issue closure.

## Context and Orientation

The private, locally git-excluded A2 evidence is under
`output/issue-731-a2-2026-11-03/`; it contains source rows, pair identities and
the 90-date window 2026-08-05..2026-11-02. Do not publish those personal rows.
`data/data_processor.py::ActivityProcessor._zone_weighted_tss` sums all supplied
zone seconds; `_pace_tss` uses moving duration, CSS threshold pace and distance.
`models/load_metrics.py` supplies canonical 90-day CTL/ATL/TSB using the local
TSS column. `models/signals_engine.py::acwr_metrics` owns ACWR EWMA semantics and
minimum history. The approved research decision is on branch
`research/today-v2-recon`, file `research/today_v2_recon_2026-10-25.md`:
TSB watch < -5, attention < -10; ACWR watch > 1.3, attention > 1.5, all provisional.

## Plan of Work and Milestones

M1 freezes seven exact identities before fetching new evidence. Choose the five
largest positive A2 deltas and select one running and one swimming control by
closest elapsed/moving ratio among remaining same-method activities. This uses
duration, not closeness of TSS, to avoid choosing a flattering control. Read
only the necessary local numeric fields through mode=ro/query_only; never call
Database, whose initialization can repair data. Make at most seven read-only
activity-detail requests through IntervalsICUClient, timeout 15 s each, no
retries. Save only whitelisted numeric/provenance fields. No wellness, Garmin,
sync or provider writes. If per-sample active-time identity is unavailable, say
so; do not infer a pause mask from total moving duration.

M2 checks each case and independent formula reconstruction, including pure
synthetic pause/no-pause controls. A fix needs a named existing invariant and
enough data for a correct algorithm; uniformly scaling zone times is explicitly
not an established correction. Production changes would require Class A spec
and RED tests before implementation, and must not silently rewrite old captures
or trigger a personal-history repair in this run.

M3 evaluates the accepted thresholds on frozen daily history with zero-filled
rest days. Daily rolling canonical TSB uses only available prior dates, exact
90-day bounds and production Banister math. ACWR uses production EWMA, minimum
84-day history and missing/zero guards. Record denominators, warm-up exclusions,
finite values and overlapping vs exclusive thresholds. Never compare a warm
baseline to a cold-start provider series without disclosing the difference.
Use all available matched frozen activities for sensitivity, not just seven
diagnostic cases. Keep personal backtest results private; repo artifacts contain
synthetic controls, method, decision and honest coverage only.

M4 publishes one evidence PR, linking Refs #731 and #732 without closing them.
Record #733 post-merge process outcome in the same substantive evidence slice.
Hand B0 to the UI/Design Specialist with existing #732 token scope; no CSS or
UI work is performed in this domain/architecture experiment.

## Validation and Acceptance

Seven unique exact identities must have explicit observations or named gaps.
Frozen inputs, selection, calls and outputs must be hash-bound and privately
reproducible. Synthetic tests should demonstrate the current duration behavior,
not invent a desired algorithm. Every causal statement uses Observed/Inferred/
Verified by and includes a falsifying check. Backtest calculation must reproduce
production values on an independent selected-date cross-check and preserve
minimum-history denominators. Run focused contributor-safe tests through
`python scripts/run_isolated_tests.py`, then Ruff. If runtime code changes, also
run the required affected/full contour. A docs/evidence-only result does not
require web lint/build because no web code changes.

## Concrete Steps

From the repository root, inspect private A2 inputs, freeze cases and query the
selected store with SQLite URI mode=ro and query_only. Store all personal
outputs in the already excluded private directory. Run offline diagnostic and
backtest scripts there after the bounded GET pass. For tracked synthetic
characterization use the isolated launcher before pytest plugins load.
Commit only docs and anonymous synthetic code/tests, push this named branch,
open a Draft PR and attach it to this chat. No native review is automatically
requested; no owner acceptance, merge or live write is performed.

## Surprises & Discoveries

Observed: A2 has four runs with zone-time totals greater than moving duration
and one swim with different moving durations between sources. Inferred:
duration semantics may explain the outliers. Verified by: A2 pure formula
reconstruction matched all five values; exact provider pause semantics and
active zone distribution are not yet proved. The cheapest falsification is to
check primary duration fields and a no-pause same-method control.

## Decision Log

2026-11-04, Codex: start as Class C evidence/characterization, with no production
behavior change. Escalate before any persistent/domain formula change. Retain
the existing #731 issue contract rather than create a duplicate epic. Preserve
the local TSS scale; owner accepted diagnosis, not a global multiplier.

## Idempotence and Recovery

Keep a completed-request ledger and never refetch completed case ids on rerun.
Do not persist raw streams. Offline analysis may be repeated from minimal saved
fields. SQLite connections must be read-only and report total_changes=0.
No service restart, config change, migration or private-history mutation is
authorized. Private output stays out of Git via local info/exclude.

## ASR / risk traceability

ASR-REL-2: missing timing data stays an explicit gap. ASR-SEC-1: no keys,
personal identities or raw activity fields enter the PR. ADR-0003 canonical
projection and ADR-0008 local-first TSS/provenance remain unchanged. The catalog
statuses are not changed by an evidence-only experiment.

## Outcomes & Retrospective

Pending diagnosis and backtest. B0 is not started. The one-hour limit applies
to diagnosis; unavailable input becomes a documented gap, not an excuse to
invent a correction or enlarge the experiment indefinitely.

Revision 2026-11-04: created before new provider reads to freeze the owner-
accepted experiment, conditional fix gate and privacy boundary.
