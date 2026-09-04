# Slice Spec and Review: issue #523

- Issue / PR: #523 / pending
- Author / checker / merge owner: Codex / pending independent checker / Greg
- Date: 2026-08-31
- Candidate head SHA: pending

## Change Class

- Class: A
- Rationale: new finite evidence-policy boundary for athlete-facing claims.
- Automatic escalation triggers checked: safety/evidence semantics and a new
  architecture boundary both require Class A.
- Review budget used: 0 / 2 rounds
- Review trigger mode: manual
- Review acceptance head SHA: pending
- Review budget exception: N/A

## Scope

- Behavior that changes: historical trend/comparison candidates are classified
  against A-F and matched to exact evidence domains; explicit future G and
  unrelated text preserve pass-through behavior.
- Files/modules in scope: coach narrative evidence/classifier, comparable-session
  evidence projection if required, focused smoke tests, ExecPlan and this spec.

## Non-goals

- Behavior deliberately unchanged: readiness, HRV suppression, calendar,
  missed-session, causal, UI, API, planning, and replacement wording policies.
- Deferred work and owner: new longitudinal pace/power/HR producers are separate
  product work; until such evidence exists those claims fail closed.

## Definition of Done

- [x] Acceptance criteria are observable.
- [x] Required tests/checks are named in the ExecPlan.
- [x] Merge owner is Greg; cleanup owner is Codex after merge confirmation.

## Public Contracts

- API and TypeScript: unchanged.
- Database/events/configuration/CLI: unchanged.
- User-visible contract: changed compatibly for bounded historical
  trend/comparison safety outcomes; existing reason codes remain stable.

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result: missing, ambiguous, unsupported, or mismatched
  evidence returns the existing fail-closed trend reason.
- Retry/idempotency key and duplicate behavior: pure function; identical inputs
  yield identical outputs.
- Rollback procedure and proof: revert the implementation commit and rerun the
  focused baseline.
- [x] No new persistent state.
- [x] Full reset is N/A because no runtime artifacts are introduced.
- [x] Restart and partial-failure recovery remain unchanged.

## State Boundaries and Identity

- Source of truth and owner: structured tool results assembled by
  `build_coach_narrative_evidence`; policy owned by the model layer.
- Stable identity/provenance keys: target activity id/date and comparator
  activity id/date.
- Cursor/checkpoint lifecycle: N/A.
- Concurrency and stale-write behavior: N/A; validation is immutable.

## Evidence Boundary Matrix

| Identity | Time/provenance | Evidence state | Fallback | Expected result / falsifier |
| --- | --- | --- | --- | --- |
| one target | historical pair | exact metric present | allow | byte-identical pass |
| one target | historical pair | wrong/partial metric | fail closed | missing comparator reason |
| many targets | historical pair | no claim date | fail closed | ambiguity is not guessed |
| dated target | historical pair | exactly one date match | allow | unrelated pair ignored |
| period | longitudinal | aggregate matching domain | allow | direction checked |
| one pair | longitudinal | pair only | fail closed | pair never proves trend |
| future | explicit future verb | no evidence | allow | form G stays outside history |
| arbitrary text | no historical candidate | no evidence | allow | no false-positive trend block |

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| F completed variants | parameterize all four verbs with a valid pair | builder lacked generic session domain | 4 variants pass; missing pair blocks |
| B pace + HR | same target exposes both metric domains | builder had no session-HR evidence | additive source-labelled HR comparison |
| dated A disambiguates | two pairs, one matching claim date | global aggregation dropped both | exact date selects one target |
| unsupported history fails | generic aggregate plus non-whitelisted claim | generic domain passed | unsupported candidate blocks |
| C multiple observations | three dated same-sport pace pairs | one pair was always insufficient | 3 consistent dated observations pass |
| G remains future | explicit future table | characterization stays green | pass-through preserved |

## ASR / ADR Traceability

- ASRs affected: ASR-REL-2, ASR-MOD-2, ASR-MOD-3, ASR-PERF-2.
- ADR reused: ADR-0001 web-primary/shared-domain boundary.
- Tactic and trade-off: finite deterministic policy over open-ended language;
  unsupported variants prefer false refusal to unsupported athlete claims.
- New architecture boundary: per-claim target binding for multiple structured
  session comparisons.

## Delivery Slices

1. Classifier and contract matrix: RED, GREEN, focused verification.
2. Session identity and HR evidence: RED, GREEN, comparable-engine verification.
3. Broad regression and evidence bundle.

## Evidence Bundle

- Head SHA: recorded in the draft PR evidence bundle after push
- Changed invariants: metric isolation, exact comparator identity, historical
  tense, longitudinal minimum, explicit future separation
- Focused and broad tests: 158 focused; 2174 smoke; 2220 contributor-safe
- CI checks/reruns/flakes: local green; one parallel-only socket exhaustion was
  falsified by sequential green reruns
- Lifecycle/probe evidence: pure-function repeatability
- Changed contracts: gate/evidence and comparable-session rule versions bumped
  to v2; public API/TypeScript artifact unchanged and fresh
- Unresolved review-thread count: 0 before PR
- Residual risks and follow-ups: new Russian phrasings outside A-G intentionally
  fail closed; new longitudinal producers remain separate work

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| P3 | Observed one parallel-only socket resource failure; sequential reruns green | no gate | closed |

## Native Review Rounds

| Round | Reviewed head SHA | Trigger | Findings disposition | Stop / exception decision |
| ---: | --- | --- | --- | --- |
| 1 | pending | manual | pending | pending |
| 2 | pending if needed | verification | pending | stop |

## Final Verdict

- Verdict: READY for commit and draft PR; native review/CI still pending
- Blocking findings remaining: none locally
- Review rounds used: 0
- Accepted risk or follow-up issue: pending
- Merge owner final gate: Greg
- Post-merge sync/branch/worktree/progress cleanup: Codex after confirmation
