# Engineering Process Metrics

This is an append-only, evidence-first retrospective for the tiered engineering
workflow. Record outcomes after merge or cancellation. Use GitHub timestamps,
checks, review threads, and explicitly labelled working-session observations.
Unknown values are `not captured`; never infer active coding time from calendar
time.

## Metric Definitions

- **Issue lead time** — issue creation to linked PR merge/issue close. Includes
  queue and human wait; report it as calendar time.
- **PR cycle time** — PR creation to merge/close. It is not active review time.
- **Review rounds** — every consolidated reviewer pass, including a clean
  verification or a pass whose findings are disproved without author changes;
  record separately whether the pass triggered changes and distinguish GitHub
  review objects from recorded working-session reviews.
- **Pre-merge P0/P1** — every blocking finding discovered before merge, with a
  source link or labelled session evidence and disposition: fixed, removed by
  narrowing scope, or canceled.
- **Pre-merge blocking P2** — correctness-, reliability-, data-, security-, or
  contract-related P2 findings discovered before merge, with the same explicit
  disposition.
- **Escaped defects** — post-merge defects causally linked to the PR. Absence at
  snapshot time is not proof that none will appear.
- **CI reruns/flakes** — rerun count and failures classified as flaky rather than
  product failures.
- **Follow-up P2** — non-blocking P2 findings converted into an owned issue.
- **Agent wait time** — separately observed quota, action, connector, or human
  wait. If session timing is unavailable, write `not captured`.

## Baseline Retrospective — 2026-08-23

