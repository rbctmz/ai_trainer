# Coach Decision Log

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds. This document follows `.agent/PLANS.md` from the repository root.

## Purpose / Big Picture

The AI coach can already answer questions, but its decisions are opaque: the athlete sees a recommendation without a durable trail of why the coach chose recovery, moderation, monitoring, or pushing forward. After this change, every completed coach answer writes a compact decision record to SQLite. The web app exposes those records on `/decisions`, grouped by day, so the athlete can audit how the coach has been reacting to fatigue, readiness, and load.

The working behavior is visible in two places: after a successful `/api/coach/chat` stream finishes, `GET /api/decisions` returns a new decision with `type`, `reason`, and timestamp; opening `/decisions` in the Next.js app shows those decisions grouped newest first. If no decisions exist, the page says `No decisions logged yet`.

## Progress

- [x] (2026-07-02 16:19Z) Removed stale `status: blocked` labels from #21 and #23.
- [x] (2026-07-02 16:20Z) Added `status: in progress` to #21.
- [x] (2026-07-02 16:20Z) Fast-forwarded local `main` to `origin/main` after #50.
- [x] (2026-07-02 16:20Z) Created branch `codex/issue-21-coach-decision-log`.
- [x] (2026-07-02 16:29Z) Inspected the current coach stream, runtime finalization, database table style, API router registration, and web navigation.
- [x] (2026-07-02 16:36Z) Added contract-first smoke tests for database write/read, API grouping, coach completion logging, and router registration.
- [x] (2026-07-02 16:45Z) Implemented `coach_decisions` persistence and deterministic decision classification.
- [x] (2026-07-02 16:45Z) Added `/api/decisions` and registered it in `api/main.py`.
- [x] (2026-07-02 16:45Z) Added `/decisions` web page and navigation entry.
- [x] (2026-07-02 16:48Z) Ran focused smoke, full smoke, web build, and `git diff --check`.
- [ ] Commit, push, open PR with `Closes #21`, wait for checks, and merge if green.

## Surprises & Discoveries

- Observation: The streaming coach path performs final synthesis inside `api/routers/coach.py` when the provider supports streaming, while the non-streaming path calls `models.ai_coach_runtime.finalize_ai_chat_response`.
  Evidence: `api/routers/coach.py` builds `streamed_final` from `stream_tokens(...)`, then otherwise calls `finalize_ai_chat_response(...)`.
- Observation: The right single integration point for logging is after `final` is known in `api/routers/coach.py`, not inside `models.ai_coach_runtime`.
  Evidence: Both stream and non-stream paths assign the final assistant text to `final` immediately before `chat_manager.add_message(chat_id, "assistant", final)`.
- Observation: SQLite schema changes in this repository are additive and idempotent through `Database.init_tables`.
  Evidence: `data/database.py` uses `CREATE TABLE IF NOT EXISTS` and `_ensure_*_columns` helpers during `Database(...)` initialization.
- Observation: The mock provider is sufficient for contributor-safe coach completion coverage.
  Evidence: `tests/smoke/test_coach_decisions.py` completes `/api/coach/chat` with `provider="mock"` and then reads the persisted decision without live AI credentials.

## Decision Log

- Decision: Store decision records in the existing SQLite database, in a new table `coach_decisions`, created by `Database.init_tables`.
  Rationale: The issue explicitly asks for a new DB table, and SQLite is already the local source of truth for product state.
  Date/Author: 2026-07-02 / Codex.
- Decision: Write the decision record from `api/routers/coach.py` after the final assistant answer is produced and before the SSE `done` event.
  Rationale: This single point covers streaming and non-streaming providers without duplicating logic or changing lower-level runtime helpers.
  Date/Author: 2026-07-02 / Codex.
- Decision: Use a deterministic classifier rather than another LLM call to assign `Push`, `Moderate`, `Recovery`, or `Monitor`.
  Rationale: The audit trail must be stable and contributor-safe. A deterministic rule based on current metrics and final-answer text is testable without API keys and avoids changing provider costs or latency.
  Date/Author: 2026-07-02 / Codex.
- Decision: The `/decisions` web page is a product page but should stay minimal in this slice: navigation entry, empty state, grouped records, type badge, reason, and time.
  Rationale: The issue asks for visibility, not a full analytics dashboard. A small page minimizes frontend risk while fulfilling the acceptance criteria.
  Date/Author: 2026-07-02 / Codex.

## Outcomes & Retrospective

Implementation outcome: every successful coach chat completion classifies and persists one auditable decision after final synthesis and before the SSE `done` event. API clients can fetch grouped decisions from `/api/decisions`, and the web app renders `/decisions` with grouped records and the exact empty state `No decisions logged yet`.

Validation completed locally:

    python3 -m pytest tests/smoke/test_coach_decisions.py -q
    python3 -m pytest tests/smoke/test_api_phase1.py tests/smoke/test_api_operational_states.py tests/smoke/test_coach_decisions.py -q
    python3 -m pytest tests/smoke -q
    cd web && npm run build
    git diff --check

All commands passed on 2026-07-02.

## Context and Orientation

The main product path is FastAPI plus Next.js. The FastAPI app is assembled in `api/main.py`, which imports routers from `api/routers/*` and calls `app.include_router(...)`. The web app lives under `web/app` and uses `web/components/Nav.tsx` for the top navigation.

The coach chat endpoint is `api/routers/coach.py::coach_chat`. It creates a chat id, saves the user message through `models.chat_manager.ChatManager`, runs the AI provider and tools, streams token events to the frontend, then saves the final assistant answer. A successful coach turn emits an SSE `done` event. This is the right moment to write a decision record.

