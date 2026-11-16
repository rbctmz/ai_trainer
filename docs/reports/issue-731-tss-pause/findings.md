# TSS duration experiment: evidence and B0 handoff (#731 / #732)

## Decision

Preserve production TSS math and the local scale. The accepted bounded pass
completed seven exact identities: four running outliers, one swim outlier and
two same-method controls. It did not establish a correct pause-fix algorithm.
This is a Class C evidence/characterization slice, not a runtime correction.
The documentation's former blanket claim that every formula uses moving time
was inaccurate for zone-weighted TSS; it is now corrected without changing math.

## Observed / Inferred / Verified by

Observed: the problem runs have stored local zone durations much longer than
moving duration. The provider's recording duration is close to elapsed time,
while its HR-zone-duration total is close to its moving duration. This supports
different time populations, not a recording-timer-pause claim: nonmovement can
occur while recording continues. Provider zone bins differ from the local bins.
Intervals' selected training load equals power_load on the four runs; on three
it differs from hr_load, and on the fourth all available load values coincide.
The selected-load method identifier was absent, so equality is an observation,
not proof of the provider's selection rule.

Inferred: both time inclusion and cross-method comparison can contribute. A
global scale factor or uniform zone-time rescaling cannot be justified by these
comparisons. Verified by: all five problem values reproduce from saved local
inputs; the primary detail responses expose distinct provider load measures;
the anonymous counterexample in `test_tss_pause_evidence.py` constructs two
possible active-zone histories with identical aggregate zone/moving inputs and
different active-load values. The missing chronology cannot be recovered by a
duration ratio alone.

Observed: the running control selected by closest elapsed/moving ratio has
almost equal clocks and a local zone result close to provider hr_load. No real
swim in the frozen same-method sample has equal elapsed/moving clocks: its best
control still has a material gap. Verified by: deterministic selection by clock
ratio, exact provider identity and pure synthetic no-pause controls. The real
swim no-pause comparison is a named evidence gap, not a passed acceptance claim.

Observed: the outlying swim's local pace formula reproduces its stored value;
changing only duration to provider moving time makes the arithmetic much closer
to provider pace_load. Inferred: the clock definition is consequential.
Verified by: a pure duration sensitivity probe, not a validation of either
source's clock, CSS or distance. No clock substitution is shipped.

## Narrow follow-up gate

Before a runtime correction, specify whether each method should include
nonmoving time, distinguish timer-stopped from recording-but-stationary
segments, and obtain time-aligned movement/HR evidence or an explicit provider
contract that establishes which clock/population each zone uses. A swim clock
decision also needs a genuine no-pause control and distance/CSS comparability.
Raw streams must not be persisted. Any approved algorithm needs Class A
acceptance, a failing synthetic regression and an explicit history/capture
compatibility policy: Database initialization can repair activity TSS, so a
formula change is not automatically forward-only. No personal repair is
authorized by this experiment.

## Frozen threshold replay

`scripts/tss_pause_replay.py` reads an explicitly supplied activity JSON; it
does not import Database, select a runtime store, read credentials or perform
network I/O. TSB uses exact canonical 90-date windows and production rounding.
ACWR uses the dashboard's inclusive 91-date history policy, the production EWMA
and its minimum-history/low-chronic-load refusals. Rest days are zero-filled to
each anchor. Multisport lineage is retained before filtering.

The private replay covers ninety evaluation dates on unchanged stored local
TSS, using earlier frozen rows for warm-up. Counts, input hashes and each daily
value are delivered privately, not committed here. Each day is independently
cross-checked by calendar aggregation and exponential recurrences. Thresholds
remain the research proposal: strict TSB < -5 / < -10 and ACWR > 1.3 / > 1.5.
Watch includes attention; exclusive watch counts and eligible denominators are
reported separately. These predicates intentionally differ from the existing
descriptive ACWR zone boundary conventions; no public classifier changes.

This is retrospective reconstruction from current stored activities, not a
replay of the athlete's original immutable readiness captures or a prospective
validation. Earlier research percentages used a different observation window
and persisted TSB coverage; direct before/after improvement is not claimed.
No corrected variant was invented when the pause policy remained unresolved.
The rerun measures alert frequency, not injury risk or clinical correctness.

An early scratch replay omitted provider lineage fields. That result was
discarded after discovering a multisport envelope in the lookback. The final
input preserves the same IDs/dates/TSS values plus the production lineage
projection; a synthetic complete-envelope test prevents double counting.

## Reproduction and validation

For an anonymous supplied JSON with date/sport/tss and activity_id plus
provider_external_id when lineage exists:

    python -m scripts.tss_pause_replay --input frozen.json --output new-output.json --start YYYY-MM-DD --end YYYY-MM-DD
    python scripts/run_isolated_tests.py tests/smoke/test_tss_pause_evidence.py tests/smoke/test_activity_tss_reconciliation.py tests/smoke/test_load_metrics_canonical.py -q
    python -m ruff check .

Output creation is exclusive; input/old results are never overwritten. Exact
private inputs, seven single-attempt GET records, case table and expanded
validation are in the owner's locally git-excluded A2 directory. No actual
identity, date, training metric, stream or API key is included in this report
or the anonymous tests. Tests characterize the current behavior and information
limit; they do not pretend to be a RED/GREEN runtime fix.

## B0 handoff

Role: UI / Design Specialist. Continue #732 B0 on its own branch from accepted
main. Exact scope is the issue's additive Today-only tokens in
`web/app/globals.css` and `web/tailwind.config.ts`: no consumption outside Today,
no pixel changes in B0, existing tokens unchanged. Validate web lint/build and
affected e2e as specified in #732. This domain experiment makes no styling or
layout decisions. B1 keeps TSB/ACWR provisional; B0 does not depend on adopting
a pause correction. B2's persisted Today/Dashboard semantics remain the explicit
owner/spec handoff recorded in #731; they were not delivered by #733.

#731, #660 and #616 remain open. A2 analytical delivery does not claim owner
acceptance of a new method, live-screen parity, B0 completion or issue closure.
