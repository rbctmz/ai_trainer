# S4 M3 — integrated acceptance

2026-10-22 Europe/Moscow, #714 / PR #715, parent #677. Supervisor/Integrator
consumes the unchanged [M1 specification](../../planning_confirmation_s4_spec.md)
and [M2 UI evidence](../../design/evidence/issue-714/README.md). Tested product
source d00fb5f570d0f3dae118bc67c7c2a87a01db02d6; actual UI files unchanged since
46201b3. Main is still00de158. M3 adds acceptance evidence and temporary-data
probes only, with no UI/domain/API/schema change. #713 and #712 remain separate.

## Automated acceptance and evidence reuse

[CI39824848819](https://github.com/rbctmz/ai_trainer/actions/runs/39824848819)
was read back during M3 and names exactd00fb5f head, conclusionSUCCESS. It runs the
whole approved contributor-safe contour (3942passed,39skipped,101deselected,
6warnings,442.86s), all77browser tests (327.37s), and contract job24passed(3.49s).
Gitleaks and issue link also passed. No product/test edits since that run require
another copy of the same whole suite for M3; the new named probes below verify
additional acceptance observations. New evidence/scripts will receive targeted
checks and the repository's automatic final-head CI. Earlier two stale-source
failures and their fixes remain recorded in M2; they are not counted as success.

The following is an acceptance-to-executed-test map, not new criteria. All test
names are in the named modules under tests/e2e/ or tests/smoke/ and ran in that CI.
The table alias S4 means tests/e2e/test_planning_confirmation_s4_ui.py.

| M1 ID | Executed observable coverage | Boundary |
| --- | --- | --- |
| S4-01 | test_planning_confirmation_s4_ui::test_frozen_decision_scope_load_and_forecast_are_understandable, six viewport/theme cases; M3 owner-caseA capture | Real backend frozen facts, identity-only confirm; synthetic only |
| S4-02 | same module::test_event_and_manual_summary_use_applied_candidate_data, event/manual | One supported real event fixture; not universal generator support; #707 unchanged |
| S4-03 | same module::test_edit_different_horizon_has_no_undated_comparison; M3 caseB | Actual8→4 preview, absent undateddelta, cancel preserves checkpoint; not a comparable-dose efficacy claim |
| S4-04 | same module::test_replacement_explains_consequence_before_confirmation; test_planning_cycle_lifecycle_ui::test_replacement_requires_ack_and_cancel_keeps_old_selected; M3 caseC | Real replacement preview/cancel, lifecycle/history tests from whole CI |
| S4-05 | test_frozen_decision_scope_load_and_forecast_are_understandable | Canonical payload total/peak/target vs availability; numerical fixture values are not a dose recommendation |
| S4-06 | test_planning_entry_ui::test_missing_starting_data_has_structured_actionable_refusal, test_explicit_starting_limits_preview_sources_invalidate_and_confirm, test_infeasible_explicit_dose_and_input_validation_are_not_success, test_coverage_is_explicit_scoped_and_never_inferred_from_sync; S4::test_structured_readiness_refusal_is_explained_without_confirm | Entry cases use real endpoints; the structured M3-error display case is an explicitly modified422 fixture. No fake publication is claimed |
| S4-07 | S4::test_frozen_decision_scope_load_and_forecast_are_understandable | Keyboard-open dated numeric table; no legacy efficacy message; six screenshot themes/viewports; not a screen-reader user test |
| S4-08 | test_planning_build_confirmation_ui::test_distance_edit_discards_late_preview, test_stale_requires_explicit_new_preview; smoke/test_planning_build_commit::test_confirmation_expiry_boundary_is_checked_under_lock | Browser generation/stale guards plus real server expiry boundary; no implicit rebuild on confirm |
| S4-09 | same browser module::test_lost_response_locks_reset_and_retries_same_identity, test_unresolved_errors_preserve_locked_attempt; lifecycle::test_new_build_lost_response_keeps_preview_identity; M3 caseD | Real confirm commit followed by deliberate transport loss; retry replays same identity |
| S4-10 | same browser module::test_historical_retry_does_not_claim_active_plan; S4::test_legacy_and_partial_display_does_not_invent_current_or_zero; smoke/test_planning_build_commit::test_replay_survives_restart_expiry_rules_and_later_plan | Actual historical replay plus labelled read-only legacy/current-null/partial display fixtures |
| S4-11 | S4::test_legacy_and_partial_display_does_not_invent_current_or_zero, test_structured_readiness_refusal_is_explained_without_confirm; error/stale/uncertain tests above; additional probe_loading.py | Partial/legacy fixtures do not introduce a second publication policy; loading/build-error probe outcome recorded below |

M2 independent UI review1/2 at46201b3 repeated14S4 cases; scoped review2/2 atd00fb5f
repeated9 affected source smoke tests and Ruff, with no open P1/blocking P2. This
is existing evidence, not a new full-diff review round. Native ledger at M3 start:
zero submitted reviews and zero authenticated clean-result comments; budget0/2.

## Four real owner cases

capture_owner_cases.py reuses the repository's existing web_stack harness and
candidate helpers. It creates a temporary SQLite/demo instance, clears provider
credentials, starts its own API/Next ports and removes the instance in finally.
No .env, personal SQLite or live/provider write is used. All images are direct
Playwright DOM captures, not mocks or an edited bitmap. Captures A/B/C cover the
wizard, frozen summary and save controls; D covers the actual unknown-result
status and available controls. Focus/current step are checked after wizard
transitions; CSS animations are finished before capture.

A is a new preparation proposal; B changes the horizon to four weeks and cancels;
C previews replacement of a selected previous cycle then cancels. Temporary
checkpoint assertions verify cancellation effects. D intentionally discards a
successful real-confirm response, verifies controls remain locked, then retries
and verifies replayed receipt with the same preview identity and identity-only
request. Backend facts and diagnostic counts are stored in case-oracle.json;
this is the grading oracle, not a hint supplied with the owner's question.

The first capture attempt incorrectly asserted that every browser console error
was an unhandled JavaScript error. Its four503 entries are solely
/api/planning/events, where disabled provider discovery is unavailable; one
ERR_FAILED is the deliberately aborted confirm response. After recording paths,
only those exact expected network diagnostics are allowed; pageerror/other console
messages still fail. This diagnostic-oracle correction is not a product fix/RED.
A second overly broad assertion expected a new wizard-title focus on the unchanged
step during unknown confirmation; restricted to actual wizard transitions. It is
also a probe assertion error, not a UI patch. The final complete probe exited0:
four real cases captured, cancellations/replay verified, unhandled JS errors0.
No claim of a silent browser console or universal external-provider availability.

## Owner comprehension — pending

The owner was given the four unannotated A/B/C/D screens and one grouped free-text
question. For A/B/C: period, assigned total load, meaning of available hours and
confirmation consequence; for D: what is known and next action. No answer key,
choices with correct answers, coaching or explanation was supplied during the
exercise. Responses, mistakes, ambiguity and any later hints must be recorded
verbatim before scoring. Earlier conversation already explained the product;
this is an unassisted task within that context, not a blind first-use study.
Static screenshots test comprehension; they do not prove interactive task success.

Owner responses: **PENDING**. Hints during this exercise:0 so far. Outcome:
**NOT YET**, not inferred from silence or green automation. Real assistive-
technology testing was not performed; existing #712 is not closed by this work.

## Additional loading/error probe

probe_loading.py uses a separate temporary stack and never changes the four owner
screens after the question. It invalidates the earlier candidate by changing the
load mode, holds the next build request, checks loading/disabled navigation and
absence of confirm, then deliberately fails that request before sending it to
API. Error is visible, rebuild is available, next/confirm are unavailable and no
active checkpoint exists. This is a controlled transport scenario, not a fabricated
successful backend result. Outcome: **PASS**, exit0. Its initial locator used a
spelling of the mode label different from the current returned options; the probe
now selects the actual0.90 option. This was a capture-helper locator error, not
a failed product loading/error assertion. No runtime code changed.

## Reproduction and final checks

From the task worktree, with the primary venv on PATH and PYTHONPATH=.:

    python docs/reports/2026-10-22-planning-confirmation-s4-m3/capture_owner_cases.py
    python docs/reports/2026-10-22-planning-confirmation-s4-m3/probe_loading.py
    python -m ruff check docs/reports/2026-10-22-planning-confirmation-s4-m3/ --no-cache
    npm --prefix web run contract:extract -- --check
    git diff --check

After giving screens to the owner, do not overwrite them during the question.
A rerun can regenerate random synthetic identities; compare semantic facts, not
raw identity equality. No old PNG evidence needs rewriting. Before a native
request, finalize documentation/evidence and confirm current-head CI. Native
request must come from the connected maintainer account and counts at most2rounds.
At this report's commit, no owner acceptance label, ready-to-merge label, native
request or merge has been performed. Native can independently inspect the stable
implementation after final-head CI while the owner's response is pending. That
review does not satisfy the owner-comprehension criterion. Later responses and
review receipts are append-only issue/PR records; do not push cosmetic outcome
updates after native review just to invalidate its head. If a response reveals a
real blocking behavior, reproduce it and follow the bounded fix/delta-review
process. Merge still requires a separate explicit owner decision.
