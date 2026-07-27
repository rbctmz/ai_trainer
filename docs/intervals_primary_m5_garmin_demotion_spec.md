# Intervals-primary M5: финальный демоушен Garmin в UI

Этот ExecPlan является живым документом. Он завершает Intervals-primary трек
без изменения уже принятого контракта данных. После M5 новый пользователь видит
Intervals.icu первым источником для активностей и восстановления, а Garmin
Connect — явно необязательным дополнительным источником. При этом существующая
Garmin-история не мигрируется повторно и не переписывается: provider-link
backfill был выполнен в M0, а метрики восстановления уже несут provenance из
M4.

## Purpose

Сейчас функциональный поток уже source-aware, но оставшийся текст
`Для старта без Garmin` по-прежнему определяет продукт через Garmin, список
источников показывает Garmin первым, а подписи provenance дублируются в четырёх
React-компонентах. M5 убирает эти последние UX-сигналы обязательности Garmin,
не меняя синхронизацию, выбор primary source, схему SQLite или исторические
данные.

## Progress

- [x] (2026-07-27) Изучены issue #274, parent ExecPlan, ASR и фактические
  source-aware API/web контракты.
- [x] (2026-07-27) Добавлены RED-гейты порядка источников, onboarding-текстов и единого
  provenance formatter.
- [x] (2026-07-27) Реализованы минимальные API metadata и web-тексты/метки.
- [x] (2026-07-27) Выполнены targeted, smoke, offline, lint/build и браузерная приёмка.
- [x] (2026-07-27) Обновлены parent ExecPlan/ASR и выполнен self-review.
- [ ] Открыть PR, дождаться CI/review и передать владельцу на merge.

## Surprises & Discoveries

- Observation: M5 не требует миграции данных. M0 уже выполнил offline backfill,
  а принятый parent ExecPlan прямо ограничивает M5 UI-текстами и метками.
  Повторная миграция здесь была бы scope creep и риском для истории.
- Observation: M4 корректно показывает фактический источник HRV/сна, но
  преобразование технического source в пользовательскую подпись реализовано
  отдельно в `web/app/hrv/page.tsx`, `web/app/sleep/page.tsx`,
  `web/components/dashboard/SleepWidget.tsx` и
  `web/components/dashboard/AthleteProfileCard.tsx`.

## Decision Log

- Decision: сохранить `PRIMARY_ACTIVITY_SOURCE=garmin` как backward-compatible
  default ADR-0008. M5 меняет только представление: Intervals.icu идёт первым в
  onboarding, Garmin помечен дополнительным и необязательным. Явная настройка
  primary source продолжает определять рекомендуемый sync.
  Date/Author: 2026-07-27 / Codex.
- Decision: один чистый TypeScript formatter в `web/lib/sourceLabels.ts`
  преобразует provider provenance в UI-текст. Неизвестный source отображается
  как «источник не сохранён», а не как сырая техническая строка.
  Date/Author: 2026-07-27 / Codex.
- Decision: не добавлять схему, backfill или data mutation. Сохранность истории
  доказывается существующими M0/M1 regression suites и отсутствием data-layer
  diff.
  Date/Author: 2026-07-27 / Codex.

## Context and Orientation

`services/sync_providers.py::connection_overview` возвращает безопасный список
источников для `GET /api/sync/providers`. `web/components/sync/SyncControl.tsx`
рендерит этот список на пустом Dashboard и запускает явный provider sync.
Страницы сна и HRV получают уже канонические per-metric source значения из API.
M5 не касается `services/activity_ingest.py`, `services/wellness_ingest.py` или
`data/database.py`.

Затрагиваются ASR-MOD-2 (единый formatter уменьшает расхождение UI-компонентов),
ASR-MOD-3 (никаких изменений схемы или повторного backfill) и ASR-REL-2
(неизвестный provenance деградирует в понятную подпись).

## Behavior and Acceptance

Given пустой продуктовый экран, When API возвращает доступные источники, Then
Intervals.icu расположен первым и описан как источник активностей и
восстановления, а Garmin Connect расположен вторым и обозначен необязательным
дополнительным источником.

Given ни один источник не настроен, When пользователь читает onboarding, Then
текст предлагает настроить источник и не использует конструкцию «без Garmin».

Given метрика пришла из Intervals, Garmin, demo, mixed или derived source, When
её показывает Sleep/HRV/Dashboard/Profile, Then все компоненты используют один
formatter и показывают источник факта, а не hardcoded provider.

Given существующая SQLite-база с Garmin provider-links, When M5 устанавливается,
Then таблицы и история не изменяются, потому что M5 не выполняет data mutation.

## Plan of Work

Сначала `tests/smoke/test_m5_garmin_demotion.py` фиксирует продуктовый контракт и
падает на текущем порядке/текстах/дублированных formatter-ах. Затем
`services/sync_providers.py` получает только порядок и безопасное поле
`description`; соответствующий TypeScript contract расширяется аддитивно.
Новый `web/lib/sourceLabels.ts` используется всеми recovery/profile
компонентами и sync status. Onboarding copy становится provider-neutral.

## Validation

Из корня worktree выполнить:

    python -m pytest tests/smoke/test_m5_garmin_demotion.py -q
    python -m pytest tests/smoke/test_m3_sync_provider_api.py tests/smoke/test_m3_sync_ui_contract.py tests/smoke/test_m4_intervals_wellness.py -q
    python -m pytest tests/smoke -q
    python -m pytest -m "not live and not debug" tests/
    npm --prefix web run lint
    npm --prefix web run build

Браузерная приёмка выполняется на временной БД и отдельных портах. На пустом
Dashboard Intervals.icu должен быть первой карточкой, Garmin Connect — второй с
подписью «Дополнительный источник · необязательно», а onboarding-текст не
должен предполагать наличие Garmin.

## Idempotence and Recovery

Изменения не мутируют SQLite и безопасны при повторном запуске. Rollback —
обычный revert UI/API metadata commit; provider-links и канонические данные при
этом не затрагиваются.

## Outcomes & Retrospective

M5 реализован без data-layer изменений. `GET /api/sync/providers` показывает
Intervals.icu первым и добавляет безопасное описание роли; явный
`recommended_source` сохраняет backward compatibility. Garmin Connect
обозначен дополнительным необязательным источником. Recovery/profile/sync
поверхности используют общий `web/lib/sourceLabels.ts`, поэтому фактический
provenance отображается одинаково, а неизвестный source не протекает в UI как
техническая строка.

RED-гейт дал три ожидаемых падения и стал зелёным после реализации. Targeted
M3–M5 suite: 44 passed. Contributor-safe smoke: 1269 passed, 1 skipped.
Полный offline: 1312 passed, 6 skipped, 24 deselected. Next lint/build зелёные.
Изолированная browser-приёмка на пустой SQLite подтвердила порядок карточек,
опциональную подпись Garmin, нейтральный onboarding и отсутствие console errors.

Главный процессный вывод: формулировка «миграция владельца» не должна
автоматически становиться новой мутацией БД. Исторический backfill уже закрыт и
протестирован M0; финальный milestone безопаснее завершить удалением
presentation debt и прогоном существующей ingest regression.
