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
