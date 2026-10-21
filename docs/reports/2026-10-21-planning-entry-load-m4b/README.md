# M4b: frozen sport exposure, initial limits and typed contracts

2026-10-21, Europe/Moscow. Issue #710 / draft #711, parent #677. Role:
Domain / API Implementer, authorized by the reviewed M4a handoff plus owner's
M4b request. Scope begins at `58d838b`; no UI, provider or athlete database writes.
[ExecPlan](../../planning_entry_dose_m4_execplan.md),
[AC1–AC7](../../planning_entry_dose_m4_slice_spec.md).

## Implemented boundary

The pure profile reads only supplied rows, as-of local date, timezone and coverage.
It preserves four completed seven-day bins, 84-day context, sport-specific
observed/eligible counts, duration, last date/gap and TSS provenance/coverage.
Unknown coverage yields nullable totals; known observed minutes are retained.
Complete coverage with zero rows yields recorded zero, not a positive baseline.
Invalid/missing/nonfinite duration, unknown dates/sports, identity conflicts and
multisport remainder remain visible quality limits. Same-day partial/future rows
cannot supply observed reference or complete a past multisport group.

Grouping reuses explicit provider lineage identity, while physical completeness
uses valid completed-day durations, independently of TSS. Zero/missing-TSS legs
are not erased. The existing global authoritative load projection is unchanged;
there is no envelope+legs sum, fuzzy date match or invented split.

Limits use the approved same-sport reference or explicit declarations, with the
source window/scope and declared ceiling preserved. Declared ceilings can lower
an observed reference, not silently enlarge it. A resolved reference is still
**unassessed, can_publish=false**: no catalog fit/final prescription has been
validated here. Absent evidence remains needs_baseline. Available-time/catalog
feasibility and rolling assignment constraints are M4c, not inferred successes.

New request fields are validated by the shared capture for HTTP and non-HTTP
callers, retained in normalized parameters, echoed in prepare/confirm, and bound
to dependency_digest with entry-load-v1 and the existing exact source frame.
Typed Python/TS profile/assessment shapes are reserved as optional additive
fields. Builds do not emit entry_load yet; M4c owns the final response and guard.
The four M4a strict XFAIL therefore remain expected, not relabelled GREEN.

## Executed RED and falsifiers

Before implementation, the corrected public/capture contour had three real RED:
explicit starting limits disappeared from capture, BuildRequest rejected both
new fields, and public prepare failed to echo them (3 failed in 0.81s). Initial
oracle wiring errors (using calculate as if it decorated parameters and passing
internal normalized parameters as a lifecycle request) were corrected before
recording these behavioral REDs; they are not counted as feature evidence.

The first profile matrix found pandas overflowing while inferring an unused
huge duration column in its lineage frame. The fix builds only identity/lineage
columns with sanitized TSS. The invalid-duration case now discloses a gap.
A later self-review falsifier reproduced two assertion failures where future or
partial-today linked stages incorrectly completed a past group; both now pass
with eligible completed-day physical completeness.

Six paired whole-payload controls ran with/without only the new context stamp.
Only build_readiness.candidate_fingerprint changes; all other checkpoint/response
fields are equal. Five original prescription/daily/event/forecast/science hashes
remain identical in every historical case. Three first-plan old-context whole
hashes reproduce the historical readiness-v2 fixture. Existing-plan seed history
is itself version-stamped now, so no old entire-binding equality is claimed for
those input histories. The historical fixture remains unchanged; a separate
entry-capture-v1 fixture pins the new complete response/checkpoint hashes.

## Verification

- M4b profile/capture tests: **83 passed in 3.35s** on the implementation tree.
- Expanded compatibility before the final two date-boundary regressions:
  **359 passed / 4 strict XFAIL / 1 warning in 37.28s**. Includes prior
  preparation/confirmation/storage/M3 readiness/multisport, HTTP conformance,
  extractor and API-call inventory tests. Final contour is recorded below.
- Python Ruff (whole repository), TS extraction freshness, API-call inventory,
  web lint and production build: passed. No UI rendering changed.
- All-table checks cover pure capture, malformed non-HTTP declarations and
  unchanged applied replay; new normalized inputs survive prepare/confirm.
  Explicit declarations/coverage, policy stamp, lineage and duration changes
  alter the frozen digest. All-table M4c final refusal/tamper/reset/rollback is
  **NOT YET**, not implied by these narrower proofs.
- Final contributor-safe contour on runtime `176b77e1bf48a39a6cf9d37d6f554a7472fc4c6f`:
  **3921 passed / 16 skipped / 82 deselected / 4 strict XFAIL / 7 warnings in
  238.78s**. The four XFAIL are the retained M4c build-integration RED, not new
  implementation failures. Earlier pre-final-date-fix broad run: 3919 passed /
  same skip/deselect/XFAIL counts in 240.99s; not substituted for the final run.
- Independent M4b scoped review round 1 on `176b77e1bf48a39a6cf9d37d6f554a7472fc4c6f`:
  **READY for M4c handoff; zero blocking P1/P2**. Checker reran 83 M4b tests
  (3.63s), 145 storage/preparation/M3/multisport checks (26.91s, one existing
  Starlette/httpx warning), and changed-Python Ruff. Clean tracked tree/head
  before/after; parent push changed tracking only. Full broad and web checks
  above are author evidence, not checker-run. No owner merge acceptance.

Run with an activated repository environment and existing temporary parent paths
for DATABASE_PATH, DEMO_DATABASE_PATH and CHATS_DIR:

    python -m pytest tests/smoke/test_planning_entry_profile_m4b.py tests/smoke/test_planning_entry_capture_m4b.py -q -p no:cacheprovider
    python -m pytest -m "not live and not debug and not e2e" tests/ -q -p no:cacheprovider
    python -m ruff check --no-cache .
    npm --prefix web run contract:extract -- --check
    npm --prefix web run contract:inventory
    npm --prefix web run lint
    npm --prefix web run build

Unit/compatibility tests verify the already reviewed operational policy. They
are not a model-selection or physiological validation experiment. The separately
frozen 30-case numerical-feasibility experiment is still future M4c work; no
clinical safety/effectiveness result is claimed.

## Review and handoff

Independent M4b delta round 1 is READY on `176b77e`; M4a spec source review
remains READY on `fb06cb8`. No blocking findings to dispose. This following
documentation-only evidence record changes no runtime, tests or AC.
Native review is not triggered per intermediate checkpoint (0/2 until M4d).
M4c must integrate the pure profile/limits with constrained generation, trusted
execution partition and bounded atomic validation; emit honest refusals before
pending creation; preserve old applied replay; reject stale/tampered evidence;
cover rolling windows, retained entry anchor, full table rollback/reset/backup
and usable successful allocations. S4 UI consumes the eventual DTO without
moving domain mathematics to the browser. Human retains merge/live-write gates.
