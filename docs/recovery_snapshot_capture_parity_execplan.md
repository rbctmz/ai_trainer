# Паритет post-sync capture readiness-снимка для Garmin и Intervals (issue #562)

Этот ExecPlan — живой документ, который ведётся по правилам `.agent/PLANS.md` (корень репозитория): разделы `Progress`, `Surprises & Discoveries`, `Decision Log`, `Outcomes & Retrospective` обязаны поддерживаться в актуальном состоянии, а каждая правка плана фиксируется в `Change log` в конце документа. Документ самодостаточен: читатель, у которого есть только это дерево и этот файл, должен суметь выполнить работу целиком.

Issue: [#562](https://github.com/rbctmz/ai_trainer/issues/562). Change Class: **A — Full**. Базовая точка: `main` = `9ba4a37` (в main уже влиты #552 — revisioned evidence head и lifecycle, #557/#563 — freshness/provenance readiness и fail-closed intervention, #564/#565 — интервенционное evidence и guard отката `training_readiness`).

Ревизия документа: v1.9 (реализация: M1 и M2 закрыты, плюс hardening-слайс F1–F3; план отревьюен раундами `4ae3f4b`/`20f9dcb`, решения владельца D4/D5/D8 применены). Публичный API payload, UI и схема пока не менялись.

## Purpose / Big Picture

Сегодня post-sync derived capture есть только в Garmin-пути: `services/sync.py` после сохранения wellness-данных вызывает `record_post_sync_recovery_state(...)`. Intervals-путь (`services/intervals_sync.py::sync_intervals_data`) такого вызова не содержит, поэтому спортсмен, который синхронизируется только через Intervals.icu, систематически остаётся без prospective readiness-снимка, а его день позже исключается из recovery-эпизодов как `missing_pre_anchor`. При этом даже в Garmin-пути результат capture невидим: единственная строка `Recovery snapshot: …` уезжает в `notices`, а веб показывает notices только при `sync_state == "partial"` и не более двух.

После изменения при **каждой** успешной или частично успешной синхронизации — Garmin или Intervals.icu — сохраняется ровно один явно подтверждённый prospective-снимок с локальным временем, пригодностью и машинно-читаемой причиной, а UI сразу сообщает, успел ли снимок зафиксировать состояние **до первой активности дня**. Человек видит одно из пяти честных состояний: снимок сохранён до нагрузки, сохранён слишком поздно, старт активности неизвестен (`activity_start_missing`), снимок непригоден, capture завершился ошибкой — вместо общего «Синхронизация завершена». Ошибка derived capture не откатывает основной sync: данные провайдера остаются валидными, а сбой виден отдельным полем.

Проверить это можно так: запустить синхронизацию из UI для каждого источника и увидеть в строке синка локальное время снимка, статус pre-activity и причину; повторный запуск того же job не создаёт новую ревизию, а новая синхронизация в тот же день создаёт монотонную дневную ревизию.

## Progress

- [x] (2026-09-12) Plan-only этап: создан этот ExecPlan и Class A slice-spec, зафиксированы решения, RED→GREEN матрица и контур milestones. Код/API/UI/схема не менялись.
- [x] (2026-09-12) M1. Provider-neutral capture-контракт и identity semantics — ветка `codex/issue-562-recovery-capture-parity` от обновлённого `main` (`facc2b4`), собственный review budget (D8). `capture_post_sync_recovery_state(...)` в `services/recovery_analytics.py`, правило пяти состояний — `capture_verdict` в `models/recovery_response.py`, дурабельный `capture_provider` в провенансе, общая граница дня `daily_activity_cutoff`. Исходный RED `13 failed` → GREEN `13 passed`; safety RED `2 failed` (`6dbe415`) → GREEN `14 passed`; подробности — `Artifacts and Notes`.
- [x] (2026-09-13) M2. Garmin-путь использует общий контракт без двойной записи; `SyncJobManager` генерирует отдельный полный `capture_run_id` и передаёт его через API runner в `sync_garmin_data`, direct/demo вызов генерирует полный UUID сам. RED `4 failed` (`22fda6b`) → GREEN `34 passed` на Garmin/job/audit focused-контуре; D4 сохраняет `partial` + warning при `capture_failed`. Подробности — `Artifacts and Notes`.
- [ ] M3. Intervals parity: тот же контракт в `services/intervals_sync.py`, fail-open как в Garmin.
- [ ] M4. Additive API↔web контракт: `recovery_capture` в payload обоих провайдеров, `web/lib/types.ts`, регенерация `tests/contracts/ts_contract.json`, инвентарь.
- [ ] M5. UI readback: локальное время, статус, причина в строке синка (роль UI/Design Specialist — см. Decision Log D6).
- [ ] M6. Приёмка: синтетическая browser-приёмка обоих провайдеров, инвариант «capture-статус ⇔ дневной anchor», fail-open, идемпотентность/монотонность, широкий контур, ASR-каталог, evidence bundle.

## Surprises & Discoveries

- **Observed**: `SyncControl` смонтирован только на дашборде — `web/app/dashboard/page.tsx:42` (компактный вариант) и `:128` (подробный, в пустом состоянии); отдельной страницы `/sync` нет. Текст сообщения рендерится как `<p>` (`SyncControl.tsx:147`) либо как `<span className="hidden … sm:inline">` (`:155`), то есть в компактном варианте строка скрыта на узких экранах.
  **Inferred**: браузерный сценарий M6 обязан целиться в тот вариант, который реально видим на выбранной ширине, иначе приёмка «пройдёт» по невидимой строке; а UI-слайс M5 ограничен дашбордом, встраивать отдельную страницу синка нельзя (это расширение scope).
  **Verified by**: чтение `web/app/dashboard/page.tsx:42,128` и `SyncControl.tsx:147,155` на `9a4ba37`-предке ветки плана (`main` = `9ba4a37`).
- **Observed**: веб-строка синка — это один текст, собранный `web/components/sync/SyncControl.tsx::formatSyncJob` (`:203-233`); она читает только `sync_state`, `source`, `reused`, `progress.percent/message`, `error.message`, `result.title`, `result.counts.new/updated` и `result.notices`, причём notices подставляются **только** при `sync_state === "partial"` и обрезаются до двух (`:225-236`). Поля `result.summary/severity/mode/highlights/activity_changes/recovery_changes/synced_at`, `progress.step_text/stats_message` и `operational_state` не отображаются вообще.
  **Inferred**: даже после добавления capture в Intervals-путь человеко-читаемая строка в `notices` не сделает результат видимым — нужен структурный блок и явный рендер; иначе AC4/AC5/AC8 выполняются «в данных», но не «на экране».
  **Verified by**: чтение `SyncControl.tsx` и `web/lib/types.ts:680-711` на `9ba4a37`; отдельного JS-теста на `formatSyncJob` в репозитории нет (в `web/` нет JS-тест-раннера), есть только статические проверки строк в `tests/smoke/test_m3_sync_ui_contract.py` (4 теста).
- **Observed**: реестр контракта связывает путь `/api/sync` с интерфейсом `SyncJobResponse` (`tests/contracts/registry.json:145-150`, сценарий `demo`, ожидается 200), но drift-харнесс выполняет только `GET` (`tests/smoke/test_web_contract_drift.py:192` — безусловный `client.get(url, …)`), а в зарегистрированном сценарии джоб не терминальный, то есть `result` отсутствует.
  **Inferred**: аддитивный блок `recovery_capture` внутри `result` не будет автоматически пойман конформанс-проверкой (в demo-сценарии его просто нет), а `POST /api/sync` не проверяется вовсе — поэтому AC9 закрывается не только регенерацией артефакта, но и явным тестом формы ответа для обоих источников.
  **Verified by**: чтение `registry.json:145-150`, `test_web_contract_drift.py:185-200` и `web/scripts/extract-contract.mjs`; `web/package.json` не содержит JS-тест-раннера (scripts: dev/build/start/lint/contract:inventory/contract:extract), то есть строковый вывод `formatSyncJob` сейчас вообще не покрыт тестом.
- **Observed**: идемпотентность capture по run identity уже реализована и покрыта: `data/database.py::save_readiness_snapshot` считает `fingerprint = sha256({capture_run_id, capture_mode})`, атомарно (`BEGIN IMMEDIATE`) возвращает `{'created': False}` на повторе и ведёт монотонную `revision` в пределах `target_key = readiness:<mode>:<local_date>`; `tests/smoke/test_recovery_episode_materializer.py::test_capture_run_identity_wins_over_retry_clock` это доказывает (`first.created is True`, `retry.created is False`, одна строка, `revision` не растёт).
  **Inferred**: AC3 закрывается не новой механикой хранения, а **стабильной идентичностью рана на API-пути**: сегодня `services/sync.py` генерирует `uuid.uuid4()` внутри `sync_garmin_data`, то есть идентичность не связана с job'ом.
  **Verified by**: чтение `services/sync.py:411-424`, `data/database.py:1224-1295`, `api/sync_jobs.py:47-110`.
- **Observed**: M1 принимал `capture_run_id` и доказывал его storage/idempotency semantics, но production `SyncJobManager` всё ещё вызывал runner только с progress callback, а Garmin создавал собственный UUID внутри сервиса; значит end-to-end job identity ещё не была закрыта.
  **Inferred**: полный UUID должен рождаться один раз на job boundary и передаваться keyword-аргументом через provider-neutral runner; короткий `job_id` остаётся только display/audit handle.
  **Verified by**: M2 RED `4 failed` на `22fda6b`; GREEN: тест API job получает ровно один parseable full UUID при reuse, Garmin wrapper вызывается один раз с тем же явным ID, direct вызов генерирует отдельный full UUID.
- **Observed**: `SyncJobManager` — process-local: новый процесс инициализируется idle-снимком (`api/sync_jobs.py::_idle_snapshot`), то есть терминальный `result` (а с ним и `recovery_capture`) не переживает рестарт API; `capture_failed` при этом не пишет ни одной строки в журнал, поэтому восстановить его из базы нельзя.
  **Inferred**: терминальный readback capture-статуса **эфемерен**; дурабельна только сама запись снимка (её строка и provenance). Значит «переживает рестарт» нельзя заявлять как покрытое свойство — это надо честно объявить эфемерным, а персистенцию исходов (включая провалы) вынести за scope.
  **Verified by**: чтение `api/sync_jobs.py` (`_idle_snapshot`, `start_or_get`, `_public_snapshot_locked`) и структуры `readiness_snapshots` (поля исхода capture там нет) на `9ba4a37`.
- **Observed**: активности нужно читать **по дате самой ревизии**, а не окном от текущего момента: `db.get_activities(days=N)` отсчитывает окно от сегодня, поэтому backfilled-захват прошлого дня не видел бы активности этого дня и вердикт стал бы `saved_before_load` вместо `saved_too_late`.
  **Inferred**: граница дня относится к дате capture, а не к моменту запуска; выборка обязана быть детерминированной и не зависеть от того, когда захват выполнен.
  **Verified by**: первый прогон RED-тестов дал ровно этот симптом (`assert 'saved_before_load' == 'saved_too_late'` на исторической дате `2026-07-16`); после перехода на `db.get_activities_between(local_date − 1 день, local_date)` тест зелёный, и это же покрывает backfilled-режим.
- **Observed**: активность дня добавляет фактор TSB, поэтому снимок, который без активности был бы непригоден (`low_confidence`), становится `eligible` — фикстура «непригодный снимок + нечитаемый старт» сначала дала `eligibility_status == "eligible"`.
  **Inferred**: при проверке приоритета предикатов нельзя опираться на «рядом есть активность» как на признак непригодности: непригодность нужно создавать независимо (в тесте — один сигнал readiness, 0.2–0.4 < 0.60 даже с TSB).
  **Verified by**: `test_capture_activity_start_missing_wins_over_ineligible` после правки фикстуры: статус `activity_start_missing`, `eligibility_status == "ineligible"`.
- **Observed**: ошибка `get_activities_between(...)` после успешной записи ревизии поглощалась как пустой список, поэтому публичный вердикт маскировал технический отказ обычным доменным статусом; кроме того, `str(exc)` попадал в будущий публичный `recovery_capture` и мог раскрыть локальный путь или иной внутренний текст.
  **Inferred**: невозможность доказать временную границу обязана завершаться fail-closed статусом, а публичная причина должна быть стабильным кодом, не текстом исключения.
  **Verified by**: RED `2 failed` на checkpoint `6dbe415`; GREEN `14 passed` — уже сохранённая ревизия возвращается с `capture_failed/activity_lookup_failed`, провал записи с `capture_failed/snapshot_capture_failed`, исходный текст исключения отсутствует в блоке.
- **Observed**: словарь состояний уже частично существует: `models/recovery_response.py::select_daily_anchor` возвращает `reason ∈ {invalid_timezone, activity_start_missing, no_eligible_pre_anchor_snapshot}`, а `evaluate_snapshot_eligibility` — причины `missing_as_of`, `missing_score`, `low_confidence` (<0.60), `stale_snapshot`, `stale_factor`, `future_factor`; cutoff = минимальный старт активности дня, иначе локальный полдень.
  **Inferred**: новые пять состояний capture — это проекция уже существующих примитивов, а не новая научная логика; расхождение с `select_daily_anchor` было бы дефектом, поэтому инвариант «capture-статус ⇔ дневной anchor» попадает в RED-матрицу.
  **Verified by**: чтение `models/recovery_response.py:66-140` на `9ba4a37`.
- **Observed**: e2e-стенд (`tests/e2e/conftest.py::web_stack`) поднимает изолированный uvicorn + Next.js + Chromium и **гасит креды провайдеров** (`GARMIN_EMAIL=""`, `GARMIN_PASSWORD=""`, `INTERVALS_ICU_API_KEY=""`, `:214-216`), из-за чего оба провайдера приходят как `configured: false`, а кнопка синка и выбор источника в UI отключены; ни один e2e-тест не обращается к `/api/sync`, каталога `tests/e2e/fixtures/` нет.
  **Inferred**: требование «синтетическая browser-приёмка обоих provider-путей» нельзя выполнить «как есть» — нужен один из двух механизмов (Decision Log D5).
  **Verified by**: чтение `tests/e2e/conftest.py:189-260` и поиск обращений к `/api/sync` по `tests/e2e/`.

## Decision Log

- Decision (D1): **владение capture — общий provider-neutral вход в `services/recovery_analytics.py`**, вызываемый обоими sync-сервисами; Garmin-путь перестаёт держать собственный инлайн-блок.
  Rationale: capture обязан работать не только на API-пути. Легаси-Streamlit и demo вызывают `services/sync.py::sync_garmin_data` и `services/intervals_sync.py::sync_intervals_data` напрямую; хук в `api/routers/system.py` оставил бы эти поверхности без снимка — то есть воспроизвёл бы дефект #562 в другом месте. Отвергнутая альтернатива — вызов capture только в API-раннере (`_run_garmin_sync`/`_run_intervals_sync`): меньше файлов в диффе, но потеря поведения на не-API поверхностях.
  Date/Author: 2026-09-12 / agent (Spec / Architecture Owner, plan-only этап).
- Decision (D2): **устойчивая идентичность capture-рана — полный UUID, а не усечённый `job_id`**: `api/sync_jobs.py::SyncJobManager.start_or_get` продолжает создавать короткий `job_id` как display/job handle, но дополнительно генерирует `capture_run_id = str(uuid.uuid4())` (полный) и передаёт его в раннер; оба sync-сервиса принимают аддитивный keyword `capture_run_id: str | None = None`, а при `None` генерируют полный UUID сами (обратная совместимость для прямых вызовов, demo и тестов).
  Rationale: AC3 требует «повтор того же capture run не создаёт ревизию, отдельная синхронизация в тот же день создаёт новую монотонную ревизию», и это обеспечено хранением (`fingerprint = sha256({capture_run_id, capture_mode})` + монотонная `revision`), но только при стабильной и **неколлизирующей** идентичности. `job_id = str(uuid.uuid4())[:8]` (`api/sync_jobs.py:63`) — это 32-битное пространство, а дедупликация идёт по `(capture_mode, capture_run_id)` (индекс `readiness_snapshots(capture_mode, capture_run_id)`, `data/database.py:946`) глобально, без ограничения датой: коллизия двух разных job'ов молча пометила бы новую синхронизацию ретраем и потеряла бы дневную ревизию (review P2). Полный UUID (122 бита) исключает это, короткий id остаётся человеко-читаемым.
  Контракт раннера **изменён, а не расширен аддитивно** (F1): `SyncRunner` стал `Protocol` с **обязательным** keyword-аргументом `capture_run_id` (`api/sync_jobs.py:29`), вызов — `run_sync(on_progress, capture_run_id=…)`, `_run_garmin_sync`/`_run_intervals_sync` пробрасывают id в сервисы. Обязательность осознанная: опциональный keyword позволил бы молча не протянуть идентичность до сервиса и вернул бы дефект 32-битного `job_id`; вызывающие и тестовые двойники обновлены в том же слайсе M2. Публичным контрактом `SyncRunner` не является — он внутренний для `api/`.
  Date/Author: 2026-09-12 / agent (уточнено по review P2).
- Decision (D3): **пять состояний capture вычисляются, а не хранятся**: `saved_before_load`, `saved_too_late`, `activity_start_missing`, `ineligible`, `capture_failed` — проекция уже существующих примитивов (eligibility + старты активностей дня + cutoff из `select_daily_anchor`), без новой колонки и без миграции.
  Rationale: состояние выводимо из журнала `readiness_snapshots` и активностей в любой момент; персистенция дублировала бы выводимое состояние и потребовала бы миграции (автоматический триггер более тяжёлого класса).
  **Состояние относится к конкретной сохранённой ревизии, а не ко дню** (review P1): для ревизии `r` с собственной eligibility `e_r` и временем наблюдения `t_r` при cutoff дня `c` — `saved_before_load` ⇔ `e_r ∧ t_r ≤ c`; `saved_too_late` ⇔ `e_r ∧ t_r > c`; `ineligible` ⇔ `¬e_r`; `activity_start_missing` ⇔ provenance старта активности дня непригодна (fail-closed, вычисляется независимо от `t_r`); `capture_failed` ⇔ capture выбросил исключение. День может нести несколько ревизий (AC3), поэтому «нашёлся anchor за день» **не** означает «новая ревизия до нагрузки»: при захвате в 05:00, активности в 10:00 и новой ревизии в 11:00 новая ревизия обязана быть `saved_too_late`, а anchor дня остаётся у 05:00.
  **Предикаты статуса взаимоисключающие, порядок разрешения конфликтов задан явно** (review P2): (1) `capture_failed`, если capture выбросил исключение; (2) `activity_start_missing`, если provenance старта активности дня непригодна — **до** проверки eligibility, как это делает `select_daily_anchor` (`models/recovery_response.py:113-120`); (3) `ineligible`, если ревизия не прошла gate; (4) иначе `saved_before_load` при `t_r ≤ c` и `saved_too_late` при `t_r > c`. Пересекающийся случай (непригодная ревизия в день с нечитаемым стартом) обязан давать `activity_start_missing`, а не `ineligible`.
  Отдельный дневной инвариант (не подменяет статус ревизии): `select_daily_anchor` находит кандидата ⇔ существует ревизия со статусом `saved_before_load`, и выбранный кандидат — последняя eligible-ревизия с `t_r ≤ c` (существующее поведение сохраняется).
  Date/Author: 2026-09-12 / agent (уточнено по review P1).
- Decision (D4): **fail-open граница — без отката данных и без ложного `succeeded`** (решение владельца, 2026-09-12): при сбое derived capture данные провайдера остаются сохранёнными, `sync_state="partial"` и warning **сохраняются**, а `recovery_capture.status = "capture_failed"` с машинно-читаемой причиной объясняет, какая именно производная операция не выполнилась.
  Rationale: fail-open означает отсутствие отката, а не выдачу успеха за неудачу. Сегодняшний `build_sync_status_payload` уже переводит ответ в `partial` при `result.warnings` — это поведение сохраняется, поэтому единственным новым наблюдаемым элементом остаётся структурный блок с точной причиной; «частичная синхронизация» перестаёт быть непрозрачной. Первоначальная редакция плана предлагала не переводить успешную синхронизацию в `partial` — **это предложение отклонено владельцем** и в план не входит.
  Date/Author: 2026-09-12 / agent (переформулировано по решению владельца).
- Decision (D5): **browser contract/UX acceptance** (подтверждено владельцем, 2026-09-12): Playwright перехватывает `/api/sync/providers`, `POST /api/sync` и `GET /api/sync` фикстурами обоих провайдеров, а форму фикстуры пришпиливает отдельный тест, сравнивающий её ключи с реальным payload'ом. Это **не** называть настоящим provider E2E: сервисный и API-контур доказывается Python-тестами с инъекцией клиентов (в том числе `sync_intervals_data(client=…)`). Отвергнутая альтернатива — тест-онли переключатель «фейкового провайдера» в продуктовом пути: даёт настоящий end-to-end, но добавляет тест-зависимую ветку в продукт.
  Rationale: в e2e-стенде креды провайдеров погашены, а кнопка синка отключена (см. `Surprises`), поэтому «как есть» приёмка невозможна; перехват маршрутов не требует ни продуктового кода ради тестов, ни изменения стенда, и остаётся честным при связке «фикстура ↔ форма ответа» тестом. Цена отвергнутой альтернативы уточнена разведкой: API-раннеры `_run_garmin_sync`/`_run_intervals_sync` (`api/routers/system.py:150-206`) не принимают override клиента, `POST /api/sync` не имеет параметра `demo` и всегда работает с `real_database()` (`:131`), а `sync_intervals_data(client=…)` существует только на Python-уровне, — то есть настоящий end-to-end требует явной точки инъекции в продуктовом пути, а не одного флага. Выбор **подтверждён владельцем**; provider E2E на фейковом провайдере в этом плане не предусмотрен — он вводится только отдельным решением.
  Date/Author: 2026-09-12 / agent.
- Decision (D6): **UI-слайс — граница ролей**: план описывает требуемое поведение и контракт, но правки `web/components/sync/SyncControl.tsx` выполняет UI / Design Specialist (по `AGENTS.md`), а не автор этого плана. Если владелец назначает роль иначе, это фиксируется отдельной строкой в `Change log`.
  Rationale: `AGENTS.md` разделяет Spec/Architecture Owner, Domain/API Implementer и UI/Design Specialist; «заодно поправить рендер» внутри backend-слайса нарушило бы границу и сделало бы ревью слайса смешанным.
  Date/Author: 2026-09-12 / agent.
- Decision (M1): **правило пяти состояний живёт в `models/recovery_response.py`, а не в сервисе**: `capture_verdict(...)` — чистая функция рядом с `evaluate_snapshot_eligibility` и `daily_activity_cutoff`; сервис только оркестрирует (сохранение ревизии, чтение активностей, сборка блока).
  Rationale: вердикт — это правило (как eligibility и anchor), а модуль объявлен как «pure rules … no database, provider, FastAPI, or UI imports», поэтому он тестируется без БД и без провайдера; кроме того так исключается вторая реализация правила, за которую предыдущие раунды ревью справедливо снижали оценку (приоритет предикатов, граница дня).
  Date/Author: 2026-09-12 / agent (M1).
- Decision (M1): **граница дня считается по дате ревизии**: активности читаются `db.get_activities_between(local_date − 1 день, local_date)`, а не окном от «сейчас».
  Rationale: `capture_mode` допускает `backfilled`, и тогда окно от текущего момента даёт неверный вердикт; запас в один день покрывает границу тайм-зоны, не расширяя чтение на историю.
  Date/Author: 2026-09-12 / agent (M1).
- Decision (M2): **контракт раннера — обязательный `capture_run_id`** (F1): `SyncRunner` объявлен `Protocol` с обязательным keyword; вызывающие в `api/routers/system.py` и тестовые двойники обновлены в том же слайсе.
  Rationale: идентичность обязана рождаться один раз на job boundary и не теряться по пути; опциональный keyword позволил бы вызвать раннер без идентичности, и сервис молча сгенерировал бы собственный UUID — то есть дефект из review P2 вернулся бы. Формулировка плана «аддитивно» была неточной и исправлена (F1).
  Date/Author: 2026-09-13 / agent (M2 hardening).
- Decision (M2): **человеко-читаемая строка `details` намеренно сменила содержимое** (F2): было `Recovery snapshot: <eligibility_status> · rev N`, стало `Recovery snapshot: <capture_status> · rev N` — пятисоставный словарь M1 вместо булевой пригодности.
  Rationale: строка остаётся в `details` для совместимости (план этого требовал), но `eligibility_status` не сообщал, опоздал ли снимок; пятисоставный статус описывает решение целиком. Изменение внутреннее: публичный payload в M2 не менялся, строка попадает в `notices` только при `partial`. Пинится тестом `test_sync_garmin_uses_shared_capture_once_with_explicit_run_identity`.
  Date/Author: 2026-09-13 / agent (M2 hardening).
- Decision (M2): **причина отказа capture остаётся серверным следом, а не публичным текстом** (F3): все три ветки отказа логируют `logger.warning(<стабильный код>, exc_info=True)`, публичный блок и warning несут только код (`snapshot_capture_failed` / `activity_lookup_failed`).
  Rationale: до харденинга M1 сырой `str(exc)` уходил в warning синка (виден оператору), после — не сохранялся нигде, то есть диагностика была потеряна; возвращать текст в публичный контракт нельзя (утечка локальных путей и внутренних сообщений), поэтому traceback идёт в лог, а контракт остаётся стабильным.
  Date/Author: 2026-09-13 / agent (M2 hardening).
- Decision (D8): **plan-PR мержится отдельно и не переиспользуется под реализацию** (подтверждено владельцем, 2026-09-12): после принятия плана PR плана закрывается своим мержем, а M1–M6 идут **новой веткой от обновлённого `main`** и с собственным review budget.
  Rationale: смешивание плана и реализации в одной ветке сделало бы head одним объектом для двух разных бюджетов ревью и смазало бы evidence bundle: правки плана и правки кода имеют разные критерии приёмки. Побочный эффект: `docs/recovery_snapshot_capture_parity_execplan.md` живёт в main и обновляется уже веткой реализации.
  Date/Author: 2026-09-12 / agent (по решению владельца).
- Decision (D7): **расширять задачу за пределы issue нельзя**: без cron/фонового расписания, polling-надстроек, backfill исторических снимков, автокоррекции плана и provider writeback; правило pre-anchor не ослабляется, исторические `missing_pre_anchor` не переклассифицируются.
  Rationale: прямые non-goals issue #562 и указание владельца; любое из этих расширений меняет класс и стоимость ревью.
  Date/Author: 2026-09-12 / agent.

## Outcomes & Retrospective

Plan-only этап: см. `Progress` и `Surprises & Discoveries`. `Outcomes` заполняется по завершении M1–M6; на этом этапе единственный результат — план, готовый к ревью, и отсутствие изменений в коде/API/UI/схеме (проверяется `git diff --stat` по ветке плана).

## Context and Orientation

**Что такое capture.** «Post-sync capture» — производная запись (derived analytics), которая после синхронизации провайдера фиксирует текущее состояние готовности как prospective-снимок в журнале. Термины: *prospective* — снимок, снятый в день, к которому относится (в отличие от `backfilled`); *eligibility* — прохождение научного гейта (`evaluate_snapshot_eligibility`); *cutoff* — граница дня, после которой снимок уже не может быть pre-activity anchor'ом (минимальный старт активности дня, иначе локальный полдень); *pre-anchor* — снимок, существовавший до cutoff.

**Текущее состояние (факты на `9ba4a37`).**

- `services/recovery_analytics.py::record_post_sync_recovery_state(db, *, capture_run_id, observed_at_utc=None, capture_mode="prospective")` — строит канонический snapshot (`services/readiness_snapshot.py::build_readiness_snapshot`), считает eligibility, пишет через `db.save_readiness_snapshot`, затем обновляет эпизоды в собственном `try/except` и возвращает `{**saved, "eligibility": …, "episode_refresh": …}`.
- `data/database.py::save_readiness_snapshot` — атомарная идемпотентная вставка: `fingerprint = sha256({capture_run_id, capture_mode})`, `target_key = readiness:<capture_mode>:<local_date>`, монотонная `revision`, `supersedes_snapshot_id`; читатели — `get_readiness_snapshots(capture_mode=…, local_date=…)` и `get_readiness_snapshot_history(target_key)`.
- `services/sync.py::sync_garmin_data` — единственный production-вызов capture (`:411-424`): `capture_run_id=str(uuid.uuid4())`, fail-open `try/except`, человеко-читаемая строка в `result.details`, ошибка — в `result.warnings`. Payload (`build_sync_status_payload`) отдаёт `notices = (warnings + details)[:4]`.
- `services/intervals_sync.py::sync_intervals_data` — capture отсутствует; результат `IntervalsSyncResult` (new/updated/skipped/ingested/warnings/source/halted/…) без поля `details`; payload `build_intervals_sync_status_payload` повторяет форму Garmin-ответа.
- `api/sync_jobs.py::SyncJobManager` (`start_or_get:47`, `job_id = uuid4()[:8]:63`, `_run_job:99`) — process-local job'ы: `job_id = uuid4()[:8]`, single-flight по всем провайдерам, повторный запрос отдаёт running-job с `reused=True`; `_run_job` вызывает `run_sync(on_progress)` и публикует снимок.
- `api/routers/system.py` — `POST /api/sync` (`:127`) и `GET /api/sync` (`:119`), `_build_run_sync` выбирает раннер (`_run_garmin_sync`/`_run_intervals_sync`), оба затем идут через `_sync_payload_with_operational_state` и `_attach_shadow_forecast`.
- `models/recovery_response.py` — `evaluate_snapshot_eligibility:64` (причины выше) и `select_daily_anchor:98` (cutoff и причины); `build_episode_outcomes` сохраняет независимую пропущенность наблюдений.
- Веб: `web/components/sync/SyncControl.tsx` (одна строка статуса, `formatSyncJob`), `web/lib/types.ts` (`SyncResult`/`SyncJobResponse`), `/api/sync/providers` для списка источников; контрактный реестр `tests/contracts/registry.json` связывает `/api/sync` с `SyncJobResponse`.
- Тесты: `tests/smoke/test_sync_job_api.py` (job lifecycle), `tests/smoke/test_garmin_sync_service.py` (пайплайн синка), `tests/smoke/test_recovery_episode_materializer.py` (в т.ч. идемпотентность capture-рана), `tests/smoke/test_recovery_response.py`, `tests/smoke/test_api_recovery_analytics.py`, `tests/smoke/test_m3_sync_ui_contract.py` (статические UI-строки), `tests/e2e/` (Playwright-стенд).

## Plan of Work

**M1 — provider-neutral capture и run identity.** В `services/recovery_analytics.py`: (а) новый публичный вход `capture_post_sync_recovery_state(db, *, capture_run_id, provider, observed_at_utc=None, capture_mode="prospective") -> dict`, который вызывает существующий `record_post_sync_recovery_state` и обогащает результат структурным блоком `recovery_capture` (поля — в `Interfaces and Dependencies`); (б) вычисление пяти состояний и причины; (в) **`provider` становится дурабельным, а не только эфемерным**: обёртка передаёт его в существующий рекордер аддитивным keyword `capture_provider: str | None = None`, и рекордер кладёт его в уже существующий JSON провенансы (`input_provenance.capture_provider` внутри сохраняемого payload), поэтому провайдер восстанавливается из журнала без новой колонки и без миграции. `provider` **не** входит в `target_key` и `fingerprint`: идентичность capture-рана остаётся прежней, существующие записи не переинтерпретируются (review P2). RED: тесты пяти состояний на синтетических входах, инвариант «статус ⇔ anchor», провал capture → `capture_failed` без исключения наружу.

**M2 — Garmin без двойной записи.** В `services/sync.py::sync_garmin_data`: инлайн-блок заменяется вызовом общего контракта; `result` получает аддитивное поле `recovery_capture` (структурный блок), человеко-читаемая строка остаётся в `details` для совместимости; `GarminSyncResult` не теряет существующих полей; `capture_run_id` приходит аргументом, при `None` генерируется внутри. RED: «ровно одна запись на ран», «повтор рана не создаёт ревизию», «ошибка capture не меняет сохранённые данные и оставляет `sync_state="partial"` + warning, добавляя `capture_failed` в структурный блок».

**M3 — Intervals parity.** В `services/intervals_sync.py::sync_intervals_data`: тот же вызов в том же месте (после основных записей), тот же fail-open; `IntervalsSyncResult` получает аддитивное `recovery_capture`; в `intervals`-пути capture использует тот же контракт identity/eligibility/failure-isolation. RED: паритетный тест «оба провайдера дают одинаковый набор полей и одинаковые состояния».

**M4 — API↔web контракт.** Оба payload-билдера добавляют ключ `recovery_capture` (берётся из результата сервиса); `web/lib/types.ts` получает `RecoveryCapture` и аддитивное поле в `SyncResult`; `npm --prefix web run contract:extract` регенерирует `tests/contracts/ts_contract.json`; проверки `contract:extract -- --check`, `contract:inventory`, `tests/smoke/test_contract_extractor.py`, `tests/smoke/test_api_call_inventory.py`. RED: тест формы ответа `POST /api/sync` для обоих источников (drift-харнесс покрывает только GET — см. `Surprises`).

**M5 — UI readback (роль UI / Design Specialist, D6).** Точки монтирования: `web/app/dashboard/page.tsx:42` (компактно) и `:128` (подробно, пустое состояние) — отдельная страница не создаётся. `formatSyncJob` и рендер `SyncControl` показывают локальное время снимка, статус pre-activity и причину; строка не ломает существующие состояния (`running`/`failed`/`idle`), а `notices` остаются для `partial`. RED: расширение статических UI-контрактных проверок в `tests/smoke/test_m3_sync_ui_contract.py` (в `web/` нет JS-раннера и нет ни одного теста на вывод `formatSyncJob`, поэтому это единственная существующая форма гейта) + проверка появления новых строк для обоих источников и того, что утверждается видимый вариант строки (см. `Surprises` про `hidden sm:inline`).

**M6 — приёмка.** Browser contract/UX acceptance обоих путей (D5; это не provider E2E — сервисный и API-контур доказывается Python-тестами с инъекцией клиентов): каталога `tests/e2e/fixtures/` нет — фикстуры ответов создаются этим слайсом; существующий `test_main_user_journey` синк не трогает, а `PRIMARY_ACTIVITY_SOURCE`, `ACCEPTANCE_MODE`, `ACCEPTANCE_AUTO_DEMO`, `ACCEPTANCE_DISABLE_GARMIN` в web-стенд не подключены (они обслуживают Streamlit `run_acceptance.sh`), поэтому опираться на них нельзя. Далее: сквозные проверки идемпотентности/монотонности, fail-open, инварианта anchor, обновление `docs/architecture/asr_catalog.md` (**ASR-REL-3** — обрыв/частичная синхронизация не портит данные, **ASR-REL-2** — отсутствие данных даёт data gap, **ASR-MOD-2/3** — server-owned проекция и аддитивный контракт; ASR-REL-1 про reconciliation плана этот контур не затрагивает), evidence bundle в PR, запись метрик после мержа.

## Concrete Steps

Рабочая директория — изолированный worktree ветки плана; общий чекаут не трогается.

    # docs-проверки (этот этап)
    python -m pytest tests/smoke/test_dev_workflow_v2_docs.py -q     # ожидаем 6 passed
    python -m ruff check .                                           # ожидаем All checks passed!
    git diff --stat                                                  # ожидаем только два docs-файла

Дальнейшие этапы (по мере реализации, каждая команда — на своей ветке):

    python -m pytest -m "not live and not debug and not e2e" tests/ -q
    npm --prefix web run lint && npm --prefix web run build
    npm --prefix web run contract:extract -- --check
    python -m pytest -m e2e tests/e2e -q

## Validation and Acceptance

Приёмка формулируется поведением, по одной строке на acceptance criterion issue (полная матрица — в slice-spec):

1. Garmin sync (успешный/частичный) → ровно одна идемпотентная prospective-ревизия на capture-run; ошибка derived analytics не откатывает основной sync.
2. Intervals sync → тот же provider-neutral контракт с теми же identity/eligibility/failure-isolation.
3. Повтор того же рана → новая ревизия не создаётся; отдельная синхронизация в тот же день → новая монотонная дневная ревизия.
4. Снимок до первой активности → API и веб показывают локальное время и статус «снимок до нагрузки сохранён».
5. Активность началась раньше capture → снимок остаётся аудируемой записью, а API/веб явно сообщают, что он не может быть pre-activity anchor'ом, с машинно-читаемой причиной и без маскировки общим «Синхронизация завершена».
6. Нет provenance старта активности → fail-closed `activity_start_missing`, а не утверждение о подтверждённом pre-anchor.
7. Снимок не прошёл eligibility → «снимок сохранён, но не пригоден» + безопасная причина без приватных значений.
8. Terminal response отображается в `SyncControl` и для `garmin`, и для `intervals`.
9. Контракт: `web/lib/types.ts`, `tests/contracts/ts_contract.json` и API-инвентарь согласованы; `contract:extract -- --check` зелёный.
10. Существующие снимки и эпизоды остаются читаемыми, исторические строки не мутируются.

Browser contract/UX acceptance (D5): **параметризованные сценарии на все пять состояний** (`saved_before_load`, `saved_too_late`, `activity_start_missing`, `ineligible`, `capture_failed`) для обоих источников — иначе пропущенный или неверный UI-маппинг любого из трёх «плохих» состояний пройдёт все веб-гейты и пользователь увидит то самое общее «Синхронизация завершена», которое фича должна заменить (review P2). Перехватываются `/api/sync/providers` и job-эндпоинты, утверждается **видимый** вариант строки. Плюс тест-«пришпиливание» формы фикстуры к реальному payload'у, чтобы фикстура не разошлась с продакшеном. Статические проверки в `tests/smoke/test_m3_sync_ui_contract.py` остаются дополнением, а не заменой: они не исполняют `formatSyncJob`.

## Idempotence and Recovery

Повторный запуск тех же шагов безопасен: capture идемпотентен по `capture_run_id`; миграций нет, откат — `git revert` соответствующего коммита (журнал `readiness_snapshots` append-only, исторические строки не переписываются). Ошибка derived capture не оставляет частичного состояния: запись снимка атомарна (`BEGIN IMMEDIATE`), а обновление эпизодов уже изолировано собственным `try/except`. Если реализация выявит необходимость миграции или backfill — работа останавливается и класс пересматривается (эскалация по `docs/AI_Feature_Development_Workflow.md`).

## Artifacts and Notes

Plan-only этап: артефакты — этот файл и `docs/recovery_snapshot_capture_parity_slice_spec.md`. Прогоны и выводы будут дополнены в M1–M6 (RED-падения, GREEN-прогоны, браузерные снимки текста, evidence bundle).

### M1 — provider-neutral capture и run identity (2026-09-12)

Новый файл тестов `tests/smoke/test_recovery_capture_contract.py` (14 тестов). Исходный RED: `13 failed` — обёртки `capture_post_sync_recovery_state` не существовало; исходный GREEN: `13 passed`. Дополнительный safety-RED на checkpoint `6dbe415`: `2 failed`; GREEN: `14 passed`.

Покрыто: `saved_before_load` без активностей (граница — локальный полдень); `saved_too_late` при активности раньше наблюдения и при наблюдении после полудня; вердикт **по ревизии**, а не по дню (05:00 → before_load, 11:00 после активности 10:00 → too_late, дневной anchor остаётся у ранней ревизии); приоритет предикатов (`activity_start_missing` побеждает `ineligible`); `ineligible` с безопасной причиной `low_confidence`; пустая база → `ineligible`/`missing_score` вместо падения; провал записи snapshot → `capture_failed/snapshot_capture_failed` без исключения и сырого текста наружу; провал чтения временной границы после записи → `capture_failed/activity_lookup_failed` с сохранёнными `snapshot_id`/`revision`; провайдер в `provenance` журнальной строки и в `snapshot.input_provenance`; идемпотентность рана (тот же id → `created: false`, одна ревизия; новый id → `revision 2`); локальное время атлета в блоке; явное окно активностей как параметр.

Совместимость: `record_post_sync_recovery_state(..., capture_provider: str | None = None)` — аддитивно, без аргумента поведение прежнее; `select_daily_anchor` переведён на общий `daily_activity_cutoff` без изменения возвращаемого словаря (focused-контур `180 passed`).

### M2 — Garmin handoff без двойной записи (2026-09-13)

RED-checkpoint `22fda6b`: `4 failed` — `sync_garmin_data` не принимал `capture_run_id`, общий wrapper не вызывался, direct-вызов не генерировал ID для общего контракта, job runner не передавал полный UUID. GREEN: `GarminSyncResult.recovery_capture` добавлен внутренне; старый inline recorder заменён ровно одним вызовом `capture_post_sync_recovery_state(provider="garmin")`; API job генерирует полный UUID отдельно от короткого `job_id` и прокидывает его через единый runner; Intervals runner уже принимает keyword, но до M3 его не использует.

D4 сохранён: `capture_failed` добавляет безопасный warning и итоговый status payload остаётся `sync_state="partial"`; сохранённая Garmin-активность не откатывается. Совместимость тестовых runner doubles закрыта в том же слайсе. Focused Garmin/job/audit-контур: `34 passed`; расширенный recovery/sync-контур: `119 passed`; contributor-safe: `2488 passed, 28 skipped, 26 deselected`, 0 failed; `ruff check .` чисто. Skips — существующее отсутствие `web/node_modules`, local-listening socket, `garth` и локальных диагностических данных; публичный web-контракт в M2 не менялся.

### M2 hardening — F1–F3 (2026-09-13)

Короткий слайс по итогам независимой проверки M2.

- **F1 (только документация).** Формулировка «контракт раннера расширяется аддитивно» заменена на фактическую: `SyncRunner` — `Protocol` с обязательным keyword `capture_run_id`, вызывающие и двойники обновлены в M2; зафиксировано решение M2 с обоснованием, почему обязательность предпочтительнее опциональности (иначе идентичность может не дотянуться до сервиса, и дефект 32-битного `job_id` вернётся).
- **F2.** Смена содержимого строки `details` (`eligibility_status` → пятисоставный `capture_status`) записана как намеренное внутреннее изменение M2 с обоснованием и ссылкой на пинящий тест.
- **F3.** Серверное логирование: `logger.warning(<стабильный код>, exc_info=True)` добавлено в три ветки — отказ рекордера и отказ чтения границы дня в `services/recovery_analytics.py`, плюс защитная ветка в `services/sync.py` (там код-литерал осознан: ветка достижима даже при неудачном импорте обёртки). Публичный блок и warning несут только стабильные коды; сырой текст исключения остаётся в логе.

RED (F3): `3 failed` — два теста в `tests/smoke/test_recovery_capture_contract.py` (записи лога нет) и один в `tests/smoke/test_garmin_sync_service.py` (`0 == 1` записей). GREEN: focused-набор M1+M2+F3 — `51 passed`; заметки: ровно одна запись на один сбой, `exc_info` присутствует, `athlete.db` отсутствует и в сообщении лога, и в публичном блоке, и в `notices`.

## Interfaces and Dependencies

Ожидаемые к концу M1–M4 стабильные имена:

    # services/recovery_analytics.py
    def capture_post_sync_recovery_state(
        db: Database,
        *,
        capture_run_id: str,                 # полный UUID (не усечённый job_id)
        provider: str,                       # "garmin" | "intervals"
        observed_at_utc: datetime | None = None,
        capture_mode: str = "prospective",
    ) -> dict[str, Any]:
        """Возвращает {**saved, "recovery_capture": {...}, "eligibility": {...}, "episode_refresh": {...}}."""

    # api/sync_jobs.py — контракт раннера изменён (F1): обязательный keyword,
    # опциональность скрыла бы непротянутую идентичность
    class SyncRunner(Protocol):
        def __call__(self, on_progress: Callable[[SyncProgressUpdate], None], *,
                     capture_run_id: str) -> dict[str, Any]: ...

    # services/recovery_analytics.py — аддитивный keyword существующего рекордера
    def record_post_sync_recovery_state(..., capture_provider: str | None = None) -> dict[str, Any]: ...
    # записывает provider в input_provenance сохраняемого payload (schema не меняется)

    # services/sync.py / services/intervals_sync.py
    def sync_garmin_data(state, days=None, on_progress=None, *, capture_run_id: str | None = None) -> GarminSyncResult: ...
    def sync_intervals_data(database, *, days=None, now=None, on_progress=None, client=None,
                            chunk_days=CHUNK_DAYS, capture_run_id: str | None = None) -> IntervalsSyncResult: ...

    # Dataclass-поля (аддитивные)
    GarminSyncResult.recovery_capture: dict[str, Any] | None
    IntervalsSyncResult.recovery_capture: dict[str, Any] | None

    # web/lib/types.ts
    export interface RecoveryCapture {
      provider: "garmin" | "intervals" | string;
      status: "saved_before_load" | "saved_too_late" | "activity_start_missing" | "ineligible" | "capture_failed" | string;
      reason: string | null;               // машинно-читаемая причина
      eligibility_status: "eligible" | "ineligible" | string;
      eligibility_reasons: string[];
      local_date: string;
      observed_at_utc: string;
      observed_at_local: string;           // локальное время атлета для UI
      cutoff_at_utc: string | null;
      capture_run_id: string;              // ПОЛНЫЙ UUID — единственная идентичность рана
      job_id: string;                      // короткий display handle job'а; в идентичность не входит
      snapshot_id: number | null;
      revision: number | null;
      created: boolean;                    // идемпотентность: false = повтор рана
      error: string | null;                // только для capture_failed
    }
    export interface SyncResult { /* … существующие поля … */ recovery_capture?: RecoveryCapture | null; }

Зависимости: `services/readiness_snapshot.py` (канонический snapshot), `models/recovery_response.py` (eligibility/cutoff/причины), `data/database.py` (журнал снимков), `api/sync_jobs.py` (job id), `services/sync_contracts.py` (общий контракт прогресса), `web/lib/types.ts` + `tests/contracts/*` (контракт), `tests/e2e/` (browser-приёмка).

## Risks and Mitigations

- **Роль UI (D6)**: правки `SyncControl.tsx` вне роли backend-исполнителя → слайс M5 передаётся UI / Design Specialist, backend отдаёт только контракт и тест формы; при отсутствии UI-исполнителя слайс остаётся незакрытым и это видно в `Progress`.
- **Browser contract/UX acceptance (D5)**: e2e-стенд не умеет запускать синк (креды погашены) → перехват маршрутов + тест «фикстура ↔ форма ответа» (подтверждено владельцем). Риск остаточный: приёмка проверяет рендер и форму контракта, а не работу провайдера — за это отвечают Python-тесты с инъекцией клиентов, и эту границу надо называть вслух, чтобы не выдать UX-гейт за provider E2E.
- **Двойная запись**: перенос capture из `sync_garmin_data` в общий контракт может случайно оставить старый вызов → тест «на один sync ровно одна ревизия» и проверка отсутствия второго вызова.
- **Расхождение статуса и anchor'а**: две разные реализации одного правила → инвариантный тест «статус ⇔ `select_daily_anchor`» на одной и той же фикстуре дня.
- **Форма ответа POST не покрыта drift-харнессом** (см. `Surprises`) → явный тест формы ответа для обоих источников плюс регенерация артефакта.
- **Совместимость `notices`**: строка может «выдавить» полезные notices (лимит 4 на сервере, 2 в UI) → структурный блок не должен вытеснять существующие строки; проверяется тестом.
- **Расширение вызова раннера**: `_run_job` начнёт вызывать `run_sync(on_progress, capture_run_id=…)`, поэтому тестовые двойники раннера (в `tests/smoke/test_sync_job_api.py` и смежных) обязаны принимать keyword — иначе существующие тесты упадут на неожиданном аргументе. Митигация: передавать id позиционно-совместимым способом либо явно обновить двойники в том же слайсе, где меняется контракт, и покрыть это тестом реюза running-job.
- **Статус синка при сбое capture (D4)** — решением владельца сохранены `sync_state="partial"` и warning: наблюдаемое поведение по статусу не меняется, новым элементом остаётся только структурный блок с причиной.

## Non-goals

- cron/фоновое расписание, polling-надстройки, backfill исторических снимков;
- **персистенция исходов capture** (включая `capture_failed`) и переживание рестарта API: терминальный readback остаётся эфемерным, как и весь снимок job'а; дурабельна только запись снимка с её провенансой — расширение требует нового состояния и решения владельца;
- автоматическая коррекция плана и provider writeback;
- ослабление правила pre-anchor и переклассификация исторических `missing_pre_anchor`;
- изменение формулы readiness, порогов confidence, D+1/D+2/D+3, maturity gates и обучение `k_*`/`tau_*`;
- изменение схемы БД и миграции (состояние capture выводится, а не хранится);
- новый публичный эндпоинт: readback идёт через существующий terminal response синхронизации;
- расширение `web/app/recovery/` без доказанной необходимости (по issue — только если понадобится уже существующий статус дневного capture);
- публикация личных дат, health-метрик, названий тренировок и provider payload.

## Change log

- v1 (2026-09-12): plan-only этап по issue #562. Зафиксированы: provider-neutral владение capture, run identity из sync-job, пять вычисляемых состояний с инвариантом к `select_daily_anchor`, fail-open граница, аддитивный API↔web контракт `recovery_capture`, UI readback как отдельный ролевой слайс, RED→GREEN матрица на 10 acceptance criteria, подход к browser-приёмке обоих провайдеров, non-goals. Код, API, UI и схема не менялись; решения D4 и D5 вынесены на подтверждение владельцу.
- v1.1 (2026-09-12): уточнены факты о покрытии контракта (реестр покрывает GET-статус `/api/sync`, POST и `result` в demo-сценарии — нет; JS-тест-раннера в `web/` нет) и номера строк в ссылках на `api/sync_jobs.py` и `models/recovery_response.py`. Проверено чтением `registry.json`, `test_web_contract_drift.py`, `web/package.json`.
- v1.2 (2026-09-12): внесены уточнения из завершившейся read-only разведки web/e2e: точки монтирования `SyncControl` и варианты рендера (видимость строки), отсутствие JS-раннера и формы UI-гейта, отсутствие `tests/e2e/fixtures/`, неподключённость `PRIMARY_ACTIVITY_SOURCE`/`ACCEPTANCE_*` к web-стенду, и конкретная цена отвергнутой альтернативы в D5 (нет override клиента в API-раннерах, нет `demo` у `POST /api/sync`). Код не менялся.
- v1.3 (2026-09-12): правки по раунду независимого ревью плана (6 находок: 1 P1 + 5 P2). Состояние capture привязано к конкретной ревизии, а не ко дню (P1); идентичность рана — полный UUID вместо усечённого `job_id` (32-битное пространство и глобальный дедуп по `capture_run_id`); терминальный readback объявлен эфемерным, а персистенция исходов вынесена в non-goals; провайдер стал дурабельным через `input_provenance` без миграции; ASR-маппинг исправлен на REL-3/REL-2/MOD-2/3 вместо REL-1; браузерная приёмка расширена до всех пяти состояний. Код не менялся.
- v1.4 (2026-09-12): по решению владельца D4 переформулирован (сбой capture сохраняет `sync_state="partial"` и warning; предложение понижать его отклонено), D5 подтверждён и переименован в browser contract/UX acceptance (не provider E2E), добавлено D8 (plan-PR мержится отдельно и не переиспользуется под реализацию; M1–M6 — новая ветка от обновлённого `main` со своим бюджетом). Код не менялся.
- v1.5 (2026-09-12): правки по раунду 2 (**9 находок: 8 P2 + 1 P3**). Задан явный приоритет предикатов статуса (`capture_failed` → `activity_start_missing` → `ineligible` → before/too_late), снят двойной идентификатор `capture_run_id_full` из TS-контракта (единственная идентичность — полный `capture_run_id`, короткий `job_id` только display), закрыт D5 без условных формулировок, зафиксированы неизменяемые reviewed SHA (`4ae3f4b`, `20f9dcb`), ревизия плана синхронизирована с change log. В slice-spec: несогласованность D2 устранена, `capture_provider` помечен как аддитивное persistent state, исправлен путь `tests/contracts/conformance.py`, M6 расщеплён по ролям (M6a/M6b/M6c). Код не менялся.
- v1.6 (2026-09-12): M1 реализации закрыт. Правило пяти состояний вынесено в `models/recovery_response.py::capture_verdict`, общая граница дня — `daily_activity_cutoff` (используется и `select_daily_anchor`), сервис получил `capture_post_sync_recovery_state`, рекордер — аддитивный `capture_provider` с дурабельной записью в провенанс. RED `13 failed` → GREEN `13 passed`, focused-контур `180 passed`. Две находки: активности читаются по дате ревизии (иначе backfilled-захват получает неверный вердикт) и активность добавляет фактор TSB, меняя eligibility снимка.
- v1.7 (2026-09-12): safety hardening M1. RED-checkpoint `6dbe415` доказал два fail-closed дефекта: ошибка чтения активностей маскировалась обычным статусом, а сырой `str(exc)` попадал в будущий публичный блок. GREEN возвращает стабильные коды `activity_lookup_failed`/`snapshot_capture_failed`, сохраняет идентичность уже записанной ревизии и не раскрывает внутренний текст; focused `14 passed`, Ruff чисто.
- v1.8 (2026-09-13): M2 закрыл Garmin handoff и фактическую job identity. RED `4 failed` на `22fda6b`; GREEN заменяет legacy inline recorder общим wrapper, сохраняет ровно один capture, прокидывает полный UUID от `SyncJobManager`, генерирует его для direct/demo вызовов и сохраняет D4 (`partial` + безопасный warning при `capture_failed`). Focused `34 passed`, расширенный recovery/sync `119 passed`, contributor-safe `2488 passed, 28 skipped, 26 deselected`, 0 failed; Ruff чисто; публичный API payload ещё не менялся (M4).
- v1.9 (2026-09-13): hardening-слайс F1–F3. F1 — документация приведена к факту: контракт раннера не аддитивен, а изменён (Protocol с обязательным `capture_run_id`), решение M2 записано с обоснованием. F2 — смена содержимого строки `details` на пятисоставный статус зафиксирована как намеренная. F3 — серверное логирование с `exc_info=True` во всех трёх ветках отказа; публичный блок и warning несут только стабильные коды. RED `3 failed` → GREEN `51 passed` в focused-наборе.
