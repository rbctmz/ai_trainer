# Enforce the finite A-G coach narrative evidence whitelist

This ExecPlan is a living document. Keep `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` current while issue #523 is in
progress. The repository contract is `docs/gate_whitelist_contract.md`; this
plan explains how to make that contract executable.

## Purpose / Big Picture

The athlete-facing coach may describe a completed session, a longitudinal
trend, or an explicit future plan. After this change, historical comparison
claims are accepted only when they match one of the finite A-F forms and every
named metric has matching structured evidence. Explicit future form G remains
outside historical evidence validation. Ordinary advice and statements that do
not make a historical trend/comparison claim remain unaffected.

The observable result is deterministic: supported claims pass byte-identical
when their evidence and direction agree; missing, ambiguous, cross-domain, or
unsupported historical claims fail closed with the existing stable reason
codes.

## Progress

- [x] 2026-08-31: Synced `codex/issue-523-coach-gate-whitelist` to current
  `origin/main` (`d6f8ade`), which includes the merged A-G prose contract.
- [x] 2026-08-31: Re-ran the focused baseline: 92 tests passed.
- [x] 2026-08-31: Audited the current evidence projection and identified
  missing executable paths for generic completed-session and session-HR claims.
- [x] 2026-08-31: Added RED contract-matrix tests for forms A-G, unsupported historical
  forms, target binding, and metric-domain isolation.
- [x] 2026-08-31: Implemented the finite classifier, exact target/evidence
  matching, same-session HR evidence, and the three-observation longitudinal
  threshold.
- [x] 2026-08-31: Ran focused, smoke, contributor-safe, Ruff, contract
  freshness, and diff checks.
- [x] 2026-08-31: Committed the first GREEN implementation as `82e01c4` and
  opened draft PR #525 linked to #523.
- [x] 2026-08-31: Reproduced all six findings from the first native Codex
  Review as 10 failing assertions: metric context, explicit future tense,
  exact comparator pair, claimed discipline, previous-session object, and
  literal longitudinal HR direction.
- [x] 2026-08-31: Closed the review delta without expanding A-G, then reran
  focused, smoke, contributor-safe, Ruff, contract freshness, and diff checks.
- [x] 2026-08-31: Reproduced the scoped delta-review finding for all four
  missing personal forms of future `быть`, added them to the explicit-future
  recognizer, and closed the final RED/GREEN slice at 170 focused tests.
- [x] 2026-08-31: Reproduced the final same-clause finding with two failing
  assertions and bound the explicit future verb to the clause containing the
  temporal marker and historical candidate.

## Surprises & Discoveries

- Observed: PR #524 added `docs/gate_whitelist_contract.md` to `main`, but no
  executable gate change accompanied it. Verified by `git log` and the focused
  92-test baseline.
- Observed: issue #523 contains a bot report for local SHA `0e30cda`, but GitHub
  has no such commit, branch, or PR. Verified by the commits API and PR search.
- Observed: the existing comparable-session result carries one sport metric
  (pace or power) and TSS, but no explicit heart-rate comparison. Verified by
  `models/comparable_sessions.py`.
- Inferred: treating every arbitrary sentence outside A-G as unsafe would
  regress neutral coaching text. The fail-closed default therefore applies to
  detected historical trend/comparison candidates, while unrelated text keeps
  the existing pass behavior. This is falsified if a neutral-advice regression
  test begins returning a trend reason code.
- Observed: running two broad pytest suites concurrently exhausted local socket
  buffers and made the preflight socket constructor fail with `Errno 55`.
  Verified by rerunning sequentially: the focused, smoke, and contributor-safe
  suites all passed; no product change was made for the environmental failure.
- Observed: target-only identity was insufficient for form B. Two evidence
  records could share the target while comparing pace and HR against different
  prior sessions. Verified by the native-review reproduction; compound claims
  now require one exact target/comparator pair.
- Observed: pairwise HR improvement and longitudinal HR direction need
  different projections. Lower HR can support pairwise improvement, while a
  literal claim that HR rose or fell must follow the numeric delta. Verified by
  paired RED/GREEN assertions for three dated observations.
- Observed: recognizing only third-person `будет`/`будут` made otherwise
  explicit form-G clauses with `буду`, `будешь`, `будем`, or `будете` fail
  closed as historical. Verified by four failing assertions before extending
  the finite future-tense pattern.
- Observed: an explicit future auxiliary in a later independent clause could
  previously suppress validation of an earlier marker-only or completed claim.
  Verified by two RED examples separated by `, а затем`; future detection is
  now bounded to the marker-and-claim clause.

## Decision Log

- Decision: classify bounded historical trend/comparison candidates into A-F,
  with G recognized as explicit future; unsupported candidates map to a missing
  evidence result. Rationale: finite policy without turning the gate into a
  general Russian-language factuality checker.
- Decision: keep readiness, HRV suppression, calendar, missed-session, causal,
  replacement-text, and reason-order behavior unchanged. Rationale: issue #523
  is limited to trend/comparison evidence.
- Decision: preserve existing public API and TypeScript shapes. Any additional
  comparator evidence is internal/additive and must not mutate source data.
- Decision: require one exact target/comparator identity across all metric
  evidence for a compound session claim. A date in the claim may disambiguate
  targets, but never permits metrics from different prior sessions to combine.
