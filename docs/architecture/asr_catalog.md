# ASR Catalog — единая точка истины по quality attributes

Статусы на 2026-07-20. Источник сценариев: `architecture_analysis_add3.md` §2.
Правило ведения: новый архитектурный трек (ExecPlan) обязан назвать задетые
ASR в секции «ASR / risk traceability» и обновить здесь статус/проверку.

| ID | Сценарий | Приоритет | Как обеспечивается | Как проверяется | Статус |
|----|----------|-----------|--------------------|-----------------|--------|
| ASR-PERF-1 | «Сегодня» < 2 сек с 3 годами данных | High | локальный SQLite, canonical snapshot без provider-вызовов на рендере (`include_provider=False`, #228) | `test_today_snapshot_perf_gate.py` — p95 < 2с на 3 годах синтетических данных (#241) | ✅ |
| ASR-PERF-2 | Коуч: первый токен < 5 сек | High | стриминг SSE; native function calling (#190) убрал маркерный второй проход у поддерживающих провайдеров | `first_token_ms` в SSE `done`, покрыт смоуком (#241); 5с — наблюдение, авто-гейта на порог нет (недетерминизм провайдера) | 🟡 |
| ASR-PERF-3 | Инкрементальный Garmin-sync, дельта дня < 10 сек | Medium | инкрементальная выборка, `_OptionalSignalTracker` | smoke sync-сьюты | ✅ |
| ASR-PERF-4 | Planning preview 16 недель < 10 сек | Medium | детерминированный scheduler без БД внутри цикла (#205) | референс-сборки в smoke (секунды) | ✅ |
| ASR-REL-1 | Reconciliation: ни одна активность не теряется при перепланировании | High | content-derived session identity + lineage (`replaces_session_id`, #206/#209), append-only ledger | `test_recovery_transfer_identity_handoff.py`, twin-матрица identity | ✅ |
| ASR-REL-2 | Отсутствие данных → data gap, не падение | High | gate-исходы silence/data_gap (#154), `has_plan=false` пробросы (#228) | smoke-гейты loop/ribbon | ✅ |
| ASR-REL-3 | Обрыв sync не портит частичные данные | Medium | partial UPDATE по присутствующим ключам (#88) | `test_garmin_sync_service.py` | ✅ |
| ASR-MOD-1 | Новый AI-провайдер без правки основного кода | High | `AIProvider` ABC + фабрика; capability-флаги (`supports_native_tools`, #190) делают расширения аддитивными | capability-матрица в `test_coach_native_tools.py` | ✅ |
| ASR-MOD-2 | Новый компонент дашборда без регрессии | Medium | canonical snapshot проекции (#152/#153) | trust-alignment smoke | ✅ |
| ASR-MOD-3 | Смена схемы — обратная совместимость | Medium | аддитивные поля чекпойнтов, migrate-on-read (#206), append-only журналы | legacy-byte-equivalence гейты | ✅ |
| ASR-SEC-1 | Ключи не в логах/UI/git | High | `.env` вне git, UI скрывает поля, env-fallback | ревью; авто-скана нет | 🟡 |
| ASR-SEC-2 | Basic Auth перед публичным доступом | High | Caddy + Basic Auth в self-hosted стеке | деплой-чеклист | ✅ |
| ASR-DEP-1 | `docker compose up` поднимает весь стек | High | compose + `/api/health` + healthcheck (уже реализованы) | самопроверка compose | ✅ |
| ASR-DEP-2 | Обновление без потери данных | High | SQLite в named volume; append-only чекпойнты | деплой-практика; backup-скриптов нет | 🟡 |

## Контракт-тесты API-роутеров (ASR-MOD-2, issue #242)

Свип по `api/routers/*` (кодовый долг из ATAM-карты, `architecture_analysis_add3.md`
§4.1: «нет contract tests → рефакторинг ломает api молча»). Установленный
паттерн — прямой вызов router-функций с временной SQLite `Database` (без
`TestClient`/HTTP-слоя, без live-провайдеров), как в существующих
`tests/smoke/test_api_*.py`. Минимум на роутер: (а) успешный ответ с ключевыми
полями схемы, (б) пустое/degraded-состояние без 500, (в) неверный вход там, где
у роутера есть собственная validation-ветка (`HTTPException(422, …)`, маппинг
исключений вида `LookupError -> 404` / `ValueError -> 422`) или Pydantic-констрейнт
на request-модели.

Важно про (в): из-за прямого вызова router-функций проверяются два слоя — своя
validation/exception-ветка роутера и констрейнты request-моделей (то, что
FastAPI отклонит до хендлера). Настоящий HTTP-round-trip через валидацию FastAPI
(path/query `Query`-констрейнты) требует `TestClient` и смены паттерна; он закрыт
для `planning.py` в #248 отдельным файлом — см. ниже.

| Роутер | Тест-файл(ы) |
|--------|--------------|
| `activities.py` | `test_api_operational_states.py`, `test_api_phase1.py` |
| `adherence.py` | `test_adherence_ribbon.py` |
| `athlete_profile.py` | `test_api_athlete_profile_contract.py` |
| `coach.py` | `test_api_operational_states.py`, `test_api_phase1.py`, `test_coach_decisions.py`, `test_coach_native_tools.py`, `test_readiness_snapshot_contract.py`, `test_readiness_conflicts.py`, `test_coach_load_metrics_window.py` |
| `dashboard.py` | `test_api_dashboard.py`, `test_api_operational_states.py`, `test_readiness_snapshot_contract.py`, `test_signals_engine.py`, `test_dashboard_tsb_zones.py` |
| `decisions.py` | `test_coach_decisions.py`, `test_recovery_replan_loop.py`, `test_recovery_transfer_product_surface_web.py` |
| `hrv.py` | `test_api_operational_states.py`, `test_api_phase1.py` |
| `planning.py` | `test_api_planning.py`, `test_coach_constraints.py`, `test_planning_target_demand_history.py`, `test_api_planning_router_contract.py`, `test_api_planning_router_http_contract.py` |
| `recovery_analytics.py` | `test_api_recovery_analytics.py` |
| `session_feedback.py` | `test_post_workout_feedback.py`, `test_api_session_feedback_router_contract.py` |
| `session_quality.py` | `test_session_quality_forecast.py`, `test_api_session_quality_router_contract.py` |
| `settings.py` | `test_briefing_settings.py` |
| `sleep.py` | `test_api_operational_states.py`, `test_api_phase3.py`, `test_sleep_metric_provenance.py` |
| `system.py` | `test_api_operational_states.py`, `test_sync_job_api.py`, `test_api_phase3.py`, `test_session_quality_forecast.py` |
| `today.py` | `test_api_today.py`, `test_briefing_settings.py` |

Остаток #246 закрыт: 13 ранее непокрытых эндпоинтов `planning.py`
(`target-preview`, `demand` GET/POST, `events`, `plan`, `export/ics`,
`export/workout/{index}`, `reconciliation`, `reconciliation/matches`,
`rebalance/preview`, `rebalance/confirm`, `adjust`, `history`) теперь
исполняются на уровне роутера в `test_api_planning_router_contract.py`
(direct-call: happy-path со схемой, degraded без 500, маппинг исключений
`ValueError → 422` / `StalePlanningCheckpointError → 409` / `IntervalsICUError →
503`, `Response`-контракт export-роутов).

Остаток #248 закрыт: HTTP-слой валидации FastAPI (path/query `Query`-констрейнты
+ round-trip через реальный `Depends`) для `planning.py` теперь пинается в
`test_api_planning_router_http_contract.py` (`TestClient`, `get_database`
переопределён на временную БД): по каждому констрейнту — нарушение границы → 422
и включительная граница → не-422 (404 на пустой БД либо 200 через sentinel для
`/events`, что заодно пинует реальный DI + сериализацию dict). `planning.py` —
ЕДИНСТВЕННЫЙ роутер с path/query `Query`-констрейнтами (`events.days` `ge/le`,
`export/workout.fmt` `pattern`, `export/workout.leg` `ge/le`); у остальных
роутеров валидируется только тело запроса через Pydantic `Field(...)`, а оно уже
пинается при конструировании модели в direct-call свите (#242/#246). Поэтому
HTTP-слой свёлся к одному роутеру, а не к свипу по `api/routers/*`.

## Открытые долги (по 🟡)

- PERF-2: first-token остаётся наблюдением, не гейтом — порог 5с не детерминирован
  на уровне провайдера, авто-гейт на сам порог не заводится (#241).
- SEC-1: секрет-скан в CI (gitleaks или аналог) — кандидат в hardening.
- DEP-2: backup/restore-скрипты SQLite — кандидат в service-readiness шаг 2.

## Реестр ADR

| ADR | Тема |
|-----|------|
| [ADR-0001](adr_0001_web_primary_ui.md) | Web-first направление + критерии EOL Streamlit |
| [ADR-0002](adr_0002_sqlite_primary_store.md) | SQLite как primary store |
| [ADR-0003](adr_0003_canonical_signals_snapshot.md) | Канонический readiness/signals snapshot |
| [ADR-0004](adr_0004_coach_mutations_via_proposals.md) | Мутации коуча только через approval-gated proposals |
| [ADR-0005](adr_0005_execplan_driven_development.md) | ExecPlan-driven development |
| [ADR-0006](adr_0006_append_only_planning_versions.md) | Append-only версии плана |
| [ADR-0007](adr_0007_mock_ai_demo_acceptance.md) | Mock AI для demo/acceptance |
