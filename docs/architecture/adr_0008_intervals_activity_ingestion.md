# ADR 0008: Приём активностей из нескольких источников (Intervals-primary)

- Status: Accepted
- Date: 2026-07-22
- Related: `docs/intervals_primary_handoff_execplan.md` (M0), `activities` таблица, `activity_provider_links` (новая), `services/activity_ingest.py` (новый), `services/sync.py`, `services/intervals_icu.py`, `docs/activity_tss_methodology.md`, ADR-0002

## Context

Трек Intervals-primary (`docs/intervals_primary_handoff_execplan.md`) требует, чтобы провайдерская активность становилась нашей канонической записью, способной нести идентичность и нагрузку ДВУХ источников (Garmin и Intervals) одновременно, не ломая инварианты проекта. Сегодня: `activities.activity_id TEXT PRIMARY KEY` — единственный ключ без провенанса источника; `source_tss` — одна колонка (у Garmin и Intervals нагрузка разная); синк Garmin-gated (`services/sync.py:238`) и пишет напрямую через `save_activities`. Просто «upsert по Intervals id» не доказывает идемпотентность и coexistence. Нужен зафиксированный контракт `provider data → canonical activity → planning` ДО кода адаптера.

## Decision

1. **Каноническая активность + provider-link модель.** `canonical_activity_id` — это существующий `activities.activity_id` (потребители не ломаются). Связи с источниками — в отдельной таблице `activity_provider_links(canonical_activity_id FK, provider, provider_activity_id, external_provider, external_id, provider_tss REAL, imported_at, UNIQUE(provider, provider_activity_id))`. Одна каноническая активность может нести Garmin-link И Intervals-link. Миграция аддитивна и идемпотентна (ensure-column/create, как для прочих новых таблиц).

2. **Fail-closed сопоставление.** Точная пара (`external_provider`, `external_id`) может связывать записи двух источников в одну каноническую. Отсутствие или неоднозначность `external_id` → НЕ склеивать эвристикой: оставить раздельными каноническими и пометить для ревью. `external_id` — механизм внешнего сопоставления, не глобальный идентификатор физической тренировки; поэтому namespace `external_provider` обязателен (иначе `external_id="123"` ложно «глобально уникален»).

3. **TSS — явное исключение, а не «инвариант цел».** `provider_tss` (Garmin `trainingLoad` / Intervals `icu_training_load`) хранится ПО КАЖДОЙ связи и НЕ участвует в локальном каскаде расчёта `tss`. При нехватке данных для локального расчёта `provider_tss` может стать каноническим `tss` как ЯВНО маркированный `tss_method="intervals_icu_provider_fallback"`. Это сознательное исключение из политики `docs/activity_tss_methodology.md` — документ обновляется (раздел «Решение»), а не декларируется нетронутым.

4. **`activities.source_tss` — legacy-проекция.** Оставляем колонку для совместимости как проекцию `provider_tss` ВЫБРАННОГО источника: значение берётся из провайдера сконфигурированного первичного источника (при конфликте — приоритет источника), обновляется при ingest. Канонический `tss` (+`tss_method`) — отдельно и первичен для аналитики; `source_tss` — только совместимость.

5. **Common ingest для ОБОИХ источников.** Единственная точка записи активности — `services/activity_ingest.py::to_canonical_activity(provider_row, source) -> (canonical, link)`. И Intervals-адаптер, и внутренний persistence-путь Garmin (`services/sync.py`) пишут через неё, создавая provider-link. Внешнее поведение `sync_garmin_data` (сообщения, результат, окно) сохраняется байт-в-байт; меняется только внутренняя запись. Иначе новые Garmin-активности после миграции писались бы без link и снова ломали coexistence (backfill покрывает лишь историю).

6. **Поведение при двух настроенных источниках.** Приоритет — сконфигурированный первичный источник (для беты обычно единственный). Дедуп канонических — по link (`external_provider`,`external_id`); coexistence, не overwrite: наличие обоих источников связывает их в одну каноническую, а не затирает.

7. **Backfill + rollback — в M0.** Каждая существующая Garmin-активность получает link (`provider='garmin'`, `provider_activity_id=activity_id`, `provider_tss`←текущий `source_tss`, `external_id` если известен из Intervals-джойна) ещё в M0 — иначе M1 не сможет доказать coexistence. Неоднозначные исторические строки помечаются, не склеиваются. Rollback: снять link-таблицу / вернуть прямой persistence — операция аддитивна и обратима.

8. **Курсоры синка — per-provider и per-domain.** Активности и wellness — раздельные курсоры на источник (не «oldest across tables», иначе activity-only синк с пустыми wellness-таблицами раздувает окно). `source` — в состоянии и результате job (`api/sync_jobs.py`). Первый bootstrap — минимум 90 дней, далее инкрементально по доменному курсору.

## Consequences

- ✅ Garmin и Intervals сосуществуют без потери истории; повторный синк идемпотентен; провенанс TSS честный (провайдерская нагрузка отдельно, fallback явно помечен); handoff тестеру без Garmin разблокирован.
- ✅ Контракт зафиксирован до кода: M1 реализует адаптер и common ingest против этого ADR; идемпотентность/coexistence/fail-closed доказываются тестами (вкл. регресс «новая Garmin-активность → link, затем Intervals-копия → та же каноническая»).
- ⚠️ Link-таблица и common-ingest funnel затрагивают persistence-путь Garmin-синка; внешнее поведение защищено снапшот-тестом. Миграция/backfill аддитивны, приемлемы для single-athlete SQLite (ADR-0002).
- ⚠️ `activities.source_tss` становится вторичной (legacy-проекцией) — потребители, читавшие её как «нагрузку», должны переходить на канонический `tss` или на per-link `provider_tss`; переход — по мере необходимости, не ломающе.
