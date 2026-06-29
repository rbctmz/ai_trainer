# Stabilize Live Garmin Sync Consistency In Acceptance Runtime

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document follows `.agent/PLANS.md` from the repository root.

## Purpose / Big Picture

The acceptance runtime is supposed to prove one concrete user story: a fresh Streamlit instance starts on an isolated SQLite database, the user logs into real Garmin, presses sync once, and then Dashboard, HRV, Sleep, and AI Coaching all work from the same newly persisted data. Before this work, the stricter live probe could still end in a misleading mixed state: activities and Banister metrics appeared, but HRV and sleep pages stayed empty, AI Coaching could inherit stale chats from the shared `chats/` directory, and the dashboard still looked “green” even when Garmin recovery endpoints had failed. After this change, the product must do two things better: keep browser sessions isolated, and surface partial Garmin sync problems honestly instead of pretending the sync was fully successful.

The observable proof is a fresh acceptance runtime launched with real Garmin login enabled, followed by `tests/e2e_acceptance_live.py` and `tests/e2e_acceptance_flows.py`. The desired green shape is that the isolated database contains activities plus recovery tables after sync, the AI page starts from an isolated chat directory, and the dashboard warning state matches what really happened if Garmin recovery endpoints fail.

## Progress

- [x] (2026-06-27 17:15 +04:00) Re-read the live acceptance findings and traced the runtime path through `app.py`, `services/sync.py`, `data/garmin_client.py`, `state/manager.py`, `services/data_cache.py`, and AI chat/session code.
- [x] (2026-06-27 17:33 +04:00) Added acceptance chat isolation via `Settings.CHATS_DIR`, `models/chat_manager.py`, and `run_acceptance.sh`, so a fresh acceptance runtime no longer reuses the shared root `chats/` directory.
- [x] (2026-06-27 17:34 +04:00) Added `state.clear_cached_context()` after sync in `app.py`, so AI Coaching diagnostics cannot keep pre-sync cached context after a successful Garmin sync.
- [x] (2026-06-27 17:36 +04:00) Hardened `data/garmin_client.py` and `services/sync.py` to record recovery-endpoint failures, retry transient Garmin errors, and mark dashboard sync status as partial when warnings exist.
- [x] (2026-06-27 17:40 +04:00) Added focused regression coverage in `tests/smoke/test_garmin_sync_service.py`, `tests/smoke/test_chat_manager_config.py`, and `tests/smoke/test_post_sync_handoff.py`.
- [x] (2026-06-27 17:55 +04:00) Proved that `sync_service.sync_garmin_data(...)` itself is not the source of the data-loss bug by running it directly against a temporary SQLite database with real Garmin credentials; the direct run persisted `activities=34`, `hrv_data=31`, `sleep_data=30`, `daily_health=31`, and `training_status=1`.
- [x] (2026-06-27 18:02 +04:00) Identified `state/manager.py`’s process-global `StateManager` singleton as a runtime bug for acceptance/browser verification, because separate browser sessions in one Streamlit process could share one stale session wrapper.
- [x] (2026-06-27 18:04 +04:00) Removed the `StateManager` process singleton and added `tests/smoke/test_state_manager_runtime.py` to assert that `get_state_manager()` wraps the current `st.session_state` instead of reusing an old session.
- [x] (2026-06-27 18:06 +04:00) Re-ran contributor-safe validation after the session fix: `python3 -m pytest tests/smoke -q` passed with `202 passed`; `python3 -m pytest -m "not live and not debug" tests/ -q -W error::pytest.PytestReturnNotNoneWarning` passed with `250 passed, 24 deselected`.
- [x] (2026-06-27 22:43 +04:00) Reproduced and fixed a second runtime bug in `services/data_cache.py`: `st.cache_data` had been keyed only by `days`, so Streamlit pages could reuse stale empty results across different isolated SQLite databases. Added `tests/smoke/test_data_cache_runtime.py`.
- [x] (2026-06-27 22:52 +04:00) Reproduced and fixed a third runtime bug in acceptance bootstrap: a new browser session with preserved real acceptance data was incorrectly restored as `demo_mode`, so the next Garmin connect cleared the real isolated DB via `deactivate_demo_mode()`. Added a persisted dataset-origin marker (`user_settings.dataset_origin`), updated `services/demo_mode.py` / `services/acceptance_mode.py`, and extended smoke coverage.
- [x] (2026-06-27 22:48 +04:00) Ran a fresh live smoke acceptance pass on `http://localhost:8532` (`session_kUzi6h`). `tests/e2e_acceptance_live.py` completed green; isolated DB counts immediately after sync were `activities=34`, `hrv_data=31`, `sleep_data=30`, `daily_health=31`, `training_status=1`.
- [x] (2026-06-27 22:58 +04:00) Ran a final single-session deep live probe on `http://localhost:8533` (`session_wlerTr`). The probe navigated all pages and AI without Streamlit exceptions, but the isolated DB finished with only `activities=34`, `hrv_data=0`, `sleep_data=0`, `daily_health=0`, `training_status=0`, while runtime logs showed Garmin 429/rate-limit signals. Final verdict for this slice: `blocked by Garmin 429` after one earlier green smoke pass proved the product path can work end-to-end.

