# Завершить исследование Garmin Personal API и операторский smoke (#737)


Живой ExecPlan по `.agent/PLANS.md`; bounded contract —
[garmin_personal_smoke_slice_spec.md](garmin_personal_smoke_slice_spec.md).
Class A из-за обработки credentials и read-only SQLite; продуктовый Garmin sync
не меняется. Автор Codex; независимый checker — manual native GitHub review
финального контракта/реализации, merge owner Greg. Пользователь 16.11.2026 поручил
скорректировать прежние выводы и закончить именно #737. Следующий приоритет —
плавание; runtime Personal API сюда не включён.

## Purpose / Big Picture


Оператор получит актуальное исследование и smoke, который не превращает сетевой
сбой в доказательство поддержки API, не раскрывает секреты в ошибке и читает
выбранную SQLite, а не оставшуюся старую копию внутри checkout. Пользователь
выбрал вариант A: официальный Personal API как дополнительный транспорт provider
garmin. Исследование фиксирует решение, но не включает новый транспорт на данных.

## Progress


- [x]2026-11-16: original 5245da7 and #736/#737 inspected; native 0/2.
- [x] Original review on owned snapshot: 10 tests PASS, 5 probes FAIL (secret
  truncation, false cap evidence for 401/429/500, ignored DATABASE_PATH).
- [x] Own branch codex/pr737-study-completion; original author's worktree clean
  and unchanged. Main 7e539d0 integrated without conflicts as 6efa079.
- [x] Public Garmin Swagger/FAQ and official SDK reread 16.11; no actual credentials
  or provider data read. Swagger 26 paths/109 schemas; SDK/Swagger VO2 discrepancy.
- [x] Bounded safety specification recorded before changing the tool.
- [x] Behavioral RED: 38 failed / 9 passed; fixes GREEN: 47 passed. Diagnostics,
  redirect isolation, range evidence and DB selection corrected.
- [x] Dated study rewritten; historic live evidence labelled, activity filename
  anonymized, source fingerprints added and unsupported claims corrected.
- [x] Related DB tests: 124 passed. Whole-tree Ruff passed. Broad run: 4527 passed,
  6 failed / 18 errors due to broken system Node 25 (missing simdjson dylib);
  all affected modules rerun with existing Node 22: 31 passed. No host repair.
- [ ] Final links/diff checks, current CI and independent review.
- [ ] Resolve review findings, record owner merge gate and final #737 receipt;
  #736 remains open for separately scoped integration. No swimming implementation.

## Context and Orientation


scripts/garmin_personal_smoke.py is an explicit operator CLI, not a dependency of
services/sync.py. It exchanges a selected API key for a token and calls a fixed
probe list. tests/smoke/test_garmin_personal_smoke.py uses local HTTP stubs and
owned temporary SQLite. config/database_paths.py provides a pure path selector
with DATABASE_PATH override and application-data defaults; no Database import is
needed. The existing script incorrectly defaults to REPO_ROOT/ai_trainer.db.

docs/garmin_personal_api_study.md holds the 26.10.2026 research/live observations.
Current Swagger is embedded as JSON in Garmin's public Swagger-page component;
its extracted schema has 26 paths and 109 schemas. It does not list maxmet, while
the official SDK README lists get_daily_vo2_max. Preserve that disagreement,
not an invented supported/unsupported verdict. SDK pyproject requires Python 3.12;
our CI uses 3.11 and Dockerfile.api 3.10. This PR adds no SDK/Python dependency.

## Plan of Work and Milestones


M1 is the safety characterization. Extend the existing test module with dummy
error-body secrets/health canaries, all result paths, range failure/boundary cases,
DB precedence/no-write cases, direct-ID mismatch and a local redirect canary.
Run through the isolated launcher first and retain expected failures; existing
HTTP success controls must remain green. Never run the operator's real main.

M2 fixes the explicit operator boundary. HTTP diagnostics retain only safe
status/path, known secrets are masked on every result branch and arbitrary
exceptions expose type only. Restrict automatic redirects to the request origin.
Compare 31/32 inclusive dates and distinguish explicit range 400 from unrelated
failures. Reuse the pure database selector, honor --db and never initialize or
fall back to an old checkout DB. Require direct activityId equality for the
direct-read sample. No network client factory/product path is changed.

