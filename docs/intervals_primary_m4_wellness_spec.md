# M4: Intervals.icu wellness → локальная readiness, Сон и HRV

This ExecPlan is a living document. The sections `Progress`, `Surprises &
Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to
date as work proceeds. This document must be maintained in accordance with
`.agent/PLANS.md`.

## Purpose / Big Picture

После M1–M3 атлет без Garmin уже может синхронизировать активности из
Intervals.icu и построить план, но recovery-поверхность остаётся пустой:
`/today` не видит HRV, сон и пульс покоя, а страницы `/sleep` и `/hrv` всё ещё
предлагают синхронизировать Garmin. M4 проводит дневные wellness-записи
Intervals.icu в существующие канонические таблицы и локальную readiness-модель.

Наблюдаемый результат: при единственном настроенном Intervals.icu один явный
sync наполняет активности и wellness. После него `/today` рассчитывает readiness
локально, `/sleep` показывает длительность/оценку сна с подписью Intervals.icu,
а `/hrv` показывает rMSSD и его источник. Ни provider readiness, ни provider
CTL/ATL не подменяют локальные расчёты.

## Progress

- [x] (2026-07-27) Issue #273, родительский ExecPlan, ADD/ASR и текущие
  storage/readiness/API/web-контракты прочитаны.
- [x] (2026-07-27) Официальная OpenAPI-схема Intervals.icu wellness сверена;
  mapping и fail-closed правила зафиксированы ниже.
- [x] (2026-07-27) RED-гейты клиента, mapping, схемы, транзакции, приоритета
  источников, вертикали sync, readiness и API/UI подтверждены: первый контракт
  падает на отсутствующем production `list_wellness`.
- [ ] GREEN: client + чистый normalizer + атомарный wellness batch и доменный
  cursor.
- [ ] GREEN: readiness/provenance API и source-agnostic web.
- [ ] Полная regression, lint/build и изолированная browser-приёмка.
- [ ] PR с `Closes #273`, зелёными checks и `status: ready to merge`.

## Surprises & Discoveries

- Observation: OpenAPI различает `hrv` и `hrvSDNN`; каноническая модель
  AI Trainer ожидает rMSSD.
  Evidence: `Wellness.hrv` и `Wellness.hrvSDNN` — отдельные поля; официальный
  Intervals.icu forum прямо называет `hrv` rMSSD.

- Observation: Intervals wellness — дневная запись с локальной датой, а не
  timestamp сна.
  Evidence: endpoint описывает `id` как local ISO-8601 day, а диапазон
  `oldest/newest` — локальные даты.

- Observation: текущие canonical recovery-таблицы имеют разную гранулярность
  provenance: sleep score уже хранит source, RMSSD/resting HR/duration сна — нет.
  Evidence: `sleep_data.sleep_score_source` существует, а
  `hrv_data.rmssd`, `daily_health.resting_hr` и
  `sleep_data.total_sleep_minutes` не имеют парных source-колонок.

- Observation: существующие `sync_hrv_data` и `sync_sleep_data` заменяют весь
  ряд и могут обнулить метрики другого источника отсутствующими ключами.
  Evidence: unconditional `UPDATE ... field=?` для всех колонок.

## Decision Log

- Decision: `Wellness.id` — каноническая локальная дата атлета
  `YYYY-MM-DD`; её не преобразуем в UTC.
  Rationale: provider не отдаёт время измерения, а локальные canonical-таблицы
  уже индексированы дневной датой. Выдуманный UTC timestamp создаст ложную
  точность и сдвиги суток.
  Date/Author: 2026-07-27 / Codex.

- Decision: `Wellness.hrv` маппится в `hrv_data.rmssd` в миллисекундах;
  `hrvSDNN` не является fallback.
  Rationale: rMSSD и SDNN — разные метрики. Подмена испортит персональный
  baseline и readiness.
  Date/Author: 2026-07-27 / Codex.

- Decision: `sleepSecs` преобразуется в канонические минуты сна;
  `sleepScore` сохраняется как provider score 0–100. `sleepQuality` 1–4 не
  преобразуется в score, фазы сна не выдумываются.
  Rationale: эти шкалы неэквивалентны, а API не предоставляет стандартные
  deep/light/REM поля.
  Date/Author: 2026-07-27 / Codex.

- Decision: `restingHR` маппится в `daily_health.resting_hr`. `readiness`,
  `ctl`, `atl`, `rampRate`, `ctlLoad`, `atlLoad` не запрашиваются и не
  импортируются.
  Rationale: readiness и CTL/ATL остаются локальными каноническими расчётами;
  provider-значения нельзя смешивать с нашей методологией.
  Date/Author: 2026-07-27 / Codex.

