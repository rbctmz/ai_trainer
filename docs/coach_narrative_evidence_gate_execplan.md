# Coach Narrative Evidence Gate (#499)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

After this change, an athlete sees only a coach narrative whose bounded material claims are supported by canonical structured evidence. A provider may still draft an incorrect explanation, but the application validates the complete final narrative before the first narrative token is delivered, before the decision is classified, and before the assistant message is saved. Unsupported recovery, HRV, trend, session-completion, and calendar-relative claims are replaced by a deterministic evidence-bounded response with stable machine reason codes. Supported text passes byte-for-byte unchanged.

## Progress

- [x] (2026-08-24) Read the issue, workflow, ASR catalog, ADD analysis, ADR-0003, and Class A slice template; created branch `codex/issue-499-coach-evidence-gate` from `e23d344`.
- [x] (2026-08-24) Completed two independent read-only audits of the narrative delivery boundary and canonical evidence sources.
- [x] (2026-08-24) Cheap falsifying check confirmed the existing finalizer passes `Восстановление плохое, HRV подавлен...` unchanged when no evidence gate exists.
- [x] (2026-08-24) Recorded deterministic pure-policy RED: 7 failed, 2 characterization tests passed; the existing streaming trace also exposed raw provider deltas before validation.
- [x] (2026-08-24) Implemented the pure evidence bundle, stable reason policy, deterministic safe replacement, and shared final delivery wrapper.
- [x] (2026-08-24) Persisted additive gate metadata in the existing coach decision audit and exposed the same metadata in the final SSE event.
- [x] (2026-08-24) Completed focused (177 passed), smoke (2055 passed, 1 skipped), contributor-safe (2101 passed, 3 skipped, 26 deselected), Ruff, web lint/build, contract (23 passed), and independent checker gates.
- [ ] Commit, push, open a draft PR with `Closes #499`, and post the final evidence to the issue.

## Surprises & Discoveries

- **Observed**: `api/routers/coach.py` yields live provider deltas directly as `token` events and only later has the complete `final` string. **Inferred**: post-stream validation cannot protect the athlete because an unsupported claim has already been rendered. **Verified by**: static trace of the streaming branch and the existing React token consumer; the cheap falsifier is a scripted stream whose first delta is an unsupported HRV claim.

- **Observed**: readiness already has a canonical structured snapshot with factor-level HRV evidence, freshness, completeness, provenance, and TSB. **Inferred**: a second readiness calculation in the gate would create drift. **Verified by**: `services/readiness_snapshot.py` and ADR-0003; the gate consumes this snapshot unchanged.

- **Observed**: the coach prompt and tools use server-local `date.today()`/`datetime.now()` although `Settings.ATHLETE_TIMEZONE` is canonical. **Inferred**: midnight UTC/local boundaries can make otherwise deterministic relative-date wording disagree. **Verified by**: a fixed `2026-08-23T21:30:00Z` probe, which is already `2026-08-24` in `Europe/Moscow`.

- **Observed**: no canonical comparable-session DTO exists. **Inferred**: claims such as “this session is better than the previous one” must be a data gap even when unrelated activity rows exist. **Verified by**: audit of tool raw results and plan/fact reconciliation contracts.

- **Observed**: independent adversarial probes found that sentence-wide negation, advice, and conditional shortcuts could hide a second assertion, while common Russian forms such as `HRV просел` and `Нагрузка выросла` escaped the initial taxonomy. **Inferred**: guards must be evaluated per matched assertion, not per complete response or sentence. **Verified by**: added regression fixtures for mixed negated/asserted misses, assertion-plus-advice clauses, bare-`при` conditions, and production-natural recovery/trend wording; final checker verdict READY.

## Decision Log

- Decision: validate only a narrow, versioned taxonomy: readiness/recovery, HRV suppression, trend/comparison, missed-session, and calendar-relative claims. Rationale: issue #499 explicitly excludes a generic factuality checker and LLM-as-judge. Date/Author: 2026-08-24 / Codex.

- Decision: use raw structured evidence and canonical snapshots, never formatted tool prose. Rationale: presentation strings are mutable and lose provenance/data-gap semantics. Date/Author: 2026-08-24 / Codex.

- Decision: replace the complete narrative when any material claim fails. Rationale: sentence repair can leave cross-sentence causal meaning intact and is harder to falsify deterministically. Date/Author: 2026-08-24 / Codex.

- Decision: buffer only the final narrative, while continuing to stream meta, tool, and proposal events. Rationale: this is the smallest safe boundary before display, persistence, and decision classification. The cost is later live time-to-first-narrative-token; the local deterministic five-second gate remains required and live latency is recorded as a trade-off. Date/Author: 2026-08-24 / Codex.