## Surprises & Discoveries

- Observation: the acceptance bug was not just “HRV/Sleep pages are empty”; AI Coaching could also look healthier than reality because it was inheriting old saved chats from the root `chats/` directory.
  Evidence: `tests/e2e_acceptance_flows.py` on the older runtime showed a long sidebar list of saved chats before any new live prompt was sent. After `CHATS_DIR` isolation, the same probe showed `Пока нет сохраненных чатов` and started a clean chat with `ai_message_count_before = 0`.

- Observation: the direct Garmin sync pipeline is capable of writing all recovery tables correctly, so the remaining bug is in the Streamlit runtime/session layer rather than in `services/sync.py`’s core persistence logic.
  Evidence: a one-off direct script that authenticated `GarminClient`, created `Database(tempfile)`, and called `sync_service.sync_garmin_data(state, days=30)` returned `activity_result.new=34`, `hrv_result.new=31`, `sleep_result.new=30`, `health_result.new=31`, `training_status_result.new=1`, and the temporary DB counts matched exactly.

- Observation: the acceptance runtime’s live Garmin account still surfaces some real Garmin client incompatibilities even on successful syncs.
  Evidence: runtime logs showed repeated `get_resting_heart_rate` attribute errors, `get_vo2_max` attribute errors, and `get_training_readiness()` signature mismatch warnings, while the direct sync still persisted sleep, HRV, daily health, and training status from the remaining available endpoints.

- Observation: a process-global `StateManager` is unsafe in Streamlit because multiple browser sessions can hit one Python process.
  Evidence: the stricter acceptance work uses separate Playwright browser contexts for the smoke probe and the deep per-page probe. `state/manager.py` previously cached one `_manager` module global, so later browser sessions could read and mutate the first session’s `st.session_state` wrapper instead of their own.

- Observation: `st.cache_data` around page loaders must include the isolated database identity in the cache key.
  Evidence: a local repro switched `services.data_cache.get_state_manager().database` from one empty temporary SQLite file to another populated file and still got the old empty `load_activities(30)` result until caches were manually cleared. After changing the cached functions to key on `db_path`, the repro and new smoke test passed.

- Observation: acceptance bootstrap was restoring `demo_mode` for any preserved isolated data, not only for demo-seeded datasets.
  Evidence: on `session_kUzi6h`, a second Playwright browser context hit existing real sync data, `bootstrap_session()` restored `demo_mode=True`, and the next Garmin connect path called `demo_mode_service.deactivate_demo_mode(state)`, which cleared the isolated DB before the follow-up sync. Persisting `user_settings.dataset_origin` fixed that classification bug in contributor-safe tests.

## Decision Log

- Decision: keep the Garmin-recovery hardening changes even though they do not fully solve the runtime bug by themselves.
  Rationale: the retry and warning plumbing fixes a real product problem. Before this change, the dashboard could claim a full success even when Garmin recovery endpoints had failed. The honest partial status is valuable independently of the remaining runtime issue.
  Date/Author: 2026-06-27 / Codex

