# ExecPlan: канонический дневной decision snapshot (issue #174)

Этот ExecPlan — living document. Разделы `Progress`, `Surprises & Discoveries`, `Decision Log` и `Outcomes & Retrospective` обновляются по ходу работы согласно `.agent/PLANS.md`.

## Purpose / Big Picture

Экран `/today` уже отвечает на вопрос «что делать сегодня?», но собирает ответ прямо в FastAPI-роутере из нескольких источников с разными жизненными циклами. Из-за этого реальный конфликт готовности без созданного предложения маскируется под «План в силе», вчерашняя тренировка показывается как простая сумма активностей без plan-vs-actual контекста, а shadow-прогноз качества сессии вообще не попадает в дневной снимок.

После этой работы один headless-сборщик будет возвращать версионированный дневной decision snapshot. В нём совместно, но без смешивания семантики, присутствуют: каноническая готовность; исход salience-gate и его evidence; активная плановая сессия с уже существующей структурированной prescription из #173; текущее или устаревшее предложение Recovery Replan; последний подходящий shadow-прогноз; reconciliation плана и факта за вчера; явное primary action. FastAPI только отдаёт этот снимок, а Next.js визуализирует его.

Пользовательский эффект проверяется пятью состояниями: `no_plan`, `data_gap`, `conflict_actionable`, `conflict_unactionable`, `silence`. В частности, конфликт без безопасного предложения больше никогда не называется тишиной: экран честно объясняет, что конфликт обнаружен, но применимого варианта нет. Shadow-прогноз помечен как наблюдение и не меняет ни состояние, ни рекомендацию.

## Progress

- [x] (2026-07-13 17:24Z) Прочитаны issue #174, аудит Claude Code, исходный `/api/today`, Recovery Replan, readiness/gate, forecast, proposal/checkpoint persistence, reconciliation, web `/today` и существующие тесты.
- [x] (2026-07-13 17:24Z) Подтверждено, что #173 уже добавил persisted structured prescription и checkpoint fallback; этот код переносится без изменения доменной семантики.
- [ ] Закоммитить этот ExecPlan отдельным docs-коммитом.
- [x] (2026-07-13 17:28Z) Добавлены контрактные BDD-тесты; красная фаза: `8 failed, 2 passed` на отсутствующих v2-полях/состояниях, без production-изменений.
- [x] (2026-07-13 17:35Z) Реализован headless `today_decision_snapshot_v2`; FastAPI-роутер сокращён до адаптера. Focused: `14 passed`; smoke: `563 passed, 1 skipped`.
- [x] (2026-07-13 17:43Z) Next.js `/today` обновлён для пяти состояний, gate evidence, shadow forecast и reconciliation-вчера; lint/build зелёные.
- [x] (2026-07-13 17:46Z) Пройдены focused 14, smoke 563+1 skip, broad 606+6 skips+24 deselected, compileall, touched-file Ruff, diff check, web lint/build и живая приёмка.
- [x] (2026-07-13 17:50Z) Ветка опубликована, draft PR #183 открыт с `Closes #174`; первый CI-head зелёный.

## Surprises & Discoveries

- Observation: структурированная сессия уже является частью сегодняшнего API и умеет деградировать к checkpoint-template, если gate не вернул сессию.
  Evidence: `api/routers/today.py::_day_session` проецирует `template_id`, `stimulus`, `steps`, `legs` и использует плановый день из checkpoint при `data_gap`; smoke-тест `test_today_projects_catalog_prescription` закрепляет контракт.

- Observation: текущий каскад считает конфликтом только сочетание `outcome == "conflict"` и существующего active proposal.
  Evidence: `api/routers/today.py` в ветке выбора состояния иначе проваливается в `silence`. Поэтому protected-date, дедуп, непредставимая сессия или ошибка создания proposal дают ложное «План в силе».

- Observation: терминально обработанный пользователем конфликт сознательно возвращается в тишину.
  Evidence: smoke-тест с `rejected` proposal ожидает `silence`. Новый `conflict_unactionable` не должен снова тревожить пользователя после `rejected`, `approved` или `rolled_back`; `failed` остаётся неразрешённым и потому неactionable.