- Decision: provenance хранится по метрике, не по дневной строке:
  `rmssd_source`, `resting_hr_source`, `total_sleep_source` и существующий
  `sleep_score_source`.
  Rationale: один день может содержать Garmin-фазы сна, Intervals-длительность
  и другой источник HRV. Row-level source был бы ложным.
  Date/Author: 2026-07-27 / Codex.

- Decision: `PRIMARY_WELLNESS_SOURCE` определяет детерминированный приоритет
  Garmin/Intervals и по умолчанию наследует `PRIMARY_ACTIVITY_SOURCE`.
  Primary заменяет secondary независимо от порядка прихода; secondary
  заполняет пропуск, но не перетирает primary. Повтор своего источника
  обновляет метрику.
  Rationale: last-write-wins делает два одинаковых sync в другом порядке
  разными и ломает Intervals-primary.
  Date/Author: 2026-07-27 / Codex.

- Decision: один чистый wellness chunk, все его canonical-записи и курсор
  `(intervals, wellness)` фиксируются одной SQLite-транзакцией.
  Rationale: отдельные commits по HRV/sleep/health могли оставить cursor за
  частично записанным recovery-днём. На ошибке весь chunk и cursor
  откатываются; уже чистые предыдущие chunks остаются.
  Date/Author: 2026-07-27 / Codex.

- Decision: provider training readiness остаётся опциональным дополнительным
  фактором, а completeness readiness определяется source-agnostic тройкой
  `sleep + hrv + resting_hr`.
  Rationale: Intervals-only атлет с полным recovery-набором не должен всегда
  считаться provisional только из-за отсутствия Garmin-specific score.
  Date/Author: 2026-07-27 / Codex.

## ASR / Risk Traceability

M4 затрагивает ASR-REL-2, ASR-REL-3, ASR-MOD-2, ASR-MOD-3 и ASR-PERF-3.
ASR-REL-2 обеспечивается graceful partial readiness и отсутствием выдуманных
метрик. ASR-REL-3 обеспечивается атомарностью wellness chunk + cursor и
fail-closed malformed provider payload. ASR-MOD-3 обеспечивается аддитивными
source-колонками и legacy defaults без переписывания существующих строк.
ASR-PERF-3 обеспечивается отдельным `(intervals, wellness)` high-water cursor.
ASR-MOD-2 обеспечивается аддитивным provenance API, который web читает без
provider-specific бизнес-логики.

## Context and Orientation

`services/intervals_icu.py` — HTTP-клиент провайдера. `services/intervals_sync.py`
уже синхронизирует activities и возвращает результат для
`api/sync_jobs.py`. `services/sync_cursor.py` содержит строгий ISO-date cursor и
окна sync. `data/database.py` хранит `hrv_data`, `sleep_data`, `daily_health` и
`sync_cursors`. `services/readiness_snapshot.py` читает эти таблицы, а чистая
формула живёт в `models/readiness.py`. API-проекции находятся в
`api/routers/sleep.py` и `api/routers/hrv.py`; web-поверхности — в
`web/app/sleep/page.tsx`, `web/app/hrv/page.tsx` и dashboard SleepWidget.

Wellness record — один объект Intervals.icu за локальный календарный день.
Clean chunk — ответ, который является list, все элементы которого являются
mapping с точной датой и валидными значениями всех присутствующих канонических
полей. Dirty chunk — transport/provider/malformed/normalization failure; его
cursor не двигается.

## Provider Mapping Contract

Входные поля и каноническая проекция:

| Intervals.icu | Канон | Правило |
|---|---|---|
| `id` | `date` | raw string, строго `YYYY-MM-DD`, календарно валидна |
| `hrv` | `hrv_data.rmssd` | finite number, `> 0`, ms |
| `hrvSDNN` | — | намеренно игнорируется |
| `sleepSecs` | `sleep_data.total_sleep_minutes` | finite number, `>= 0`, секунды → минуты |
| `sleepScore` | `sleep_data.sleep_score` | finite number, `0..100` |
| `sleepQuality` | — | намеренно не преобразуется |
| `restingHR` | `daily_health.resting_hr` | integer, `20..250`, bpm |
| `readiness`, `ctl`, `atl`, load fields | — | не запрашиваются/не импортируются |
| `updated` | diagnostic provenance | optional ISO timestamp; не определяет canonical day |

`null` означает отсутствие метрики и не очищает сохранённое значение. Unknown
fields игнорируются. Невалидное присутствующее canonical-поле делает весь chunk
dirty: иначе cursor перескочит потерянную метрику.

