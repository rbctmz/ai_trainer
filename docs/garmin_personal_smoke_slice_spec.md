# Безопасное завершение исследования Personal API — #737 / #736

Author: Codex, Spec/Domain Implementer. Independent checker: manual native GitHub
review of the final specification and implementation. Merge owner: Greg.
Date: 2026-11-16. Original head 5245da7; integration 6efa079 includes main 7e539d0.

## Change Class

Class A: the existing operator tool handles credentials and reads a selected
SQLite. This promotes the original Class C claim for the bounded diagnostic
hardening; it does not implement a runtime Garmin transport. Native budget0/2,
manual trigger only. Owner requested completion of #737; final acceptance/merge
is checked separately after the candidate and its evidence are ready.

## Scope

Correct docs/garmin_personal_api_study.md using current public Garmin material.
Harden scripts/garmin_personal_smoke.py and its synthetic tests: diagnostics,
range evidence and selected read-only DB. API/web schemas and dependencies stay
unchanged. Companion plan: garmin_personal_api_study_execplan.md.

## Non-goals

No runtime sync adapter, SDK dependency/Python upgrade, new provider namespace,
TSS/threshold changes, personal history/captures repair, UI work or new FIT ingest.
No actual Garmin credentials, personal DB or authenticated provider calls in
implementation/tests. No swimming implementation in this PR; it is the owner's
next priority. #736 remains a decision/future-integration issue, referenced by
Refs, not closed by this bounded delivery.

## Public contracts

The CLI flags and exit codes 0/1/2 stay compatible. The ordinary DB default now
uses config.database_paths.resolve_database_paths: explicit --db wins, otherwise
DATABASE_PATH or the platform application-data default. Selecting a filename
does not instantiate Database, initialize schema, create directories or adopt
an old checkout DB. --skip-db never opens a DB.

Successful probes print only intended field names, counts, dates, units and
activity IDs. HTTP errors print status/path, not raw provider bodies. Known
secrets are redacted on every result path. Unknown exceptions expose their type,
not arbitrary exception text. Redirects may stay on the request's origin only;
keys/tokens are not forwarded to another host/port/scheme automatically.

The sleep-cap probe compares inclusive 31/32-day windows, one fixed end date.
PASS requires 31 accepted plus 32 rejected with a recognizable range-specific
HTTP 400 body. Arbitrary 401/403/429/5xx never confirms a range limit. A generic 400
is inconclusive (WARN); an accepted 32-day window also means the 31-day boundary
was not demonstrated. Missing data is not evidence that a larger window works.
The historic 26.10 result used 31/40 and remains labelled historic evidence.

ID overlap is sample evidence, not a universal namespace guarantee. Direct
activity reads must return the requested activityId; HTTP 200 alone is insufficient.

## Failure, rollback and persistent state

This adds no product persistent state. SQLite access remains URI mode=ro plus
query_only; absent files are skipped rather than created. No cleanup/adoption of
operator files. Repeated synthetic runs use owned pytest paths and local HTTP
stubs. Missing key is configuration exit 2. Probe errors produce FAIL/exit 1;
WARN/SKIP remain explicit and do not claim successful coverage. Revert the PR to
roll back code/docs; no data migration or recovery operation is needed. Product
reset and restart contracts are unchanged because there is no product state.

## Evidence boundary matrix

| Boundary | Evidence | Expected result |
| --- | --- | --- |
| API key / bearer in HTTP body, before/across/after 160 chars | dummy response | no body or secret fragment in text/JSON |
| HTTP failure / unexpected exception | synthetic canary | safe status/type, no payload values |
| Same origin / foreign origin redirect | local source and destination stubs | ordinary request works; foreign origin never receives Authorization |
| 31 success, 32 explicit range 400 | response pair | PASS with observed query boundary |
| 31 success, 32 generic 400/401/403/429/5xx | response pair | WARN/FAIL, never boundary PASS |
| Explicit path / environment / platform / absent file | owned temp inputs | correct selection, no fallback/create/write |
| DB ID requested / different response ID | synthetic activity JSON | direct equality required; no false namespace proof |
| Swagger / SDK / historic live sample | public snapshots and dated record | disagreements and untested coverage remain explicit |

## RED matrix and verification

| Invariant | RED / falsifier | GREEN |
| --- | --- | --- |
| No credential fragments | truncated dummy secret survives old error | all public error paths omit raw HTTP body |
| Honest cap evidence | old 31/40 returns PASS for 401/429/500 | exact boundary and rejection classification tests |
| Selected DB | DATABASE_PATH ignored by old parser | env/platform/explicit/no-create tests |
| No foreign credential forwarding | local redirect canary | no destination Authorization |
| Honest identity evidence | 200 with wrong activityId | no positive direct-ID conclusion |

Baseline reviewer experiment: 10 existing tests PASS, 5 new probes FAIL on the
unchanged original tool with current main's isolated test launcher. These five
failures cover the first three reviewed defects; further failure-path probes
ran RED before the tool changes: 38 failed / 9 passed. After the fix the same
47 cases pass; related DB path tests: 124 passed. No live characterization was rerun.

Required checks: isolated tests/smoke/test_garmin_personal_smoke.py; related
database path/guard tests; whole-tree Ruff; Markdown links/diff; contributor-safe
CI, contract, E2E, Gitleaks and bounded native review. Web source is unchanged,
so a local web build/screenshots are N/A. No new public API/TS/DB contract.

## ASR / ADR traceability

ASR-SEC-1: no keys/raw personal payload in diagnostics, no credential forwarding.
ASR-REL-2: missing/uncertain evidence stays WARN/SKIP, not fabricated success.
ASR-REL-3/DEP-2 and ADR-0002: read-only selected store, no initialization/adoption.
ADR-0008: existing Garmin IDs/provenance and local-first TSS remain unchanged.
ADR-0001/0007: no UI changes or live fixtures. No new transport ADR is accepted
here; owner choice A is recorded in #736 for later Class A implementation.

## Review / delivery

One consolidated native review after the candidate and CI stabilize; any second
round is scoped to fixes after that SHA. Every finding gets fixed-in/follow-up/
disputed evidence. Stop at two rounds; never waive open blocking findings.
Independent checker and final evidence are recorded in #737. No bypass or
automatic review trigger. After accepted review/GREEN gates, owner controls merge;
post-merge receipt records tree equality and remaining #736 scope.

Implementation and local checks completed; candidate remains pending current CI,
independent review and owner acceptance. Final evidence is recorded in #737.
