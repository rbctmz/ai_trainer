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
- **Review rounds** — consolidated finding batches followed by author changes;
  distinguish GitHub review objects from recorded working-session reviews.
- **Pre-merge P0/P1** — blocking findings discovered and fixed before merge,
  with a source link or labelled session evidence.
- **Escaped defects** — post-merge defects causally linked to the PR. Absence at
  snapshot time is not proof that none will appear.
- **CI reruns/flakes** — rerun count and failures classified as flaky rather than
  product failures.
- **Follow-up P2** — non-blocking P2 findings converted into an owned issue.
- **Agent wait time** — separately observed quota, action, connector, or human
  wait. If session timing is unavailable, write `not captured`.

## Baseline Retrospective — 2026-08-23

| PR | Class | Issue lead time | PR cycle time | Review rounds | Pre-merge P0/P1 | CI reruns/flakes | Follow-up P2 | Agent wait time |
| --- | --- | ---: | ---: | --- | --- | --- | --- | --- |
| [PR #493](https://github.com/rbctmz/ai_trainer/pull/493) / [issue #468](https://github.com/rbctmz/ai_trainer/issues/468) | A — Full | 115h 46m 35s | 18m 44s | 2 labelled working-session checker rounds; 0 formal GitHub reviews | 2 P1 fixed before PR: orphan proposal retention and event-level causal attribution gate | 0 observed; 8 current-head checks green | 0; same-scope findings fixed | not captured |
| [PR #486](https://github.com/rbctmz/ai_trainer/pull/486) / [issue #469](https://github.com/rbctmz/ai_trainer/issues/469) | C — Fast track | 48h 53m 51s | 43m 49s | 0 corrective rounds visible in GitHub | 0 observed | 0 observed; 8 current-head checks green | 0 observed | not captured |

### Interpretation

**Observed:** PR #493 used the full architecture review path and its independent
checker found two P1 defects before publication. PR #486 was a one-file docs
change and completed without a separate ExecPlan or visible corrective review
round. Both had green current-head checks before merge. Timestamps, check counts,
and formal-review counts come from the linked GitHub records as observed on
2026-08-23; the two P1 findings come from the labelled working-session review,
not from formal GitHub review objects.

**Inferred:** class-based ceremony preserves deep review where state and causal
correctness require it while avoiding the same documentation burden for a small
docs change.

**Verified by:** the two cases verify that the routing is usable and retained
P0/P1 scrutiny for the Class A case. They do **not** yet verify reduced lead time:
issue/PR timestamps include unknown queue, human, and agent wait, and active time
is `not captured`.

## Revisit Gate

After 5–10 classified PRs, compare medians within similar change types and
inspect P0/P1 coverage, escaped defects, follow-up P2, CI reruns/flakes, and wait
time. Keep, tighten, or change the class boundaries and two-round review budget
from that evidence; do not optimize from the two-case baseline alone.