| PR | Retrospective class proxy | Issue lead time | PR cycle time | Review rounds | Pre-merge P0/P1 | Pre-merge blocking P2 | Escaped defects | CI reruns/flakes | Follow-up P2 | Agent wait time |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |
| [PR #493](https://github.com/rbctmz/ai_trainer/pull/493) / [issue #468](https://github.com/rbctmz/ai_trainer/issues/468) | Proxy A — Full | 115h 46m 35s | 18m 44s | 2 labelled working-session checker passes, both triggered changes; 0 formal GitHub reviews | 2 P1 fixed before PR: orphan proposal retention and event-level causal attribution gate | not captured separately in the pre-policy review | 0 linked defects observed as of 2026-08-23; observation remains open | 0 observed; 8 current-head checks green | 0; same-scope findings fixed | not captured |
| [PR #486](https://github.com/rbctmz/ai_trainer/pull/486) / [issue #469](https://github.com/rbctmz/ai_trainer/issues/469) | Proxy C — Fast track | 48h 53m 51s | 43m 49s | 0 reviewer passes visible in GitHub | 0 observed | 0 observed | 0 linked defects observed as of 2026-08-23; observation remains open | 0 observed; 8 current-head checks green | 0 observed | not captured |
| [PR #496](https://github.com/rbctmz/ai_trainer/pull/496) / [issue #441](https://github.com/rbctmz/ai_trainer/issues/441) | **Prospective A — Full** (first pilot) | 203h 57m 44s | 20m 18s | 2 passes: 1 working-session checker (2 P3) + 1 native Codex review (1 P1 + 2 P2); both triggered changes | 1 P1 fixed pre-merge: SDK without `responses` resource (Codex) | 2 fixed pre-merge: picker config branch, probe length | 0 linked defects observed as of 2026-08-23; observation remains open | 0 observed; all current-head checks green | 0; both P3 recorded as optional follow-ups in the slice spec | not captured |
| [PR #497](https://github.com/rbctmz/ai_trainer/pull/497) | **Prospective C — Fast track** (first docs pilot) | N/A (post-merge record, no issue) | 13m 41s | 2 passes: 1 native Codex review (1 P1 + 1 P2) + 1 working-session fix pass | 1 P1 fixed pre-merge: smoke assertion pinned to the new pilot state | 1 fixed pre-merge: ExecPlan M3 milestone closed | 0 linked defects observed as of 2026-08-23; observation remains open | 0 observed; all current-head checks green | 0 | not captured |

### Interpretation

**Observed:** both proxy PRs predate this policy. PR #493 used a pre-policy deep
architecture review whose independent checker found two P1 defects before
publication. PR #486 was a pre-policy one-file docs change and completed without
a separate ExecPlan or visible reviewer pass. Both had green current-head checks
before merge. Timestamps, check counts, and formal-review counts come from the
linked GitHub records as observed on 2026-08-23; the two P1 findings come from
the labelled working-session review, not from formal GitHub review objects.

**Inferred:** the proxies illustrate where class-based ceremony would preserve
deep review and where it could avoid unnecessary documentation burden. They do
not show that contributors can apply the new routing, budget, and bundle in
practice.

**Verified by: NOT YET** for routing usability or reduced lead time. The proxies
only confirm that the proposed class labels fit two historical shapes and that
pre-policy deep review retained P0/P1 scrutiny. Issue/PR timestamps include
unknown queue, human, and agent wait, and active time is `not captured`.

## Review-Loop Incident Retrospective — 2026-08-26

| PR | Class | PR cycle time | Native review rounds | Findings | Manual review requests | Premature ready comments | Disposition | Agent wait time |
| --- | --- | ---: | ---: | --- | ---: | ---: | --- | --- |
| [PR #505](https://github.com/rbctmz/ai_trainer/pull/505) / [issue #500](https://github.com/rbctmz/ai_trainer/issues/500) | Class A — Full | 52h 12m 01s | 13 submitted Codex reviews | 10 P1 + 37 P2; 39/47 findings in three identity/recovery modules | 10, including a duplicate pair four seconds apart | 12 SHA-specific `Ready to merge` comments | 10 P1 and 33 P2 fixed in-branch; 4 final P2 accepted as post-merge follow-ups without issue numbers recorded at merge | not captured |

**Observed:** the repository already limited review to two rounds, but the limit
was prose-only. Automatic reviews were enabled while the maintainer also posted
manual review commands. The readiness workflow checked current-head CI and
GitHub mergeability before a later native review arrived; it neither queried
review threads nor reran on review events. A docs-only outcome commit after the
second pass changed the head and was followed by another full review.

**Inferred:** PR #505 turned a full-diff reviewer into an unbounded edge-case
generator. Large scope amplified the effect, but scope alone does not explain the
loop: the missing executable stop rule and stale readiness projection allowed
every fix SHA to become another review candidate.

**Verified by:** GitHub timestamps and review objects for PR #505, its 47 inline
Codex findings, the 15-commit history, and the pre-fix
`.github/workflows/pr-ready-to-merge.yml`. Issue #506 owns the executable review
gate; issue #507 owns the short agent-visible stop rule.

## Class A Post-Merge Record — PR #563 / issue #557 (2026-09-11)

| PR | Retrospective class proxy | Issue lead time | PR cycle time | Review rounds | Pre-merge P0/P1 | Pre-merge blocking P2 | Escaped defects | CI reruns/flakes | Follow-up P2 | Agent wait time |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |
| [PR #563](https://github.com/rbctmz/ai_trainer/pull/563) / [issue #557](https://github.com/rbctmz/ai_trainer/issues/557) | **Class A — Full** (prospective; merged as `a82be7b`, 36 files, +6684/−328) | 33h 10m 1s | 2h 31m 31s | 2 native Codex rounds at the 2-round budget: round 1 = full diff on `a04aca3` (2 P1 + 3 P2, all triggered changes), round 2 = scoped delta on `4b2db94` (2 new P2, triaged as issues with no code changes; 3 round-1 comments re-anchored without new content) | 2 P1 fixed pre-merge in `73645be`: server-date freshness anchor replaced by the athlete calendar; composite training-status row kept on the sync day instead of the readiness date | 3 fixed pre-merge in `73645be`: `dailySleepDTO.calendarDate` provenance fallback, duplicate-column-tolerant provenance migrations, conflict evidence restricted to intervention-eligible factors | 0 linked defects observed as of 2026-09-11; absence at snapshot time is not proof, the observation stays open | 1 manual re-run (Review gate, after the native round landed on the current head); 4 red gate runs by design while awaiting the native review and the owner acceptance; 0 test-job failures or flakes (CI, Contributor-safe pytest, Web E2E, Web contract artifact green on every head) | 2 non-blocking P2 with reproductions and owned issues: [#564](https://github.com/rbctmz/ai_trainer/issues/564) (conflict evidence quotes the descriptive channel), [#565](https://github.com/rbctmz/ai_trainer/issues/565) (same-day resync rolls `training_readiness` back to an older observation date) | not captured |

**Observed:** the review budget held: two native rounds, no third round requested, no `review-budget-exception` needed. Round 1 produced five findings and all five were fixed in `73645be` with a reproduction or a named invariant plus regression tests (anchor probe across the UTC/Auckland boundary, same-day resync row, captured DTO payload shape, lost `ALTER TABLE` race, stale-HRV driver). Round 2 produced two further findings; both reproduce, neither violates the issue acceptance criteria, so both were answered in writing as `follow-up` with owned issues instead of widening the merged diff. Issue/PR timestamps, the two review objects, the seven resolved threads, the label transitions and the check conclusions come from the linked GitHub records as observed on 2026-09-11.

**Inferred:** the stop rule plus the acceptance step is what ended the loop here, not the absence of findings — round 2 still returned suggestions, and merging on zero open P1 with every P2 triaged in writing is the behaviour the policy intends. Classifying both round-2 findings as non-blocking depended on judging them against acceptance criteria rather than on severity alone.

**Verified by:** the merge commit `a82be7b` (tree identical to the reviewed head `4b2db94`), the green `CI` / `Secret scan` / `Project roadmap sync` / `PR ready to merge` runs on it, the closed issue #557, the seven resolved review threads, and the reproduction steps recorded in issues #564 and #565. Active and wait time remain `not captured`; lead and cycle times are calendar time and include queue, human and agent waits.

## Class A Post-Merge Record — PR #567 / issue #565 (2026-09-12)

| PR | Retrospective class proxy | Issue lead time | PR cycle time | Review rounds | Pre-merge P0/P1 | Pre-merge blocking P2 | Escaped defects | CI reruns/flakes | Follow-up P2 | Agent wait time |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |
| [PR #567](https://github.com/rbctmz/ai_trainer/pull/567) / [issue #565](https://github.com/rbctmz/ai_trainer/issues/565) | **Class A — Full** (prospective, right-sized by merge-owner decision; merged as `63773ed7ce02`, 7 files, +503/−6, 2 commits) | 14h 18m 34s | 11h 34m 43s | 1 native Codex round on `3f08a8d` — clean, no findings; budget 1/2; the round was requested by the merge owner after the PR opened | 0 observed: no independent P0/P1 findings; two defects were found by the author's own atomicity and malformed-date checks before the fix commit and disclosed in the PR body | 0 observed: no correctness, reliability, data, security or contract P2 survived to merge | 0 linked defects observed as of 2026-09-12; absence at snapshot time is not proof, the observation stays open | 0 manual re-runs and 0 test-job failures or flakes; 1 red `PR ready to merge` run while the Review gate awaited the owner acceptance label (expected state, not a test failure); `CI` green on the PR head and on the merge commit | none for this change ([#564](https://github.com/rbctmz/ai_trainer/issues/564) is an independent follow-up from #563) | not captured |

**Observed:** the right-sized Class A contour was sufficient and did not collapse into a loop: one RED→GREEN slice, a filled slice spec, the living ExecPlan extended instead of a new one, focused plus broad Python contours, one independent round, and zero findings in it. Both defects that surfaced came from the author's own falsifying checks rather than from review — the first version's `CASE` compared a date parsed from the readiness *value* column instead of the observation column, which split the value/date pair; the second version derived the rejection counter with `datetime.strptime`, which accepts `2026-7-1` while SQLite `date()` does not, so the counter and the write could disagree. Both were caught before the fix commit by the atomicity test and the malformed-date characterization test, and the counter was re-derived from the write itself so the two cannot diverge. Timestamps, the review ledger status, the label transitions and the check conclusions come from the linked GitHub records as observed on 2026-09-12.

**Inferred:** a small change with real Class A triggers (provenance ownership plus persistent-write semantics) can be reviewed proportionately — narrowing the artefact set did not reduce the evidence demanded of it, because the invariant is proved by the write statement itself and by an independent probe outside the unit tests. One clean round here is not evidence that one round suffices for larger Class A work.

**Verified by:** the merge commit `63773ed7ce02` (tree identical to the reviewed head `3f08a8d`), the green `CI` / `Secret scan` / `Project roadmap sync` / `PR ready to merge` runs on it, the automatically closed issue #565 with the `status: in progress` label removed, the review-gate ledger entry `review-gate/codex-clean/5640061515:3f08a8d23a`, and the reproduction/inspection steps recorded in the slice spec and the PR body. Active and wait time remain `not captured`; lead and cycle times are calendar time and include queue, human and agent waits.

## Class A Post-Merge Record — PR #569 / issue #564 (2026-09-12)

| PR | Retrospective class proxy | Issue lead time | PR cycle time | Review rounds | Pre-merge P0/P1 | Pre-merge blocking P2 | Escaped defects | CI reruns/flakes | Follow-up P2 | Agent wait time |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |
| [PR #569](https://github.com/rbctmz/ai_trainer/pull/569) / [issue #564](https://github.com/rbctmz/ai_trainer/issues/564) | **Class A — Full** (prospective, right-sized by merge-owner decision; merged as `43984faced50`, 8 files, +461/−10, 2 commits) | 15h 33m 12s | 12m 30s | 1 native Codex round on `565a6d3` — clean, no findings; budget 1/2 | 0 observed: no independent P0/P1 findings; no defect surfaced during implementation (the frozen descriptive channel was proved unchanged by a parity probe rather than by a review finding) | 0 observed: no correctness, reliability, data, security or contract P2 survived to merge | 0 linked defects observed as of 2026-09-12; absence at snapshot time is not proof, the observation stays open | 0 manual re-runs and 0 test-job failures or flakes; the Review gate was red until the merge owner accepted the review (expected state); CI `Contributor-safe pytest` on the PR head — **2472 passed, 27 skipped, 26 deselected** (CI has no node dependencies); a separate **local** run in a worktree with `web/node_modules` symlinked gave **2494 passed, 5 skipped, 26 deselected**, 0 failed — the two runs are not interchangeable and are labelled as such here | none for this change | not captured |

**Observed:** the second right-sized Class A change merged in the same shape as the first: one RED→GREEN slice, a filled slice spec, the living ExecPlan extended, focused plus broad contours, web contract regeneration for the additive field, and one clean independent round with zero findings. The evidence that mattered was a differential probe rather than a review finding: the same probe run against `origin/main` and against the branch showed the audit text moving from `HRV: HRV 40.0 мс против базовых 42.5 (−5.9%)` to `HRV 40.0 мс против базовых 45.7 (−12.5%)` at an unchanged gate input of `40.0`, while a four-fixture parity comparison found **0 differences** in the descriptive channel (`score`, `status`, `confidence`, `as_of_date`, `intervention_score`, and the `evidence`/`baseline`/`deviation` strings). Timestamps, the review ledger status, the label transitions and the check conclusions come from the linked GitHub records as observed on 2026-09-12.

**Inferred:** adding a field to a shared contract is cheap to review when the change is proven additive by differential comparison instead of by argument, and the two-probe setup (parity for the frozen channel, before/after for the changed one) is reusable for the remaining evidence-channel work. One clean round on a small diff again does not generalize to larger Class A scope; the reverification cost of a head move stayed the reason to keep the diff small.

**Verified by:** the merge commit `43984faced50` (tree identical to the reviewed head `565a6d3`), the green `CI` / `Secret scan` / `Project roadmap sync` / `PR ready to merge` runs on it, the automatically closed issue #564 with the `status: in progress` label removed, the review-gate ledger entry `review-gate/codex-clean/5644835586:565a6d3d06`, the regenerated `tests/contracts/ts_contract.json` gate, and the reproduction steps in the slice spec and the PR body. Active and wait time remain `not captured`; lead and cycle times are calendar time and include queue, human and agent waits.

## Class A Post-Merge Record — PR #572 / issue #562 (2026-09-13)

| PR | Retrospective class proxy | Issue lead time | PR cycle time | Review rounds | Pre-merge P0/P1 | Pre-merge blocking P2 | Escaped defects | CI reruns/flakes | Follow-up P2 | Agent wait time |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |
| [PR #572](https://github.com/rbctmz/ai_trainer/pull/572) / [issue #562](https://github.com/rbctmz/ai_trainer/issues/562) | **Class A — Full** (prospective; the plan was reviewed separately in PR #571, merged as `facc2b4` after two rounds plus a budget exception; the implementation merged as `c0371558c940`, 37 files, +4509/−81, 23 commits (`facc2b4..ce3cd1f`), milestone-by-milestone with role handoffs) | 1d 23h 44m 41s | 14h 20m 7s | 2 native Codex rounds: round 1 — consolidated full-diff on `9bb781e`, 5 findings (1 P1 + 4 P2); round 2 — scoped delta `9bb781e..ce3cd1f` on `ce3cd1f`, clean, no findings; implementation budget 2/2, no post-budget exception needed | 1 found by review: an idempotent retry mixed the persisted immutable revision with freshly computed eligibility (`services/recovery_analytics.py`), `fixed-in 002fbdd` before merge; 0 escaped | 4 found by review, all fixed before merge: Garmin published a second legacy failure readback (`002fbdd`), the defensive fallback returned a partial block that `project_recovery_capture` filled with `null` (`002fbdd`), the compact `SyncControl` hid the readback below `sm` (`98f2388`), and the restart-evidence section generalised every `capture_failed` as pre-save (`50c3581`) | 0 linked defects observed as of 2026-09-13; absence at snapshot time is not proof, the observation stays open | 1 flake-driven red: `Contributor-safe pytest` failed on two **pre-existing** midnight-window smoke tests unrelated to #562 (reproduced on the base commit `facc2b4` under `TZ=UTC`; they build the fixture day from the process date while routes use the athlete timezone), `fixed-in 2cf3b76`; 1 head with **zero** workflow runs (the docs-only push `50c3581`) retriggered with the empty commit `ce3cd1f`; `CI` green on `ce3cd1f` and on the merge commit `c037155`; 0 manual test re-runs beyond those two | none for this change | not captured |

**Observed:** three of the defects that shaped this change were found by the work itself rather than by review: the `capture_failed` API fixtures carried `succeeded` with no warning and therefore documented a state the product never emits (`fixed-in a9f6790`, with a new cross-field invariant and a real-path parity test); the browser acceptance assertion then exposed a machine code leaking into the user-visible sync line (`fixed-in 661dee6`); and the two explanations of one capture failure were collapsed on the merge owner's decision (`fixed-in 294aeda`). The first independent round was not redundant: it produced a real P1 — a retry of the same `capture_run_id` returned the stored immutable revision while reporting eligibility recomputed from changed inputs — that no local suite had caught, plus three contract-shaped P2s and one documentation inaccuracy. Round 2 was scoped to the delta and returned clean, and the change merged on green with zero open P1/P2 and five resolved threads. Delivery stayed role-separated (Domain/API, UI/Design, Spec/Arch with explicit handoffs); the plan-PR was kept separate per D8. The declared evidence boundary held: local Python contours, browser acceptance through route interception, and an evidence bundle that separates verified-locally from the explicitly unverified live-provider E2E, records the ephemerality of the terminal readback, and confirms the public projection excludes the internal `episode_refresh["error"]`. No schema change or migration shipped, and the non-goals (no backfill, no polling, no automatic plan correction) stayed closed. Operational friction was environmental rather than logical: the required check needed a retrigger, and the merge landed from the merge owner's account roughly two minutes after the gate turned green — no automation in this repository can merge (no `pulls.merge` call exists in any workflow, and no auto-merge event was recorded), so the merge decision stayed human.

**Inferred:** the two-round budget was sufficient but not slack — the expensive part of this Class A change was evidence plumbing (pinned fixtures, route-intercepted browser acceptance, an evidence bundle with explicit boundaries, plus a pre-existing timezone-dependent test pair) rather than review rework, and the second round cost little because it was scoped to a named delta instead of re-reviewing the full diff. A defect class that local suites systematically miss — inconsistency between an immutable stored revision and freshly recomputed derived state — was caught only by the independent round, which is the strongest available argument for keeping at least one native round on Class A even when the author's own acceptance suite is broad. Cross-role handoffs kept the diff reviewable at 37 files, but running two agent sessions against one PR branch produced a real hazard: the merge landed from another session while the reporting session still held the worktree. Lead and cycle time here are dominated by wall-clock waiting (plan-PR round trip, review quota reset), not by effort; they are calendar time and are not comparable with the right-sized records above.

**Verified by:** the merge commit `c0371558c940` (tree identical to the reviewed head `ce3cd1fbdc`), the green `CI` / `Secret scan` / `Project roadmap sync` / `PR ready to merge` runs on it, the automatically closed issue #562 with reason `COMPLETED`, the five resolved review threads with written `fixed-in` answers, the review-gate ledger entry `review-gate/codex-clean/5653331236:ce3cd1fbdc`, the two committed screenshot assets under `docs/assets/`, and the evidence bundle `docs/recovery_snapshot_capture_parity_evidence.md` with ExecPlan v1.20. Active and wait time remain `not captured`.

## Prospective Validation Status

- Class A architecture-changing PR: **done — PR #496**, **PR #563 / issue #557**, **PR #567 / issue #565**, **PR #569 / issue #564**, **PR #572 / issue #562** (prospective rows above).
- Class C UI/docs PR: **done — PR #497** (prospective row above; сам пилот — пост-мержевая запись метрик).
- Routing/lead-time verdict: **routing verified across the prospective records — Class A n=5 (PR #496, PR #563, PR #567, PR #569, PR #572), Class C n=1 (PR #497), total n=6** (Class A прошёл полный контур пять раз, дважды в right-sized виде; Class C — fast track; P0/P1 coverage сохранился: пойманы до merge все P1 — 1 в #496, 1 в #497 (Class C-пилот), 2 в #563 и 1 в #572; #567 и #569 закрыты без независимых P0/P1). Cycle time этих пяти Class A записей — **12m 30s … 14h 20m 7s** (PR #569 12m 30s, PR #496 20m 18s, PR #563 2h 31m 31s, PR #572 14h 20m 7s, PR #567 11h 34m 43s); pre-policy proxy #493 (18m 44s) и review-loop incident #505 (52h 12m 01s) в эту когорту не входят и для вывода о trend не используются. Сокращение lead time с n=6 не доказывается; thresholds и trend остаются на Revisit Gate (5–10 prospective PR).

## Revisit Gate

After 5–10 **prospectively classified** PRs, compare medians within similar change types and
inspect P0/P1 and blocking-P2 coverage, escaped defects, follow-up P2, CI
reruns/flakes, and wait time. Keep, tighten, or change the class boundaries and two-round review budget
from that evidence; do not optimize from the two-case baseline alone.

**Gate decision recorded 2026-09-13 (after #562, n=6 prospective records): keep the class
boundaries and keep the two-round native review budget unchanged.** The #562 record adds the
first Class A case where the independent round caught a defect class local suites missed
(immutable stored revision vs freshly recomputed derived state), which argues against
tightening the budget; nothing in the record argues for widening it either, since round 2 was
a cheap scoped delta and no post-budget exception was consumed by the implementation PR.
Next revisit at **n=10** prospective records, or earlier if a second post-budget exception is
requested for a single PR.
