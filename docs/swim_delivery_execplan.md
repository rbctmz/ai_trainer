# Deliver the calendar workout to Intervals.icu and Garmin FR255

This plan follows .agent/PLANS.md. Issue #764 in #760. Class A. The product
contract and checks live in [swim_delivery_slice_spec.md](swim_delivery_slice_spec.md).

## Purpose / Big Picture

A swimmer previews exactly what will go to Intervals.icu from the selected
trainer-authored assignment. The preview exposes incompatibilities before
confirmation. To complete the first 25 m rollout, the provider readback and
a real FR255 must agree on the selected control workout and its rest behavior.

## Progress

- [x] 18 November 2026. Read issue #764, merged calendar 856cacb, the
  current Intervals transport, issue #702 and the applicable ASRs/ADR.
- [x] Establish a separate worktree. Define the owner approval and evidence
  boundaries, authored step projection and candidate transport.
- [x] Provider-neutral projection passes 16 cases for both schemas. RED
  9489593 fails because the projection does not exist yet. GREEN preserves
  all three totals, exact pauses, nested round identity and authored content.
- [x] Native Intervals text and strict readback checks pass offline. RED
  7db257d defines a seven-step 250 m control and mismatched provider
  responses. The reader checks each step as well as pool length and total.
  It rejects missing rests, distance from rest, dropped cues and lost Lap.
  The three complete controls also retain 2200/2000/1900 m in native text.
  The live provider's handling of the zero-duration Lap token is pending.
- [x] Resolve a delivery candidate from the selected calendar without
  provider I/O. RED 27673d3 defines version pinning, stale date and late
  forced rest. All three pass. The separate ai_trainer_swim namespace
  stays outside generic plan cleanup.
- [x] Extend the existing Intervals client with strict date-window preflight
  and exact event-ID readback. RED 66bc756 shows the legacy empty fallback.
  Synthetic HTTP responses verify that malformed lists cannot grant write
  permission and that a different event ID cannot stand in for the target.
- [x] Retain the preview and confirm a single provider attempt. RED
  04668a2 defines the missing interaction. Eleven service scenarios cover
  selection, immutable source, replay, concurrent claims, stale constraints,
  unknown preflight, demo refusal, provider mismatch, backup and full reset.
- [x] Expose typed preview, confirm and receipt read through the calendar
  API. RED 6accce1 found no route. The real HTTP flow proves the retained
  preview and strict Boolean confirmation, plus receipt reload without a second
  write. Update the generated contract with the new response shapes.
- [ ] Wire the confirmed calendar action, verify the isolated browser flow,
  and run CI and independent review. Human acceptance precedes merge.
- [ ] Obtain scope-bound approval and verify receipt and behavior on FR255.
  Check the three complete controls and wider supported profiles separately.

## Surprises & Discoveries

- **Observed**: legacy delivery derives a numeric step duration from generic
  time fields and uses a fallback when they are absent. The authored library
  supplies distance and heterogeneous rest semantics.
- **Inferred**: authored instructions need a dedicated conversion before the
  shared Intervals client, with their own provider identity and readback.
- **Verified by**: repository feasibility probe and current call-path read.
  M4 uses a new failing projection test to cover the actual contract.
- **Observed**: the Intervals maintainer documents native distance and pool
  syntax as well as workout_doc readback. Garmin distinguishes fixed rest,
  open rest and send-off. One FR965 user reported rest-induced distance and
  skipped final rests. The report is a test case for FR255.
- **Inferred**: write the candidate once, read back the compiled structure,
  and check the resulting device behavior in a separate acceptance step.
- **Verified by**: the provider and Garmin sources below. Device findings
  remain unverified.

## Decision Log

Keep one provider route for the initial acceptance. Use native descriptions
via the existing Intervals HTTP client. The independent exact step sequence
is available for checking the compiled response. Unroll repeat structures to
avoid relying on provider repeat-end behavior and surface the step limit.
Treat unsupported pool lengths/forms and ambiguous conditions explicitly.
An alternate transport may be needed if the live provider removes essential
semantics. Evaluate that after reproduced evidence from the same path.

## Context and Orientation

M3 writes immutable library references in selected-cycle checkpoints.
`models/swim_program.py` and `models/swim_program_v2.py` govern steps; the
current calendar service resolves exact saved versions. Generic plan
delivery in `services/intervals_plan_delivery.py` has different ownership
and cleanup semantics. Reuse this repo's provider wiring, version readers,
snapshot state, and safety guards. Keep authored workflow out of legacy UI.

## Plan of Work

Work through domain projection, provider representation, selected-cycle
service plus contract, then web and acceptance. Use the existing anonymous
fixture corpus and exact-version checkpoints. Record each evidence
boundary before the next role takes over.

## Concrete Steps

Run focused Python through `scripts/run_isolated_tests.py`. Compare native
text with expected canonical steps and independent provider-shaped response
fixtures. Regenerate TS contracts as API changes; run lint/build, browser
checks in owned scratch, contributor-safe CI and bounded review. Record
the exact review head and live test consent, then verify the result at
each hop before declaring delivery to the device.

## Validation and Acceptance

See the slice matrix. A successful provider response body alone is
insufficient. For the live check prepare a short 25 m test with distinct
distance steps, fixed and Lap rests, and a last rest at a repeat boundary.
Exact distance at each hop and device-observed rest behavior are required.

## Idempotence and Recovery

Use stable per-assignment ownership and a confirmation receipt independent
of normal calendar checkpoints. Preflight known state, distinguish
successful readback from uncertainty, prevent duplication on replay and
leave unrelated events untouched. Only create a new event after a strict preflight and
the locally committed reservation. A malformed provider list is unknown.
After creation use the provider event ID when available and check identity
and workout_doc. Lost acknowledgement permits readback only. Use single
event creation so a hidden or moved event cannot be overwritten by upsert.
Reversible live test evidence includes
the exact lab event and explicit approval for any cleanup action.

## Artifacts and Notes

- [Intervals builder](https://forum.intervals.icu/t/workout-builder/1163)
- [Intervals pool distance syntax](https://forum.intervals.icu/t/workout-builder/1163/672)
- [Intervals workout_doc readback](https://forum.intervals.icu/t/downloading-planned-workouts-from-the-api/93737)
- [Intervals workout upload](https://forum.intervals.icu/t/uploading-planned-workouts-to-intervals-icu/63624)
- [Garmin swim rest behavior](https://support.garmin.com/sl-SI/?faq=P0ItIZKjN49OaCCVb5UOZA)
- [FR255 manual](https://www8.garmin.com/manuals/webhelp/GUID-676967A0-1B23-4384-9BC9-76F3D643F1C8/EN-US/GUID-92B2952D-C8D5-4F66-9FBF-5A00549F0390.html)
- [FR965 user report for the acceptance matrix](https://forum.intervals.icu/t/pool-swim-workouts-on-garmin-rest-time-added-to-total-distance-last-rest-in-repeat-skipped/133451)

## Interfaces and Dependencies

Use the versioned swim library, selected-cycle context, existing Intervals
client and binding-safe author confirmation. The web layer renders typed
transport steps and receipt status. It does not derive workout semantics.

## Outcomes & Retrospective

Pending implementation and device acceptance.
