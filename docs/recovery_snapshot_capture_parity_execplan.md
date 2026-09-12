# Паритет post-sync capture readiness-снимка для Garmin и Intervals (issue #562)

Этот ExecPlan — живой документ, который ведётся по правилам `.agent/PLANS.md` (корень репозитория): разделы `Progress`, `Surprises & Discoveries`, `Decision Log`, `Outcomes & Retrospective` обязаны поддерживаться в актуальном состоянии, а каждая правка плана фиксируется в `Change log` в конце документа. Документ самодостаточен: читатель, у которого есть только это дерево и этот файл, должен суметь выполнить работу целиком.

Issue: [#562](https://github.com/rbctmz/ai_trainer/issues/562). Change Class: **A — Full**. Базовая точка: `main` = `9ba4a37` (в main уже влиты #552 — revisioned evidence head и lifecycle, #557/#563 — freshness/provenance readiness и fail-closed intervention, #564/#565 — интервенционное evidence и guard отката `training_readiness`).

Ревизия документа: v1 (plan-only). Код, API, UI и схема на этом этапе **не менялись**: артефакт этапа — этот план и Class A slice-spec `docs/recovery_snapshot_capture_parity_slice_spec.md`, которые выносятся на ревью владельцу.

## Purpose / Big Picture

Сегодня post-sync derived capture есть только в Garmin-пути: `services/sync.py` после сохранения wellness-данных вызывает `record_post_sync_recovery_state(...)`. Intervals-путь (`services/intervals_sync.py::sync_intervals_data`) такого вызова не содержит, поэтому спортсмен, который синхронизируется только через Intervals.icu, систематически остаётся без prospective readiness-снимка, а его день позже исключается из recovery-эпизодов как `missing_pre_anchor`. При этом даже в Garmin-пути результат capture невидим: единственная строка `Recovery snapshot: …` уезжает в `notices`, а веб показывает notices только при `sync_state == "partial"` и не более двух.

После изменения при **каждой** успешной или частично успешной синхронизации — Garmin или Intervals.icu — сохраняется ровно один явно подтверждённый prospective-снимок с локальным временем, пригодностью и машинно-читаемой причиной, а UI сразу сообщает, успел ли снимок зафиксировать состояние **до первой активности дня**. Человек видит одно из пяти честных состояний: снимок сохранён до нагрузки, сохранён слишком поздно, старт активности неизвестен (`activity_start_missing`), снимок непригоден, capture завершился ошибкой — вместо общего «Синхронизация завершена». Ошибка derived capture не откатывает основной sync: данные провайдера остаются валидными, а сбой виден отдельным полем.

Проверить это можно так: запустить синхронизацию из UI для каждого источника и увидеть в строке синка локальное время снимка, статус pre-activity и причину; повторный запуск того же job не создаёт новую ревизию, а новая синхронизация в тот же день создаёт монотонную дневную ревизию.

## Progress

- [x] (2026-09-12) Plan-only этап: создан этот ExecPlan и Class A slice-spec, зафиксированы решения, RED→GREEN матрица и контур milestones. Код/API/UI/схема не менялись.
- [ ] M1. Provider-neutral capture-контракт и run identity (`services/recovery_analytics.py`): структурированный результат + пять состояний + явный `provider`; RED→GREEN.
- [ ] M2. Garmin-путь использует общий контракт без двойной записи (`services/sync.py`).
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
- Decision (D2): **идентичность capture-рана приходит из sync-job'а**: `api/sync_jobs.py::SyncJobManager.start_or_get` создаёт `job_id` на job и переиспользует его при повторном запросе (`reused=True`), этот id прокидывается в оба sync-сервиса аддитивным keyword-аргументом `capture_run_id: str | None = None`; при `None` сервис генерирует id сам (обратная совместимость для прямых вызовов, demo и тестов).
  Rationale: AC3 требует «повтор того же capture run не создаёт ревизию, отдельная синхронизация в тот же день создаёт новую монотонную ревизию». Это уже обеспечено хранением (`fingerprint` + `revision`), но только если идентичность рана стабильна. `uuid4()` внутри `sync_garmin_data` делает повтор job'а новым раном; job id делает его идемпотентным и остаётся человеко-читаемым в аудите.
  Date/Author: 2026-09-12 / agent.
- Decision (D3): **пять состояний capture вычисляются, а не хранятся**: `saved_before_load`, `saved_too_late`, `activity_start_missing`, `ineligible`, `capture_failed` — проекция уже существующих примитивов (eligibility + старты активностей дня + cutoff из `select_daily_anchor`), без новой колонки и без миграции.
  Rationale: состояние выводимо из журнала `readiness_snapshots` и активностей в любой момент; персистенция дублировала бы выводимое состояние и потребовала бы миграции (автоматический триггер более тяжёлого класса). Инвариант: `saved_before_load` ⇔ для этого дня `select_daily_anchor` находит кандидата; остальные четыре состояния ⇔ кандидата нет, и причина совпадает с причиной anchor'а.
  Date/Author: 2026-09-12 / agent.
- Decision (D4): **fail-open граница**: ошибка derived capture не откатывает данные провайдера и не превращает успешную синхронизацию в «сломанную» — она отражается как `recovery_capture.status = "capture_failed"` с машинно-читаемой причиной.
  Rationale: AC1/AC10 требуют сохранности основного sync; сегодняшнее поведение Garmin (`result.warnings.append(...)`) сохраняет данные, но из-за `build_sync_status_payload` переводит весь ответ в `sync_state="partial"`, то есть сообщает о проблеме с данными провайдера там, где её нет. План сохраняет человеко-читаемую строку в `notices` для совместимости, но статус синка отражает именно данные провайдера, а сбой capture виден в структурном блоке. **Это осознанное изменение наблюдаемого поведения — прошу владельца подтвердить его на ревью плана** (альтернатива: оставить `partial`, тогда AC5-подобная честность теряется, а пользователь видит «частичную синхронизацию» без причины).
  Date/Author: 2026-09-12 / agent.
- Decision (D5): **синтетическая browser-приёмка обоих путей** — Playwright перехватывает `/api/sync/providers`, `POST /api/sync` и `GET /api/sync` фикстурами обоих провайдеров (оба источника «настроены», снимок «сохранён»), а корректность самих данных доказывается Python-тестами с инъекцией клиентов; форму фикстуры пришпиливает отдельный тест, сравнивающий её ключи с реальным payload'ом. Отвергнутая альтернатива — тест-переключатель «фейковый провайдер» в `api/routers/system.py`/сервисах: даёт настоящий end-to-end, но добавляет тест-онли ветку в продуктовый путь.
  Rationale: в e2e-стенде креды провайдеров погашены, а кнопка синка отключена (см. `Surprises`), поэтому «как есть» приёмка невозможна; перехват маршрутов не требует ни продуктового кода ради тестов, ни изменения стенда, и остаётся честным при связке «фикстура ↔ форма ответа» тестом. Цена отвергнутой альтернативы уточнена разведкой: API-раннеры `_run_garmin_sync`/`_run_intervals_sync` (`api/routers/system.py:150-206`) не принимают override клиента, `POST /api/sync` не имеет параметра `demo` и всегда работает с `real_database()` (`:131`), а `sync_intervals_data(client=…)` существует только на Python-уровне, — то есть настоящий end-to-end требует явной точки инъекции в продуктовом пути, а не одного флага. **Прошу владельца подтвердить выбор на ревью плана** (если нужен настоящий end-to-end на фейковом провайдере, это отдельное решение и отдельный слайс в M6).
  Date/Author: 2026-09-12 / agent.
- Decision (D6): **UI-слайс — граница ролей**: план описывает требуемое поведение и контракт, но правки `web/components/sync/SyncControl.tsx` выполняет UI / Design Specialist (по `AGENTS.md`), а не автор этого плана. Если владелец назначает роль иначе, это фиксируется отдельной строкой в `Change log`.
  Rationale: `AGENTS.md` разделяет Spec/Architecture Owner, Domain/API Implementer и UI/Design Specialist; «заодно поправить рендер» внутри backend-слайса нарушило бы границу и сделало бы ревью слайса смешанным.
  Date/Author: 2026-09-12 / agent.
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

**M1 — provider-neutral capture и run identity.** В `services/recovery_analytics.py`: (а) новый публичный вход `capture_post_sync_recovery_state(db, *, capture_run_id, provider, observed_at_utc=None, capture_mode="prospective") -> dict`, который вызывает существующий `record_post_sync_recovery_state` и обогащает результат структурным блоком `recovery_capture` (поля — в `Interfaces and Dependencies`); (б) вычисление пяти состояний и причины; (в) `provider` попадает в аудит (`provider` не меняет `target_key` и `fingerprint`, чтобы не сломать существующие записи). RED: тесты пяти состояний на синтетических входах, инвариант «статус ⇔ anchor», провал capture → `capture_failed` без исключения наружу.

**M2 — Garmin без двойной записи.** В `services/sync.py::sync_garmin_data`: инлайн-блок заменяется вызовом общего контракта; `result` получает аддитивное поле `recovery_capture` (структурный блок), человеко-читаемая строка остаётся в `details` для совместимости; `GarminSyncResult` не теряет существующих полей; `capture_run_id` приходит аргументом, при `None` генерируется внутри. RED: «ровно одна запись на ран», «повтор рана не создаёт ревизию», «ошибка capture не меняет данные и статус провайдерского sync».

**M3 — Intervals parity.** В `services/intervals_sync.py::sync_intervals_data`: тот же вызов в том же месте (после основных записей), тот же fail-open; `IntervalsSyncResult` получает аддитивное `recovery_capture`; в `intervals`-пути capture использует тот же контракт identity/eligibility/failure-isolation. RED: паритетный тест «оба провайдера дают одинаковый набор полей и одинаковые состояния».

**M4 — API↔web контракт.** Оба payload-билдера добавляют ключ `recovery_capture` (берётся из результата сервиса); `web/lib/types.ts` получает `RecoveryCapture` и аддитивное поле в `SyncResult`; `npm --prefix web run contract:extract` регенерирует `tests/contracts/ts_contract.json`; проверки `contract:extract -- --check`, `contract:inventory`, `tests/smoke/test_contract_extractor.py`, `tests/smoke/test_api_call_inventory.py`. RED: тест формы ответа `POST /api/sync` для обоих источников (drift-харнесс покрывает только GET — см. `Surprises`).

**M5 — UI readback (роль UI / Design Specialist, D6).** Точки монтирования: `web/app/dashboard/page.tsx:42` (компактно) и `:128` (подробно, пустое состояние) — отдельная страница не создаётся. `formatSyncJob` и рендер `SyncControl` показывают локальное время снимка, статус pre-activity и причину; строка не ломает существующие состояния (`running`/`failed`/`idle`), а `notices` остаются для `partial`. RED: расширение статических UI-контрактных проверок в `tests/smoke/test_m3_sync_ui_contract.py` (в `web/` нет JS-раннера и нет ни одного теста на вывод `formatSyncJob`, поэтому это единственная существующая форма гейта) + проверка появления новых строк для обоих источников и того, что утверждается видимый вариант строки (см. `Surprises` про `hidden sm:inline`).

**M6 — приёмка.** Синтетическая browser-приёмка обоих путей (D5): каталога `tests/e2e/fixtures/` нет — фикстуры ответов создаются этим слайсом; существующий `test_main_user_journey` синк не трогает, а `PRIMARY_ACTIVITY_SOURCE`, `ACCEPTANCE_MODE`, `ACCEPTANCE_AUTO_DEMO`, `ACCEPTANCE_DISABLE_GARMIN` в web-стенд не подключены (они обслуживают Streamlit `run_acceptance.sh`), поэтому опираться на них нельзя. Далее: сквозные проверки идемпотентности/монотонности, fail-open, инварианта anchor, обновление `docs/architecture/asr_catalog.md` (ASR-REL-1/REL-2, ASR-MOD-2/3), evidence bundle в PR, запись метрик после мержа.

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

Браузерная приёмка (D5): два сценария (оба источника) в Playwright-стенде, где перехвачены `/api/sync/providers` и job-эндпоинты; проверяется отрендеренный текст для состояний «до нагрузки» и «слишком поздно». Плюс тест-«пришпиливание» формы фикстуры к реальному payload'у, чтобы фикстура не разошлась с продакшеном.

## Idempotence and Recovery

Повторный запуск тех же шагов безопасен: capture идемпотентен по `capture_run_id`; миграций нет, откат — `git revert` соответствующего коммита (журнал `readiness_snapshots` append-only, исторические строки не переписываются). Ошибка derived capture не оставляет частичного состояния: запись снимка атомарна (`BEGIN IMMEDIATE`), а обновление эпизодов уже изолировано собственным `try/except`. Если реализация выявит необходимость миграции или backfill — работа останавливается и класс пересматривается (эскалация по `docs/AI_Feature_Development_Workflow.md`).

## Artifacts and Notes

Plan-only этап: артефакты — этот файл и `docs/recovery_snapshot_capture_parity_slice_spec.md`. Прогоны и выводы будут дополнены в M1–M6 (RED-падения, GREEN-прогоны, браузерные снимки текста, evidence bundle).

## Interfaces and Dependencies

Ожидаемые к концу M1–M4 стабильные имена:

    # services/recovery_analytics.py
    def capture_post_sync_recovery_state(
        db: Database,
        *,
        capture_run_id: str,
        provider: str,                       # "garmin" | "intervals"
        observed_at_utc: datetime | None = None,
        capture_mode: str = "prospective",
    ) -> dict[str, Any]:
        """Возвращает {**saved, "recovery_capture": {...}, "eligibility": {...}, "episode_refresh": {...}}."""

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
      capture_run_id: string;
      snapshot_id: number | null;
      revision: number | null;
      created: boolean;                    // идемпотентность: false = повтор рана
      error: string | null;                // только для capture_failed
    }
    export interface SyncResult { /* … существующие поля … */ recovery_capture?: RecoveryCapture | null; }

