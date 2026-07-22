# ADR 0008: Приём активностей из нескольких источников (Intervals-primary)

- Status: Accepted
- Date: 2026-07-22
- Related: `docs/intervals_primary_handoff_execplan.md` (M0), `activities` таблица, `activity_provider_links` (новая), `services/activity_ingest.py` (новый), `services/sync.py`, `services/intervals_icu.py`, `services/demo_mode.py`, `config/settings.py`, `docs/activity_tss_methodology.md`, ADR-0002

## Context

Трек Intervals-primary (`docs/intervals_primary_handoff_execplan.md`) требует, чтобы провайдерская активность становилась нашей канонической записью, способной нести идентичность и нагрузку ДВУХ источников (Garmin, Intervals) одновременно, не ломая инварианты проекта. Сегодня: `activities.activity_id TEXT PRIMARY KEY` — единственный ключ без провенанса; `source_tss` — одна колонка (у источников нагрузка разная); синк Garmin-gated (`services/sync.py:238`), пишет напрямую через `save_activities`. В БД уже есть не-Garmin строки — demo-активности `demo_activity_*` (`services/demo_mode.py:144`) и локально добавленные. Нужен зафиксированный, детерминированный контракт `provider data → canonical activity → planning` ДО кода адаптера.

## Decision

1. **Каноническая активность + provider-link модель.** `canonical_activity_id` = существующий `activities.activity_id` (потребители не ломаются). Связи — в `activity_provider_links(canonical_activity_id, provider, provider_activity_id, external_provider, external_id, provider_tss REAL, match_status, imported_at, UNIQUE(provider, provider_activity_id))`. Связь `canonical_activity_id → activities.activity_id` — **логическая** (без SQLite `FOREIGN KEY`, как и прочие связи в схеме — `PRAGMA foreign_keys` выключен); отсутствие orphan-links закрепляется ТЕСТОМ, не декларацией. DB-констрейнты в DDL: `CHECK (match_status IN ('matched','ambiguous','unmatched'))` и `CHECK ((external_id IS NULL AND external_provider IS NULL) OR (external_id IS NOT NULL AND external_provider IS NOT NULL))` — статус ограничен тремя значениями, `external_id` невозможен без namespace `external_provider`. Одна каноническая может нести Garmin-link И Intervals-link. `match_status` — место хранения fail-closed «пометки для ревью». Миграция аддитивна и идемпотентна.

2. **Fail-closed сопоставление.** Точная пара (`external_provider`, `external_id`) связывает две записи в одну каноническую (`match_status='matched'`). Отсутствие/неоднозначность → НЕ склеивать: раздельные канонические, `match_status ∈ {unmatched, ambiguous}`. `external_provider` — обязательный namespace (иначе `external_id="123"` ложно «глобально уникален»).

3. **TSS — явное исключение, ТОЛЬКО для Intervals.** `provider_tss` хранится ПО КАЖДОЙ связи и НЕ участвует в локальном каскаде расчёта `tss`. Fallback различает источники: **Intervals `icu_training_load`** при нехватке данных для локального расчёта МОЖЕТ стать каноническим `tss` как ЯВНО маркированный `tss_method="intervals_icu_provider_fallback"`. **Garmin `trainingLoad`** — Firstbeat/EPOC-нагрузка, НЕ TSS, и НИКОГДА не становится каноническим `tss`: для Garmin остаётся локальный каскад/heuristic (при нехватке данных — существующее поведение, не provider-fallback). Это сознательное исключение — `docs/activity_tss_methodology.md` обновляется, а не декларируется нетронутым.

4. **Первичный источник + детерминированное слияние (order-independent).** Настройка `PRIMARY_ACTIVITY_SOURCE` (`config/settings.py`, env): значения `garmin`|`intervals`; **дефолт `garmin`** (обратная совместимость); Intervals-quickstart ЯВНО задаёт `PRIMARY_ACTIVITY_SOURCE=intervals`; **неизвестное значение → fail-fast** (`config.settings._primary_activity_source` бросает `ValueError`, не угадывает). Канонические поля (спорт/длительность/дистанция/…) и `activities.source_tss` (legacy-проекция) при каждом ingest берутся из link ПРИОРИТЕТНОГО присутствующего источника: primary, если его link есть; иначе — присутствующий secondary. Результат зависит от НАБОРА связей, не от порядка их прихода. Обязательный тест: `Garmin → Intervals` ≡ `Intervals → Garmin` (совпадают canonical row, `tss`, `source_tss`, обе link). Канонический `tss`+`tss_method` первичны; `source_tss` — только совместимость.