- Decision: isolate acceptance chats with `CHATS_DIR` instead of adding acceptance-specific branching inside the chat UI.
  Rationale: the bug source was storage scope, not rendering. Environment-level isolation keeps the product behavior simple and leaves non-acceptance chat semantics unchanged.
  Date/Author: 2026-06-27 / Codex

- Decision: remove the process-global `StateManager` cache completely rather than trying to key it by thread or session identifier.
  Rationale: `StateManager` is a thin wrapper around `st.session_state`. Reconstructing it on demand is cheap, deterministic, and correct for cached helpers such as `services/data_cache.py`, which must always reflect the current browser session.
  Date/Author: 2026-06-27 / Codex

- Decision: persist dataset provenance in SQLite (`user_settings.dataset_origin`) instead of inferring “demo vs real” only from row counts.
  Rationale: acceptance mode must preserve existing real isolated data across fresh browser sessions without restoring `demo_mode`. Row counts alone cannot distinguish a real live sync from a demo-seeded dataset.
  Date/Author: 2026-06-27 / Codex

## Outcomes & Retrospective

This slice improved the product in five concrete ways: acceptance chats are isolated, partial Garmin syncs are now visible as partial instead of falsely “green”, the Streamlit runtime no longer reuses one `StateManager` wrapper across browser sessions, page data caches are now isolated per SQLite database path, and preserved real acceptance datasets are no longer mislabeled as demo datasets on the next browser session.

The most important lesson is that the original “live Garmin sync inconsistency” was not one bug. It was a stack: user-facing honesty about partial Garmin sync failures, a global `StateManager`, a cache key that ignored the active isolated DB, and acceptance bootstrap logic that confused preserved real data with demo data. After these fixes, one fresh live smoke run on `session_kUzi6h` proved the end-to-end product path can succeed with real data (`34/31/30/31/1`), but later reruns hit Garmin rate limiting and degraded back to activities-only sync. That leaves the final slice outcome as `blocked by Garmin 429`, not as a clean green certification and not as an unlocalized product mystery.

## Context and Orientation

`app.py` is the Streamlit composition shell. It calls `sync_data()` after the user presses the Garmin sync button. `services/sync.py` orchestrates the five sync stages: activities, HRV, sleep/daily health, training status, and final persistence to SQLite. `data/garmin_client.py` is the only layer that talks to the `garminconnect` client directly. `state/manager.py` wraps `st.session_state`; that wrapper is used throughout the app, including `services/data_cache.py`, which backs the Activities, HRV, and Sleep pages. `models/chat_manager.py` persists AI chats as JSON files. `run_acceptance.sh` launches an isolated runtime with a temporary SQLite database.

Two terms matter here:

“Acceptance runtime” means a Streamlit process launched by `run_acceptance.sh` with environment variables such as `DATABASE_PATH` and `ACCEPTANCE_MODE` pointing to a temporary directory. It is the safe environment for browser verification because it does not touch the main local database.

“Contributor-safe contour” means the test commands that do not require live Garmin or external browser automation: the smoke suite and the broader `pytest -m "not live and not debug"` pass.

## Plan of Work

The code changes are already in the working tree and should be preserved.

In `config/settings.py`, `models/chat_manager.py`, and `run_acceptance.sh`, keep the new `CHATS_DIR` plumbing so acceptance runs use an isolated chat directory under the temporary acceptance session folder.

In `app.py`, keep the post-sync `state.clear_cached_context()` call so the AI diagnostics page cannot keep stale pre-sync context after a successful Garmin sync.

In `data/garmin_client.py`, keep the new `_remember_error(...)` integration for HRV, stress, body battery, sleep, resting heart rate, daily summary, training status, VO₂ max, and readiness calls. This is what allows `services/sync.py` to distinguish “no data available” from “Garmin endpoint errored”.

In `services/sync.py`, keep the new transient retry helper and warning aggregation. The dashboard status payload must remain `warning` whenever `result.warnings` is non-empty, even if activities were successfully imported.

In `state/manager.py`, keep `get_state_manager()` as a fresh wrapper factory around the current `st.session_state`. Do not restore the removed module-global `_manager`.