Зависимости: `services/readiness_snapshot.py` (канонический snapshot), `models/recovery_response.py` (eligibility/cutoff/причины), `data/database.py` (журнал снимков), `api/sync_jobs.py` (job id), `services/sync_contracts.py` (общий контракт прогресса), `web/lib/types.ts` + `tests/contracts/*` (контракт), `tests/e2e/` (browser-приёмка).

## Risks and Mitigations

- **Роль UI (D6)**: правки `SyncControl.tsx` вне роли backend-исполнителя → слайс M5 передаётся UI / Design Specialist, backend отдаёт только контракт и тест формы; при отсутствии UI-исполнителя слайс остаётся незакрытым и это видно в `Progress`.
- **Браузерная приёмка (D5)**: e2e-стенд не умеет запускать синк (креды погашены) → перехват маршрутов + тест «фикстура ↔ форма ответа»; если владелец выберет настоящий end-to-end на фейковом провайдере, это отдельный слайс и отдельное решение.
- **Двойная запись**: перенос capture из `sync_garmin_data` в общий контракт может случайно оставить старый вызов → тест «на один sync ровно одна ревизия» и проверка отсутствия второго вызова.
- **Расхождение статуса и anchor'а**: две разные реализации одного правила → инвариантный тест «статус ⇔ `select_daily_anchor`» на одной и той же фикстуре дня.
- **Форма ответа POST не покрыта drift-харнессом** (см. `Surprises`) → явный тест формы ответа для обоих источников плюс регенерация артефакта.
- **Совместимость `notices`**: строка может «выдавить» полезные notices (лимит 4 на сервере, 2 в UI) → структурный блок не должен вытеснять существующие строки; проверяется тестом.
- **Изменение статуса синка при сбое capture (D4)** — единственное наблюдаемое изменение поведения в этом контуре; вынесено на подтверждение владельцу.

## Non-goals

- cron/фоновое расписание, polling-надстройки, backfill исторических снимков;
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