## Behavior Scenarios

    Given пустая SQLite и только Intervals credentials
    When пользователь запускает source=intervals sync
    Then activities и wellness получают независимые cursors
    And HRV, sleep и resting HR видны в локальных API
    And readiness рассчитан без Garmin provider-readiness

    Given Intervals wellness содержит hrv=42 и hrvSDNN=77
    When запись нормализуется
    Then canonical rmssd равен 42
    And SDNN не подменяет RMSSD

    Given clean activity chunk и malformed wellness chunk
    When запускается общий Intervals sync
    Then activity cursor продвигается
    And wellness cursor не продвигается
    And job имеет partial status и понятный notice

    Given запись wellness затрагивает HRV, sleep и resting HR
    When SQLite падает на одном из canonical upserts
    Then ни одна метрика chunk и его cursor не фиксируются
    And повтор безопасно загружает весь chunk

    Given primary=intervals и один день пришёл из Garmin и Intervals
    When источники синхронизируются в любом порядке
    Then canonical mapped metrics и metric_source одинаковы
    And Garmin-only sleep stages не стираются отсутствующими Intervals полями

    Given Intervals-only recovery содержит sleep, rMSSD и resting HR
    When строится readiness snapshot
    Then recovery completeness равна 1.0
    And snapshot не provisional только из-за отсутствия Garmin readiness
    And CTL/ATL считаются локально по canonical activities

## Plan of Work

Сначала добавить RED smoke suite `tests/smoke/test_m4_intervals_wellness.py` и
web contract suite. Затем расширить `config/settings.py` и аддитивную schema в
`data/database.py`; legacy rows сохраняют `legacy_unknown`. В data-layer
реализовать один атомарный batch writer с metric-level precedence и cursor
commit.

После schema добавить чистый `services/wellness_ingest.py` и fail-closed
`IntervalsICUClient.list_wellness`. Расширить `sync_intervals_data`: activities
и wellness обрабатываются независимо, поэтому ошибка одного домена не скрывает
успех другого; общий result складывает notices и recovery counts.

Затем сделать readiness source-agnostic: Garmin provider score остаётся
дополнительным фактором, а основная completeness — sleep/HRV/RHR. API сна и HRV
аддитивно возвращают source, web показывает Intervals.icu и не рисует пустые
sleep stages. Наконец обновить родительский ExecPlan и ASR catalog.

## Concrete Steps

Рабочая директория:

    /private/tmp/ai-trainer-m4-wellness

Основные проверки:

    source /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/activate
    python -m pytest tests/smoke/test_m4_intervals_wellness.py -q
    python -m pytest -m "not live and not debug" tests/
    npm --prefix web run lint
    npm --prefix web run build

Browser acceptance запускается на временной SQLite и свободных API/web портах;
локальные `:8000/:3000` и `ai_trainer.db` пользователя не затрагиваются.

## Validation and Acceptance

M4 принят, когда contributor-safe tests и полный offline contour зелёные,
web lint/build зелёные, а browser scenario на временной БД показывает:
readiness на Today, `Intervals.icu` у сна и HRV, отсутствие фиктивных стадий сна,
и отдельный wellness cursor. Повтор sync не создаёт дублей и не откатывает
cursor. PR закрывает #273 и получает `status: ready to merge`.

## Idempotence and Recovery

Schema migration только добавляет nullable/default source-колонки. Повторная
инициализация безопасна. Sync cursor монотонный. Повтор provider-window
идемпотентно обновляет те же дневные PK. Dirty chunk не двигает cursor.
`clear_all_data()` уже очищает все domain cursors вместе с canonical recovery
таблицами, поэтому следующий sync делает bootstrap.

## Interfaces and Dependencies

В `services/intervals_icu.py`:

    IntervalsICUClient.list_wellness(oldest: date, newest: date) -> list[dict[str, Any]]

В `services/wellness_ingest.py`:

    normalize_intervals_wellness(row: Mapping[str, Any]) -> WellnessRecord

В `data/database.py`:

    Database.sync_wellness_batch(
        records: Sequence[Mapping[str, Any]],
        *,
        provider: str,
        cursor_value: str,
        primary_source: str,
    ) -> dict[str, Any]

В `services/intervals_sync.py` `IntervalsSyncResult` получает аддитивные
wellness counts/cursor/halted-поля; старые activity counts сохраняют смысл.

Новых зависимостей нет: stdlib `datetime`, `math`, `zoneinfo`, существующий
SQLite/Pandas/FastAPI/Next.js стек.

## Outcomes & Retrospective

Заполняется после реализации и browser-приёмки.