5. **Ingest = нормализация + атомарная запись.** Разделены: `normalize_provider_activity(provider_row, source) -> candidate` (чистое преобразование, без БД) и `ingest_provider_activity(db, candidate) -> result`, которая в ОДНОЙ SQLite-транзакции upsert'ит canonical activity + provider-link + пересчёт `source_tss`-проекции (п.4) + продвижение курсора. И Intervals-адаптер, и внутренний persistence Garmin (`services/sync.py`) пишут через `ingest_provider_activity` — нет полу-записанных состояний между `activities` и link. Внешнее поведение `sync_garmin_data` (сообщения/результат/окно) байт-в-байт неизменно.

6. **Два настроенных источника.** Приоритет — `PRIMARY_ACTIVITY_SOURCE`; дедуп — по (`external_provider`,`external_id`); coexistence, не overwrite. Слияние канонических полей — детерминированно (п.4).

7. **Backfill — офлайн и детерминированно, с классификацией.** Миграция/backfill НЕ обращаются к Intervals (никакого поиска `external_id` по сети) — работают офлайн. Классификация существующих строк по форме `activity_id`: `demo_activity_*` → `provider='demo'` (без внешнего link); уверенно Garmin (числовой Garmin-id) → `provider='garmin'`; иначе → `provider='legacy_unknown'` (НЕ притворяться Garmin). `external_id` при backfill — null (свяжется позже ingest'ом M1, когда придут Intervals-данные). `provider_tss` ← текущий `source_tss`. Обязательный тест: повторный backfill стабилен по матрице `garmin/demo/legacy_unknown` (идемпотентность классификации).

8. **Курсоры** — per-provider и per-domain (активности отдельно от wellness); `source` — в состоянии/результате job (`api/sync_jobs.py`); bootstrap ≥90 дней; курсор продвигается внутри транзакции ingest (п.5).

9. **Rollback ≠ удаление link-таблицы.** После M1 удаление таблицы = потеря провенанса. Правильный rollback: отключить новый read/write path (вернуть прямой persistence), аддитивные данные (link-таблица, колонки) СОХРАНИТЬ. Физическое удаление — отдельная осознанная миграция только после backup.

## Consequences

- ✅ Ingest атомарен (canonical + link + `source_tss`-проекция + cursor в одной транзакции) — нет частично-записанных активностей при сбое.
- ✅ Результат order-independent: `Garmin→Intervals ≡ Intervals→Garmin` (обязательный тест), повторный синк разных источников не меняет canonical.
- ✅ Backfill офлайн/детерминирован, честно классифицирует `garmin/demo/legacy_unknown`, не выдаёт наследие за Garmin; повторный прогон стабилен (матрица-тест).
- ✅ «Пометка для ревью» имеет представление в данных (`match_status`); rollback не теряет провенанс (аддитивные данные сохраняются).
- ⚠️ Link-таблица и ingest-funnel затрагивают persistence-путь Garmin-синка; внешнее поведение защищено снапшот-тестом. Миграция/backfill аддитивны, приемлемы для single-athlete SQLite (ADR-0002).
- ⚠️ `activities.source_tss` — вторична (legacy-проекция первичного источника); потребители «нагрузки» переходят на канонический `tss` или per-link `provider_tss` по мере необходимости.

## ASR / risk traceability (ADD 3.0)

M0 задевает три ASR (`docs/architecture/asr_catalog.md`):

- **ASR-REL-3** (обрыв sync не портит частичные данные) — `ingest_provider_activity` атомарен (одна SQLite-транзакция: canonical + link + `source_tss`-проекция + cursor); сбой не оставляет полу-записи. Проверка — schema/ingest тесты.
- **ASR-MOD-3** (смена схемы обратно-совместима) — миграция `activity_provider_links` аддитивна и идемпотентна; потребители `activity_id` не ломаются. Проверка — schema RED→GREEN тест.
- **ASR-PERF-3** (инкрементальный sync) — per-provider/per-domain курсоры не раздувают окно при activity-only синке.

## Обязательные RED-матрицы для M0

- Порядок источников: `Garmin → Intervals` == `Intervals → Garmin` (canonical row, `tss`, `source_tss`, обе link совпадают).
- Классификация backfill при повторе: `garmin` / `demo` / `legacy_unknown` стабильны и не мутируют.
