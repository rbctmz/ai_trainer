# M1 Slice-Spec: common ingest для обоих источников + Intervals-адаптер (#270)

- Status: На ревью (код НЕ пишется до принятия)
- Related: `docs/intervals_primary_handoff_execplan.md` (Milestone M1), ADR-0008
  (`docs/architecture/adr_0008_intervals_activity_ingestion.md`), M0 (#269, merged)
- Архитектура: без изменений (M0 established provider-link + проекционную модель).
  Этот документ — как M1 ИСПОЛНЯЕТСЯ внутри неё, точки касания и RED-матрицы.

## 1. Scope / Non-goals / Definition of Done

**В объёме M1:**
- Провести ОБА источника через общий `services.activity_ingest.ingest_provider_activity`:
  - внутренний persistence Garmin (`services/sync.py::_sync_activities`) учится
    создавать provider-link — БЕЗ изменения внешнего поведения `sync_garmin_data`;
  - новый Intervals-адаптер `sync_intervals_data(state, days, on_progress)` — не
    гейтится на Garmin-аутентификацию.
- Персистентный per-provider / per-domain курсор (M0 отложил персистентность).
- `source` в состоянии/результате sync-job (`api/sync_jobs.py`).
- Coexistence доказан тестами (Garmin+Intervals одной тренировки → одна каноническая
  через link, без задвоения), включая регресс «новая Garmin-активность → link, затем
  Intervals-копия присоединяется к той же канонической».

**НЕ в объёме M1 (границы):**
- Онбординг параметров и построение плана — M2 (#271). M1 «плана не обещает».
- Wellness (HRV/сон/RHR/readiness) из Intervals — M4 (#273). M1 — только активности.
- Source-agnostic UI / Docker quickstart — M3 (#272).
- Демоушен Garmin в UI-текстах — M5 (#274).
- Пересчёт локального TSS по потокам Intervals — см. Decision D2 (осознанно отложено).

**Definition of Done:** только-Intervals синк (без Garmin-кред) наполняет `activities`
provider-link'ами; CTL/ATL считаются по этим активностям; `sync_garmin_data` — байт-в-байт
как до M1; coexistence и идемпотентность — зелёными тестами.

## 2. Точки касания live-Garmin (критический риск)

`services/sync.py::_sync_activities(database, activities)` сейчас:
```
df = ActivityProcessor.process_activities(activities)
ftp, lthr = resolve_athlete_ftp_lthr(database)
resolved = [row + ActivityProcessor.resolve_tss(row, ftp, lthr) for row in df]
return database.sync_activities(resolved)   # -> {'new','updated','skipped'}
```
Возврат `{new,updated,skipped}` попадает в `GarminSyncResult.activity_result` и дальше
рулит `_build_success_messages`, `build_sync_status_payload`, `sync_state`. **Внешнее
поведение обязано остаться байт-в-байт** (ADR-0008 п.5).

**Контракт рефактора (M1):** `_sync_activities` для каждой resolved-активности зовёт
`normalize_provider_activity(activity_dict, "garmin")` → `ingest_provider_activity(db,
candidate, primary_source=Settings.PRIMARY_ACTIVITY_SOURCE)` и АГРЕГИРУЕТ те же счётчики:
- `skipped` — активность без `activity_id` (отсекается до normalize, как сейчас);
- `new` — `result['canonical_created'] is True`;
- `updated` — каноническая уже существовала.

Значит `ingest_provider_activity`/`write_provider_activity` **возвращают `canonical_created`
снова** (в M0 раунд-3 его убрали) — аддитивно к текущему возврату. Семантика совпадает:
проекция создаёт строку `activities` (new) либо обновляет (updated) — 1:1 со старым
`database.sync_activities`.

**Гарантия:** RED-матрица «byte-identical» (§7 M1-T3) снимает `GarminSyncResult` +
`build_sync_status_payload` до и после рефактора на идентичных fake-данных Garmin —
должны совпасть полностью.

**`database.sync_activities`** после рефактора не используется Garmin-путём. Решение:
оставить как deprecated-shim (демо/легаси-тесты) ИЛИ удалить с правкой вызовов —
см. Decision D4.

## 3. Intervals-адаптер `sync_intervals_data`

Новый модуль/функция (симметрично `sync_garmin_data`, но НЕ Garmin-gated):
```
def sync_intervals_data(state, days=None, on_progress=None) -> IntervalsSyncResult
```
- Гейт: `Settings.INTERVALS_ICU_API_KEY` (+ athlete_id). НЕТ `garmin_service.is_authenticated`.
- Окно: из курсора (§4); bootstrap ≥90 дней; клиент `services/intervals_icu.py::list_activities`
  (уже тянет `id, external_id, source, start_date, start_date_local, type, name,
  icu_training_load, moving_time`; окно ≤ `MAX_RECONCILIATION_WINDOW_DAYS` — резать на чанки).
- Нормализация: `normalize_provider_activity(row, "intervals")` (M0, чистая) → батч.
- Запись: `ingest_provider_batch(db, candidates, advance_cursor=…, primary_source=…)` —
  курсор двигается только после успешного batch (M0 guardrail).
- TSS: local-first — см. Decision D2 (в M1 — provider-fallback `icu_training_load`).
- Результат: структурный, UI-agnostic (`new/updated/skipped`, warnings, `source='intervals'`).
- Внешние сбои Intervals → warnings, не exceptions (как в Garmin-пути).

## 4. Курсор — персистентный, per-provider / per-domain

Новая аддитивная таблица (ASR-MOD-3):
```
CREATE TABLE IF NOT EXISTS sync_cursors (
    provider TEXT NOT NULL,           -- 'garmin' | 'intervals'
    domain   TEXT NOT NULL,           -- 'activities' (wellness — M4)
    cursor_value TEXT,                -- ISO-дата последнего успешно принятого окна
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (provider, domain)
)
```
- Чтение окна: `cursor_value` есть → инкремент от него; нет → bootstrap now−90д.
- Продвижение: ТОЛЬКО после успешного batch — через `advance_cursor` из
  `ingest_provider_batch` (M0). Значение = max(дата активностей окна).
- Сбой в середине окна → курсор прежний; повтор идемпотентен (M0: UNIQUE + upsert).
- **Garmin в M1 курсорную таблицу НЕ принимает**: `resolve_sync_window`
  (`services/sync.py`) остаётся как есть, чтобы не менять внешнее поведение Garmin.
  Курсор-таблица — для Intervals (и будущих провайдеров). См. Decision D3.

## 5. Job / API wiring

`api/sync_jobs.py::SyncJobManager` сейчас Garmin-специфичен (сообщения «Синхронизация
Garmin…», имя треда `garmin-sync-…`). M1:
- `source` в снапшоте job (`'garmin'|'intervals'`) и в `result`; дефолтные сообщения
  не зашивают провайдера жёстко.
- Точка входа Intervals-синка не гейтит на Garmin. Решение по форме (обобщить
  `SyncJobManager(source=…)` vs отдельный менеджер) — Decision D5.
- Существующие Garmin-эндпоинты/снапшоты — без изменения контракта (добавление
  `source` аддитивно; проверяется контракт-тестами `test_sync_job_api`).

## 6. Общий common-ingest — оба источника, один funnel

- Garmin: `_sync_activities` → normalize("garmin") → ingest (см. §2).
- Intervals: `sync_intervals_data` → normalize("intervals") → ingest (см. §3).
- Дедуп/coexistence — через M0-резолвер: Garmin `provider_activity_id` = координата,
  Intervals-копия ссылается `external=(garmin, external_id)` (только точный Garmin-`source`).
- Нет второго write-пути: `activities` пишется ТОЛЬКО через `write_provider_activity`
  (проекция). Никакого прямого `save/sync_activities` из провайдер-путей.

## 7. Обязательные RED-матрицы M1

- **M1-T1 coexistence:** Garmin-активность G + её Intervals-копия (`external_id=G`,
  `source=GARMIN_CONNECT`) → ОДНА каноническая, две `matched`-связи, один ряд в
  `activities`. Оба порядка прихода (переиспользуем M0 order-independence).
- **M1-T2 регресс (ExecPlan):** НОВАЯ Garmin-активность синкается ПОСЛЕ M0 через
  переписанный persistence → получает garmin-link; затем Intervals-копия
  присоединяется к той же канонической (две `matched`).
- **M1-T3 byte-identical Garmin:** `sync_garmin_data` на идентичном fake-клиенте до/после
  рефактора → совпадают `GarminSyncResult` (counts/warnings/messages/mode) и
  `build_sync_status_payload`.
- **M1-T4 Intervals-only vertical:** без Garmin-кред `sync_intervals_data` наполняет
  `activities`; CTL/ATL считаются (не пусто) по Intervals-нагрузке.
- **M1-T5 идемпотентность + курсор:** повторный Intervals-синк того же окна → без
  дублей; курсор стабилен на no-op; сбой в середине окна → курсор прежний, повтор
  добивает без дублей.
- **M1-T6 fail-closed end-to-end:** Intervals-активность с не-Garmin/пустым `source`
  не склеивается с Garmin-историей (standalone), даже если `external_id` численно
  совпадает с Garmin-id.

## 8. ASR / risk traceability (ADD 3.0)

- **ASR-PERF-3** (инкрементальный sync, дельта дня): персистентный per-provider/per-domain
  курсор — окно Intervals не раздувается «oldest across tables» (проблема из ExecPlan).
- **ASR-REL-3** (обрыв sync не портит данные): ingest атомарен (M0); курсор двигается
  только после успешного batch → нет данных за курсором.
- **ASR-MOD-1/2** (новый источник/компонент без регресса): Intervals входит через тот же
  funnel; Garmin внешне неизменен.

## 9. Открытые решения для ревью (Decisions)

- **D1 — форма ingest-возврата.** Вернуть `canonical_created` в результат
  `write_provider_activity` (аддитивно), чтобы `_sync_activities` собрал те же
  `new/updated/skipped`. Альтернатива — отдельный счётчик в ingest_batch. Предлагаю D1a
  (canonical_created), минимально и 1:1 со старой семантикой.
- **D2 — TSS для Intervals в M1: provider-fallback, не local recompute.**
  `list_activities` не несёт потоков мощности/ЧСС → локальный каскад невозможен без
  доп. запросов. Предлагаю: M1 использует `icu_training_load` (провайдерский Coggan-TSS,
  близкий к нашему локальному по `activity_tss_methodology.md`), ЯВНО маркированный
  `intervals_icu_provider_fallback`; этого достаточно для CTL/ATL. Локальный пересчёт по
  потокам — отдельный поздний срез. (Local-first-контракт M0 сохранён: если поле `tss`
  уже посчитано — оно приоритетно.)
- **D3 — Garmin не переходит на курсор-таблицу в M1.** `resolve_sync_window` остаётся,
  чтобы не рисковать байт-идентичностью Garmin. Курсор-таблица — Intervals + будущее.
- **D4 — `database.sync_activities`.** Оставить deprecated-shim (демо/тесты) vs удалить
  с правкой вызовов. Предлагаю оставить shim в M1 (меньше поверхности риска), удалить в
  отдельном clean-up.
- **D5 — форма Intervals-job.** Обобщить `SyncJobManager` параметром `source` vs
  отдельный менеджер. Предлагаю обобщение (один снапшот-контракт, добавляем `source`).
- **D6 — демо-активности и links.** Демо-сид (`services/demo_mode.py`, `demo_activity_*`)
  после сидирования прогонять `backfill_provider_links` (классификация `demo`), чтобы
  демо-поверхность жила в той же модели. Мелкое, но зафиксировать.

## 10. Риски и rollback

- Главный риск — регресс внешнего поведения Garmin. Митигируется M1-T3 (byte-identical
  снапшот) до включения нового пути.
- Rollback (ADR-0008 п.9): вернуть Garmin-persistence на прямой путь, аддитивные данные
  (link-таблица, `sync_cursors`) сохранить. Физического удаления не требуется.

## 11. Порядок работ (после принятия спеки)

1. D1: `canonical_created` в возврат ingest + переписать `_sync_activities` через ingest;
   M1-T3 byte-identical зелёный (гейт до продолжения).
2. `sync_cursors` (миграция аддитивно) + чтение/продвижение окна Intervals.
3. `sync_intervals_data` (адаптер) + `ingest_provider_batch`; M1-T4/T5.
4. Coexistence/регресс M1-T1/T2; fail-closed M1-T6.
5. `source` в `api/sync_jobs.py`; контракт-тесты.
6. Обновить ExecPlan Progress; PR из ветки `claude/issue-270-*` (закроет #270).