M3 updates the study using public snapshots and owner decision A. Distinguish
published API, SDK wrappers and the older personal live sample. Document SDK
compatibility, key lifecycle, uncertain limits/coverage and an implementation
handoff that preserves provider identity, canonical TSS and wellness provenance.
Do not promise absence of 403/429 or automatic support for all legacy metrics.
The sleep boundary method changes now; the old 31/40 results remain historic.

M4 verifies the complete PR against main. Run focused/related isolation tests,
whole-tree Ruff, relative links and privacy/diff checks; push small complete
checkpoints. Update #737 to Refs #736, because future integration remains outside
this PR. Obtain GREEN CI and a manual native checker result on the frozen head;
triage any finding with a reproduction and scoped second round if needed.

## Concrete Steps


Commands run from this task worktree with the existing primary virtualenv,
without copying .env or using personal SQLite:

    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python scripts/run_isolated_tests.py tests/smoke/test_garmin_personal_smoke.py -q
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python scripts/run_isolated_tests.py tests/smoke/test_database_paths.py tests/smoke/test_database_path_guardrails.py -q
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m ruff check .
    git diff --check

The HTTP stub may need localhost permission; this never authorizes a live Garmin
call. The normal CLI now reads a user's .env/key only when the operator explicitly
invokes it; tests replace that loader and use dummy credentials. Product/API/web
is not started. CI runs the contributor-safe, contract, E2E and secret checks.

## Validation and Acceptance


Existing successful token/profile/activity/sleep/HRV controls pass. A dummy key
crossing the previous 160-character cut and a health canary in an error response
must never appear in text or JSON. A foreign redirect must not receive its header.
401/429/5xx and generic 400 must not claim a confirmed sleep cap; documented 31
acceptance plus recognizable 32 range rejection is positive evidence. Explicit,
environment and platform DB paths resolve without new files; only read-only
queries inspect an owned fixture. The study states what was checked now and what
was merely reported in the 26.10 run. No live success or runtime feature is claimed.

## Surprises & Discoveries


Observed: published Swagger contains26 paths/109 schemas and no maxmet path;
official SDK README contains a maxmet wrapper. Inferred: the two public artifacts
are not a single synchronized capability guarantee. Verified by: direct public
downloads and extracted path list16.11. No authenticated maxmet call was made.

Observed: a fake secret cut at 160 survives old _snippet; HTTP 401/429/500 for the
long window produces PASS; DATABASE_PATH is ignored. Inferred: diagnostics can
leak partial credentials and overstate evidence/read the wrong store. Verified
by: five failing reviewer probes plus ten passing controls. Fresh regressions
proved the corrected behavior: 47 passed after 38 failed / 9 passed RED.

## Decision Log


16.11.2026, owner: finish only #737 now; swimming planning/accounting is next.
No runtime transport implementation or personal rollout belongs to this work.

16.11.2026, implementer: promote bounded tool hardening to Class A because it
touches secrets/selected SQLite; use a separate spec and behavioral failures.
The final native reviewer is the independent checker; no self-review is presented
as an independent result. Scope is testable with public/fake data only.

16.11.2026, implementer: keep VO2 capability unresolved between artifacts, preserve
historic live findings, and avoid SDK adoption/Python upgrades in a research PR.

## Idempotence and Recovery


No product state, token cache or migration is added. Repeated tests use guarded
temporary paths, never delete/adopt another path and do not invoke live main.
Source rollback is a normal revert; user DB/history/provider state is untouched.
The original branch/worktree remains available; our working branch pushes only
fast-forward commits to the existing PR branch after checking its expected head.

## Outcomes & Retrospective


Public contract refresh and bounded hardening are implemented. The original
47-case run gave 38 failed / 9 passed; the same cases now pass. DB checks: 124
passed. The broad run exposed only the existing broken Node 25 installation;
31 affected-module tests pass with the already installed Node 22. No system
repair or product runtime change was made. Current CI and independent review
remain; final receipts are recorded in #737 on their actual heads.

## Artifacts and Notes


Public contract fingerprints, inspected SDK snapshots and their source URLs are
recorded in the study. Personal case rows, keys and raw streams are excluded.
No earlier private health record is reopened to refresh the public report.

## Interfaces and Dependencies


CLI flags and0/1/2 exit meanings remain; diagnostic classifications become more
conservative. Reuse stdlib urllib/sqlite/json and the existing pure path selector.
No new third-party dependency, database schema, API/TS contract or UI surface.

Revision 16.11.2026: plan created before tool changes to bound research correction,
credential/read-only safeguards and delivery, preserving the owner's next priority.