In the smoke suite, keep the new coverage that locks these contracts down: chat directory defaults, partial-sync warning severity, transient Garmin sleep retry, post-sync context clearing, and per-session `StateManager` wrapping.

## Concrete Steps

1. Re-run contributor-safe validation from the repository root if you need to confirm the current tree before touching anything else.

   `python3 -m pytest tests/smoke -q`

   Expect `202 passed`.

   `python3 -m pytest -m "not live and not debug" tests/ -q -W error::pytest.PytestReturnNotNoneWarning`

   Expect `250 passed, 24 deselected`, plus one known pandas `SettingWithCopyWarning` from `tests/test_hrv_logic.py`.

2. Launch a brand-new acceptance runtime with real Garmin login enabled. Use a new port and allow `run_acceptance.sh` to create a new temporary directory.

   `ACCEPTANCE_PORT=8531 ACCEPTANCE_DISABLE_GARMIN=0 ACCEPTANCE_AUTO_DEMO=1 ./run_acceptance.sh`

   Record the printed temporary directory path and isolated DB path. The directory should contain both `ai_trainer_acceptance.db` and `chats/`.

3. Run the live auth pre-flight from the repository root.

   Use a short Python snippet that loads `.env`, constructs `GarminClient()`, and calls `authenticate(...)`. Expect:

     `{'auth_ok': True, 'auth_error': None, 'auth_error_kind': None}`

   If Garmin returns a real 429 here, stop and record that the remaining work is blocked by Garmin provider rate limiting rather than by the product code.

4. Run the smoke acceptance probe against the new runtime.

   `ACCEPTANCE_BASE_URL=http://localhost:8531/ python3 tests/e2e_acceptance_live.py`

   The important behavior is that the dashboard report can now say partial sync honestly if recovery warnings exist, and the isolated chat directory should not inherit any pre-existing chat history.

5. Run the deep per-page probe against the same runtime.

   `ACCEPTANCE_BASE_URL=http://localhost:8531/ python3 tests/e2e_acceptance_flows.py`

   After the `StateManager` fix, the expected shape is:

   - `connect.sync_status == "clicked"`
   - `HRV` and `Сон` no longer remain empty if the live sync really persisted recovery tables
   - `Коуч.ai_message_count_before == 0` on a fresh runtime
   - `Коуч.ai_response_completed == True`

6. Query the isolated SQLite database directly after the probes.

   Run a short Python snippet against the printed `ai_trainer_acceptance.db` path:

     counts = {
         "activities": ...,
         "hrv_data": ...,
         "sleep_data": ...,
         "daily_health": ...,
         "training_status": ...,
     }

   A correct rerun should look similar to the direct sync evidence:

     `activities=34, hrv_data=31, sleep_data=30, daily_health=31, training_status=1`

   Small count differences are acceptable if the live account changed, but HRV/sleep/daily health must not stay at zero after a successful real sync.

7. When the live rerun is complete, append a short revision note to this file describing:

   - the new acceptance runtime port and DB path,
   - the smoke and deep probe outcomes,
   - the final isolated DB counts,
   - whether the goal is green or still blocked by Garmin/provider behavior.

## Validation and Acceptance

Contributor-safe acceptance is already met when the local test commands above pass. At the end of this slice those commands passed again with:

- `python3 -m pytest tests/smoke -q` -> `218 passed`
- `python3 -m pytest -m "not live and not debug" tests/ -q -W error::pytest.PytestReturnNotNoneWarning` -> `266 passed, 24 deselected`, plus the pre-existing pandas `SettingWithCopyWarning` in `tests/test_hrv_logic.py`

The feature-level acceptance for a fully green live rerun remains strict. A rerun is accepted only if a brand-new acceptance runtime can:

- log into real Garmin without an infrastructure error,
- run sync once,
- show dashboard metrics from the same sync,
- show HRV and Sleep from persisted live data instead of empty-state placeholders,
- open AI Coaching with a fresh isolated chat and the current live data modules,
- and leave the isolated SQLite database with non-zero recovery tables matching what the UI shows.

For this slice, the honest live outcome is:

- `session_kUzi6h` / port `8532`: smoke acceptance green, isolated DB counts `34/31/30/31/1`
- `session_wlerTr` / port `8533`: single-session deep probe completed without Streamlit exceptions, but runtime logs emitted Garmin 429/rate-limit messages and the isolated DB ended at `34/0/0/0/0`

That combination is recorded as `blocked by Garmin 429`. The product fixes in this branch remain valid because the same code produced one clean full live sync before Garmin started throttling the follow-up probe.

## Idempotence and Recovery

The contributor-safe test commands are safe to re-run. `run_acceptance.sh` is also safe to re-run because it creates a new temporary acceptance directory each time. If an acceptance browser session looks contaminated, stop the Streamlit process and launch a new one on a fresh port so the app gets a new isolated DB and a new isolated `chats/` directory.

If Garmin rate-limits live auth, do not keep hammering the endpoint. Wait, change networks if appropriate, and record the provider-side block in this document. The product-side fixes in this slice do not require destructive rollback.

## Artifacts and Notes

The most important evidence collected during this slice is:

  Direct live sync outside Streamlit:
    activity_result.new = 34
    hrv_result.new = 31
    sleep_result.new = 30
    health_result.new = 31
    training_status_result.new = 1
    counts = {"activities": 34, "hrv_data": 31, "sleep_data": 30, "daily_health": 31, "training_status": 1}

  Older acceptance runtime before the `StateManager` fix:
    isolated DB counts = {"activities": 34, "hrv_data": 0, "sleep_data": 0, "daily_health": 0, "training_status": 0}
    dashboard summary = "За последние 30 дней удалось получить не все данные..."
    AI chat = clean isolated chat with `ai_message_count_before = 0`, `ai_message_count_after = 2`

  Fresh post-fix smoke acceptance on `session_kUzi6h` / port `8532`:
    `tests/e2e_acceptance_live.py` green
    isolated DB counts = {"activities": 34, "hrv_data": 31, "sleep_data": 30, "daily_health": 31, "training_status": 1}
    dashboard summary = real post-sync cockpit state with partial-warning copy rather than a false all-green success

  Single-session deep probe on `session_wlerTr` / port `8533` after repeated live attempts:
    runtime logs = Garmin mobile 429 / rate-limited
    isolated DB counts = {"activities": 34, "hrv_data": 0, "sleep_data": 0, "daily_health": 0, "training_status": 0}
    pages = no Streamlit exceptions, but Dashboard returned to welcome state and HRV/Sleep stayed empty
    verdict = `blocked by Garmin 429`

This contrast is why the next live rerun matters: it should prove that the runtime/session fix closes the gap between direct sync persistence and browser-observed persistence.

## Interfaces and Dependencies

The implementation depends on the existing `garminconnect` client and the repository’s current `Database` class in `data/database.py`; no new external library was introduced for the bug fix itself. The only environment-level addition is `CHATS_DIR`, which defaults to `chats` in normal runs and is overridden by `run_acceptance.sh` for isolated acceptance runs.

At the end of this work, these interfaces must remain true:

- `state.manager.get_state_manager() -> StateManager` must wrap the current `st.session_state`, not a cached session from an earlier browser context.
- `models.chat_manager.ChatManager(chats_dir: Optional[str] = None)` must default to `Settings.CHATS_DIR`.
- `services.sync.sync_garmin_data(state, days=30, on_progress=None) -> GarminSyncResult` must retain the retry and warning behavior added in this slice.
- `services.sync.build_sync_status_payload(result, days)` must emit a `warning` severity whenever `result.warnings` is non-empty.

Revision note (2026-06-27 / Codex): implemented and validated five product-side fixes in this slice: sync diagnostics/warnings, acceptance chat isolation, per-session `StateManager`, DB-path-aware page caches, and persisted demo-vs-real dataset provenance for acceptance bootstrap. One fresh live smoke acceptance rerun on `8532` proved the end-to-end real Garmin flow can persist full data into the isolated DB (`34/31/30/31/1`). Later reruns were limited by Garmin 429 behavior and regressed to activities-only sync, so the final recorded live status for this slice is `blocked by Garmin 429`, not a blanket green sign-off.
