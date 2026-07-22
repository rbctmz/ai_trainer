# M1 Slice-Spec: common ingest для обоих источников + Intervals-адаптер (#270)

- Status: Принято (ред. 3) — код M1 идёт строго по §11; ветка `claude/issue-270-*`
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
provider-link'ами; CTL/ATL считаются по этим активностям; `sync_garmin_data` на
success-path **идентичен как до M1, КРОМЕ единственного нового поля `source`** (§2, гейт
M1-T3), failure-path — намеренно изменён (§2, M1-T3b); coexistence и идемпотентность —
зелёными тестами.

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
поведение success-path обязано остаться идентичным, кроме единственного нового поля
`source`** (ADR-0008 п.5; детали — ниже).

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

**Совместимость Garmin делится на два пути (уточнение ревью #4):**

- **Success-path — идентичен, КРОМЕ единственного нового поля `source`** (уточнение
  ревью #2). Когда все активности окна приняты без ошибок: `GarminSyncResult`
  (counts/warnings/mode/messages) и `build_sync_status_payload` совпадают с
  до-рефакторной версией ЗА ИСКЛЮЧЕНИЕМ одного аддитивного ключа `source` (='garmin'),
  который M1 вводит осознанно (§5). `GarminSyncResult` получает поле `source: str =
  'garmin'`, payload — ключ `source`; больше ничего не меняется. Гейт `M1-T3`: снапшот
  до/после на идентичном fake-клиенте, сравнение со списком разрешённых новых ключей =
  `{'source'}` (не буквальное равенство), плюс `assert source == 'garmin'`. Т.к. при нуле
  ошибок warnings пуст, а `new/updated/skipped` берутся из `canonical_created` 1:1 со
  старым `sync_activities` — всё прочее совпадает.
- **Failure-path — НАМЕРЕННО изменён.** Старый `database.sync_activities` = один bulk-commit
  (all-or-nothing для батча активностей). Новый путь — per-activity атомарный ingest, и
  это сознательное улучшение: ошибка на ОДНОЙ активности не откатывает весь батч и не
  теряет остальные. Интендед-поведение M1:
  - каждая активность пишется атомарно (canonical+link — одна транзакция, M0 no-orphan):
    сбойная активность откатывается ЦЕЛИКОМ (нет activity без link), уже принятые —
    остаются;
  - per-activity ошибка → в `warnings` (модель Garmin-синка уже так делает для HRV/сна),
    синк продолжает следующую активность, а не падает целиком;
  - повтор идемпотентен (M0: UNIQUE + upsert → без дублей).
  Гейт `M1-T3b` (§7): инъекция сбоя на 2-й активности → 1-я принята с link, сбойная
  отсутствует целиком, warning есть, повтор добивает без дублей. Этот путь НЕ обязан
  совпадать со старым и тестируется ОТДЕЛЬНО от `M1-T3`.

**`database.sync_activities`** после рефактора не используется Garmin-путём. Решение:
оставить как deprecated-shim (демо/легаси-тесты) ИЛИ удалить с правкой вызовов —
см. Decision D4 (принято: shim в M1).

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

## 4. Курсор — граница успешно обработанного ОКНА (не дата активности)

Новая аддитивная таблица (ASR-MOD-3):
```
CREATE TABLE IF NOT EXISTS sync_cursors (
    provider TEXT NOT NULL,           -- 'garmin' | 'intervals'
    domain   TEXT NOT NULL,           -- 'activities' (wellness — M4)
    cursor_value TEXT,                -- ISO-дата ГРАНИЦЫ успешно обработанного окна
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (provider, domain)
)
```

**Семантика курсора — это high-water граница обработанного ВРЕМЕННО́ГО окна, а НЕ дата
последней активности** (уточнение ревью #1):
- `cursor_value` = верхняя граница (`end`) окна, которое было УСПЕШНО обработано целиком,
  зажатая по `now`. Пустое, но успешно обработанное окно всё равно продвигает границу
  (иначе бесконечный ре-синк пустого хвоста); наличие/отсутствие активностей на границу
  не влияет.
- Чтение окна: `cursor_value` есть → `[cursor_value − overlap_day, now]`; нет → bootstrap
  `[now − 90д, now]`. `overlap_day` (граничный день пересинкивается намеренно) ловит
  поздно загруженные/отредактированные активности; идемпотентный upsert (M0) поглощает
  перекрытие без дублей.
- Разбиение: окно режется на чанки ≤ `MAX_RECONCILIATION_WINDOW_DAYS`
  (`services/intervals_icu.py`), обрабатываются ХРОНОЛОГИЧЕСКИ (старые→новые).

**Продвижение курсора — только по чисто завершённому чанку; ошибка провайдера НЕ
двигает курсор** (уточнение ревью #2):
- Чанк «чист», если провайдерский fetch прошёл БЕЗ ошибок И все кандидаты чанка приняты
  ingest'ом. Тогда `advance_cursor` (из `ingest_provider_batch`, M0) двигает границу.
- **Продвижение МОНОТОННО — historical reload не откатывает курсор** (уточнение ревью #1):
  `cursor_value = max(текущий_cursor_value, end_чанка)`. Явный ре-синк старого окна
  (`days=N` больше дельты, bootstrap-перезалив истории) обрабатывает старые чанки, но
  НИКОГДА не опускает high-water границу ниже уже достигнутой. Курсор — истинный
  high-water mark, а не «последнее обработанное окно».
- Любая провайдерская ошибка (429/сеть/частичная страница) на чанке → продвижение
  ОСТАНАВЛИВАЕТСЯ на `end` последнего ЧИСТОГО чанка; курсор = граница непрерывного
  успешно-обработанного префикса. Данные за ошибкой НЕ пропускаются — добираются
  следующим запуском. Ошибки уходят в warnings (как в Garmin-пути), не в exception.
- Сбой ingest внутри чанка (не провайдерский) → M0-гарантия: курсор не двинут, повтор
  идемпотентен.

**Garmin в M1 курсорную таблицу НЕ принимает**: `resolve_sync_window`
(`services/sync.py`) остаётся как есть, чтобы не менять внешнее поведение Garmin.
Курсор-таблица — для Intervals (и будущих провайдеров). См. Decision D3.

## 5. API-контракт запуска Intervals + конкурентная семантика (уточнение ревью #3)

Текущее (Garmin): `POST /api/sync` (`SyncRequest{days}`) и `GET /api/sync` (статус),
через единый single-flight `sync_job_manager.start_or_get` (`api/routers/system.py:50`,
`api/sync_jobs.py`).

**API-контракт M1:**
- `POST /api/sync` — `SyncRequest` расширяется полем `source: 'garmin' | 'intervals'`
  (**дефолт `garmin`** — обратная совместимость; отсутствие поля = как сейчас).
  `source='intervals'` строит `run_sync`, зовущий `sync_intervals_data` (без Garmin-auth,
  гейт — `INTERVALS_ICU_API_KEY`); `source='garmin'` — без изменений.
- Неизвестный `source` → `422` (fail-fast, не угадывать) — симметрично
  `PRIMARY_ACTIVITY_SOURCE`.
- `GET /api/sync` — снапшот получает поле **`source`** (какой провайдер синкается/синкался);
  аддитивно, существующие поля не меняются.
- `result` job'а несёт `source` (для UI M3 и диагностики).

**Конкурентная семантика — single-flight по ВСЕМ провайдерам (SQLite = один писатель):**
- Менеджер запускает не более ОДНОГО sync-job'а одновременно, независимо от `source`.
  Запрос второго синка (любого источника), пока идёт первый → возвращается снапшот
  ТЕКУЩЕГО job'а (`reused=true`, с его `source` и `sync_state='running'`), НОВЫЙ job НЕ
  стартует. Это исключает гонку двух писателей по `activities`/`sync_cursors` и совпадает
  с нынешним поведением `start_or_get`.
- Форма реализации: обобщить `SyncJobManager` — `start_or_get(..., source)`, снимая
  Garmin-хардкод в сообщениях/имени треда; `source` кладётся в снапшот. Отдельный
  per-provider менеджер (параллельные синки) в M1 НЕ вводим (риск SQLite-lock,
  преждевременно). Пере-оценить, если понадобится параллелизм (тогда — отдельный ADR).
- Контракт-тест `test_sync_job_api`: (а) `GET /api/sync` содержит `source`; (б) при
  running-job'е второй `POST` (другой `source`) возвращает `reused=true` и НЕ меняет
  `source` текущего; (в) неизвестный `source` → `422`.

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
- **M1-T3 Garmin SUCCESS-path (идентичен кроме `source`):** `sync_garmin_data` на
  идентичном fake-клиенте БЕЗ ошибок до/после рефактора → `GarminSyncResult` и
  `build_sync_status_payload` совпадают ЗА ИСКЛЮЧЕНИЕМ единственного нового ключа
  `source` (разрешённый набор новых ключей = `{'source'}`), плюс `source == 'garmin'`.
- **M1-T3b Garmin failure-path (намеренно изменён; продолжение после ошибки):** батч из
  ТРЁХ активностей `[A, B(сбой), C]` — B падает В СЕРЕДИНЕ. Ожидаем: A принята с link;
  B отсутствует ЦЕЛИКОМ (нет activity без link, M0-атомарность); **C всё равно принята
  (доказывает continue-after-error, а не только «до сбоя»)**; B → warning, синк не падает;
  повтор идемпотентен (без дублей). Отдельно от T3.
- **M1-T3c count-матрица D1:** доказать, что `canonical_created` считается по
  СУЩЕСТВОВАНИЮ строки `activities` (а не связи), и маппинг `→ new/updated/skipped` 1:1 со
  старым `sync_activities`. Матрица:
  - (а) первый синк 2 новых + 1 без `activity_id` → `{new:2, updated:0, skipped:1}`;
  - (б) повтор тех же 2 → `{new:0, updated:2, skipped:0}`;
  - (в) смешанный (1 новая + 1 существующая) → `{new:1, updated:1}`;
  - (г) **существующий canonical БЕЗ link** (легаси-строка `activities` до backfill) →
    Garmin-ingest → `updated` (`canonical_created=False`, т.к. строка есть), НЕ `new` —
    доказывает, что счёт по строке, а не по наличию link;
  - (д) **Intervals-first → Garmin:** сначала Intervals-копия создала `intervals_<id>`,
    затем Garmin-активность G → `new` (создаётся НОВЫЙ canonical `G`, intervals-standalone
    поглощается/удаляется), НЕ `updated` и без задвоения — счёт идёт по разрешённому
    Garmin-canonical, coexistence-очистка не искажает счётчики.
  Все случаи совпадают с до-рефакторным `database.sync_activities` на тех же входах.
- **M1-T4 Intervals-only vertical:** без Garmin-кред `sync_intervals_data` наполняет
  `activities`; CTL/ATL считаются (не пусто) по Intervals-нагрузке.
- **M1-T5 курсор = граница окна + ошибка не двигает:** (а) повторный синк того же окна →
  без дублей, курсор стабилен; (б) УСПЕШНО обработанное ПУСТОЕ окно всё равно двигает
  границу (не дата активности); (в) провайдерская ошибка на чанке → курсор на `end`
  последнего чистого чанка, данные за ошибкой добираются повтором без дублей.
- **M1-T6 fail-closed end-to-end:** Intervals-активность с не-Garmin/пустым `source`
  не склеивается с Garmin-историей (standalone), даже если `external_id` численно
  совпадает с Garmin-id.
- **M1-T7 конкурентный sync:** при running-job'е второй `POST /api/sync` (другой `source`)
  возвращает `reused=true`, не стартует второй job и не меняет `source` текущего;
  неизвестный `source` → `422`.

## 8. ASR / risk traceability (ADD 3.0)

- **ASR-PERF-3** (инкрементальный sync, дельта дня): персистентный per-provider/per-domain
  курсор — окно Intervals не раздувается «oldest across tables» (проблема из ExecPlan).
- **ASR-REL-3** (обрыв sync не портит данные): ingest атомарен (M0); курсор двигается
  только после успешного batch → нет данных за курсором.
- **ASR-MOD-1/2** (новый источник/компонент без регресса): Intervals входит через тот же
  funnel; Garmin внешне неизменен.

## 9. Решения (Decisions)

- **D1 [ПРИНЯТО] — форма ingest-возврата.** Вернуть `canonical_created` в результат
  `write_provider_activity` (аддитивно), чтобы `_sync_activities` собрал те же
  `new/updated/skipped` 1:1 со старой семантикой.
- **D2 [ПРИНЯТО] — TSS для Intervals в M1: provider-fallback, не local recompute.**
  `list_activities` не несёт потоков мощности/ЧСС → локальный каскад невозможен без
  доп. запросов. M1 использует `icu_training_load` (провайдерский Coggan-TSS, близкий к
  нашему локальному по `activity_tss_methodology.md`), ЯВНО маркированный
  `intervals_icu_provider_fallback`; достаточно для CTL/ATL. Локальный пересчёт по
  потокам — отдельный поздний срез. Local-first-контракт M0 сохранён (готовый `tss`
  приоритетен).
- **D3 [ПРИНЯТО] — Garmin не переходит на курсор-таблицу в M1.** `resolve_sync_window`
  остаётся, чтобы не рисковать success-path-совместимостью Garmin. Курсор-таблица — Intervals +
  будущее.
- **D4 [ПРИНЯТО] — `database.sync_activities`.** Оставить deprecated-shim (демо/тесты)
  в M1; удаление — отдельный clean-up.
- **D5 [СПЕЦИФИЦИРОВАНО, ждёт подтверждения] — форма Intervals-job + конкурентность.**
  Зафиксировано в §5: обобщить `SyncJobManager(start_or_get(..., source))`, single-flight
  по всем провайдерам (SQLite = один писатель), второй параллельный запрос →
  `reused=true` без старта; `POST /api/sync {source}` (дефолт garmin), неизвестный →
  `422`; `GET /api/sync` и `result` получают `source` аддитивно. Тест — `M1-T7`.
- **D6 [ПРИНЯТО] — демо-активности и links.** Демо-сид (`services/demo_mode.py`,
  `demo_activity_*`) после сидирования прогоняет `backfill_provider_links`
  (классификация `demo`), чтобы демо-поверхность жила в той же модели.

## 10. Риски и rollback

- Главный риск — регресс внешнего поведения Garmin. Митигируется гейтом M1-T3
  (success-path идентичен кроме единственного поля `source`) до включения нового пути;
  failure-path — намеренно изменён и покрыт отдельно (M1-T3b).
- Rollback (ADR-0008 п.9): вернуть Garmin-persistence на прямой путь, аддитивные данные
  (link-таблица, `sync_cursors`) сохранить. Физического удаления не требуется.

## 11. Порядок работ (после принятия спеки)

1. D1: `canonical_created` в возврат ingest + переписать `_sync_activities` через ingest.
   Гейты до продолжения: **M1-T3** (success, идентичен кроме `source`), **M1-T3b**
   (failure-path, 3 активности — продолжение после ошибки), **M1-T3c** (count-матрица D1).
2. `sync_cursors` (миграция аддитивно) + чтение окна `[cursor−overlap, now]` + продвижение
   по чистому чанку (§4). Гейт **M1-T5** (граница окна, пустое окно двигает, ошибка не двигает).
3. `sync_intervals_data` (адаптер, D2 provider-fallback) + `ingest_provider_batch`; **M1-T4**.
4. Coexistence/регресс **M1-T1/T2**; fail-closed **M1-T6**.
5. `source` в `SyncJobManager`/`api/sync_jobs.py` + `POST/GET /api/sync` (§5); **M1-T7**
   (конкурентность/`422`).
6. D6 (демо-сид → backfill). Обновить ExecPlan Progress; PR из ветки `claude/issue-270-*`
   (закроет #270).