- Observation: forecast может иметь несколько immutable revisions для одной цели в течение дня.
  Evidence: `session_quality_predictions` хранит `revision`, `created_at` и target identity; resolver выбирает последнюю допустимую ревизию по `(created_at, id)`, а не по номеру, пришедшему из конкретного loop-вызова.

- Observation: план не хранит точное время начала будущей сессии.
  Evidence: forecast содержит `target_date`, checkpoint и session index, но не scheduled start UTC. Поэтому Today не должен заявлять доказанную pre-start eligibility; он показывает последнюю релевантную pending revision с честным `target_time_provenance: date_only`. Строгая проверка pre-start остаётся в forecast resolver после появления фактического `started_at_utc`.

- Observation: reconciliation уже вычисляет plan-vs-actual и adherence, но `/today` его не использует.
  Evidence: `api/planning_service.py::reconciliation_at` возвращает строки с `session_id`, match/adherence, фактическими активностями и метриками, тогда как `_yesterday_summary` лишь суммирует последние активности.

- Observation: красная фаза падает ровно на новой границе контракта.
  Evidence: focused Today suite дала `8 failed, 2 passed`: отсутствуют `snapshot_version`, `primary_action`, `gate`, `proposal`, `forecast`, reconciliation-поля и `session_id`; старое состояние по-прежнему возвращает `conflict` или ошибочно `silence`.

- Observation: живая БД сразу дала осмысленный составной Today v2 без специальных acceptance-фикстур.
  Evidence: на копии `ai_trainer.db` экран показал `silence`, readiness 69.2, recovery bike 16 TSS, shadow forecast 65% на 18.07 revision 8 и reconciliation за 12.07: план 9 TSS, факт 50 TSS, major deviation, 19 TSS вне плана. Console warnings/errors отсутствуют.

- Observation: repository-wide Ruff пока не является зелёным проектным gate.
  Evidence: полный `ruff check api models services data tests/smoke` находит 51 ошибку в нетронутых legacy-файлах (`garmin_client.py`, `ai_coach*.py`, `planning_near_term.py` и другие). Ruff на всех изменённых Python-файлах проходит без ошибок; массовая legacy-зачистка не включена в #174.

## Decision Log

- Decision: ввести чистую границу `api/today_snapshot.py::build_today_decision_snapshot` и оставить `api/routers/today.py` тонким адаптером Depends/HTTP.
  Rationale: один headless-контракт можно вызывать и тестировать без FastAPI и web; доменная композиция не должна жить в UI-роутере.
  Date/Author: 2026-07-13 / Codex.

- Decision: версия ответа называется `today_decision_snapshot_v2`, а старые top-level поля сохраняются аддитивно на период миграции.
  Rationale: `/today` уже используется web-клиентом и тестами. Удаление `loop_outcome`, `pending_proposal`, `readiness_source` или legacy yesterday-полей создаст ненужную миграцию в одном PR.
  Date/Author: 2026-07-13 / Codex.

- Decision: состояние выбирается в порядке `no_plan` → `data_gap` → current active proposal → gate conflict без безопасного current proposal → `silence`.
  Rationale: отсутствие плана и данных первичны; существующее pending/applying действие должно оставаться видимым при повторном loop-вызове; необслуживаемый конфликт не может маскироваться под тишину.
  Date/Author: 2026-07-13 / Codex.

- Decision: terminal user-handled proposal (`approved`, `rejected`, `rolled_back`) означает `silence`, а `failed` означает `conflict_unactionable`.
  Rationale: первое — уже принятое решение пользователя, второе — технически неисполненное решение, требующее прозрачного evidence без кнопки approve.
  Date/Author: 2026-07-13 / Codex.

- Decision: proposal разрешается относительно активного checkpoint, а не только из результата текущего loop-вызова.
  Rationale: pending proposal должен пережить следующий вызов, даже если новый outcome оказался `silence`. Proposal с другим `base_checkpoint_id` показывается как stale evidence и не получает action controls.
  Date/Author: 2026-07-13 / Codex.