- Decision: three pairwise observations count as longitudinal evidence only
  when they use one metric, one discipline, at least three distinct target
  dates, and one consistent direction. Rationale: implement the contract's
  explicit alternative without mixing disciplines or duplicate observations.
- Decision: a temporal marker such as `следующая` is form G only when the same
  clause contains an explicit future verb. Completed or marker-only wording is
  validated as historical and fails closed without evidence.
- Decision: retain discipline-qualified longitudinal domains and match an
  explicit run/bike/swim noun in the claim. The unqualified domain is exposed
  only when exactly one discipline satisfies the three-observation threshold.

## Outcomes & Retrospective

The finite policy is executable and verified locally. Forms A/B now bind exact
session metrics, C/E cannot be proven by one pair, D preserves its historical
clause, F recognizes all four completed verbs, and G remains explicit future.
Multiple comparator identities fail closed; an ISO date disambiguates only one
matching target. Same-session average HR is source-labelled and additive. The
review delta also binds pace evidence to a training metric, requires an actual
previous-session comparison object, preserves claimed sport, and keeps literal
longitudinal HR direction separate from pairwise improvement semantics. The
explicit-future recognizer covers every present personal form of future
`быть`, not only third person, and does not borrow that verb from another
clause.

Validation completed on 2026-08-31:

- focused gate + comparable sessions: 172 passed;
- smoke: 2188 passed, 1 environment skip;
- contributor-safe: 2234 passed, 3 skips, 26 deselected;
- Ruff, contract artifact freshness, and `git diff --check`: passed.

No persistent state, API/TypeScript contract, frontend, or plan mutation was
introduced. Native PR review and CI remain the final external gates.

## Context and Orientation

`models/coach_narrative_evidence.py` builds an allowlisted evidence payload and
is the final deterministic boundary called by `models/ai_coach_runtime.py`.
Historical trend detection currently lives in regex helpers in the same file.
`models/comparable_sessions.py` constructs the source-labelled pairwise session
comparison consumed through `get_comparable_session`. The focused contract
suite is `tests/smoke/test_coach_narrative_evidence_gate.py`.

The new `models/coach_narrative_evidence_gate.py` owns only the finite A-G
classification matrix. Evidence collection, delivery replacement, runtime
fallback, and non-trend policies stay in the existing module.

## Plan of Work

First add tests that expose the missing supported paths: A/B metric isolation,
F completed-tense variants with and without a comparator, G explicit future,
date-based target disambiguation, and rejection of an unsupported historical
comparison despite generic evidence. Confirm those tests fail for the intended
reason.

Then add a small pure classifier that returns form, required domains, direction,
and optional target date for each historical candidate. Replace the current
domain heuristics in validation with per-claim evidence resolution. Extend the
internal comparable-session evidence projection only as far as needed to expose
generic session identity and same-session heart-rate evidence.

Finally run the focused suite, all smoke tests, contributor-safe tests, Ruff,
and `git diff --check`. Since public API/web contracts are intended to remain
unchanged, run the contract freshness checks as a falsifying check rather than
regenerating artifacts.

## Concrete Steps

From `/Users/gregkisel/Developer/ai_trainer`:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_coach_narrative_evidence_gate.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke/test_comparable_sessions.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke -q
    ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/
    ai_trainer_env/bin/python -m ruff check models/coach_narrative_evidence.py models/coach_narrative_evidence_gate.py models/comparable_sessions.py tests/smoke/test_coach_narrative_evidence_gate.py tests/smoke/test_comparable_sessions.py
    npm --prefix web run contract:extract -- --check
    git diff --check

## Validation and Acceptance

Acceptance is demonstrated by a table-driven A-G suite plus negative cases:

- A and B pass only with metric-matched, unambiguous session evidence.
- C and E reject one comparable-session pair and accept only a matching
  longitudinal domain already supplied by the relevant aggregate tool.
- D validates its historical clause independently of its future clause.
- F treats `была`, `получилась`, `оказалась`, and `вышла` as completed.
- G remains pass-through only with an explicit future verb/marker.
- Unsupported historical forms and cross-domain evidence fail closed.
- Neutral advice and all non-trend policy regressions stay green.

## Idempotence and Recovery

The change is pure and stateless. It introduces no database rows, files at
runtime, cursors, migrations, or network calls. Re-running validation with the
same narrative and evidence produces the same result and fingerprint. Rollback
is a normal commit revert; the prior gate has no persisted state to restore.

## Artifacts and Notes

The issue contract is #523. The immutable prose whitelist is
`docs/gate_whitelist_contract.md`. The final PR body must include exact test
commands and `Closes #523`; UI screenshots are not required because no UI
surface changes.

## Interfaces and Dependencies

The classifier exposes a frozen claim-contract value with: form A-G or
unsupported, required evidence domains, claimed direction, and optional target
date. It depends only on Python standard-library regex/dataclasses. The existing
`CoachNarrativeGateResult` metadata shape and reason codes remain compatible.

## ASR / ADR Traceability

- ASR-REL-2: missing or ambiguous evidence becomes a data gap rather than a
  fabricated claim.
- ASR-MOD-2 and ASR-MOD-3: policy remains server-owned and contract-compatible.
- ASR-PERF-2: classification is local, deterministic, and bounded; no provider
  call enters the coach hot path.
- ADR-0001 is unchanged: the behavior remains shared Python domain logic used by
  the API/web primary path, not duplicated in legacy Streamlit or the frontend.
