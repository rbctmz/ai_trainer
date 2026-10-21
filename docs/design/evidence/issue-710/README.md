# M4 entry-load UI consumer — isolated acceptance brief

2026-10-21. #710 / draft #711, parent #677. Explicit UI/Design handoff from
reviewed M4c runtime3a28f99, current source46e17f4. The owner asked to continue.
Class A remains assigned to the whole delivery. This UI slice consumes existing
API/TS contracts; no backend, schema, AC, ADR or numerical policy is changed.

## Task and first view

On Planning step2 the athlete can describe recorded-history completeness and
optionally enter starting time, frequency and maximum session duration for each
target discipline. Inputs start blank/unchecked; completeness is not inferred
from sync, absence of records or demo values. Dates are explicitly chosen, with
an exclusive end label. Ordinary input validation checks finite positive values,
integer count and internally consistent fields; it derives no baseline or dose.
For an edit, omitting new intent preserves the server's retained-limit semantics.
Changing a field invalidates the preview; reset clears declarations. An uncertain
confirmation keeps the existing identity-only retry and locks.

The primary action remains preview, followed by explicit confirmation. A typed
missing/infeasible refusal displays the server-owned status/reasons and a return
to step2; there is no confirmation button or fabricated successful token. The
successful preview labels limits by recorded history versus athlete declaration,
shows dated scope/coverage and lists every supplied adjustment under disclosure.
No medical safety or goal-attainment claim is added. Only supported server evidence
with can_publish=true permits confirmation. Historical missing assessment stays
unassessed. Technical codes/foreign identifiers are not used as athlete guidance.

## Components and presentation

Reuse existing semantic tokens, form/fieldset/input/disclosure/card patterns.
Files: web/components/planning/EntryLoad.tsx, PlanBuilder.tsx; web/lib/api.ts
preserves structured error payload for presentation without changing HTTP/domain
contracts. No new layout system, global styling or UI math. Actual isolated
browser stack is the interactive prototype; no fake positive API interception.
Synthetic limits in E2E are explicitly typed through the real form, not defaults.

| Scenario | Observable outcome |
| --- | --- |
| unknown history, no limits | real422 needs_baseline; explain next action; no pending token |
| explicit synthetic limits | real200 preview, sourced values visible, identity-only save |
| infeasible1minute inputs | real422 blocked; no active plan or confirm affordance |
| incomplete/invalid form | no preview until chosen fields are valid; no invented value |
| dose edited after preview | old preview discarded, fresh preview identity required |
| explicit complete interval | exact chosen dates/status transmitted, not sync-derived |
| narrow/dark and wide/light | no horizontal page overflow; keyboard toggle and step-heading focus |
| uncertain/stale/cancel/history | original real-backend lifecycle/E2E contour retained |

## Evidence and limits

Before UI edits, the new real-browser consumer test failed on the missing input
heading:1failed/1warning,12.58s; the earlier M4c report independently reproduces
the real422 gap. First UI-focused contour:41passed/1existing warning,59.53s.
Web lint/build passed. Final whole-delivery contour, screenshots and exact-head
independent review are recorded below after execution. Screenshot fixtures use
isolated demo SQLite with providers disabled; real athlete data are untouched.

Visual checks cover390dark and1280light, with input and confirmation source
panels, missing-data and infeasible states. Owner usability testing without
assistance has NOT YET been performed; this does not claim a UX outcome,
screen-reader acceptance, medical validation, native acceptance or merge approval.


## Final local acceptance and review

UI source candidate:f0650b53d8e394a84db539387b699da17f35acdd, delta from46e17f4.
Independent UI consumer round1/2: **READY, zero blocking P1/P2**;5 real entry UI
E2E passed/1existing Starlette warning in12.74s, changed-Python Ruff passed.
The first attempt was blocked at localhost setup by the sandbox; the authorized
rerun passed. HEAD/source unchanged; known parent-owned regenerated PNGs only.
Native remains a separate whole-delivery review, not another UI-delta round.

