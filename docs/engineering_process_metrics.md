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
- **Pre-merge P0/P1** — blocking findings discovered and fixed before merge,
  with a source link or labelled session evidence.
- **Pre-merge blocking P2** — correctness-, reliability-, data-, security-, or
  contract-related P2 findings discovered and fixed before merge.
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

## Prospective Validation Status

- Class A architecture-changing PR: `NOT YET`.
- Class C UI/docs PR: `NOT YET`.
- Routing/lead-time verdict: remains open until both pilots complete, then the
  broader 5–10 PR revisit evaluates thresholds and trend.

## Revisit Gate

After 5–10 **prospectively classified** PRs, compare medians within similar change types and
inspect P0/P1 and blocking-P2 coverage, escaped defects, follow-up P2, CI
reruns/flakes, and wait time. Keep, tighten, or change the class boundaries and two-round review budget
from that evidence; do not optimize from the two-case baseline alone.