- Decision: preserve machine metadata with the decision audit and repeat it in the final SSE event. Rationale: the stable reason must remain inspectable after the transient request without changing historical assistant messages. Date/Author: 2026-08-24 / Codex.

## Outcomes & Retrospective

The bounded gate now freezes one canonical evidence bundle per turn, validates the complete provider narrative before any narrative token is emitted, and uses exactly the delivered text for persistence and decision classification. Unsupported claims fail closed with stable codes and an evidence fingerprint; supported prose stays byte-identical. Legacy decision rows migrate additively, and both web and legacy runtime paths use the athlete-local date from one UTC instant.

Independent review materially improved the policy: five bounded passes closed server-local date drift, comparator normalization gaps, builder exception leakage, internal first-token telemetry drift, sentence-wide false negatives, common Russian-language bypasses, and negation/advice false positives. The final checker verdict is READY. The intentional residual trade-off is that complete narrative buffering delays the first narrative token; meta/tool/proposal events still stream, and any incremental sentence-safe optimization is deferred until live latency measurement justifies the additional state machine.

## Context and Orientation

`models/ai_coach_runtime.py` owns the shared tool and synthesis pipeline. `api/routers/coach.py` owns web delivery, persistence, and the decision log. `services/readiness_snapshot.py` is the only readiness truth. `api/today_snapshot.py` already owns the bounded read-only yesterday plan/fact projection and will expose a small reusable wrapper rather than running the recovery loop twice. `data/database.py` owns the additive coach decision audit schema. `web/lib/types.ts` mirrors additive SSE and decision metadata.

## Plan of Work

First, pin the pure policy with fixed structured fixtures. Build one evidence DTO from a canonical readiness snapshot, successful raw tool results, bounded session evidence, an active race date, one timezone, and one UTC observation instant. Hash its canonical JSON payload for audit linkage.

Second, implement narrow claim detection with explicit negation, intent, and quote exclusions. A green readiness contradiction, a non-suppressed HRV contradiction, a trend without its domain comparator, a missed session without sufficient canonical plan/fact evidence, an invalid timezone, or wrong relative calendar arithmetic must produce stable reason codes in policy order. Missing/stale evidence yields `data_gap`; conflicting evidence yields `replaced`; no finding returns the original bytes.

Third, add a shared final-delivery call after synthesis/post-processing/response-contract formatting. For the API live-provider path, consume the provider stream into a complete string, validate it, then emit chunks of the delivered text. The same delivered text is classified, saved, and returned. Gate exceptions fail closed to a deterministic data-gap response.

Fourth, add additive audit fields to `coach_decisions` and the SSE `done` event. Preserve old rows and existing decision consumers. Refresh the TypeScript contract only for the additive metadata.

Fifth, run the focused matrix, latency gate, existing coach suites, full smoke, contributor-safe pytest, Ruff, web lint/build, contract extraction/check, and one independent review round.

## Concrete Steps

From `/Users/gregkisel/Developer/ai_trainer`:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_coach_narrative_evidence_gate.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke/test_coach_narrative_evidence_gate.py tests/smoke/test_ai_coach_runtime.py tests/smoke/test_coach_native_tools.py tests/smoke/test_coach_first_token_gate.py tests/smoke/test_coach_decisions.py -q
    ai_trainer_env/bin/python -m ruff check models/coach_narrative_evidence.py models/ai_coach_runtime.py api/routers/coach.py api/today_snapshot.py data/database.py tests/smoke/test_coach_narrative_evidence_gate.py
    npm --prefix web run contract:extract
    npm --prefix web run lint
    npm --prefix web run build
    ai_trainer_env/bin/python -m pytest tests/smoke -q
    ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/

## Validation and Acceptance

The fixed readiness fixture must replace poor-recovery and suppressed-HRV text with `READINESS_CLAIM_CONTRADICTED` and `HRV_CLAIM_CONTRADICTED`. Missing readiness and missing comparators must produce explicit data gaps. The UTC-midnight fixture must resolve local today as `2026-08-24`, yesterday as `2026-08-23`, Monday as the weekday, and six days to the `2026-08-30` race. Supported text must compare equal byte-for-byte. A scripted live stream must emit no unsafe narrative token, and persistence/decision/SSE must refer to the gated result and identical metadata.

## Idempotence and Recovery

The gate is pure and performs no writes. Decision columns are additive migrate-on-start fields; rerunning initialization is idempotent. All tests use temporary databases and chat directories. Rollback is a code revert: old decision rows remain readable because every new column is nullable. No live database, provider, plan, historical message, or backfill is modified.

## Artifacts and Notes

RED and GREEN transcripts, contract extractor result, review findings, and local CI state are recorded in the linked slice spec and this living document. The immutable commit SHA is posted to the issue and PR after publication because a commit cannot contain its own hash.
