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

## Prospective Validation Status

- Class A architecture-changing PR: **done — PR #496** (prospective row above).
- Class C UI/docs PR: **done — PR #497** (prospective row above; сам пилот — пост-мержевая запись метрик).
- Routing/lead-time verdict: **routing verified on both pilots** (Class A провёл полный контур, Class C прошёл fast track; P0/P1 coverage сохранился — оба P1 пойманы до merge). Сокращение lead time с n=2 не доказывается; thresholds и trend остаются на Revisit Gate (5–10 prospective PR).

## Revisit Gate

After 5–10 **prospectively classified** PRs, compare medians within similar change types and
inspect P0/P1 and blocking-P2 coverage, escaped defects, follow-up P2, CI
reruns/flakes, and wait time. Keep, tighten, or change the class boundaries and two-round review budget
from that evidence; do not optimize from the two-case baseline alone.