The `Database` class in `data/database.py` owns SQLite initialization and persistence helpers. Creating a `Database(path)` calls `init_tables()`, so adding `CREATE TABLE IF NOT EXISTS coach_decisions (...)` there makes the table available for real, demo, and test databases without a separate migration command.

A coach decision means a compact row with a timestamp, a decision type, and a short explanation. The allowed decision types are `Push`, `Moderate`, `Recovery`, and `Monitor`. `Push` means the coach sees enough readiness to progress; `Moderate` means continue but avoid excessive intensity; `Recovery` means reduce load or rest; `Monitor` means not enough strong signal to push or reduce, so watch data and proceed cautiously.

## Plan of Work

First, add smoke tests. The database test should instantiate a temp `Database`, save a decision, and read it back. The API test should call `GET /api/decisions` on an empty temp database and expect `has_data: false` and `days: []`, then save decisions and expect days grouped newest first. The coach integration test should run `coach_chat` with a mock provider and temp database, collect the stream, assert the final event is `done`, then call the decisions API and assert one record exists.

Second, implement persistence in `data/database.py`. Add `coach_decisions` to `init_tables()` with columns: `id INTEGER PRIMARY KEY AUTOINCREMENT`, `date TEXT NOT NULL`, `decision_type TEXT NOT NULL`, `reason TEXT NOT NULL`, `workout_id TEXT`, `chat_id TEXT`, `message_id TEXT`, and `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`. Add `save_coach_decision(...)` and `get_coach_decisions(...)` helpers that use parameterized SQL and return dictionaries.

Third, add a small domain helper module, likely `models/coach_decisions.py`, to classify a decision. The helper should accept the final assistant answer and the database. It should inspect recent performance metrics if available and also look for recovery/push/moderation words in the final answer. It must always return one of the four allowed types and a one-line reason no longer than roughly 160 characters.

Fourth, wire logging into `api/routers/coach.py`. After `final` is available and before `chat_manager.add_message(...)`, classify and save the decision. Use the existing `chat_id`. Generate the `message_id` once, reuse it for the DB row and the final `done` event. Do not log a decision on exception/error events because no completed synthesis exists.

Fifth, create `api/routers/decisions.py` with `GET /api/decisions`. It should accept optional `days` with a sane default, use `get_database`, and return an envelope with `has_data`, `days`, and `operational_state`. Register this router in `api/main.py`.

Sixth, add frontend types in `web/lib/types.ts`, a presentational `web/components/ui/DecisionEntry.tsx`, a page `web/app/decisions/page.tsx`, and a navigation link in `web/components/Nav.tsx`. The page should use SWR and `fetcher` like other web pages. It should show `No decisions logged yet` when there are no records.

## Concrete Steps

Work from repository root:

    cd /Users/gregkisel/Developer/ai_trainer
    python3 -m pytest tests/smoke/test_coach_decisions.py -q
    python3 -m pytest tests/smoke/test_api_phase1.py tests/smoke/test_api_operational_states.py tests/smoke/test_coach_decisions.py -q
    python3 -m pytest tests/smoke -q
    cd web && npm run build
    git diff --check

The new test file should fail before implementation because no `coach_decisions` table, API router, or logging hook exists. After implementation, all commands above should pass.

## Validation and Acceptance

Acceptance is met when a completed coach stream writes a `coach_decisions` row with `decision_type` in `Push`, `Moderate`, `Recovery`, or `Monitor`, a one-line `reason`, and a timestamp. `GET /api/decisions` must return grouped day records newest first. The `/decisions` web page must render those records and must render the exact empty state text `No decisions logged yet` when none exist. `python3 -m pytest tests/smoke -q`, focused API tests, `cd web && npm run build`, and `git diff --check` must pass locally before publishing.

## Idempotence and Recovery

The schema migration is additive and idempotent because it uses `CREATE TABLE IF NOT EXISTS`. Re-running tests creates fresh temp databases. If logging fails unexpectedly, the coach chat should still finish; a missing audit row is worse than ideal but should not break the user-facing answer. Any publish step must stage only files touched for #21 and must include `Closes #21` in the PR body.

## Artifacts and Notes

Issue #21 requires the branch name to contain `issue-21`, a PR against `main`, `Closes #21` in the PR body, and the real PR URL plus pushed commit SHA in the final issue comment. This branch is `codex/issue-21-coach-decision-log`.

## Interfaces and Dependencies

In `data/database.py`, add:

    def save_coach_decision(self, decision_type, reason, workout_id=None, chat_id=None, message_id=None, date=None) -> dict
    def get_coach_decisions(self, days=30, limit=100) -> list[dict]

In `models/coach_decisions.py`, add:

    DecisionType = Literal["Push", "Moderate", "Recovery", "Monitor"]
    @dataclass(frozen=True)
    class CoachDecision: ...
    def build_coach_decision(final_response: str, db: Any | None = None) -> CoachDecision

In `api/routers/decisions.py`, add:

    router = APIRouter(prefix="/api/decisions", tags=["decisions"])
    @router.get("")
    def list_decisions(days: int = 30, demo: bool = False, db: Database = Depends(get_database)) -> dict

In `web/lib/types.ts`, add interfaces for `CoachDecision`, `CoachDecisionDay`, and `CoachDecisionsResponse`.

Revision note (2026-07-02 / Codex): initial ExecPlan created after issue triage and source inspection, before tests.
