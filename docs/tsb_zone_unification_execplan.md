# Unify TSB threshold logic onto a single canonical models.banister.tsb_zone()

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md` (repository root).

## Purpose / Big Picture

TSB (Training Stress Balance = CTL − ATL, where CTL is Chronic Training Load and ATL is
Acute Training Load — see `models/banister.py::BanisterModel`) is a single number that
says how fresh or fatigued an athlete currently is. Before this change, roughly a dozen
different places in the codebase independently decided "what does this TSB number mean"
using their own hardcoded boundary values, and those boundaries disagreed with each
other. The AI coach could describe an athlete as "хорошая форма" (good form) via one
code path while a chart on the same page painted the exact same TSB value red
("переутомление" / overreaching) via another. After this change, every place in the app
that exists purely to *describe* a TSB value to a user or to the AI coach draws that
description from one shared function, `models.banister.tsb_zone()`, so they can no
longer silently disagree.

You can see this working by running `python -m pytest tests/smoke -q` from the repo
root (inside the `ai_trainer_env` virtualenv) and observing 317 tests pass, including
nine new test files that each pin a previously-independent site to the shared
boundaries (`tests/smoke/test_banister_tsb_zone.py`,
`tests/smoke/test_ai_data_context_tsb_zone.py`,
`tests/smoke/test_ai_tools_interpret_tsb.py`,
`tests/smoke/test_planning_service_forecast.py`,
`tests/smoke/test_planning_page_forecast.py`,
`tests/smoke/test_visualizations_tsb_colors.py`, plus the pre-existing
`tests/smoke/test_dashboard_tsb_zones.py` now pointed at the relocated canonical
function). You can also see it live: open the "Собрать план" simulator in the Planning
page or the dashboard's TSB chart and confirm the color bands, reference lines, and
forecast messages all switch at TSB = −20, −10, and +10 — the same three numbers
everywhere.

## Progress

- [x] (2026-07-02) Audited the 8 sites named in the originating task, discovered the
      premise was false (see Surprises & Discoveries), and swept the repo for every
      independent TSB threshold site — found roughly double the originally-named count.
- [x] (2026-07-02) Classified every site as migrate / leave-alone / out-of-scope, with
      evidence (test coverage grep) for each call, via a design sub-pass plus manual
      verification of its two corrections.
- [x] (2026-07-02) Milestone 1 — added public `TSB_ZONES`/`tsb_zone()` to
      `models/banister.py`; wired `api/routers/dashboard.py` to import it; deleted the
      old private `_TSB_ZONES`/`_tsb_zone`; fixed `_calculate_training_score`'s
      `load_mgmt` label to stop disagreeing with its own file's canonical table; updated
      `tests/smoke/test_dashboard_tsb_zones.py`'s import. Commit `1fc9cd3`.
- [x] (2026-07-02) Milestone 2 — migrated `models/banister.py::get_current_metrics` and
      `get_training_recommendation` to `tsb_zone()`. Commit `ff2be13`.
- [x] (2026-07-02) Milestone 3 — migrated `models/ai_data_context.py::_predict_form` and
      `_generate_load_recommendations` to `tsb_zone()`, the highest product-risk site
      (feeds the live AI coach prompt). Commit `893d7cb`.
- [x] (2026-07-02) Milestone 4 — migrated `models/ai_tools.py::_interpret_tsb` to
      `tsb_zone()`. Commit `75a3710`.
- [x] (2026-07-02) Milestone 5 — migrated `api/planning_service.py::_forecast` to
      `tsb_zone()`. Commit `fa0360a`.
- [x] (2026-07-02) Milestone 6 — migrated `ui/pages/planning.py`'s simulator forecast
      message to `tsb_zone()`. Commit `5929437`.
- [x] (2026-07-02) Milestone 7 — migrated `utils/visualizations.py`'s chart coloring
      (`create_banister_chart`, live; `create_modern_dashboard_chart`, dead code) to
      `tsb_zone()`. Commit `2d5fd2f`.
- [x] (2026-07-02) Wrote this ExecPlan.
- [x] (2026-07-02) Final full validation pass; opened PR #66 (closes #63).
- [x] (2026-07-03) Addressed human review feedback on PR #66 (rbctmz): migrated the
      two remaining `ui/pages/planning.py` 2-tone TSB stat-card sites the plan had
      originally classified "leave alone," and added consumer-level contract test
      coverage for `metrics.form`'s outward path. Commit `f677c8a`.

Remaining: awaiting PR review/merge decision (not this plan's to make).

## Surprises & Discoveries

- Observation: the task that started this work assumed `models/ai_data_context.py` had
  already been migrated to a canonical `models.banister.tsb_zone()`/`TSB_ZONES`
  (boundaries −20/−10/+10), "extracted from `api/routers/dashboard.py` in a prior
  change." Neither claim was true.
  Evidence: `models/banister.py` contained no `tsb_zone` or `TSB_ZONES` symbol before
  this plan's Milestone 1 (confirmed by reading the whole file). The real canonical
  table was `_TSB_ZONES`/`_tsb_zone`, private, still living in
  `api/routers/dashboard.py`, added by commit `028ac6a` (PR #59, issue #54) — a fix
  scoped narrowly to that file's own internal consistency plus two frontend components,
  never touching `models/ai_data_context.py`. `git log -- models/ai_data_context.py`
  showed its last touch predated `028ac6a` by many commits, and reading the file
  confirmed `_predict_form`/`_generate_load_recommendations` still carried two of their
  own hardcoded, mutually-inconsistent boundary sets.
- Observation: a repo-wide grep for TSB threshold comparisons found roughly twice as
  many independent sites as the 8 originally named — both inside files already on the
  list (`api/routers/dashboard.py`'s `_render_quick_actions` had two more independent
  blocks beyond the one already fixed) and in files never mentioned
  (`models/training_planner.py`, `models/coach_explainability.py`,
  `ui/pages/planning.py`'s own separate 2-way `>= -10` badge-color split at two more
  locations).
  Evidence: `grep -rnE "tsb.*(>=|<=|>|<)\s*-?[0-9]|..." --include="*.py" .` — see the
  Decision Log for the full classification this produced.
- Observation: `tests/smoke/test_coach_decisions.py` does not actually pin
  `build_coach_decision`'s −20/−8/5 boundaries, despite appearing to at a glance.
  Evidence: two of its three tests pass TSB-shaped strings (e.g.
  `"TSB -24.0: лучше снизить интенсивность сегодня."`) directly into
  `db.save_coach_decision()` as literal fixture text, never calling
  `build_coach_decision()` at all. The third test that does exercise the real path only
  asserts `decision_type in {"Push", "Moderate", "Recovery", "Monitor"}` — a
  set-membership check that passes regardless of where the boundaries sit. This was
  caught during design review before implementation, not after — `coach_decisions.py`
  was still left alone (see Decision Log), but for the correct reason.
- Observation: `create_modern_dashboard_chart` in `utils/visualizations.py` has zero
  callers anywhere in `ui/`, `api/`, or `web/`, and crashes even on `main` (before any
  change in this plan) with `ValueError: Trace type 'indicator' is not compatible with
  subplot type 'xy'` — a pre-existing bug unrelated to TSB thresholds, in its subplot
  `specs=` declaration.
  Evidence: reproduced directly (`Visualizations.create_modern_dashboard_chart(df,
  {'tsb': 5, ...})` raises before and after this plan's changes); confirmed via
  `git diff` that this plan never touched the `specs=` argument. Flagged as a separate
  follow-up task rather than fixed here (out of scope — this plan is about threshold
  values, not unrelated rendering bugs) — see the spawned background task
  "Fix or remove dead create_modern_dashboard_chart."
- Observation: the same function's gauge had a second, independent inconsistency —
  its `bar` color logic (4 colors: success/amber/red/dark-red) disagreed with its own
  `steps` background-band colors (dark-red/amber/gray/success) for the *same* TSB
  ranges, within a single chart.
  Evidence: read side-by-side in the original code (`utils/visualizations.py` lines
  ~50-51 vs ~62-65 before this plan). Resolved as a natural side effect of Milestone 7
  once both were driven from the same `_TSB_TONE_COLORS`/`_TSB_TONE_BG_COLORS` dicts —
  not an intentional separate fix, just a consequence of unification.

## Decision Log

- Decision: build the canonical `TSB_ZONES`/`tsb_zone()` in `models/banister.py` as a
  plain module-level function, not a `BanisterModel` staticmethod.
  Rationale: it is a pure function of one float with no use for instance state, and
  this repo's own `models/training_planner.py` already establishes plain public module
  functions (`current_periodization_phase`, `recommended_training_days`, etc.) as the
  house style for exactly this kind of shared helper. `models/banister.py` also has no
  repo-internal imports, making it a safe leaf module for both `api/` and `models/`
  code to depend on — unlike `api/routers/dashboard.py`, which cannot be imported from
  `models/` without inverting this repo's dependency direction.
  Date/Author: 2026-07-02, Claude (design review pass).
- Decision: relocate `_TSB_ZONES`/`_tsb_zone` out of `api/routers/dashboard.py`
  entirely (delete, don't alias) and update the one outside importer
  (`tests/smoke/test_dashboard_tsb_zones.py`) to import from the new location, rather
  than leaving a permanent `_tsb_zone = tsb_zone` back-compat shim.
  Rationale: both names were already underscore-prefixed/private by the file's own
  convention, signaling nothing outside the file should reach in. A repo-wide grep
  confirmed the test file was the only outside importer of `_tsb_zone`, and `_TSB_ZONES`
  had zero outside importers. A shim would create a second, permanent name for the
  same function with no consumer benefit.
  Date/Author: 2026-07-02, Claude.
- Decision: in `api/routers/dashboard.py::_calculate_training_score`, migrate only the
  `load_mgmt` sub-score's *label* to `tsb_zone()`, leaving its numeric 0-100 score curve
  (its own −10/20/−25 boundaries) untouched.
  Rationale: the numeric score is a smooth contribution to a composite "Training Score"
  total (blended with fitness/progression/consistency at fixed weights) — a
  fundamentally different concept from a 4-bucket zone description. Redesigning that
  curve was never requested and would silently change every user's overall Training
  Score total.
  Date/Author: 2026-07-02, Claude.
- Decision: classify sites as "leave alone" when they combine TSB with another signal
  (readiness, HRV, sleep, ATL ratio) into a decision or when they gate planning-safety
  budgets, rather than purely describing a TSB value. Applies to
  `ui/pages/dashboard.py::_build_dashboard_v2_summary`'s `state_label` (the actual
  authoritative composite source the canonical zones were copied from — never a
  duplicate to fix), `models/coach_explainability.py`, `models/training_planner.py`'s
  `assess_start_load_state` and three sibling `current_tsb <= -15` guards,
  `models/planning_near_term.py`'s risk-scoring guards, `models/coach_decisions.py`'s
  `build_coach_decision`, `ui/pages/dashboard.py::_render_quick_actions`'s two blocks,
  and (initially — see the reversal recorded further down this Decision Log, dated
  2026-07-03) `ui/pages/planning.py`'s narrower 2-way `>= -10` badge-color split.
  Rationale: four of these eight are pinned by their own dedicated smoke test to their
  own distinct boundaries (`test_coach_explainability.py`,
  `test_training_planner_adaptive.py`, `test_planning_near_term.py`, and originally
  believed `test_coach_decisions.py` — see the correction above), which is strong
  evidence of intentional, separate semantics rather than accidental drift. The
  remaining four (state_label, the two quick-actions blocks, the planning.py 2-way
  split) are judgment calls without test pinning, flagged explicitly rather than
  silently folded into the migration — none had been overridden as of this writing
  (2026-07-02; the planning.py 2-way split was overridden the next day after human
  review — see the dated entry below).
  Date/Author: 2026-07-02, Claude, informed by a design sub-pass.
- Decision: for the three sites whose old code had 5 TSB buckets against the
  canonical table's 4 (`ai_data_context.py::_predict_form`,
  `ai_data_context.py::_generate_load_recommendations`, `ai_tools.py::_interpret_tsb`),
  retire exactly one bucket's string per site by folding its TSB range into the
  neighboring zone's existing text, rather than inventing new text or preserving 5
  outcomes against a 4-zone table.
  Rationale: the whole point of unification is that the same TSB value produces the
  same description everywhere; keeping 5 outcomes would have required either a second,
  finer-grained zone table (defeating the purpose) or an arbitrary tie-break. Folding
  into the nearest existing neighbor keeps all surviving text exactly as authored
  before (no new prose invented) and is called out explicitly, with a negative smoke
  assertion, at each site rather than left as a silent behavior change.
  Date/Author: 2026-07-02, Claude.
- Decision: did not further deduplicate the near-identical forecast-message dicts
  between `api/planning_service.py::_forecast` and `ui/pages/planning.py`'s simulator
  handler, or extend a shared "message text" module across files.
  Rationale: the invariant this plan enforces is the *boundary values* (now unified via
  `tsb_zone()`), not every last presentation string. The two message sets already use
  slightly different wording ("Вы будете в пиковой форме" vs "выход в пиковую форму") —
  forcing them into one shared string table would be a separate, larger refactor with
  its own tradeoffs, not required by the stated goal.
  Date/Author: 2026-07-02, Claude.
- Decision: for `utils/visualizations.py`'s chart migration, define a new
  `_TSB_TONE_COLORS` (solid hex) / `_TSB_TONE_BG_COLORS` (15%-opacity rgba) /
  `_TSB_TONE_EMOJI` palette rather than trying to faithfully preserve every one of the
  old code's colors verbatim.
  Rationale: the old code was already internally inconsistent (see Surprises &
  Discoveries) — there was no single coherent "old palette" to preserve. Chose one
  clean 4-color mapping (green/gray/amber/dark-red for success/neutral/warning/danger)
  reusing colors already present somewhere in the old code (the gauge's `steps` gray
  `rgb(156,163,175)` for the "neutral" tone the canonical table introduces, which had no
  home in the old 4-bucket schemes), applied uniformly to both migrated chart
  functions.
  Date/Author: 2026-07-02, Claude, verified by inspecting the built Plotly figure's
  object graph (marker colors, shape boundaries, annotation text) directly.
- Decision: did not attempt to smoke-test `create_modern_dashboard_chart` end-to-end.
  Rationale: it fails on `main` before this change too, for a reason unrelated to TSB
  thresholds (see Surprises & Discoveries). Verified its specific TSB-color logic in
  isolation instead (constructing a standalone `go.Indicator` figure), and flagged the
  underlying bug as a separate follow-up task rather than fixing or silently working
  around it here.
  Date/Author: 2026-07-02, Claude.
- Decision: reversed the earlier "leave alone" call on `ui/pages/planning.py`'s two
  2-way `tsb_tone = "success" if tsb >= -10 else "warning"` badge-color sites
  (`summary["progress"]["current_tsb"]` and `current_metrics["tsb"]`/`form_status`),
  migrating both to `tsb_zone(tsb)["tone"]`.
  Rationale: human review on PR #66 (rbctmz, 2026-07-03) pointed out that
  `ModernUI.render_stat_card`'s underlying `_tone_color` helper already maps all four
  canonical tones (`danger`/`warning`/`neutral`/`success`) to distinct CSS colors, so
  the 2-way collapse was discarding visual distinction the UI already supported for no
  reason — under the old logic, `"Высокая усталость"` (danger) could never render
  differently from `"Накопленная усталость"` (warning), and `"Свежесть"` (success) was
  indistinguishable from `"Стабильная нагрузка"` (neutral) on these two cards. This is
  exactly the failure mode this plan exists to eliminate; the original "leave alone"
  call was flagged explicitly as a judgment call for this reason, and the reviewer's
  counter-argument was correct. Also added consumer-level contract test coverage for
  `metrics.form`'s outward path (`tests/smoke/test_api_planning.py`), since review
  noted the existing test only pinned the trivial neutral case and never exercised the
  actual outward path the web Planning page reads from.
  Date/Author: 2026-07-03, Claude, per PR #66 review from rbctmz.
- Decision: left the two undocumented frontend TSB checks
  (`web/app/coach/page.tsx:394`, `web/components/dashboard/TodayCard.tsx:25`,
  both `today.tsb < -20`) unimplemented, flagged as a separate follow-up task.
  Rationale: different tech stack (TypeScript, no shared build step with Python),
  different PR scope than a Python threshold-unification change; both already
  coincidentally match the canonical boundary, so there is no active bug, only latent
  drift risk.
  Date/Author: 2026-07-02, Claude.

## Outcomes & Retrospective

All seven migration milestones plus the prerequisite landed, each as its own commit
with its own new smoke-test file, and `python -m pytest tests/smoke -q` stayed green
throughout (296 → 300 → 305 → 307 → 310 → 312 → 315 passed, growing by exactly the
number of new tests added per milestone, zero regressions at any step). The original
task's stated goal — get `models/ai_data_context.py` onto a canonical
`models.banister.tsb_zone()` — is met, along with seven more sites the original task
didn't know about because the canonical function didn't exist yet when it was written.
A subsequent human review round on PR #66 (2026-07-03) found two more sites this plan
had explicitly flagged as a judgment call but left alone; both were migrated in
response (commit `f677c8a`), bringing the suite to 317 passed. That review round is the
best evidence this plan's "flag judgment calls instead of silently deciding" approach
worked as intended — a human caught exactly the kind of borderline case the plan
anticipated it might get wrong, and the flag made that easy to find and fix.

The biggest gap between the original ask and the actual work was scope: the task named
8 sites and assumed a foundation that didn't exist; the real work was building that
foundation first, then covering roughly double the named sites, while leaving a
documented ~8 more sites alone on purpose. Anyone re-reading just the original task
without this document would under-estimate the work by roughly half and would not know
the canonical function had to be built from scratch.

What remains, by design, is the "leave alone" list (composite decision logic and
planning-safety guards, intentionally not unified — see Decision Log) and the two
follow-ups spawned as separate background tasks: the dead, pre-existing-broken
`create_modern_dashboard_chart`, and the two undocumented frontend `TSB < -20` checks.
Neither blocks this plan's own goal.

## Context and Orientation

TSB, CTL, and ATL are computed by `models/banister.py::BanisterModel` from an athlete's
daily Training Stress Score (TSS) history using exponentially-weighted moving averages
(42-day time constant for CTL, 7-day for ATL; TSB = CTL − ATL). This plan does not touch
that computation — only the many places that take an already-computed TSB float and
decide what to call it.

Before this plan, the closest thing to a shared answer lived in
`api/routers/dashboard.py` as module-private `_TSB_ZONES` (a list of
`(upper_bound, label, tone, clause)` tuples) and `_tsb_zone(tsb)` (a function that walks
the list and returns the first zone whose `upper_bound` exceeds the given TSB). Its four
zones, boundaries at −20, −10, and +10: below −20 is `"Высокая усталость"` / tone
`"danger"`; −20 to −10 is `"Накопленная усталость"` / `"warning"`; −10 to +10 is
`"Стабильная нагрузка"` / `"neutral"`; above +10 is `"Свежесть"` / `"success"`. Those
three boundary numbers were themselves copied from `ui/pages/dashboard.py`'s
`_build_dashboard_v2_summary` function, which computes a `state_label` for the
dashboard's "СОСТОЯНИЕ" (state) card by combining TSB *and* readiness (a 0-100 score
from Garmin/HRV data) — that composite function remains the authoritative source of
truth for those three numbers and was never changed by this plan.

This plan's prerequisite step made that same `TSB_ZONES` table and `tsb_zone()` function
public and moved them into `models/banister.py`, so code in `models/` (which cannot
import from `api/routers/dashboard.py` without creating a circular or backwards
dependency) could reach them too. Everything else in this plan is either wiring one more
call site to that function, or explicitly deciding not to.

## Plan of Work

See `Progress` above for the exact sequence executed. In summary: build the canonical
function first (it didn't exist), then migrate each of the seven confirmed "pure
description" sites one at a time, each its own commit with its own new or extended
smoke-test file, running the full `tests/smoke` suite after every single change (not
just the new test) to catch cross-file breakage immediately rather than at the end.

## Concrete Steps

Every step below was run from the repository root
(`/Users/gregkisel/Developer/ai_trainer/.claude/worktrees/suspicious-ptolemy-100fd8` in
this session's worktree; any clone of this repo works identically) with the project's
virtualenv active:

    source ai_trainer_env/bin/activate
    python -m pytest tests/smoke -q

Run after every commit in this plan's sequence (`1fc9cd3`, `ff2be13`, `893d7cb`,
`75a3710`, `fa0360a`, `5929437`, `2d5fd2f`, then `bf6dd28` for this doc, then `f677c8a`
for the 2026-07-03 review-fix round, in that order — `git log --oneline 7041a42..HEAD`
reproduces this exact list against this plan's starting point). Each run showed only
passing tests, no failures, no errors, with the pass count increasing by exactly the
number of new tests that commit introduced.

For the one milestone with a visual (not just textual) output —
`utils/visualizations.py` — verification also included constructing the actual Plotly
figures and inspecting `fig.data[...].marker.color`, `fig.layout.shapes[...].y0/y1/
fillcolor`, and `fig.layout.annotations[...].text` directly in a Python REPL, rather
than relying on the smoke-test assertions alone during development (those assertions
now encode exactly what was inspected manually).

## Validation and Acceptance

Run `source ai_trainer_env/bin/activate && python -m pytest tests/smoke -q` from the
repository root. Expect `317 passed` with no failures or errors. If this instead shows
fewer passed tests or any failures, something in this plan's sequence did not apply
cleanly — bisect with `git log --oneline 7041a42..HEAD` and re-run the suite after each
commit individually to find where it diverges from the counts recorded in Concrete
Steps above.

To observe the user-visible effect directly: start the app (`./run_web.sh` for the
FastAPI + Next.js stack, or `./run.sh` for the Streamlit fallback — see repository root
`CLAUDE.md`), open the Planning page's "Собрать план" tab, expand the simulator, and run
a forecast with a TSB that lands just above and just below −20, −10, and +10 (e.g. very
high planned weekly TSS from a low starting fitness pushes TSB deeply negative; zero
planned load from a balanced start pushes it positive). Confirm the forecast message,
the CTL/ATL/TSB chart's colored background bands, and its three dashed boundary lines
all agree on exactly where each zone starts — they are now driven by the same three
numbers everywhere in the app.

## Idempotence and Recovery

Every step in this plan is a normal, additive code edit followed by a commit — there is
no destructive or one-way operation anywhere in this sequence (no data migrations, no
deleted user data, no irreversible external calls). If a milestone's commit needs to be
undone, `git revert <commit-hash>` for that specific commit is safe or the milestones
can be reverted in reverse order; because each migrated site is independent of the
others (all depend only on the Milestone-1 prerequisite, none depend on each other),
reverting any single migration milestone commit does not require reverting any other.
Re-running `python -m pytest tests/smoke -q` after any revert will immediately show
whether that site's dedicated test file (which would now import a symbol or expect
behavior that no longer exists) needs reverting alongside it — in every milestone above,
the test file was added in the *same* commit as its corresponding source change, so a
single `git revert` of one commit cleanly removes both together.

## Artifacts and Notes

Final smoke suite output (`python -m pytest tests/smoke -q`, run from repository root
inside `ai_trainer_env`, after the 2026-07-03 review-fix round):

    ........................................................................ [ 22%]
    ........................................................................ [ 45%]
    ........................................................................ [ 68%]
    ........................................................................ [ 90%]
    .............................                                            [100%]
    317 passed in 13.81s

Manual verification transcript for the one visual migration site
(`utils/visualizations.py::create_banister_chart`), confirming all four TSB-color
touchpoints move in lockstep at the canonical boundaries:

    marker colors match expected: True
      tsb=   -25 tone=danger   marker=#DC2626  expected=#DC2626  OK
      tsb= -20.1 tone=danger   marker=#DC2626  expected=#DC2626  OK
      tsb=   -15 tone=warning  marker=#F59E0B  expected=#F59E0B  OK
      tsb= -10.1 tone=warning  marker=#F59E0B  expected=#F59E0B  OK
      tsb=   -10 tone=neutral  marker=#9CA3AF  expected=#9CA3AF  OK
      tsb=     5 tone=neutral  marker=#9CA3AF  expected=#9CA3AF  OK
      tsb=    10 tone=success  marker=#10B981  expected=#10B981  OK
      tsb=    15 tone=success  marker=#10B981  expected=#10B981  OK

    shapes (background rects):
      y0=  10 y1=  30 fillcolor=rgba(16, 185, 129, 0.15)
      y0= -10 y1=  10 fillcolor=rgba(156, 163, 175, 0.15)
      y0= -20 y1= -10 fillcolor=rgba(245, 158, 11, 0.15)
      y0= -50 y1= -20 fillcolor=rgba(220, 38, 38, 0.15)

    annotations:
      y=10 text='🟢 Свежесть'
      y=-10 text='🟡 Стабильная нагрузка'
      y=-20 text='🟠 Накопленная усталость'

## Interfaces and Dependencies

In `models/banister.py`, define:

    TSB_ZONES: list[tuple[float, str, str, str]]  # (upper_bound_exclusive, label, tone, clause)

    def tsb_zone(tsb: float) -> dict[str, str]:
        ...  # returns {"label": str, "tone": "danger"|"warning"|"neutral"|"success", "clause": str}

This is the one new stable interface this plan introduces. Every other file in this
plan imports `tsb_zone` (and, only in `models/banister.py` itself, `TSB_ZONES` too)
from `models.banister` and calls `tsb_zone(some_tsb_float)["tone"]` (to select among
several existing, differently-shaped payloads) or `tsb_zone(some_tsb_float)["label"]`
(when a single short display string is all that's needed). No other module should
define its own TSB-boundary constants for the purpose of describing a TSB value to a
user or the AI coach — new code with that need should import `tsb_zone` instead of
adding a tenth independent copy.