- Decision: shadow forecast никогда не участвует в state machine или `primary_action`.
  Rationale: Issue D (#161) пре-регистрирован как наблюдательный контур. Поле `affects_decision: false` закрепляет границу машинно и визуально.
  Date/Author: 2026-07-13 / Codex.

- Decision: вчерашний блок строится вызовом `reconciliation_at(..., as_of=yesterday, weeks=1, include_provider=False)` с фильтрацией ровно вчерашней даты.
  Rationale: matcher и adherence не дублируются, а обычный GET `/today` не запускает live provider/network I/O. При сбое reconciliation весь Today остаётся доступным и возвращает явный degraded-блок.
  Date/Author: 2026-07-13 / Codex.

- Decision: persisted structured prescription из #173 переносится как есть и получает только additive stable `session_id` и недостающие provenance-поля.
  Rationale: #174 — композиция daily contract, не второй каталог тренировок и не новая материализация плана.
  Date/Author: 2026-07-13 / Codex.

## State and action contract

`state` принимает ровно пять значений:

1. `no_plan`: активного planning checkpoint нет. `primary_action.kind = "open_planning"`.
2. `data_gap`: gate не может принять решение из-за недостатка/устаревания данных. Плановая сессия сохраняется из checkpoint fallback. `primary_action.kind = "sync_or_wait"`.
3. `conflict_actionable`: существует pending/applying recovery proposal для активного checkpoint. `primary_action.kind = "review_proposal"`; только current proposal попадает в legacy `pending_proposal` и UI-кнопки.
4. `conflict_unactionable`: gate обнаружил конфликт, но безопасного current proposal нет, либо proposal failed/stale. `primary_action.kind = "inspect_evidence"`; текст не содержит «План в силе», approve/reject отсутствуют.
5. `silence`: конфликтов нет либо пользователь уже терминально обработал предложение. `primary_action.kind = "follow_plan"`.

Приоритет active proposal над последним loop outcome нужен для устойчивости write-on-read: существующее действие не исчезает только потому, что последующий snapshot readiness изменился. Терминальный proposal текущего fingerprint используется как evidence обработки и возвращает спокойный вид.

## Response contract

Сборщик возвращает существующие поля и следующие additive блоки. Псевдо-JSON показывает семантику, а не обязательный порядок ключей:

    {
      "snapshot_version": "today_decision_snapshot_v2",
      "date": "2026-07-13",
      "state": "conflict_actionable",
      "reason": "...",
      "primary_action": {"kind": "review_proposal", "enabled": true, "reason": "..."},
      "readiness": {...},
      "readiness_source": "canonical_snapshot",
      "session": {
        "session_id": "stable-id",
        "date": "2026-07-13",
        "template_id": "...",
        "stimulus": "...",
        "steps": [...],
        "legs": [...]
      },
      "gate": {
        "outcome": "conflict",
        "reason": "...",
        "data_gap": false,
        "conflicts": [...],
        "sessions_evaluated": [...],
        "proposal_gap": null,
        "decision": {"id": 7, "fingerprint": "..."}
      },
      "proposal": {
        "relation": "current|stale|resolved|none",
        "proposal": {...}|null,
        "base_checkpoint_id": 63,
        "active_checkpoint_id": 63,
        "reason": "..."
      },
      "forecast": {
        "mode": "shadow",
        "affects_decision": false,
        "prediction": {...}|null,
        "relation": "current_checkpoint|stale_checkpoint|none",
        "target_time_provenance": "date_only"
      },
      "yesterday": {
        "status": "available|empty|unavailable",
        "date": "2026-07-12",
        "planned_sessions": 1,
        "matched_sessions": 1,
        "adherence": {"exact": 0, "substituted": 0, "major_deviation": 1, "unknown": 0},
        "planned_tss": 20,
        "matched_actual_tss": 32,
        "unplanned_tss": 0,
        "total_actual_tss": 32,
        "rows": [...],
        "unplanned_activities": [...],
        "data_quality": {...},
        "rule_version": "...",
        "base_checkpoint_id": 63,
        "activities": 1,
        "minutes": 55,
        "tss": 32,
        "sports": ["cycling"]
      },
      "pending_proposal": {...}|null,
      "loop_outcome": "conflict",
      "provenance": {
        "generated_at": "...Z",
        "as_of": "2026-07-13",
        "checkpoint": {"id": 63, "created_at": "...", "source": "planning_checkpoint"},
        "readiness": {"source": "canonical_snapshot", "computed_at": "..."},
        "gate": {"decision_id": 7, "fingerprint": "..."},
        "forecast": {"prediction_id": 5, "rule_version": "session_quality_v1"},
        "reconciliation": {"rule_version": "...", "base_checkpoint_id": 63}
      },
      "operational_state": {...}
    }

`yesterday.activities/minutes/tss/sports` остаются compatibility summary, но вычисляются из reconciliation evidence, а не отдельным matcher. `loop_outcome` остаётся сырым последним исходом для диагностики и не заменяет канонический `state`.

## Behavioral Specification

Given пустая БД, when строится snapshot, then состояние `no_plan`, action ведёт в Planning, блоки proposal/forecast безопасно пусты, API не падает.

Given план и недостаточные readiness-данные, when gate возвращает `data_gap`, then состояние `data_gap`, а persisted structured session из checkpoint остаётся в ответе со steps/legs/session_id.

Given спокойный день и плановая сессия, when snapshot строится повторно, then состояние `silence`, число readiness равно `build_readiness_snapshot`, повторный GET идемпотентен по decision/proposal/forecast.

Given конфликт и current pending/applying proposal, when snapshot строится, then состояние `conflict_actionable`, proposal relation `current`, action `review_proposal`, кнопки web доступны.

Given конфликт, для которого вариант не создан из-за protected date, непривязанной сессии, дедупа или ошибки, when snapshot строится, then состояние `conflict_unactionable`, evidence и `proposal_gap` видимы, `pending_proposal` null, фраза «План в силе» не появляется.

Given pending proposal от другого checkpoint, when активный checkpoint сменился, then proposal relation `stale`, approve controls отсутствуют, а реальный gate conflict остаётся `conflict_unactionable`.

Given proposal был rejected/approved/rolled_back, when тот же конфликт встречается повторно, then экран остаётся `silence`; given proposal `failed`, then `conflict_unactionable`.

Given несколько forecast revisions для одной цели, when snapshot строится до факта, then выбирается последняя релевантная запись по `(created_at, id)`, показывается `mode=shadow`, `affects_decision=false`, а state/primary action совпадают со snapshot без forecast.

Given вчера plan и actual сопоставлены или расходятся, when snapshot строится, then блок yesterday берётся из `reconciliation_at`, содержит adherence, plan/fact TSS и evidence; отдельная legacy raw aggregation не используется.

Given Recovery Replan, readiness, forecast или reconciliation падает, when открывается `/today`, then endpoint отвечает деградированным, объяснимым snapshot и не превращает локальный сбой вспомогательного блока в HTTP 500.

## Context and Orientation

Текущий HTTP-роутер находится в `api/routers/today.py`; он одновременно запускает контур, строит состояние и проецирует UI. `api/recovery_replan_loop.py::run_recovery_replan_loop` возвращает outcome, decision, proposal, proposal gap, conflict report и fail-open shadow forecast. `api/readiness_snapshot.py::build_readiness_snapshot` — единственный источник readiness для продуктовых поверхностей.

Активный план хранится в `planning_checkpoints`; `api/planning_service.py::restore_goal_plan_from_checkpoint` восстанавливает шаблон. После #173 persisted day содержит stable `session_id`, template/stimulus/steps/legs. Нельзя заново выбирать каталог или материализовывать session в Today.

Proposal journal хранится в `coach_proposals`. `params.base_checkpoint_id` связывает предложение с версией плана, `status` определяет active/terminal lifecycle. Stale checkpoint guard уже реализован в approve/rollback; Today лишь отображает ту же границу.

Shadow forecast хранится отдельно в `session_quality_predictions`. `api/session_quality_forecast.py` отвечает за запись и строгий resolver после факта. Today только читает последний релевантный journal row и никогда не кормит им gate.

Plan-vs-actual находится в `models/plan_actual_reconciliation.py`; публичный headless вход — `api/planning_service.py::reconciliation_at`. Новая композиция повторно использует его с отключённым provider fetch.

Web-клиент — `web/app/today/page.tsx`, типы — `web/lib/types.ts`. `ProposalCard` можно рендерить только для relation current и active status. Streamlit не входит в scope.

## Plan of Work

Сначала добавить в `tests/smoke/test_api_today.py` контрактные сценарии пяти состояний, conflict-without-proposal, stale/current proposal, latest forecast revision, reconciliation yesterday, additive compatibility и fail-open. Красная фаза должна падать из-за отсутствующих v2 полей/состояний, а не из-за неверной фикстуры.

Затем создать `api/today_snapshot.py`. Перенести туда существующие безопасные projection helpers из роутера, не меняя prescription semantics. Сборщик один раз получает checkpoint, один раз запускает Recovery Replan, один раз строит readiness, затем разрешает proposal/forecast/reconciliation. Каждый вспомогательный блок имеет локальную границу деградации с явной причиной. State machine оформить маленькой детерминированной функцией, отдельно тестируемой через поведение snapshot.

После этого сократить `api/routers/today.py` до Depends и вызова builder. Старые top-level поля остаются в результате builder, поэтому route registration и внешние клиенты не ломаются.

Далее расширить `TodayResponse` и вложенные типы в `web/lib/types.ts`, затем обновить `/today`: пять заголовков, явная карточка `conflict_unactionable`, action controls только у current proposal, shadow forecast с маркировкой «не влияет на решение», gate evidence и reconciliation-backed yesterday. Существующая structured session остаётся главным объектом дня.

Наконец провести self-review на предмет трех ошибок: скрытый конфликт; shadow forecast, влияющий на решение; stale proposal с активной кнопкой. Прогнать acceptance на временной копии локальной БД, чтобы не писать новые решения/прогнозы в пользовательский journal во время проверки.

## Concrete Steps

Работа выполняется только из `/private/tmp/ai_trainer_issue174` на ветке `codex/issue-174-today-v2`. Python запускается виртуальным окружением основной копии репозитория:

    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest tests/smoke/test_api_today.py -q
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest tests/smoke/test_session_quality_forecast.py tests/smoke/test_recovery_replan_loop.py tests/smoke/test_plan_actual_reconciliation.py -q
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest tests/smoke -q
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest -m "not live and not debug" tests/ -q
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m compileall -q api models services data
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/ruff check api models services data tests/smoke
    cd web && npm run lint && npm run build
    git diff --check

Начальный contributor-safe baseline на main: `557 passed, 1 skipped`; skip связан с локальным запретом socket и допустим. Финальный count должен быть выше baseline.

## Validation and Acceptance

Focused API-тесты доказывают все пять состояний и обязательную ветку conflict-without-proposal. Отдельная assertion проверяет, что forecast не меняет state/action. Stale/current proposal тест доказывает отсутствие approve controls для stale версии. Reconciliation тест сравнивает yesterday с прямым вызовом `reconciliation_at`, включая major deviation и unplanned load.

Полный smoke и broad non-live/non-debug проходят; compileall, Ruff и `git diff --check` чисты. Web lint/build проходят. OpenAPI по-прежнему содержит `GET /api/today`.

Живая приёмка запускает API/web на альтернативных свободных портах и на копии `ai_trainer.db`. Проверяются `/`, `/today`, console/network errors и видимые состояния. Число readiness сравнивается с dashboard; сегодняшняя prescription сохраняет template/steps/legs; forecast подписан shadow; вчера показывает adherence; stale/unactionable не имеет кнопки подтверждения. Скриншот прикладывается к PR, если web изменился.

## Idempotence and Recovery

Схема БД не меняется. Builder использует уже идемпотентные decision/proposal/forecast writers. Повторный GET не должен увеличивать число строк при неизменных входах. Reconciliation — read-only. Все новые response-поля additive, поэтому откат PR не требует миграции данных.

Если forecast или reconciliation недоступны, их блок получает `relation/status = unavailable` и reason, но state остаётся функцией плана, gate и current proposal. Если Recovery Replan падает, snapshot деградирует в `data_gap` и сохраняет checkpoint session. Если readiness snapshot падает, score отсутствует и state не объявляет plan safe.

Работа ведётся в отдельном worktree. Основная директория не переключается и не коммитится. До human review PR остаётся draft; merge выполняется только по явной команде пользователя.

## Interfaces and Dependencies

Новая публичная Python-граница:

    TODAY_SNAPSHOT_VERSION = "today_decision_snapshot_v2"

    def build_today_decision_snapshot(
        db: Database,
        *,
        demo: bool = False,
        today: date | None = None,
    ) -> dict[str, Any]:
        """Build one fail-open, versioned daily decision snapshot."""

Внешние зависимости не добавляются. Сборщик зависит только от существующих Python API: `run_recovery_replan_loop`, `build_readiness_snapshot`, checkpoint restore/store, forecast journal reads, `reconciliation_at`, `build_operational_state`. HTTP-роутер и Next.js являются адаптерами этого контракта.

## Outcomes & Retrospective

Today v2 реализован как один headless snapshot, а FastAPI-роутер теперь только передаёт Database/demo. Структурная prescription из #173 сохранена и получила stable `session_id`; новое состояние `conflict_unactionable` закрывает маскировку реального gate-конфликта; active/stale/resolved proposal разрешаются относительно planning checkpoint; shadow forecast явно помечен `affects_decision=false`; вчерашний блок использует plan-actual matcher #172 вместо собственной суммы активностей.

Поведенческий контракт вырос с 8 до 14 focused-сценариев. Финальные локальные результаты: Today `14 passed`; adjacent Today/forecast/recovery/reconciliation `57 passed`; contributor-safe `563 passed, 1 skipped`; broad non-live/non-debug `606 passed, 6 skipped, 24 deselected`. Compileall и `git diff --check` чисты. Ruff чист на изменённых Python-файлах; полный старый tree имеет 51 не относящуюся к PR ошибку. Next lint/build зелёные. GitHub Contributor-safe pytest на опубликованном PR-head также зелёный.

Живая приёмка выполнена на `/tmp/ai_trainer_issue174_acceptance.db`, копии пользовательской БД, через FastAPI `:8024` и Next `:3024`. Корень дал 307 на `/today`, API — 200, DOM содержит каноническую session/readiness/forecast/reconciliation композицию, browser console warnings/errors пуст. Локальный снимок: `/tmp/ai_trainer_issue174_today_v2.png`. Он не публикуется автоматически, потому что содержит персональные тренировочные метрики.

Отклонение от исходного псевдо-контракта одно и осознанное: builder принимает `demo`, чтобы `operational_state` оставался частью того же headless payload. Строгую pre-start eligibility Today не утверждает, потому что в плане нет времени начала; показан честный `date_only / unverified_date_only`, а окончательный скоринг остаётся в Issue D resolver.

Оставшиеся риски: один active proposal текущего checkpoint может относиться к будущей сессии, поэтому экран намеренно показывает самый свежий current action; multi-athlete scope всё ещё ограничен текущей single-athlete SQLite архитектурой; day-level summary использует evidence matcher недельного окна и показывает его `data_quality` как provenance, не как отдельный новый score.

## Artifacts and Notes

Issue: `https://github.com/rbctmz/ai_trainer/issues/174`.

Draft PR: `https://github.com/rbctmz/ai_trainer/pull/183`.

Аудит перед реализацией: `https://github.com/rbctmz/ai_trainer/issues/174#issuecomment-4960647901`.

Starting base:

    9d65568 Merge pull request #182

Revision note: 2026-07-13 / Codex — создан начальный самостоятельный план после аудита текущего контракта; решения и acceptance pre-registered до production-кода. Финализирован после реализации: добавлены фактические counts, live evidence, отклонение интерфейса `demo` и граница pre-start provenance.
