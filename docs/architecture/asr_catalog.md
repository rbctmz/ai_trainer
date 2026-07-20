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
