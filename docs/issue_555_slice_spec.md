# Slice spec and review — #555

Author/integrator: Codex. Checker: OpenCode (pending availability smoke). Merge owner: human. Class A — Full due to persistence/provider and public-contract changes. Review mode manual, budget 0/2, acceptance head pending.

## Scope and contracts

Import eight ordinal self-reports; persist provider/day snapshot; expose dated observations to API, Coach and web. DB additive table; API/TS additive optional block. Existing readiness/load algorithms unchanged. No external write, diagnosis, new questionnaire, nutrition/cycle/comments, or statistical model. ExecPlan: issue_555_execplan.md.

## Definition of Done

- [x] Full route and negative acceptance checks pass.
- [x] Contract extraction, web lint/build, synthetic browser evidence complete.
- [ ] Independent checker and final evidence bundle complete; human decides merge.

## Failure, reset, rollback and identity

New table owned by intervals, key (provider,date), retained as existing wellness history until full reset. No new cursor. Chunk transaction includes data and cursor, serialized writer checks fetch order and provider timestamp. Missing/invalid are explicit; old rows cannot fill current day. Reset deletes observations and cursor. Old code ignores the additive table. Retry preserves one row per day.

## Evidence boundary matrix

| Identity/time | Evidence | Expected |
| --- | --- | --- |
| current day | valid | labeled current observation |
| historical | valid, new activity today | stale, not current |
| future | valid | excluded from today's read |
| current | null/absent/invalid | explicit missing/invalid, no healthy default |
| same date | correction/clear | replace old values |
| same date | older fetch/provider timestamp | reject stale replacement |
| chunk | DB failure | rollback data and cursor |
| reset/restart | persisted | delete on reset; recover on restart |

## RED matrix

New test_issue_555_subjective_wellness.py covers mapping, transport fields, full route, retry, invalid/clear, no mutation, stale and reset. Initial RED: ModuleNotFoundError for new subjective service. GREEN: 8 new tests pass, including real API/Coach route. Existing M4 and readiness tests are compatibility checks, not new RED evidence.

## ASR and handoffs

ASR-REL-2, ASR-REL-3, ASR-MOD-2, ASR-MOD-3 and ADR-0001. Spec owner owns scales and API types. Domain implementer owns storage/sync/Coach. UI specialist consumes frozen labels and states. No UI business logic. New boundary: provider-owned subjective observations remain separate from measured readiness.

## Evidence bundle / review

Implementation complete pending browser/checker. Broad: 2340 passed, 6 skipped, 26 deselected; additional route/date tests subsequently passed. Web lint/build passed; contract checks 67 passed; final focused 50 passed. Desktop/mobile screenshots visually inspected. External reviewer permission pending automatic export gate. Reviewer findings must be reproduced and dispositioned fixed-in SHA / disputed with evidence / follow-up. Two full-diff maximum; subsequent checks only changed delta. Final verdict BLOCK until validation. Human owns merge and later worktree cleanup.
