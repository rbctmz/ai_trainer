# Свежесть входов readiness: eligibility факторов, provenance измерений и fail-closed intervention (issue #557)

Этот ExecPlan — живой документ, который ведётся по правилам `.agent/PLANS.md` (корень репозитория). Разделы `Progress`, `Surprises & Discoveries`, `Decision Log`, `Outcomes & Retrospective` обязаны поддерживаться в актуальном состоянии, а каждая правка плана фиксируется в `Change log` в конце документа. Документ самодостаточен: читатель, у которого есть только это дерево и этот файл, должен суметь выполнить работу целиком.

Issue: [#557](https://github.com/rbctmz/ai_trainer/issues/557). Change Class: A — Full. Базовая точка: `main` = `72f69b4` (в main уже влиты #552 — revisioned evidence head и lifecycle суперсессии, и #555/#556 — датированный subjective wellness).

Ревизия документа: v3.6 (M1, M2 и срез 3.1 приняты; идёт срез 3.2 — provenance RHR, см. `Change log`).

## Purpose / Big Picture

Сегодня утренний экран и recovery-луп могут собрать «сегодняшний» низкий readiness из вчерашних HRV/sleep, из RHR, у которого сохранена дата запроса вместо даты измерения, и из текущего TSB. Самая новая дата среди факторов делает агрегат `stale=false`, presence-based confidence превышает порог `0.5`, и salience-gate создаёт actionable предложение снизить нагрузку — то есть система уверенно вмешивается в план, не имея ни одного подтверждённо сегодняшнего ночного измерения. Это нарушает ASR-REL-2 («отсутствие данных → data gap, не падение»).

После этого изменения человек утром видит одно из двух честных состояний. Либо у него есть подтверждённо сегодняшние recovery-измерения, и тогда готовность и конфликты считаются как раньше. Либо таких измерений нет, и тогда `/today` явно показывает `data_gap`/provisional-состояние с датой каждого фактора, recovery-луп молчит, новых actionable Recovery Replan не появляется, а принять решение по плану вручную по-прежнему можно. Проверить это можно, открыв `/today` на изолированной temp-SQLite базе без сегодняшних ночных строк: вместо «полного набора» и предложения снизить нагрузку экран покажет причину отсутствия данных и даты факторов, а `GET /api/today` вернёт пустые `conflicts` и ноль созданных чекпойнтов.

## Progress

- [x] (2026-09-10) Создан этот ExecPlan для ревью; реализация не начата.
- [x] (2026-09-10) Ревизия v2: закрыты три блокирующих разрыва delta-review (AC6-механизм, аддитивность legacy-полей, provenance `training_readiness`) и три дополнительных замечания; см. `Change log`.
- [x] (2026-09-10) Ревизия v3: версия правила доведена до approval API, у helper'а задана явная семантика источника и нейтральный модуль, head-колонка `rule_version` убрана как неиспользуемая, исправлен владелец `_proposal_payload`, escape hatch согласован с контрактом guard; см. `Change log`.
- [x] M1. `models/readiness.py`: per-factor `age_days`/`observation_status`/`intervention_eligible`/`evidence_kind`, аддитивные агрегаты `intervention_score`/`intervention_confidence`; legacy `score`/`confidence`/`stale` заморожены (RED→GREEN в `tests/smoke/test_readiness_model.py`). Выполнено 2026-09-10: RED `6238ba2`, GREEN; после ревью исправлены future-observation и разделение legacy/provenance-каналов (RED `99d4b82`), итог — `21 passed`, дифференциальный паритет с `origin/main` на 7 фикстурах; детали и цифры — `Artifacts and Notes`.
- [x] (2026-09-10) Ревизия v3.1: исправления по ревью M1 (future observation → `invalid`; legacy-выборка снова по дате хранения, provenance отдельным каналом; дедупликация baseline отложена на M3+); см. `Change log`.
- [x] M2. `services/readiness_snapshot.py`: аддитивный контракт `freshness` (пять корзин, включая `invalid`)/`intervention_score`/`intervention_confidence` без изменения legacy-полей (RED→GREEN в `tests/smoke/test_readiness_snapshot_contract.py`). Выполнено 2026-09-10: RED — 4 падения `KeyError: 'freshness'`; GREEN — `49 passed` в контуре снапшота и `test_recovery_response`; `READINESS_SNAPSHOT_RULE_VERSION` → `readiness_snapshot_v3` (литерал в `test_recovery_response.py` заменён на константу).
- [~] M3. Provenance измерений (идёт). Срез 3.1 — **provenance сна** выполнен 2026-09-10 и переработан после ревью: метрико-скоупные колонки `sleep_score_observed_at` / `total_sleep_observed_at`, запись только вместе с принятой метрикой (P1), назначение даты **после derivation** derived score (P2), путь Intervals.icu (`id` → observation date) и collision-тесты; legacy parity повторён трижды (идентично). Срез 3.2 (RHR) выполнен 2026-09-10: `_normalize_rhr_payload` → `observedAt` (GMT/UTC → таймзона атлета через нейтральные `utils/athlete_time.py` + `utils/observation_provenance.py`), колонка `daily_health.resting_hr_observed_at`, атомарная запись в обоих writer'ах (Garmin `sync_daily_health` и Intervals `sync_wellness_batch`), collision-тесты, legacy parity. Осталось: 3.3 HRV и `training_readiness` (sync + athlete-local ключ + `*_observed_at`, проверять обоих провайдеров), 3.4 `intervention_score_input` с observation-дедупликацией; legacy `score`/`baseline`/`deviation` остаются побайтово совместимыми (см. Decision Log).
- [ ] M4. `models/readiness_conflicts.py` + `api/recovery_replan_loop.py` + `data/database.py` + `api/routers/decisions.py`: fail-closed gate и version-qualified ownership (AC6) поверх lifecycle #552, с передачей версий из API в атомарные DB-методы.
- [ ] M5. `/today`: проекция и UI с датами факторов; `ts_contract.json` перегенерирован.
- [ ] M6. Верификация (AC10), обновление `docs/architecture/asr_catalog.md`, `Outcomes & Retrospective`.

## Surprises & Discoveries

- **Observed**: `services/readiness_snapshot.py:79` вызывает `compute_readiness_today(..., max_value_age_days=None)`, хотя дефолт модели — `STALE_AFTER_DAYS = 2` (`models/readiness.py:83`). Источник: чтение кода на `main` `72f69b4`.
  **Inferred**: значение любой давности допускается намеренно (ради отображения), но агрегатная свежесть и gate построены так, будто «любое значение = сегодняшнее».
  **Verified by**: чтение вызова и последующего расчёта `stale` из `result["as_of_date"]`.
- **Observed**: `models/readiness.py:151` считает `as_of_date = max(as_of_dates)` по всем факторам, `models/readiness.py:157` — `confidence = round(len(factors) / len(FACTOR_WEIGHTS), 2)` по факту наличия фактора; `FACTOR_WEIGHTS` содержит 5 ключей (`hrv`, `resting_hr`, `sleep`, `training_readiness`, `tsb`).
  **Inferred**: текущий TSB (или номинально сегодняшний RHR) маскирует вчерашние HRV/sleep, а presence-based confidence растёт от старых факторов.
  **Verified by**: арифметика совпадает с falsifier из issue: при `max_value_age_days=0` остаются два фактора → `2/5 = 0.4 < MIN_CONFIDENCE (0.5)` → `models/readiness_conflicts.py:324` переводит сценарий в `data_gap`.
- **Observed**: `data/garmin_client.py:497-509` (`_normalize_rhr_payload`) сводит payload к `{'restingHeartRate': value}`, теряя время измерения; `services/sync.py:1055` пишет результат под `daily_health_data[date_str]` (дата запроса). HRV собирается так же (`services/sync.py:951`, `hrv_data[date_str]`), хотя payload (`hrvSummary`) обычно содержит `calendarDate`/`startTimestampGMT`. Сон ключуется датой payload (`services/sync.py:997`, `date_key = processed_sleep.get("sleep_date") or date_str`).
  **Inferred**: RHR и HRV — метрики «под датой запроса»; без явного observation date legacy и повторные синки выглядят как сегодняшние.
  **Verified by**: чтение перечисленных строк; поведение совпадает с инцидентом из issue.
- **Observed**: `services/sync.py:1097` сохраняет `training_status_data[datetime.now().strftime("%Y-%m-%d")] = processed_status` — дата строки равна локальному «сейчас» сервера, независимо от даты измерения в provider payload. Запись идёт через `data/database.py::sync_training_status` (стр. 5927+), который использует отдельный список `_TRAINING_STATUS_COLUMN_ORDER`, а миграции — карту `_TRAINING_STATUS_COLUMN_TYPES` (стр. 141) и `_ensure_training_status_columns` (стр. 1069).
  **Inferred**: старый device readiness может попасть в snapshot как сегодняшний фактор; вместе с номинально сегодняшним RHR и текущим TSB это даёт 3/5 = 0.6 ≥ 0.5 и снова открывает gate.
  **Verified by**: чтение строки записи, метода `sync_training_status` и таблицы `training_status` (`CREATE TABLE` на стр. 405).
- **Observed**: `models/readiness.py:158-164` проецирует `drivers` только как `key/label/score/evidence` — без `as_of`/`stale_input`; `web/app/today/page.tsx:325` предпочитает `drivers`, когда они непусты; в `web/lib/types.ts:1551` `drivers` не типизированы (`Array<Record<string, unknown>>`).
  **Inferred**: даже корректно помеченный устаревший фактор доходит до UI без даты, а `stale=false` и «полный набор» читаются как доказательство свежести.
  **Verified by**: чтение проекции и страницы.
- **Observed**: legacy-поля снапшота уже управляют поведением: `models/session_quality_forecast.py:54-55` (порог по `confidence` и `stale`), `services/recovery_analytics.py:73,77`, `models/recovery_response.py:78,83`, `models/coach_narrative_evidence.py:302,314,436-437`, `services/comparable_sessions.py:334,432`, `api/session_quality_forecast.py:143-144`.
  **Inferred**: переопределение смысла `confidence`/`stale` — behavioral breaking change для четырёх+ подсистем, а не косметика контракта.
  **Verified by**: grep по читателям `"confidence"`/`"stale"` в `models/`, `services/`, `api/` (список приведён выше и зафиксирован в Decision Log).
- **Observed**: в `data/database.py::save_recovery_decision` (стр. ~2087-2200) head `recovery_evidence_heads` обновляется только при `outcome != "data_gap"`; `api/recovery_replan_loop.py` вызывает `supersede_pending_recovery_proposals` только при `outcome != "data_gap" and proposal is None`; `claim_current_recovery_proposal` требует, чтобы head имел `outcome == "conflict"` и совпадающие fingerprint/revision.
  **Inferred**: после деплоя новая версия правил, классифицирующая прежнее evidence как intervention-ineligible, даст исход `data_gap`; head останется прежним conflict-ом, суперсессии не будет, а approve по-прежнему пройдёт claim и мутирует план — AC6 через один лишь rule version во fingerprint не закрывается.
  **Verified by**: чтение трёх перечисленных мест и существующего теста `tests/smoke/test_recovery_replan_loop.py::test_data_gap_does_not_supersede_last_complete_conflict` (политика intentional: transient data_gap не отменяет последнее полное evidence).
- **Observed**: `api/recovery_replan_loop.py:64-75` (`_fingerprint`) включает `as_of`, `checkpoint_id`, `readiness`, `horizon_days`, `conflicts`, `data_gap`, `silence` — без версии правил; `READINESS_SNAPSHOT_RULE_VERSION` (`models/recovery_response.py:20`, сейчас `"readiness_snapshot_v2"`) только записывается в снапшот (`services/readiness_snapshot.py:130,156`, ре-экспорт в `api/readiness_snapshot.py`) и никем не ветвит поведение.
  **Inferred**: версия правил полезна как часть identity (defence in depth), но сама по себе ничего не инвалидирует; для AC6 нужен отдельный version-qualified ownership.
  **Verified by**: grep по `READINESS_SNAPSHOT_RULE_VERSION` и `rule_version` (поведенческих читателей нет).
- **Observed**: baseline'ы issue (`2307 passed, 1 skipped` для `pytest tests/smoke -q`) сняты в окружении с установленными `web/node_modules` и свободным портом; в свежем worktree на `72f69b4` тот же smoke-прогон даёт `2285 passed, 22 skipped, 1 failed`, а contributor-safe — `2328 passed, 27 skipped, 1 failed`. Единственный фейл (`tests/smoke/test_run_web_preflight.py::test_run_web_rejects_busy_api_port_before_startup`) воспроизводится на чистом `main` и вызван занятым портом :8000 в локальной среде.
  **Inferred**: сравнивать baseline'ы между окружениями нельзя; реализатор обязан снять «до/после» в своём окружении тем же самым набором.
  **Verified by**: два прогона в изолированном worktree `/tmp/main557` (smoke и contributor-safe) на `72f69b4`.

## Decision Log

- Decision: у фактора появляется явная пригодность. `observation_status ∈ {"confirmed_today", "outdated", "unverified", "invalid", "missing"}` (пятый статус `invalid` добавлен в v3.1 — см. ниже); `intervention_eligible = (observation_status == "confirmed_today")`; `evidence_kind ∈ {"measurement", "derived_state"}`; `age_days` — возраст наблюдения выбранной строки (для `invalid` он отрицательный).
  Rationale: AC1/AC3 требуют, чтобы вчерашний фактор не делал свежими остальные и не поднимал интервенционную уверенность, а наблюдаемое состояние оставалось датированным. `missing` зарезервирован для фактора, которого нет вовсе (в списке факторов он не появляется, но статус нужен контракту M2/M5).
  Date/Author: 2026-09-10 / agent (по issue #557; набор статусов расширен в v3.1).
- Decision: legacy-поля `score`, `confidence`, `stale`, `source_completeness`, `is_provisional` **сохраняют текущую семантику без изменений**; вся новая информация идёт аддитивно: `intervention_score`, `intervention_confidence`, `freshness`, `eligible_inputs`, `ineligible_inputs`, `intervention_blocked_reason` (+ per-factor поля из предыдущего решения).
  Rationale: переопределение `confidence`/`stale` сломало бы `models/session_quality_forecast.py`, `services/recovery_analytics.py`, `models/recovery_response.py`, `models/coach_narrative_evidence.py`, `services/comparable_sessions.py`, `api/session_quality_forecast.py` и противоречило AC8 (additive/backward-compatible). Дефолт-направление безопасности достигается в gate, а не подменой общего поля.
  Date/Author: 2026-09-10 / agent (ревизия v2 по ревью).
- Decision: `_split_frame` возвращает frozen dataclass `FactorWindow` вместо кортежа, и он разделён на **два независимых канала**: legacy (`value`, `as_of`, `age_days`, `stale`, `history`) и provenance (`observation_as_of`, `observation_age_days`, `observation_verified`). `ineligible_inputs[].reason` — стабильные коды `observation_date_unverified` / `observation_outdated` / `observation_in_future`.
  Rationale: шесть позиционных значений в кортеже читались бы как лотерея; каналы нельзя смешивать — legacy-поля читают session-quality forecast, recovery analytics, recovery_response и другие подсистемы, поэтому выбор значения, `as_of`, `stale` и окно базлайна остаются строго по дате строки хранения (как до #557). Даты измерения живут только в provenance-канале и не переключают выбранную строку; коды причин устойчивы для тестов и будущей локализации в UI.
  Date/Author: 2026-09-10 / agent (M1, ревизия по delta-review).
- Decision (amends previous, M1 fix): `intervention_eligible` возникает **только при `observation_age_days == 0`**. Отрицательный возраст (измерение датировано позже anchor) — не «свежесть», а недостоверные данные: `observation_status = "invalid"`, `reason = "observation_in_future"`, фактор неучаствует во вмешательстве.
  Rationale: условие `age_days <= 0` делало будущее измерение подтверждённо сегодняшним и открывало gate на данных, которых ещё не было (нарушение AC2). Отдельный статус `invalid` честнее, чем `unverified`: дата известна, но недопустима.
  Date/Author: 2026-09-10 / agent (M1 fix по delta-review).
- Decision (amends M1 dedupe decision, действующее поведение M1): повторное наблюдение под другой датой запроса **не переключает выбранную строку и не становится «сегодняшним»** — факт пригодности определяется observation-датой выбранной (последней по дате хранения) строки. Никакой дедупликации ряда в M1 нет; объём и инварианты будущей дедупликации зафиксированы в записи «заменяет отменённую выше» ниже.
  Rationale: предыдущая формулировка (ряд ключуется observation-датой) меняла замороженные `raw_value`/`score`/`as_of`/`stale_input` — это ловится фикстурой prov_a: main выбирает последнюю сохранённую строку (RHR 80 → score 40), а выбор по observation-дате выбрал бы RHR 50 → score 70. Прямое требование AC8 (обратная совместимость) важнее, а защита от «повтора под новой датой» достигается тем, что провенанс берётся у используемой строки.
  Date/Author: 2026-09-10 / agent (M1 fix по delta-review).
- Decision: единственный мигрирующий потребитель — salience-gate `models/readiness_conflicts.py::detect_readiness_conflicts`: он читает `intervention_score` (вместо `score`) и `intervention_confidence` (вместо `confidence`) и дополнительно требует хотя бы одно `intervention_eligible` primary-измерение (sleep/HRV/RHR). Все остальные потребители остаются на legacy-полях, и на каждого пишется regression-тест, фиксирующий неизменность прежнего поведения.
  Rationale: AC2/AC3 требуют fail-closed именно на входе в интервенцию; менять остальные подсистемы в рамках этой задачи — scope creep с риском для session-quality forecast и recovery analytics.
  Date/Author: 2026-09-10 / agent (ревизия v2 по ревью).
- Decision: `intervention_confidence = len(intervention_eligible факторов) / len(FACTOR_WEIGHTS)` — знаменатель 5 сохраняется; `intervention_score` — взвешенное среднее по `intervention_eligible`-факторам с перенормировкой весов, `None`, если пригодных факторов нет **или** нет ни одного пригодного primary-измерения (`intervention_blocked_reason = "no_confirmed_today_primary_recovery_measurement"`).
  Rationale: AC3 фиксирует ровно `0.4` для пары {подтверждённо сегодняшний RHR, текущий TSB} = 2/5 и `0.2` для одного TSB = 1/5; сохранение шкалы и порога `MIN_CONFIDENCE = 0.5` даёт fail-closed без изменения policy. `intervention_score = None` напрямую переводит gate в `data_gap` тем же кодом, что и сегодня (`score is None`).
  Date/Author: 2026-09-10 / agent (ревизия v2 по ревью).
- Decision: `freshness` — новый объект снапшота (`state ∈ {"fresh","provisional","data_gap"}`, `anchor`, `confirmed_today`, `outdated`, `unverified`, `invalid`, `missing`, `intervention_eligible`, `blocked_reason`). Легаси-поле `stale` не переопределяется; UI читает `freshness.state`. Корзина `invalid` отдельная (не слита с `unverified`), чтобы UI честно показывал некорректную будущую дату измерения.
  Rationale: AC5 требует не подавать `stale=false` как доказательство общей свежести, но legacy-читатели `stale` должны продолжать работать ровно как раньше; пять статусов модели должны иметь однозначное отображение в контракт снапшота (иначе будущая дата потерялась бы в `unverified` и выглядела бы как «дата неизвестна»).
  Date/Author: 2026-09-10 / agent (ревизия v2 по ревью; корзина `invalid` добавлена в v3.1).
  Rationale: AC5 требует не подавать `stale=false` как доказательство общей свежести, но legacy-читатели `stale` должны продолжать работать ровно как раньше.
  Date/Author: 2026-09-10 / agent (ревизия v2 по ревью).
- Decision: AC6 закрывается **version-qualified ownership**, а не правилом «data_gap суперсидит». Четыре аддитивных элемента. (1) `api/recovery_replan_loop.py::_proposal_payload` штампует pending-предложение: `params["rule_version"] = READINESS_CONFLICT_RULE_VERSION` (`"readiness_conflicts_v2"`, новый констант в `models/readiness_conflicts.py`) и то же значение в `preview`. (2) `data/database.py::claim_current_recovery_proposal(proposal_id, *, current_rule_version, compatible_rule_versions=())` получает независимую проверку версии: если штамп отсутствует (legacy) или не входит в множество совместимых — предложение переводится в `superseded` с `reason = "superseded_by_rule_version_change"`, без мутации head, чекпойнтов и provider-вызовов. **Версии передаются аргументами**: `data/` не импортирует доменные константы из `models/`, а production-вызов находится в `api/routers/decisions.py::approve_proposal` (этот файл входит в M4), рядом с уже существующим вызовом claim. (3) Новый атомарный `db.supersede_incompatible_recovery_proposals(current_rule_version, compatible_rule_versions=())` вызывается из `api/recovery_replan_loop.py` на **каждом** прогоне, включая `data_gap`, и суперсидит только `status='pending'` с отсутствующим/несовместимым штампом, никогда не трогая `applying`. (4) `_fingerprint` включает `rule_version` как defence in depth, но это не механизм AC6.
  Контракт совместимости один для guard и для sweep: предложение совместимо тогда и только тогда, когда его штамп принадлежит множеству `{current_rule_version} | set(compatible_rule_versions)`; `NULL` (legacy) несовместим всегда. Множество совместимых версий объявляется рядом с константой (`RECOVERY_EVIDENCE_COMPATIBLE_RULE_VERSIONS`, по умолчанию пустое = строгое равенство) и расширяется только вместе с записью в Decision Log и доказательством, что семантика предложения не изменилась.
  Rationale: политика #552 (transient `data_gap` не отменяет последнее полное evidence) сохраняется — тест `test_data_gap_does_not_supersede_last_complete_conflict` остаётся зелёным, потому что в нём предложение штамповано текущей версией; при этом предложение, созданное правилами прежней версии, физически не может быть применено. Сравнение идёт «штамп предложения против версии, переданной вызывающим кодом», поэтому `data_gap`-прогон, который намеренно не обновляет head, механизму не мешает.
  Date/Author: 2026-09-10 / agent (ревизия v3 по ревью).
- Decision: observation date извлекается из payload для RHR, HRV и `training_readiness`; **семантика источника задаётся вызывающим кодом явно**, а не угадывается хелпером:

      def observation_local_date(value, *, source: Literal["utc", "athlete_local"]) -> date | None

  При `source="utc"` значение (ISO-строка, epoch-миллисекунды, `datetime`) приводится к tz-aware моменту (naive трактуется как UTC — это документированная семантика Garmin-полей `*GMT`/`timestamp`), затем переводится в `Settings.ATHLETE_TIMEZONE` и берётся календарная дата. При `source="athlete_local"` (`startTimeLocal`, `calendarDate`, `sleep_date`) календарная дата берётся как есть, без конверсии. Невалидное значение или неразбираемая зона → `None` (фактор `unverified`, а не выдуманная дата).
  Общий timezone-хелпер выносится в нейтральный модуль `utils/athlete_time.py::athlete_local_date(observed_at_utc)` — канонический имплементация переезжает туда из `services/intervals_plan_delivery.py`, где остаётся тонкий delegate с прежней сигнатурой (файл и его `__all__` сохраняют имя, поэтому `api/routers/coach.py:48`, `api/today_snapshot.py:23` и существующие тесты продолжают работать без правок). Новый `services/observation_provenance.py` импортирует только `utils/athlete_time.py`, поэтому ingest не начинает зависеть от delivery-слоя.
  Rationale: AC4 требует честного provenance; UTC-дата около полуночи не равна дате спортсмена (та же ошибка, что чинили для отображения в #553). Явный `source` убирает догадки о природе значения, а нейтральный модуль — лишнюю связность ingest → delivery.
  Date/Author: 2026-09-10 / agent (ревизия v3 по ревью).
  Rationale: AC4 требует честного provenance; UTC-дата около полуночи не равна дате спортсмена (та же ошибка, что чинили для отображения в #553). Единый хелпер исключает расхождение между RHR, HRV и training status.
  Date/Author: 2026-09-10 / agent (ревизия v2 по ревью).
- Decision: хранение — ровно три аддитивные nullable-колонки: `daily_health.resting_hr_observed_at TEXT`, `hrv_data.rmssd_observed_at TEXT`, `training_status.training_readiness_observed_at TEXT`; `NULL` означает «дата измерения не подтверждена». Для `training_status` одновременно обновляются `_TRAINING_STATUS_COLUMN_TYPES` (миграция) и `_TRAINING_STATUS_COLUMN_ORDER` (путь записи в `sync_training_status`). Строка по-прежнему пишется (данные не теряем), но при `NULL` фактор `unverified`. Колонка `recovery_evidence_heads.rule_version` **не добавляется**: version-guard сравнивает штамп предложения с версией, переданной вызывающим кодом, а `recovery_evidence_heads` читается только внутри `data/database.py` (внешних потребителей нет — проверено grep), поэтому колонка осталась бы неиспользуемым расширением схемы. Audit-провенанс версии живёт там, где ему место: в неизменяемых строках `recovery_decisions.report_json` (отчёт содержит `rule_version`) и в штампе `params`/`preview` самого предложения.
  Rationale: ASR-MOD-3 требует обратно совместимой смены схемы и минимальной поверхности; legacy-строки без колонки деградируют в `unverified`, а не получают выдуманную сегодняшнюю дату.
  Date/Author: 2026-09-10 / agent (ревизия v3 по ревью).
- Decision (~~дедупликация по identity наблюдения~~ **SUPERSEDED в v3.1**, см. запись «amends M1 dedupe decision» ниже; **не реализовывать в M1/M2**): ряд фактора строится по ключу `observation_date or stored_row_date`, при повторе одной и той же observation побеждает последняя запись; `age_days` считается от выбранного ключа. Там, где observation date не подтверждена, поведение остаётся прежним (ключ = дата хранения).
  Rationale (историческая): повторный sync одной и той же observation под разными query dates не должен дважды попадать в 28-дневный baseline и искажать отклонение.
  Почему отменено: ключевание ряда по observation-дате меняло замороженные legacy-поля (`raw_value`, `score`, `deviation`, `as_of`, `stale_input`, baseline) — фикстура `prov_a` показала расхождение с `main` (main выбирает последнюю сохранённую строку RHR 80 → score 40, ключевание по observation выбрало бы RHR 50 → score 70), что нарушает AC8. Действующая формулировка — в записи ниже.
  Date/Author: 2026-09-10 / agent (v2); отменено 2026-09-10 (v3.1).
- Decision (заменяет отменённую выше, действующая формулировка дедупликации на M3+): дедупликация повторов наблюдения разрешена **только внутри интервенционного расчёта**. Инвариант M3: `factor.score`, `factor.baseline`, `factor.deviation` и остальные legacy-поля остаются побайтово совместимыми с `main`; дедуплицированный baseline не подменяет их, а питает отдельное внутреннее значение фактора.
  Название поля фиксируется заранее: per-factor `intervention_score_input` (аддитивное, внутреннее для расчёта; в M1 равно `factor["score"]`, в M3+ может считаться по дедуплицированному baseline по observation-датам), и агрегатор `intervention_score` использует **только** `intervention_score_input`, а не `score`.
  Rationale: до появления заполненных provenance-колонок дедупликацию нельзя реализовать достоверно; заранее названное поле не даёт M3 тронуть замороженные legacy-значения и делает переход проверяемым (в M3 `intervention_score_input == score` на фикстурах без дублей).
  Date/Author: 2026-09-10 / agent (v3.1 по ревью M1).
- Decision (M3, срез 3.1; переработано после ревью P1): provenance сна хранится **по метрике** — `sleep_data.sleep_score_observed_at` и `sleep_data.total_sleep_observed_at`, заполняемые только датой из payload (`calendarDate`, иначе дата окончания сна из `sleepEndTimestampLocal`), `NULL` при отсутствии/невалидности. Запись provenance происходит **внутри той же ветки, что и принятие метрики** (в `sync_sleep_data` — внутри проверок provider-priority; в `sync_wellness_batch` — внутри `should_replace`), поэтому отклонённая метрика другого провайдера не может «одолжить» свою дату чужому значению. Дата известной provenance не стирается пустым повторным sync. Фактор сна читает колонку той метрики, которая победила (`_sleep_factor` предпочитает `sleep_score`).
  Rationale: одна общая колонка связывала дату с любой метрикой строки. Воспроизведение из ревью: сохранён Garmin score=40/observed=вчера, входящий Intervals score=90 отклонён по provider-priority, но общая колонка перезаписывалась на сегодня — старый низкий score становился `confirmed_today` и мог открыть вмешательство. Метрико-скоупное разделение плюс атомарная запись закрывают и это, и случай, когда score и duration приходят из разных источников.
  Rationale: `process_sleep_data` вычисляет `calendar_date`, но сохраняет `sleep_date` только при наличии пары start/end timestamps, после чего sync ключует строку датой запроса — то есть дата строки не доказывает дату измерения. Параметр `stored_date_is_observation` из M1 удалён: он был escape hatch'ом именно для этого случая и после появления колонки стал бы источником ложной свежести.
  Побочные инварианты: ключ строки (`sleep_date or date_str`) не меняется — правда о наблюдении живёт в отдельной колонке; повторный sync без payload-даты не стирает уже известную provenance (UPDATE пропускает пустое значение); legacy-строки остаются `NULL` и деградируют в `unverified`.
  Date/Author: 2026-09-10 / agent (M3 slice 3.1).
- Decision (M3, срез 3.2): дата измерения RHR берётся из payload (`startTimeGMT`, `startTimeLocal`, `timestamp`, `calendarDate`, `date` — в этом порядке), GMT/UTC-значения конвертируются в `Settings.ATHLETE_TIMEZONE`, локальные/календарные читаются как есть; невалидное значение → `NULL`/`unverified`. Хранение — аддитивная nullable-колонка `daily_health.resting_hr_observed_at`, запись **внутри ветки принятия метрики** в `sync_daily_health` (provider-priority) и в `sync_wellness_batch` (`should_replace`), где датой служит provider-local `id` записи wellness.
  Rationale: `daily_health.date` — дата запроса, а не дата измерения; оба источника (Garmin payload и Intervals.icu wellness) должны давать проверяемую дату, при этом отклонённая метрика не имеет права «одолжить» свою дату принятой (P1 среза 3.1, повторённый здесь как collision-тест).
  Date/Author: 2026-09-10 / agent (M3 slice 3.2).
- Decision (M3, срез 3.2, уточнение плана): нейтральные helper'ы живут в `utils/`, а не в `services/`: `utils/athlete_time.py::athlete_local_date` (канонический, с delegate-реэкспортом в `services/intervals_plan_delivery.py`) и `utils/observation_provenance.py::observation_local_date(value, *, source)`.
  Rationale: ingest-слой (`data/garmin_client.py`, `data/data_processor_phase1.py`) обязан пользоваться тем же разбором дат, но не должен импортировать `services/` (это была бы связка ingest → delivery, против которой возражало ревью P2); `utils/` — нейтральный слой, уже используемый `data/`.
  Date/Author: 2026-09-10 / agent (M3 slice 3.2).
- Decision (M3, срез 3.1, P2): дата измерения сна назначается метрике **после** блока derivation, то есть derived `sleep_score` тоже получает payload-дату.
  Rationale: назначение до derivation оставляло `sleep_score_observed_at = None` у датированного Garmin-сна без нативного score, и `_sleep_factor` (он предпочитает score перед duration) объявлял свежий сон `unverified`/непригодным — при том что `total_sleep_observed_at` был заполнен. Инвариант: любая метрика, попавшая в `processed_data`, получает дату этого payload.
  Date/Author: 2026-09-10 / agent (M3 slice 3.1, P2).
- Decision (M3, срез 3.1): для Intervals.icu датой наблюдения сна служит provider-local `id` записи wellness: `sync_wellness_batch` пишет его в `sleep_score_observed_at`/`total_sleep_observed_at` только когда соответствующая метрика действительно принята (insert или `should_replace`), поэтому рекомендованный primary-источник больше не оставляет сон `unverified`.
  Rationale: `normalize_intervals_wellness` уже отдаёт авторитетную дату в `WellnessRecord.date`, но до этого среза она не доходила до сна; без неё сон из Intervals.icu навсегда оставался бы неучаствующим во вмешательстве.
  Date/Author: 2026-09-10 / agent (M3 slice 3.1).
- Decision: `training_readiness` перестаёт быть «сегодняшним по дате строки»: фактор `intervention_eligible` только при подтверждённой observation date, равной anchor. Ключ строки в `services/sync.py` меняется с `datetime.now().strftime("%Y-%m-%d")` на athlete-local дату, полученную из payload; если observation date не подтверждена, строка сохраняется, но фактор — `unverified`.
  Rationale: иначе старое device readiness вместе с RHR и TSB даёт 3/5 = 0.6 и открывает gate (сценарий из ревью).
  Date/Author: 2026-09-10 / agent (ревизия v2 по ревью).
- Decision: `READINESS_SNAPSHOT_RULE_VERSION` повышается `readiness_snapshot_v2` → `readiness_snapshot_v3` как метаданные (поведенческих читателей нет — проверено grep), а инвалидацию несут `READINESS_CONFLICT_RULE_VERSION` и version-qualified ownership.
  Rationale: AC6 требует версии в identity, но менять поведение по версии снапшота не нужно; лишняя связность удорожает ревью.
  Date/Author: 2026-09-10 / agent.
- Decision: UI не считает ничего сам. `/today` рендерит серверный контракт: даты факторов (`сегодня` / `вчера · <дата>` / `дата измерения неизвестна`), `freshness.state` и баннер provisional; подпись `source_completeness` меняется на «покрытие факторов»; описательный `score` показывается с пометкой provisional, когда `freshness.state != "fresh"`.
  Rationale: ASR-MOD-2 и Product Surface Policy — доменная логика в Python; AC5 запрещает выдавать `stale=false`/«полный набор» за доказательство свежести.
  Date/Author: 2026-09-10 / agent.

## Outcomes & Retrospective

(Заполняется по завершении реализации: что реально изменилось, какие проверки прошли на финальном дереве, что осталось за скоупом. На момент ревизии v3.1 выполнены M1 и docs-amend; код M2–M6 не начат.)

## Context and Orientation

Ключевые файлы и их роль (пути от корня репозитория):

`models/readiness.py` — каноническая фузия готовности. `FACTOR_WEIGHTS` (5 факторов), `_split_frame` (последнее значение колонки, `age_days` и `stale = age_days > 0`, при `max_age` слишком старое отбрасывается), `_deviation_factor` (HRV по `rmssd`, RHR по `resting_hr`), `_sleep_factor` (`sleep_score`/`total_sleep_minutes`), фактор тренировочного статуса (`training_readiness`), `_tsb_factor` (производное состояние нагрузки). `compute_readiness_today` собирает факторы, считает weighted `score`, `status` по `_STATUS_THRESHOLDS`, `as_of_date = max(as_of_dates)`, `confidence = len(factors)/len(FACTOR_WEIGHTS)`, `drivers` (топ-3 по вкладу), `missing_inputs`.

`services/readiness_snapshot.py` — канонический snapshot для API: вызывает `compute_readiness_today(..., max_value_age_days=None)`, считает `stale` от `computed_at`, `source_completeness`, `missing_inputs` по `PRIMARY_INPUTS = ("sleep","hrv","resting_hr")`, добавляет `provenance`, `rule_version`, `is_provisional`, `reason`; `_unknown_snapshot` даёт honest-empty состояние.

`models/readiness_conflicts.py` — salience/severity-матрица и детектор (`MIN_CONFIDENCE = 0.5`; при `score is None or confidence < MIN_CONFIDENCE` → `data_gap`, `conflicts=[]`, `silence=True`). Этот отчёт — evidence для Recovery Replan.

`api/readiness_conflicts.py::build_readiness_conflict_report` — обёртка: читает таблицы, зовёт `compute_readiness_today`, добавляет horizon-политику, правит `reason` при отсутствии плана.

`api/recovery_replan_loop.py` — recovery-луп: `_fingerprint` (identity evidence), `run_recovery_replan_loop` (immutable `recovery_decisions`, публикация/переиспользование pending-предложения через `db.publish_current_recovery_proposal`, суперсессия старых карточек при не-`data_gap` и отсутствии предложения).

`data/database.py` — схемы и миграции: `daily_health` (`CREATE` стр. 381, карта `_DAILY_HEALTH_COLUMN_TYPES` стр. 174, `_ensure_daily_health_columns` стр. 1079, запись `sync_daily_health` стр. 5819+ собирает колонки из карты); `hrv_data` (`_HRV_COLUMN_TYPES`); `training_status` (`CREATE` стр. 405, карта `_TRAINING_STATUS_COLUMN_TYPES` стр. 141, `_ensure_training_status_columns` стр. 1069, запись `sync_training_status` стр. 5927+ использует **отдельный** `_TRAINING_STATUS_COLUMN_ORDER`); `recovery_decisions`, `recovery_evidence_heads`, `coach_proposals` и методы #552: `save_recovery_decision`, `publish_current_recovery_proposal`, `supersede_pending_recovery_proposals`, `claim_current_recovery_proposal`.

`services/sync.py` — сбор данных: `_collect_phase1_hrv` (≈880-957; ключ `hrv_data[date_str]`), `_collect_phase1_daily_data` (≈970+; `sleep_data[date_key]` из payload, `daily_health_data[date_str]`), `_collect_training_status_data` (1063+; ключ `datetime.now().strftime("%Y-%m-%d")`).

`data/garmin_client.py::_normalize_rhr_payload` (стр. 497-509), `data/data_processor_phase1.py::process_daily_health_data` (стр. 229+), `process_training_status_data` — нормализация payload'ов перед записью.

`api/today_snapshot.py::_project_readiness` (стр. 285-303) — проекция снапшота в `/api/today`. `web/lib/types.ts` (readiness-типы ≈1540-1560), `web/app/today/page.tsx` (блок готовности ≈300-345).

Термины. **Фактор** — вход readiness (HRV, RHR, сон, тренировочный статус, TSB). **Observation date** — календарная дата самого измерения (из payload), в отличие от **даты запроса/хранения** (ключ строки в SQLite). **Intervention-eligible** — фактор, которому разрешено влиять на actionable вмешательство в план. **Descriptive** — то, что разрешено показывать человеку, с датой и пометкой provisional. **Evidence identity** — fingerprint+revision полной оценки, которым владеет pending-предложение (#552). **Version-qualified ownership** — дополнительное требование совпадения версии правил, штампованной в предложении, с версией, под которой работает код. **Fail closed** — при нехватке/недостоверности данных система молчит (`data_gap`).

ASR-связи: ASR-REL-2 (`docs/architecture/asr_catalog.md`, строка 16) — «отсутствие данных → data gap»; ASR-REL-1 (строка 15) — целостность identity/lineage при перепланировании (сюда добавится version-qualified ownership); ASR-MOD-2 (строка 19) — дашборд без доменных расчётов в TypeScript; ASR-MOD-3 (строка 20) — обратно совместимая смена схемы.

## Plan of Work

Работа идёт по слоям; каждый слой заканчивается зелёным прогоном своих тестов. RED-тесты пишутся первыми и должны падать на текущем `main`.

**M1 — пригодность фактора (models/readiness.py), без изменения legacy-агрегатов.** Вводим константы статусов (`OBSERVATION_CONFIRMED_TODAY`, `OBSERVATION_OUTDATED`, `OBSERVATION_UNVERIFIED`, `OBSERVATION_INVALID`, `OBSERVATION_MISSING`) и `PRIMARY_RECOVERY_KEYS = ("sleep","hrv","resting_hr")`. `_split_frame` возвращает `FactorWindow` с двумя каналами: legacy-выборка по **дате хранения** (значение, `as_of`, `stale`, окно базлайна — без изменений относительно `main`) и provenance выбранной строки (`observation_as_of`, `observation_age_days`, `observation_verified`). Каждый фактор получает `observation_as_of`, `age_days`, `observation_status`, `intervention_eligible`, `evidence_kind`. `compute_readiness_today` продолжает считать **прежние** `score`/`confidence`/`as_of_date`/`drivers` по прежним правилам (заморозка, см. Decision Log) и добавляет `intervention_score`, `intervention_confidence`, `eligible_inputs`, `ineligible_inputs` (с причинами), `intervention_blocked_reason`; `drivers` обогащаются `as_of`, `observation_as_of`, `age_days`, `observation_status`, `intervention_eligible`, `evidence_kind`, `source`. TSB — `evidence_kind="derived_state"`, `intervention_eligible=True`, но не primary. Дедупликация повторов наблюдения в M1 **не выполняется** (отложена на M3+ через `intervention_score_input`).

**M2 — аддитивный контракт снапшота (services/readiness_snapshot.py).** Добавляем `freshness` (см. Decision Log, пять корзин включая `invalid`), `intervention_score`, `intervention_confidence`, `eligible_inputs`, `ineligible_inputs`, `intervention_blocked_reason`; `stale`, `confidence`, `source_completeness`, `is_provisional`, `score` остаются ровно как есть. `state` считается так: `data_gap`, если `intervention_score is None`; `provisional`, если есть хоть один primary-фактор не `confirmed_today` (в том числе `outdated`, `unverified`, `invalid`); иначе `fresh`. Фактор со статусом `invalid` попадает в отдельную корзину `freshness.invalid` и никогда не считается подтверждённым. `_unknown_snapshot` получает те же новые ключи, чтобы форма ответа не различалась. `READINESS_SNAPSHOT_RULE_VERSION` → `readiness_snapshot_v3` (метаданные).

**M3 — provenance измерений.** Канонический timezone-хелпер переезжает в `utils/athlete_time.py::athlete_local_date`; `services/intervals_plan_delivery.py` сохраняет тонкий delegate и имя в `__all__` (импортеры `api/routers/coach.py:48`, `api/today_snapshot.py:23` и тесты не меняются). Новый `services/observation_provenance.py::observation_local_date(value, *, source)` задаёт явную семантику: `source="utc"` (ISO/epoch/`*GMT`/`timestamp`) → tz-aware момент → `Settings.ATHLETE_TIMEZONE` → календарная дата; `source="athlete_local"` (`startTimeLocal`, `calendarDate`, `sleep_date`) → дата как есть; невалидное/неизвестная зона → `None`. `data/garmin_client.py::_normalize_rhr_payload` возвращает `{'restingHeartRate': N, 'observedAt': <ISO|None>}`, разбирая по порядку `startTimeGMT` (utc), `startTimeLocal` (athlete_local), `timestamp` (utc), `calendarDate`/`date` (athlete_local). `data/data_processor_phase1.py::process_daily_health_data` прокидывает `resting_hr_observed_at`; `services/sync.py::_collect_phase1_hrv` пишет `rmssd_observed_at` из `hrvSummary` (`calendarDate` как athlete_local, `startTimestampGMT` как utc); `_collect_training_status_data` пишет `training_readiness_observed_at` и ключует строку athlete-local датой из payload вместо `datetime.now()`. `data/database.py`: `resting_hr_observed_at` в `_DAILY_HEALTH_COLUMN_TYPES`, `rmssd_observed_at` в `_HRV_COLUMN_TYPES`, `training_readiness_observed_at` в **обеих** структурах `training_status` (`_TRAINING_STATUS_COLUMN_TYPES` и `_TRAINING_STATUS_COLUMN_ORDER`) + строки в соответствующих `CREATE TABLE`; проверить, что «умная» запись обновляет строку, когда изменилась только observation date.

**M4 — fail-closed gate и version-qualified ownership.** `models/readiness_conflicts.py`: новый `READINESS_CONFLICT_RULE_VERSION = "readiness_conflicts_v2"` и `RECOVERY_EVIDENCE_COMPATIBLE_RULE_VERSIONS: tuple[str, ...] = ()`; `detect_readiness_conflicts` читает `intervention_score`/`intervention_confidence`, требует пригодное primary-измерение, кладёт в отчёт `rule_version`, `freshness` (echo) и `readiness.intervention_score` (так `rule_version` попадает и в неизменяемый `recovery_decisions.report_json`). `api/recovery_replan_loop.py::_proposal_payload` штампует `params["rule_version"]`/`preview["rule_version"]` (это API-слой, не `data/`), `run_recovery_replan_loop` вызывает `db.supersede_incompatible_recovery_proposals(current_rule_version, compatible_rule_versions=...)` на каждом прогоне, включая `data_gap`, до логики публикации, и добавляет `rule_version` в `_fingerprint`. `data/database.py`: `claim_current_recovery_proposal(proposal_id, *, current_rule_version, compatible_rule_versions=())` с version-guard'ом (данные приходят аргументами, доменных импортов в `data/` нет) и новый атомарный `supersede_incompatible_recovery_proposals` (только `pending`, `applying` не трогает, head не мутирует). `api/routers/decisions.py::approve_proposal` передаёт обе версии в claim и отдаёт 409 на несовместимый штамп — этот файл входит в M4, потому что именно там живёт production-вызов.

**M5 — поверхность `/today`.** `api/today_snapshot.py::_project_readiness` прокидывает новые аддитивные поля и обогащённые `drivers`/`factors`. `web/lib/types.ts`: типизированные `ReadinessObservationStatus` (пять значений, включая `invalid`), `ReadinessFactor`, `ReadinessDriver`, `ReadinessFreshness`; новые nullable-поля снапшота; `tests/contracts/ts_contract.json` перегенерируется. `web/app/today/page.tsx`: дата у каждого драйвера (`сегодня` / `вчера · <дата>` / `дата измерения неизвестна` / `некорректная дата измерения` для `invalid`), баннер provisional/data_gap при `freshness.state != "fresh"`, подпись «покрытие факторов», пометка provisional у описательного score. Доменных расчётов в TypeScript нет.

**M6 — верификация и документация.** Фокусный прогон, `contract:extract -- --check`, `web lint/build`, Ruff, contributor-safe pytest; независимое чтение `/api/today` на изолированной temp-SQLite с проверкой отсутствия чекпойнтов и provider-вызовов; обновление строк ASR-REL-2/ASR-REL-1/ASR-MOD-3 в `docs/architecture/asr_catalog.md`; заполнение `Artifacts and Notes` и `Outcomes & Retrospective`.

## Concrete Steps

Рабочая директория — корень репозитория `/Users/gregkisel/Developer/ai_trainer`, окружение `ai_trainer_env` (команды ниже — через `./ai_trainer_env/bin/python -m pytest ...`).

Порядок: RED-тесты слоя → прогон (падают) → реализация → GREEN-прогон → коммит. Имена полей и колонок фиксированы в `Interfaces and Dependencies`; отклонение требует записи в `Decision Log`.

Команды по слоям:

    ./ai_trainer_env/bin/python -m pytest tests/smoke/test_readiness_model.py -q
    ./ai_trainer_env/bin/python -m pytest tests/smoke/test_readiness_snapshot_contract.py -q
    ./ai_trainer_env/bin/python -m pytest tests/smoke/test_garmin_sync_service.py tests/smoke/test_garmin_client_recovery_metrics.py -q
    ./ai_trainer_env/bin/python -m pytest tests/smoke/test_readiness_conflicts.py tests/smoke/test_recovery_replan_loop.py -q
    ./ai_trainer_env/bin/python -m pytest tests/smoke/test_api_today.py -q

Покрытие RED-тестов (AC9):

`tests/smoke/test_readiness_model.py`: смешанные даты дают корректные `observation_status`/`intervention_eligible` по факту; `intervention_confidence == 0.4` для {подтверждённо сегодняшний RHR, TSB} и `0.2` для одного TSB; `intervention_score` взвешен по пригодным факторам и `None` при отсутствии пригодного primary; **future-observation**: наблюдение, датированное позже anchor, даёт `observation_status="invalid"`, `intervention_eligible=false` и `reason="observation_in_future"`, gate остаётся закрытым; **frozen-legacy тесты**: (а) `score`, `confidence`, `stale`, `as_of_date` численно совпадают с эталонами, снятыми на `main`; (б) для фикстур с несовпадающими stored/observation датами legacy-выборка, `as_of`, `stale_input`, `baseline` равны значениям `main` (случаи `prov_a` и `prov_b`), а провенанс живёт отдельным каналом; (в) повтор наблюдения под новой датой запроса не делает фактор свежим, но и не меняет legacy-поля.

`tests/smoke/test_readiness_snapshot_contract.py`: нет ночных измерений → `freshness.state == "data_gap"`, `intervention_score is None`, пустые конфликты, при этом legacy `stale`/`confidence` равны прежним значениям на той же фикстуре; вчерашние sleep/HRV + текущий TSB → `provisional`; RHR без observation date → `unverified` и не `confirmed_today`; будущая дата измерения → отдельная корзина `freshness.invalid` (не `unverified`) и `state == "provisional"`; legacy-строка без новых колонок → `unverified`, без выдуманной даты.

Garmin/sync-тесты: payload с `startTimeGMT` → observation date равна дате измерения (а не дате запроса), включая случай около полуночи, где UTC-дата и athlete-local дата различаются; payload только с `restingHeartRate` → `None`/`unverified`; невалидная дата → `unverified`; HRV payload с `calendarDate` вчера при запросе на сегодня → `outdated`; `training_readiness` пишется с athlete-local ключом и `training_readiness_observed_at` из payload, а при отсутствии даты — ключ не выдумывается, фактор `unverified`.

`tests/smoke/test_readiness_conflicts.py` и `tests/smoke/test_recovery_replan_loop.py`: gate молчит при `intervention_confidence == 0.4`; `data_gap` без пригодного primary даже при текущем TSB; отчёт содержит `rule_version`; **AC6**: pending-предложение со штампом прежней версии становится `superseded` на первом же прогоне, **в том числе когда новая оценка — `data_gap`**, без чекпойнтов и provider-вызовов, с сохранением audit-строки; **API-тест**: `api.routers.decisions.approve_proposal` на несовместимом штампе отдаёт 409, после чего счётчики `planning_checkpoints` и provider-delivery записей не изменились, а провайдер не вызывался; **тест контракта совместимости**: предложение со штампом из `RECOVERY_EVIDENCE_COMPATIBLE_RULE_VERSIONS` остаётся claimable и не суперсидится sweep'ом (при пустом множестве — строгое равенство); **race-тест** approve против version-invalidation на двух соединениях → ровно один терминальный исход, применение после суперсессии невозможно; `applying` не инвалидируется в полёте; прогон с тем же штампом и `data_gap` по-прежнему НЕ суперсидит (`test_data_gap_does_not_supersede_last_complete_conflict` остаётся зелёным).

Семантика observation helper'а покрывается в `tests/smoke/test_readiness_model.py` (или отдельным `tests/smoke/test_observation_provenance.py`): `source="utc"` около полуночи даёт athlete-local дату, отличную от UTC-даты; `source="athlete_local"` не конвертирует; невалидное значение и неизвестная зона → `None` (фактор `unverified`); `services.intervals_plan_delivery.athlete_local_date` после выноса в `utils/athlete_time.py` сохраняет прежнее поведение (существующий `tests/smoke/test_intervals_plan_delivery.py` остаётся зелёным).

`tests/smoke/test_api_today.py`: на изолированной temp-SQLite без сегодняшних ночных строк `GET /api/today` даёт `data_gap`/provisional, пустые `conflicts`, отсутствие actionable-предложения; счётчики `planning_checkpoints` и provider-delivery записей до/после не меняются, провайдер замокан.

Новый `tests/smoke/test_readiness_today_freshness_ui_contract.py` (по образцу `tests/smoke/test_recovery_transfer_product_surface_web.py`): типизированные readiness-типы в `web/lib/types.ts` (включая `invalid` в `ReadinessObservationStatus`), метки `вчера`/`дата измерения неизвестна`/`некорректная дата измерения` и баннер provisional в `web/app/today/page.tsx`, наличие `as_of`/`observation_as_of`/`observation_status` в `drivers` проекции API.

Baseline'ы (сравнивать только like-for-like в своём окружении). На `72f69b4` в изолированном worktree: `pytest tests/smoke -q` → `2285 passed, 22 skipped, 1 failed`; `pytest -m "not live and not debug and not e2e" tests/ -q` → `2328 passed, 27 skipped, 26 deselected, 1 failed`. Единственный фейл — `tests/smoke/test_run_web_preflight.py::test_run_web_rejects_busy_api_port_before_startup`, воспроизводится на чистом `main` из-за занятого порта :8000 (в окружении issue с установленными `web/node_modules` и свободным портом тот же smoke даёт `2307 passed, 1 skipped`). Перед реализацией снять baseline в своём окружении той же командой.

## Validation and Acceptance

Наблюдаемое поведение на финальном дереве (AC1–AC10):

**S1 «нет ночных данных»** (sleep/HRV вчера, RHR без observation date, текущий TSB, качественная сессия в плане): `intervention_confidence == 0.2` (пригоден только TSB), `intervention_score is None` и `intervention_blocked_reason == "no_confirmed_today_primary_recovery_measurement"`, `freshness.state == "data_gap"`, `conflicts == []`, нового pending-предложения нет. Legacy-поля (`score`, `confidence`, `stale`) на этой же фикстуре численно равны значениям на `main` — доказательство аддитивности.

**S2 «RHR подтверждён сегодня, ночь не подтверждена»** (RHR сегодня + TSB сегодня, sleep/HRV вчера): `intervention_confidence == 0.4 < 0.5` → gate молчит, `freshness.state == "provisional"`, конфликтов нет.

**S3 «всё свежее»** (подтверждённо сегодняшние sleep, HRV, RHR + текущий TSB): `freshness.state == "fresh"`, `intervention_score` численно совпадает с `score`, gate и подтверждение/отмена предложения работают как раньше, legacy-поля равны прежним.

**S4 «AC6»** (pending-предложение со штампом версии N, код работает под версией N+1): на первом прогоне, **включая прогон с исходом `data_gap`**, предложение становится `superseded` с `reason = "superseded_by_rule_version_change"`, остаётся в audit-истории, approve отвечает 409 либо не доходит до claim, чекпойнты и provider-доставки не создаются; гонка approve/supersede даёт ровно один терминальный исход.

**S5 «нулевая мутация»**: в сценарии S1 после вызова recovery-лупа счётчики `planning_checkpoints` и provider-delivery записей не изменились, провайдер не вызывался.

**S6 «старый device readiness»**: payload training status без подтверждённой даты + RHR без даты + текущий TSB → `training_readiness` и `resting_hr` в `unverified`, пригоден только TSB → `intervention_confidence == 0.2`, gate закрыт (регрессия сценария 3/5 = 0.6 из ревью).

**S7 «будущая дата измерения»**: RHR с `resting_hr_observed_at` = завтра, sleep/HRV вчера, текущий TSB → фактор получает `observation_status="invalid"` и `reason="observation_in_future"`, попадает в `freshness.invalid` (а не в `unverified`), `intervention_eligible=false`, `intervention_confidence == 0.2`, `intervention_score is None`, gate закрыт.

Команды и ожидаемый результат:

    ./ai_trainer_env/bin/python -m pytest tests/smoke/test_readiness_model.py tests/smoke/test_readiness_snapshot_contract.py tests/smoke/test_readiness_conflicts.py tests/smoke/test_api_today.py tests/smoke/test_recovery_replan_loop.py tests/smoke/test_garmin_sync_service.py tests/smoke/test_readiness_today_freshness_ui_contract.py -q
    # ожидается: все passed, live-provider вызовов нет

    ./ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/ -W error::pytest.PytestReturnNotNoneWarning -q
    # ожидается: не больше падений, чем в baseline ЭТОГО окружения (см. Concrete Steps)

    ./ai_trainer_env/bin/python -m ruff check .
    npm --prefix web run contract:extract -- --check
    npm --prefix web run lint
    npm --prefix web run build

    # независимое чтение /api/today на изолированной фикстуре:
    ./ai_trainer_env/bin/python - <<'PY'
    # temp SQLite: вчерашние sleep/HRV, RHR без observation date, текущий TSB, качественная сессия
    # напечатать freshness/intervention_confidence/conflicts
    # сравнить COUNT(*) planning_checkpoints и provider-delivery записей до/после recovery-лупа
    PY

Падение вне затронутых модулей сначала воспроизводится на чистом `main` в отдельном worktree: воспроизводимое на baseline документируется как средовое, а не как регрессия.

## Idempotence and Recovery

Схема меняется аддитивно и идемпотентно: три nullable-колонки добавляются через существующие карты и ensure-функции (`_ensure_daily_health_columns`, `_ensure_training_status_columns`), повторный запуск безопасен, `CREATE TABLE` для свежих баз просто содержит новые колонки; для `training_status` обновляются и карта, и `_TRAINING_STATUS_COLUMN_ORDER`. История не переписывается: `NULL` в observation-колонке означает «дата измерения не подтверждена» и деградирует в `unverified`.

Version-qualified ownership идемпотентен: сравнение идёт «штамп предложения против константы кода», повторные прогоны ничего не меняют; при смене версии суперсессия затрагивает только `pending`, не трогает `applying` и не мутирует `recovery_evidence_heads`, поэтому политика #552 (transient `data_gap` не отменяет последнее полное evidence) сохраняется. Откат — обычный revert кода: новые колонки безвредны и не читаются старой версией, данные восстанавливать не нужно. Если после деплоя окажется, что провайдер не отдаёт дату измерения в используемом вызове, безопасный промежуточный шаг — оставить фактор `unverified` и показать его в UI с меткой «дата измерения неизвестна»; считать неподтверждённое измерение сегодняшним или снижать `MIN_CONFIDENCE` запрещено (это отменило бы AC2/AC4).

## Artifacts and Notes

### M1 (2026-09-10)

Frozen legacy baseline, снятый на `main` `72f69b4` до реализации (фикстура `_full_inputs()` из `tests/smoke/test_readiness_model.py`, `today=2026-07-09`): `score=76.5`, `status="strong"`, `confidence=1.0`, `as_of_date="2026-07-09"`, факторы `hrv=70.0 / resting_hr=85.0 / sleep=80.0 / training_readiness=80.0 / tsb=70.0`. После M1 те же числа проверяются тестом `test_legacy_aggregates_are_frozen_and_new_keys_are_additive`, то есть описательный контракт не сдвинулся.

RED: `./ai_trainer_env/bin/python -m pytest tests/smoke/test_readiness_model.py -q` на коммите `6238ba2` падал на сборе (`ImportError: cannot import name 'OBSERVATION_CONFIRMED_TODAY'`). GREEN после реализации: `19 passed` (9 существующих + 10 новых тестов M1).

Потребители legacy-полей (проверка аддитивности): `test_readiness_snapshot_contract.py`, `test_readiness_conflicts.py`, `test_readiness_bio_signals.py`, `test_readiness_plan_purity.py`, `test_api_today.py` — `80 passed`; `test_session_quality_forecast.py`, `test_api_session_quality_router_contract.py`, `test_api_recovery_analytics.py`, `test_signals_engine.py`, `test_comparable_sessions.py`, `test_coach_narrative_evidence_gate.py`, `test_today_snapshot_perf_gate.py` — `218 passed`. `ruff check` по изменённым файлам чист.

Отклонение от плана (записано в Decision Log): `_split_frame` возвращает не кортеж из пяти элементов, а frozen dataclass `FactorWindow` с двумя каналами — legacy (`value`, `as_of`, `age_days`, `stale`, `history`) и provenance (`observation_as_of`, `observation_age_days`, `observation_verified`). Публичный контракт `compute_readiness_today` при этом не менялся, только аддитивные ключи.

### M1 fix (2026-09-10, по delta-review)

Закрыты два нарушения инвариантов плана: будущая дата измерения больше не считается сегодняшней (`age_days < 0` → `observation_status="invalid"`, `reason="observation_in_future"`, фактор вне вмешательства), а provenance перестал влиять на замороженный legacy-расчёт — выбор строки, `as_of`, `stale` и окно базлайна снова строго по дате хранения.

Дифференциальный пробник `legacy_parity_probe.py` (импортирует `models.readiness` и сравнивает legacy-ключи: `score`, `status`, `as_of_date`, `confidence`, `missing_inputs` и по каждому фактору `key`, `score`, `raw_value`, `baseline`, `deviation`, `as_of`, `stale_input`, `source`) прогнан на `origin/main` `9a46087` в отдельном worktree и на ветке: **вывод побайтово идентичен на 7 фикстурах**, включая присланные ревьюером случаи — `prov_a` (более новая observation на старой stored-строке: main выбирает RHR 80 → score 40) и `prov_b` (stored сегодня / observed вчера: legacy `as_of`=сегодня, `stale_input`=false). Эти же числа закреплены тестом `test_legacy_selection_uses_stored_date_and_provenance_is_a_separate_channel`; future-observation — тестом `test_future_observation_is_not_intervention_eligible`.

RED: `99d4b82` падал на сборе (`ImportError: cannot import name 'INELIGIBLE_REASON_INVALID_OBSERVATION'`). GREEN: `tests/smoke/test_readiness_model.py` — `21 passed`; потребители (`readiness_snapshot_contract`, `readiness_conflicts`, `readiness_bio_signals`, `readiness_plan_purity`, `api_today`, `session_quality_forecast`, `api_recovery_analytics`, `signals_engine`, `coach_narrative_evidence_gate`) — `237 passed`; `ruff check` чист.

### M2 (2026-09-10)

RED: `tests/smoke/test_readiness_snapshot_contract.py` — четыре новых теста падали с `KeyError: 'freshness'` на ветке до реализации. GREEN: тот же файл + `test_recovery_response.py` — `49 passed`.

Что наблюдаемо в снапшоте (фикстура `_seed_full_readiness` без provenance-колонок, `M3` их ещё не заполняет): `freshness.state == "provisional"`, `confirmed_today == ["sleep"]`, `unverified == ["hrv", "resting_hr", "training_readiness"]`, `missing == ["tsb"]`, `intervention_confidence == 0.2`, `intervention_score == 82.0`, при этом **legacy-канал не сдвинулся**: `is_provisional is False` (presence-based), `confidence == 0.8`, `stale is False`. Пустая база даёт `freshness.state == "data_gap"`, `missing` из пяти ключей и `blocked_reason == "no_intervention_eligible_factors"`; восьмидневная база — `data_gap` при неизменном legacy `stale is True`/`status == "stale"`.

Сценарий `invalid` проверен сквозь реальную модель: тест `test_snapshot_keeps_invalid_observations_in_their_own_bucket` подменяет `compute_readiness_today` в модуле снапшота обёрткой, которая добавляет в health-frame `resting_hr_observed_at` = завтра, и требует отдельную корзину `freshness.invalid == ["resting_hr"]`, отсутствие ключа в `unverified`/`eligible_inputs` и `reason == "observation_in_future"` в `ineligible_inputs`.

`READINESS_SNAPSHOT_RULE_VERSION` повышен `readiness_snapshot_v2` → `readiness_snapshot_v3` (метаданные, поведенческих читателей нет); единственная литеральная проверка в `tests/smoke/test_recovery_response.py` переведена на импорт константы, чтобы будущие бампы не требовали правки теста.

### M3, срез 3.1 — provenance сна (2026-09-10; переработка после ревью P1)

RED: `tests/smoke/test_sleep_metric_provenance.py` — 11 падений, включая воспроизведение P1 (`test_rejected_provider_metric_does_not_change_accepted_provenance`: сохранён Garmin score=40/observed=вчера, входящий Intervals score=90 отклонён, а общая колонка перезаписывалась на сегодня). GREEN: `test_sleep_metric_provenance.py` (17) + `test_readiness_model.py` + `test_readiness_snapshot_contract.py` + `test_m4_intervals_wellness.py` + `test_issue_555_subjective_wellness.py` — `94 passed`.

Что покрыто тестами среза: `calendarDate` без timestamps и дата из timestamps дают `sleep_score_observed_at`/`total_sleep_observed_at` из payload (при `sleep_date is None` строка по-прежнему уедет под дату запроса — правда живёт в провенансе); payload без даты и невалидная `calendarDate` → `NULL`; повторный sync без даты не стирает известную дату; отклонённая метрика другого провайдера не меняет ни значение, ни source, ни provenance принятой; принятая метрика меняет все три вместе; score и duration имеют независимую provenance (duration-only апдейт двигает только свою, а `_sleep_factor` сообщает дату победившей метрики); `sync_wellness_batch` пишет provider-local `id` как дату наблюдения (и не трогает её при отклонённом апдейте), после чего снапшот видит `confirmed_today`; legacy-миграция теперь **явно требует** наличие обеих колонок и `NULL` в старых строках (ASR-MOD-3).

Дополнительно (P2): derived `sleep_score` (Garmin payload без нативного score) теперь получает дату payload, и это закреплено сквозным тестом processor → `sync_sleep_data` → `_sleep_factor` → `build_readiness_snapshot`: датированный derived score даёт `confirmed_today`, `intervention_confidence == 0.2` и непустой `intervention_score`; derived score без payload-даты остаётся `unverified` и непригодным. RED-прогон этих трёх тестов падал (в debug-выводе процессора видно отсутствие `sleep_score_observed_at` при заполненном `total_sleep_observed_at`).

Дифференциальный пробник `legacy_parity_probe.py` против `origin/main` `9a46087` — **идентично** (повторён после переработки; третий прогон за срез). `ruff check` по изменённым файлам чист.

### M3, срез 3.2 — provenance RHR (2026-09-10)

RED: новый `tests/smoke/test_rhr_observation_provenance.py` — 13 падений до реализации. GREEN: тот же файл — `13 passed`; контур `test_intervals_plan_delivery.py` — `21 passed` (delegate сохранил прежнее поведение).

Покрытие: `startTimeGMT = 2026-07-15T22:30:00.0` при `ATHLETE_TIMEZONE=Europe/Moscow` → `observedAt = 2026-07-16` (конверсия, а не срез UTC-строки); `calendarDate` не конвертируется; форма `allMetrics.metricsMap.WELLNESS_RESTING_HEART_RATE` читается; payload без даты и невалидная дата → `None`; процессор прокидывает `resting_hr_observed_at`; круг «persist → get_daily_health» и сохранение даты при повторном sync без даты; legacy-таблица `daily_health` мигрирует с новой колонкой и `NULL` в старых строках; отклонённый Intervals-RHR при primary=garmin не меняет ни значение, ни source, ни дату, а принятый Garmin-RHR меняет все три вместе; `sync_wellness_batch` пишет provider-local `id` как дату наблюдения (и не трогает её при отклонённом апдейте); датированный RHR доходит до снапшота как `confirmed_today`/`eligible`, недатированный — как `unverified`.

Дифференциальный пробник `legacy_parity_probe.py` против `origin/main` `9a46087` — **идентично**. `ruff check` по изменённым файлам чист.

Остальные артефакты (M3.3–M6) появятся по мере реализации: независимое чтение `/api/today`, diff'ы аддитивной миграции, выдержки из `ts_contract.json`.

## Interfaces and Dependencies

`models/readiness.py`:

    OBSERVATION_CONFIRMED_TODAY = "confirmed_today"
    OBSERVATION_OUTDATED = "outdated"
    OBSERVATION_UNVERIFIED = "unverified"
    OBSERVATION_INVALID = "invalid"          # дата измерения позже anchor (fail closed)
    OBSERVATION_MISSING = "missing"          # фактора нет вовсе (для контракта M2/M5)
    PRIMARY_RECOVERY_KEYS = ("sleep", "hrv", "resting_hr")
    INTERVENTION_BLOCKED_NO_PRIMARY = "no_confirmed_today_primary_recovery_measurement"
    INTERVENTION_BLOCKED_NO_ELIGIBLE = "no_intervention_eligible_factors"

    @dataclass(frozen=True)
    class FactorWindow:
        # legacy-канал (заморожен, ровно как до #557): выбор значения, as_of и
        # окно базлайна — строго по дате СТРОКИ ХРАНЕНИЯ
        value: float | None
        as_of: str | None
        age_days: int | None
        stale: bool
        history: pd.Series
        # provenance-канал выбранной строки: даты измерения из payload
        observation_as_of: str | None = None
        observation_age_days: int | None = None
        observation_verified: bool = False

    def _split_frame(frame, column, anchor, max_age, *,
                     observation_column=None, stored_date_is_observation=False) -> FactorWindow
        # выбранная строка НЕ переключается на observation-дату; дубли строк
        # с разными query dates не схлопываются в M1 (дедупликация отложена на M3+)

    def _observation_status(*, verified: bool, age_days: int | None) -> str
        # не verified → "unverified"; age < 0 → "invalid"; age == 0 → "confirmed_today"; иначе "outdated"

    def compute_readiness_today(sleep_df, hrv_df, health_df, training_df, activities_df,
                                *, today, max_value_age_days=STALE_AFTER_DAYS) -> dict
        # legacy-поля БЕЗ изменений: score, confidence, stale-производные, as_of_date, drivers(базовые)
        # аддитивно:
        #   "intervention_score": float | None      # None без пригодного primary
        #   "intervention_confidence": float        # eligible / len(FACTOR_WEIGHTS)
        #   "eligible_inputs": list[str]
        #   "ineligible_inputs": list[dict]         # [{"key","observation_status","reason"}],
        #                                           # reason ∈ {observation_date_unverified,
        #                                           #           observation_outdated, observation_in_future}
        #   "intervention_blocked_reason": str | None
        # каждый фактор: + "observation_as_of", "age_days" (возраст наблюдения),
        #                "observation_status", "intervention_eligible", "evidence_kind"
        #                (M3+ добавит "intervention_score_input" — источник для intervention_score,
        #                 в M1 равен "score"; legacy "score"/"baseline"/"deviation" не меняются)
        # каждый driver: + "as_of", "observation_as_of", "age_days", "observation_status",
        #                  "intervention_eligible", "evidence_kind", "source"

`services/observation_provenance.py` (новый; импортирует только `utils/athlete_time.py`):

    def observation_local_date(value, *, source: Literal["utc", "athlete_local"]) -> date | None
        # source="utc": ISO / epoch-ms / datetime → tz-aware (naive := UTC, семантика Garmin *GMT)
        #               → Settings.ATHLETE_TIMEZONE → календарная дата
        # source="athlete_local": calendarDate / startTimeLocal / sleep_date → дата как есть
        # невалидное значение или неизвестная зона → None (фактор unverified)

`utils/athlete_time.py` (новый нейтральный модуль; канонический `athlete_local_date(observed_at_utc)` переезжает из `services/intervals_plan_delivery.py`, где остаётся delegate с прежней сигнатурой и записью в `__all__`).

`services/readiness_snapshot.py` (аддитивно; legacy-ключи не меняются):

    "freshness": {
        "state": "fresh" | "provisional" | "data_gap",
        "anchor": "YYYY-MM-DD",
        "confirmed_today": [str], "outdated": [str], "unverified": [str],
        "invalid": [str],          # дата измерения позже anchor; отдельная корзина, не слита с unverified
        "missing": [str],
        "intervention_eligible": [str],
        "blocked_reason": str | None,
    }
    "intervention_score": float | None
    "intervention_confidence": float
    "eligible_inputs": [str]
    "ineligible_inputs": [dict]
    # stale, confidence, source_completeness, is_provisional, score — прежняя семантика

`models/readiness_conflicts.py`:

    READINESS_CONFLICT_RULE_VERSION = "readiness_conflicts_v2"
    # detect_readiness_conflicts: score = readiness.get("intervention_score");
    # confidence = readiness.get("intervention_confidence");
    # обязательное пригодное primary-измерение; отчёт получает "rule_version" и "freshness"

`models/recovery_response.py`: `READINESS_SNAPSHOT_RULE_VERSION = "readiness_snapshot_v3"` (метаданные).

`data/garmin_client.py::_normalize_rhr_payload` → `{'restingHeartRate': N, 'observedAt': 'YYYY-MM-DD' | None}` (порядок полей: `startTimeGMT`, `startTimeLocal`, `timestamp`, `calendarDate`, `date`).

`data/data_processor_phase1.py::process_daily_health_data` → `processed_data['resting_hr_observed_at']`; `process_training_status_data` → `training_readiness_observed_at`.

`services/sync.py`: `_collect_phase1_hrv` → `rmssd_observed_at`; `_collect_training_status_data` → athlete-local ключ строки вместо `datetime.now()` и `training_readiness_observed_at` из payload.

`data/database.py`:

    _DAILY_HEALTH_COLUMN_TYPES = { ..., 'resting_hr_observed_at': 'TEXT' }
    _HRV_COLUMN_TYPES = { 'rmssd_source': "TEXT DEFAULT 'legacy_unknown'",
                          'rmssd_observed_at': 'TEXT' }
    _TRAINING_STATUS_COLUMN_TYPES = { ..., 'training_readiness_observed_at': 'TEXT' }
    _TRAINING_STATUS_COLUMN_ORDER = [ ..., 'training_readiness_observed_at' ]   # путь записи

    def supersede_incompatible_recovery_proposals(
        self, current_rule_version, *, compatible_rule_versions=()
    ) -> int
        # BEGIN IMMEDIATE; выбрать action='recovery_replan' AND status='pending';
        # params_json разбирается в Python (без зависимости от JSON1-расширения SQLite);
        # штамп отсутствует ИЛИ не входит в {current} | set(compatible) → status='superseded',
        # result_json.reason='superseded_by_rule_version_change'; head не мутируется

    def claim_current_recovery_proposal(
        self, proposal_id, *, current_rule_version, compatible_rule_versions=()
    )
        # + независимый guard по тому же контракту совместимости, что и у sweep;
        #   версии передаются аргументами (data/ не импортирует models/);
        #   несовместимый штамп → state="superseded" с тем же reason,
        #   без чекпойнтов и provider-вызовов

`api/routers/decisions.py::approve_proposal` — production-вызов claim'а: передаёт `current_rule_version=READINESS_CONFLICT_RULE_VERSION` и `compatible_rule_versions=RECOVERY_EVIDENCE_COMPATIBLE_RULE_VERSIONS` из `models/readiness_conflicts.py`; при `state="superseded"` отвечает 409 без применения, чекпойнтов и provider-вызовов.

`api/recovery_replan_loop.py`: `_proposal_payload` штампует `params/preview["rule_version"]`; `run_recovery_replan_loop` вызывает суперсессию несовместимых версий на каждом прогоне (включая `data_gap`) до логики публикации; `_fingerprint` включает `rule_version`.

`api/today_snapshot.py::_project_readiness` — прокидывает `freshness`, `intervention_score`, `intervention_confidence`, `eligible_inputs`, `ineligible_inputs`, `intervention_blocked_reason` и обогащённые `drivers`/`factors`.

`web/lib/types.ts` — `ReadinessObservationStatus`, `ReadinessFactor`, `ReadinessDriver`, `ReadinessFreshness` + новые nullable-поля `ReadinessSnapshot`; артефакт перегенерируется `npm --prefix web run contract:extract`.

Зависимости: `pandas` (уже используется), `zoneinfo` через существующий `athlete_local_date`; новых внешних библиотек нет; live-провайдер в тестах не вызывается.

## Risks and Mitigations

Переопределение legacy-полей было бы breaking change для `session_quality_forecast`, `recovery_analytics`, `recovery_response`, `coach_narrative_evidence`, `comparable_sessions` и `api/session_quality_forecast` — поэтому поля заморожены, а fail-closed живёт в gate; на каждого читателя пишется regression-тест, что его поведение не изменилось.

Несовместимость `rule_version` при деплое инвалидирует ранее созданные pending-предложения (штамп отсутствует). Это и есть AC6, но должно быть явно описано в PR и issue-комментарии; audit сохраняется (неизменяемые `recovery_decisions.report_json` несут версию отчёта). Escape hatch согласован с контрактом guard: `RECOVERY_EVIDENCE_COMPATIBLE_RULE_VERSIONS` — единственный способ оставить предложение claimable под новой версией, и он расширяется только вместе с записью в Decision Log и доказательством неизменности семантики. Обещания «список совместимых версий когда-нибудь потом» без реализации нет: sweep и claim принимают множество совместимых версий с самого начала.

Ужесточение gate может подавить легитимные конфликты при реально свежих данных: обязателен контрольный S3 с числовым сравнением с baseline, плюс S2 (0.4) как граница.

Если провайдер не отдаёт observation date, фактор навсегда остаётся `unverified` и не влияет на intervention: это безопасно, но снижает чувствительность. Митигация — метка в UI и запись в `Artifacts and Notes` о фактических полях payload, встреченных на реальных данных (без публикации персональных значений).

## Non-goals

Не меняем factor bands, 28-дневные baseline-формулы и 90-дневную TSB/Banister-математику. Не считаем TSB устаревшим только из-за отсутствия сегодняшней активности. Не смешиваем subjective wellness с measured readiness (#555 уже влито отдельно). Не auto-apply план и не убираем human confirmation. Не удаляем и не переписываем исторические readiness snapshots, decisions, proposals и checkpoints. Не делаем live-provider вызовов в тестах и не публикуем персональные health-метрики. Не меняем правила выбора downgrade/transfer и materialization тренировок. Не трогаем severity-матрицу — меняется только вход в неё. Не переопределяем смысл существующих публичных полей контракта.

## Change log

- v1 (2026-09-10): первая редакция плана (ADR-подход: per-factor eligibility, interception confidence, provenance RHR/HRV, rule version в fingerprint). Не публиковалась.
- v2 (2026-09-10): исправления по результатам delta-review.
  P1-1 (AC6): механизм заменён на version-qualified ownership — штамп `rule_version` в предложении, независимый guard в `claim_current_recovery_proposal`, явная атомарная суперсессия `supersede_incompatible_recovery_proposals`, вызываемая и на `data_gap`-прогонах; сохранена политика #552 и её тест; добавлены race-тест и тест инвалидации при `data_gap`.
  P1-2 (аддитивность): legacy `confidence`/`stale`/`score`/`source_completeness` заморожены; новые `intervention_confidence`/`intervention_score`/`freshness`; перечислены все текущие читатели legacy-полей и зафиксировано, что мигрирует только gate, а на остальных — regression-тесты.
  P1-3 (provenance `training_readiness`): добавлен `training_readiness_observed_at`, ключ строки training status перестаёт быть `datetime.now()`, фактор `unverified` без подтверждённой даты; отмечено, что нужно менять и карту миграции, и `_TRAINING_STATUS_COLUMN_ORDER`.
  P2 (числа): сценарии разделены — S1 «нет ночных данных, RHR без даты» даёт `0.2`, S2 «RHR подтверждён сегодня + TSB» даёт `0.4`; добавлен S6 «старый device readiness» как регрессия сценария 3/5 = 0.6.
  Дополнительно: observation date переводится в `ATHLETE_TIMEZONE` (UTC-поля через `athlete_local_date`, athlete-local поля как есть), дедупликация повторов observation при разных query dates заявлена (в v3.1 отменена — см. ниже); добавлен раздел `Outcomes & Retrospective`; пункт создания плана отмечен выполненным с датой; baseline'ы разделены (smoke vs contributor-safe) и сняты в изолированном worktree с оговоркой про средовой фейл занятого порта.
- v3 (2026-09-10): исправления по результатам второго delta-review (`c57cfcf..67fced7`).
  P1 (версия не доведена до approval API): в M4 и в интерфейсы добавлен `api/routers/decisions.py::approve_proposal` как production-вызов; `claim_current_recovery_proposal` и `supersede_incompatible_recovery_proposals` принимают `current_rule_version` и `compatible_rule_versions` аргументами, поэтому `data/` не импортирует доменные константы из `models/`; добавлен API-тест на 409 без чекпойнтов и provider-вызовов.
  P2 (семантика observation helper'а): у `observation_local_date` появился обязательный keyword `source: Literal["utc","athlete_local"]` (без догадок о природе значения); канонический timezone-хелпер вынесен в нейтральный `utils/athlete_time.py`, а `services/intervals_plan_delivery.athlete_local_date` остаётся тонким delegate, поэтому ingest не зависит от delivery-слоя и существующие импортеры/тесты не меняются.
  P2 (неиспользуемая head-колонка): `recovery_evidence_heads.rule_version` убрана из плана; audit-провенанс версии несут неизменяемые `recovery_decisions.report_json` и штамп `params`/`preview` предложения; зафиксировано, что `recovery_evidence_heads` читается только внутри `data/database.py`.
  P3 (владелец `_proposal_payload`): исправлено — штамп версии ставит `api/recovery_replan_loop.py::_proposal_payload`, а не `data/database.py`; формирование API-payload не переносится в слой хранения.
  Escape hatch: обещание согласовано с контрактом guard — совместимость определяется множеством `{current} | set(compatible)` в обоих методах с самого начала, по умолчанию строгое равенство.
- v3.1 (2026-09-10): исправления по итогам ревью M1 (два блокирующих нарушения собственных инвариантов плана).
  P1 (будущая дата): `intervention_eligible` теперь только при `observation_age_days == 0`; измерение из будущего получает `observation_status="invalid"` и `reason="observation_in_future"` (fail closed) с regression-тестом.
  P2 (provenance менял замороженный расчёт): `FactorWindow` разделён на legacy- и provenance-канал; выбор значения, `as_of`, `stale`, окно базлайна снова строго по дате хранения, даты измерения только описывают выбранную строку; добавлен дифференциальный пробник против `origin/main` на 7 фикстурах (идентично) и тест с эталонными числами main для случаев «новая observation на старой stored-строке» и «stored сегодня / observed вчера».
  Уточнение: прежняя формулировка дедупликации (ряд по observation-дате) отменена — она меняла замороженные агрегаты; дедуплицированный baseline для интервенционного score отложен на M3+ вместе с заполнением provenance-колонок.
- v3.2 (2026-09-10, docs-only amend по ревью M1): устранены взаимоисключающие инструкции.
  P2-1 (старые решения): набор статусов в первой Decision-записи расширен пятым значением `invalid`; отменённая дедупликация по observation key помечена `SUPERSEDED в v3.1` с причиной (расхождение с `main` на фикстуре `prov_a`), вместо неё действует запись об интервенционном-only варианте с заранее названным полем `intervention_score_input`.
  P2-2 (Interfaces): сигнатура `_split_frame` заменена на `FactorWindow` с двумя каналами и пометкой, что legacy-выборка идёт по дате хранения, а дубли строк не схлопываются; добавлены `OBSERVATION_INVALID`, `observation_as_of` и `intervention_score_input`.
  P2-3 (контракт M2): в `freshness` добавлена отдельная корзина `invalid: [str]`, правило `state` явно относит `invalid` к `provisional`, в M5 добавлена метка «некорректная дата измерения», в Acceptance — сценарий S7.
  Механически: заголовок ревизии обновлён до v3.1/v3.2, описание M1 и покрытия тестов больше не заявляют выполненную дедупликацию.
- v3.3 (2026-09-10): приёмка M1/M2 и первый срез M3.
  M2 принят ревьюером без блокирующих замечаний (независимо: `49 passed`, матрица `fresh`/`provisional`/`data_gap`, `invalid` отдельной корзиной, legacy-поля не переопределены).
  M3, срез 3.1 (provenance сна): добавлена nullable-колонка `sleep_data.sleep_observed_at`, процессор пишет дату только из payload, sync и схема обновлены, модель читает колонку вместо удалённого escape hatch'а `stored_date_is_observation`; RED по трём слоям → GREEN `48 passed`, потребители `267 passed`, legacy parity повторён (идентично), ruff чист.
  Шапка документа приведена в соответствие с Progress (было v3.1 и «M2–M6 не начаты») — замечание P3 предыдущего ревью закрыто.
- v3.4 (2026-09-10): переработка среза 3.1 по ревью (P1 + P2 + P3).
  P1 (provenance обновлялась без принятия метрики): колонка разделена на метрико-скоупные `sleep_score_observed_at`/`total_sleep_observed_at`, запись перенесена внутрь ветвей принятия метрики в обоих writer'ах, добавлены collision-тесты (отклонённый чужой провайдер, атомарное принятие, независимость score/duration) и тесты пути Intervals.icu (`id` → дата наблюдения → снапшот).
  P2 (тест миграции не проверял колонку): тест теперь требует обе колонки среди мигрированных и читает `NULL` старой строки.
  P3 (устаревший комментарий модели): комментарий у `_sleep_factor` переписан на новую семантику (дата хранения — это дата запроса, датой наблюдения считается только явная provider-дата), чтобы следующий реализатор не вернул удалённый escape hatch.
  Процесс: срезы 3.2 (RHR) и 3.3 (HRV/training_readiness) выполняются раздельно и с проверкой обоих источников — Garmin и Intervals.icu.
- v3.6 (2026-09-10): срез 3.2 — provenance RHR (принят к исполнению после приёмки 3.1).
  Добавлены `utils/athlete_time.py` (канонический `athlete_local_date`, delivery остаётся delegate'ом) и `utils/observation_provenance.py::observation_local_date(value, *, source)`; `_normalize_rhr_payload` извлекает `observedAt`, процессор прокидывает его, `daily_health.resting_hr_observed_at` пишется атомарно с принятой метрикой в обоих writer'ах; collision-тесты и legacy-миграция покрыты; legacy parity повторён (идентично). Отклонение от плана: helper'ы переехали из `services/` в `utils/`, чтобы ingest не зависел от delivery-слоя (см. Decision Log).
- v3.5 (2026-09-10): закрытие P2 среза 3.1.
  P2 (derived sleep score терял provenance): назначение `sleep_score_observed_at`/`total_sleep_observed_at` перенесено после ветки derivation, поэтому derived score датирован; добавлены три сквозных теста (датированный derived score → `confirmed_today`/eligible, derived score без payload-даты → `unverified`, и путь до снапшота с `confirmed_today`). Тесты среза: `20 passed` в файле provenance сна, `97 passed` в контуре sleep/model/snapshot/wellness, legacy parity повторён (идентично).