Author commands from the worktree (venv on PATH, synthetic temporary DB/chat
paths; providers disabled by isolated E2E harness):

    python -m pytest -m e2e tests/e2e/test_planning_entry_ui.py tests/e2e/test_planning_cycle_lifecycle_ui.py tests/e2e/test_planning_build_confirmation_ui.py -q -p no:cacheprovider --tb=short
    python -m pytest -m e2e tests/e2e -q -p no:cacheprovider --tb=short
    python -m pytest -m "not live and not debug and not e2e" tests/ -q -p no:cacheprovider --tb=short
    python -m ruff check . --no-cache
    npm --prefix web run lint
    npm --prefix web run build
    npm --prefix web run contract:extract -- --check
    npm --prefix web run contract:inventory

Results:41 focused passed/1warning59.53s; whole63E2E passed/1warning189.89s;
contributor3965passed/16skipped/87deselected/7warnings277.59s. Five newly added
entry browser cases account for82→87 contributor deselections. Lint/build,
Ruff and contract checks passed. No clinical, provider or real-athlete write test.

Screenshots, generated only by the real isolated journeys:
[input390dark](entry-input-390-dark.png), [input1280light](entry-input-1280-light.png),
[preview390dark](entry-preview-390-dark.png), [preview1280light](entry-preview-1280-light.png),
[missing data](entry-missing.png), [infeasible](entry-infeasible.png).
Input/preview narrow and infeasible panels were visually inspected; existing
automated assertions cover horizontal overflow and keyboard/focus behavior.

Nonblocking reviewer suggestion: announce structured refusals through a live
region or heading focus. Disposition: **follow-up #710**; no demonstrated
screen-reader failure, no new source change or extra review loop. Owner usability
without assistance, screen-reader acceptance and physiological safety remain
unverified. Explicit handoff now returns to Supervisor/Integrator for final-head
CI, native receipt and the owner's separate acceptance/merge decision.


## Remote CI and keyboard-test synchronization

Observed: earlier CI39668399073 onfebfbef had62E2E passes and one assertion
failure at the keyboard-toggle test's Next-disabled check (line94). The later
whole final-source CI39669348958 on4e9efe9 is **SUCCESS**:3942 contributor passed/
39skipped/87deselected/6warnings438.56s;63E2E passed249.81s;24contract passed4.37s;
Ruff and secret scan green. Local and CI skipped counts differ by installed
optional dependencies/fixtures; they are separate executed results.

Inferred: the existing requestAnimationFrame step-heading focus may occur between
the test's checkbox.focus() and global Space. A deterministic checkbox-validation
failure is falsified by the unchanged single local recheck (1passed/1warning,
6.09s), but this does not prove the intermittent race's cause or frequency.
The repeated same-node pytest CLI was deduplicated into one test, not five runs.
No product bug or confirmed causal diagnosis is claimed.

Test-only correction6895cc0 waits for the already-specified step-heading focus,
then asserts that Space actually checks the checkbox before checking disabled
navigation. It retains all input-validation/infeasible-refusal assertions, adds
one observable check and changes no product code. Author focused5passed/1warning
11.04s, Ruff/diff green. The exact correction receives only the remaining scoped
UI review round2; final stable candidate CI/native remain separately SHA-bound.


UI scoped round2/2 READY at6895cc0ef426b446b7009c5c8645fe7dcddad43e: no
new blocking P1/P2. Independent5E2E passed/1existing warning10.78s, Ruff green.
The reviewer confirmed stronger coverage, real keyboard activation and unchanged
refusal assertions, with no product-code changes; the earlier failure cause
remains inferred. HEAD unchanged, only three known synthetic PNG regenerations.
Those generated differences were restored, not included as unrelated evidence.
UI delta budget exhausted; native0/2 remains reserved for whole-delivery review.
