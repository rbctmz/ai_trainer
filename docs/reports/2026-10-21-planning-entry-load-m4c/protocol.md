# Frozen M4 numerical feasibility protocol (2026-10-21, before integration)

Question, absolute invariants, baselines and exit rules are copied from
`docs/reports/2026-10-21-planning-entry-dose-m4/README.md` (M4a): technical
constraint feasibility only, never physiological safety. Budget30cases/15minutes,
synthetic Python only, no providers/athlete DB/paid calls. Do not tune dose windows,
medians or entry scope to make templates fit. Any invariant violation rejects the
candidate; report refusal counts separately. Require usable steady-history and
run-only + declared-other-sports positive controls.

Frozen fixture values: athlete-local as_of2026-10-16; Mondays2026-10-26 and
Wednesday2026-10-28; four completed7-day bins at relative ages2,9,16,23days.
Per-session steady durations bike60/run40/swim20minutes, each30TSS; source
methods power_tss_bike/hr_tss_run/pace_tss_swim. Coverage full28days or explicit
unknown/partial. Declared other-sport limits bike60min/1session/max60 and
swim20min/1session/max20; running40min/1session/max40. Old context28mixed
60min/70TSS activities at ages30..84 step2 is fixed and cannot raise caps.
Twelve histories each on both anchors (24): run-only; matched-aggregate mixed
run1/bike2/swim1, each40min/30TSS; steady3sports; emptycomplete; emptyunknown;
sparsecomplete (age2runonly); missingduration (newest runNone); partialcapture;
complete multisport (explicit envelope+threelegs at each bin); partialmultisport
(swimlegonly); identicalduplicate (newest run); conflictingID (newest run+80min).
Six cases: future row age-1; today row age0; zero-TSS positive duration linked
stages; nonfinite newest run duration; nonfinite declared bike weekly limit;
edit retaining original Wednesday entry anchor. Fixed8week horizon,10h all7days,
training_goal balanced triathlon, no events. Partial/future rows cannot fabricate
positive reference or ownership. A missing/infeasible dose may refuse explicitly.
Baselines: unchanged global CTL/mix characterization from M4a; active-nonempty-
week summary; complete28day-bin observed envelope. Freeze this file before first
numerical operator run; record exact runner/code checkpoint, counts, invariant
results, relative dose/feasibility changes and elapsed time in the tracked report.
