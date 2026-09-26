# ExecPlan: Daily decision loop v1 — план → факт → состояние → действие (issue #607)

Этот ExecPlan — living document. Разделы `Progress`, `Surprises & Discoveries`, `Decision Log` и `Outcomes & Retrospective` обновляются по ходу работы согласно `.agent/PLANS.md` (файл лежит в корне репозитория; этот документ ведётся по его правилам).

## Purpose / Big Picture

AI Trainer не выигрывает за счёт количества дашбордов, метрик и интеграций. Дифференциатор v1 — доверенный ежедневный цикл решения: план → единый факт тренировки → отклонение и подтверждённая причина → состояние атлета → следующее действие. После этой работы атлет открывает основную поверхность и за минуту отвечает на четыре вопроса: что мне делать, почему, каким доказательствам можно верить и какой следующий шаг. Технические детали (leg-level разбивка, графики, метрики) остаются доступны через progressive disclosure — раскрытие деталей не делает запрос к провайдеру и не пересчитывает доменную семантику в браузере.

Сегодня этот ответ собирается из нескольких независимых поверхностей, и они не обязаны согласовываться. Проверяемый пользовательский эффект формулируется так: для одной и той же ревизии доказательств Today, Planning и Activity показывают одну и ту же идентичность сессии и одни и те же итоги план/факт, а любое предписывающее действие несёт источник, время наблюдения и признак свежести — либо результат честно не предписывающий.

## Progress

- [x] (2026-09-20 05:34Z) Roadmap-комментарий владельца продукта принят: Daily decision loop v1 — контролирующее направление; порядок #598 → #601 → #608 → #609 → #610 → #367; WIP-лимит «один активный Class A слайс плюс не более одного мелкого maintenance/process item».
- [x] (2026-09-20 08:20Z) Разведка: прочитаны #607/#608/#609/#610, карта модулей сборки дневного решения, канонический readiness snapshot и каноническое окно метрик нагрузки.
- [x] (2026-09-20 08:22Z) Шаг 0, слайс #598: воспроизведён дефект замороженных CTL/ATL/TSB и внутреннего противоречия payload; написан slice spec `docs/issue_598_dashboard_metrics_anchor_slice_spec.md`.
- [x] (2026-09-20 08:30Z) Шаг 0, слайс #598: RED (`7 failed, 1 passed`) → GREEN (`8 passed`); focused `117 passed`; contributor-safe `2800 passed, 13 skipped`; Ruff зелёный; contract-артефакт свежий.
- [x] (2026-09-20 08:35Z) Шаг 0, слайс #598: ветка `fix/issue-598-metrics-anchor` опубликована, PR #614 открыт с `Closes #598`.
- [x] (2026-09-20 08:40Z) Создан этот ExecPlan отдельным docs-коммитом; PR #615 открыт с `Refs #607` (планирование не закрывает эпик).
- [x] (2026-09-20 09:25Z) Шаг 0, слайс #601: шесть решений о календарном дне атлета в `api/planning_service.py` переведены на `athlete_local_date()`; RED `3 failed, 1 passed` → GREEN `4 passed`; focused planning `334 passed`; contributor-safe `2796 passed, 13 skipped`; Ruff зелёный; PR #617 с `Closes #601`. Slice spec `docs/issue_601_athlete_calendar_day_slice_spec.md`.
- [x] (2026-09-20) Слайс #608, часть 1 (Class A): описательная шкала ACWR вместо
  риск-словаря, шим совместимости с прежним словарём провайдера, провенанс и
  раздельные версии, `intervention_eligible: false`. PR #620, merge `485cd62`;
  slice spec `docs/issue_608_safe_workload_semantics_slice_spec.md`. RED
  `11 failed, 1 passed` → GREEN `12 passed`; contributor-safe `2819 passed`.
- [ ] Слайс #608, часть 2: положительный corroborated-intervention сценарий.
  Остаётся в #608: ACWR не участвует ни в одном предписании, поэтому проверять
  сценарий не на чем до появления реального consumer/composer. Решение владельца
  записано в issue #608 комментарием от 2026-09-20.
- [ ] Слайс #609 (Class A): каноническая session-first проекция план/факт с эвиденс-обоснованной причиной отклонения.
  - [x] (2026-09-21 20:14Z) Первый ограниченный milestone: slice spec `docs/issue_609_session_first_projection_slice_spec.md` и пять RED-контрактов (single, brick, partial brick, ambiguous, provider-free/non-mutating read). Прогон: `5 failed` по ожидаемой причине — новые `models.session_projection` и `services.session_projection` ещё не реализованы. GREEN, API и UI сознательно не начаты до проверки границы.
  - [x] (2026-09-22 07:35Z) Второй milestone: добавлены RED для latest explicit revision и malformed legacy (`7 failed` по отсутствующим модулям), затем минимальные чистый composer и provider-free local service. GREEN после self-review: projection `9 passed`, focused `121 passed`, contributor-safe `2801 passed, 40 skipped, 38 deselected`, Ruff зелёный. API/TypeScript/UI не менялись.
  - [x] (2026-09-23) Третий milestone: API/TS RED `5 failed` → GREEN; добавлен `GET /api/planning/session-projection/{session_id}`, typed DTO, OpenAPI/registry и Activity/Planning API reuse. Consumer RED `3 failed` → shared summary component подключён в Today, Planning и Activity. Contributor-safe `2835 passed, 16 skipped, 38 deselected`; Ruff, contract freshness/inventory, web lint и production build зелёные. Первый полный прогон выявил только harness-сбой `run_web.sh`: `python` отсутствовал в PATH. Отдельное воспроизведение и повторный полный прогон с venv в PATH прошли. Изолированный browser clickthrough не заявлен: текущий `run_acceptance.sh` запускает Streamlit, а слайс меняет Next.js.
- [x] (2026-09-23) #609 смержен владельцем: merge commit `440d1795` содержит head `2ef734b`; session-first проекция стала исходной границей #610. Browser clickthrough #609 по-прежнему не заявлен.
- [ ] Слайс #610 (Class A): Today decision story — реализация и интеграционные проверки завершены локально; ожидает независимое ревью и owner acceptance.
  - [x] (2026-09-23 13:59Z) Начальный milestone в отдельном worktree от `440d1795`: прочитаны issue #610, roadmap-комментарий #607, parent ExecPlan, ASR catalog, ADD analysis, ADR-0001 и slice-spec template. Создана bounded slice spec и четыре RED-теста: `4 failed` только из-за отсутствующего `models.today_decision_story`. GREEN не начат.
  - [x] (2026-09-23) Владелец принял delta read-back: свежий self-report `injury != Нет` даёт только review; отсутствие свежего ответа сохраняет действие gate с caveat. Добавлены тесты на `status=current` из-за другого wellness-ответа и partial DTO по #609 (`planned_leg_id`, `leg_index`, `activity_id`).
  - [x] (2026-09-23) Domain/API GREEN в изолированном worktree: pure `models/today_decision_story.py`, additive `/api/today` contract, Coach получает тот же story через read-only адаптер; no-write proof по table snapshots.
  - [x] (2026-09-23) Интегрированы compact/full Today и Coach. Coach использует pre-loop checkpoint, `_resolve_proposal`, `_resolve_state` и `_day_session` из Today boundary. Регрессия: pending proposal с `base_checkpoint_id=1` при активном checkpoint 2 должна давать `inspect_evidence`.
  - [x] (2026-09-23) Проверки: focused story/API/Coach `37 passed`; combined focused regressions `50 passed`; contributor-safe suite из свежей временной копии с отдельной SQLite `2827 passed, 40 skipped, 39 deselected`; Ruff, contract freshness/inventory, web lint/build прошли. Today Playwright прошёл дважды на 390/1280 px, включая повтор после финального Coach parity изменения.
  - [x] (2026-09-23 14:01Z) Проверена граница Coach: `models/ai_tools.py::get_readiness_today` выполняет локальные чтения, но `build_today_decision_snapshot` вызывает `run_recovery_replan_loop`, который сохраняет решения и может публиковать proposal. Coach будет потреблять чистый composer через read-only адаптер, не Today builder.
  - [x] (2026-09-23 14:14Z) Приняты замечания независимого read-only review: выбрано, что свежий injury-ответ не обязателен для сохранения существующего `follow_plan`, но без свежего ответа история обязана явно запретить формулировку «без симптомов/допуск»; добавлен UI RED для приоритета next action в compact/full; read-only гарантия ограничена Coach adapter, а `/api/today` описан с существующими loop-записями; fixture #609 исправлена. Повторный RED: 5 composer-тестов падают только из-за отсутствующего модуля, UI контракт падает на отсутствии `decision_story` в текущем Today.
  - [ ] Независимое ревью и owner acceptance. Отдельные screen-reader и browser states loading/empty/error/stale ещё не проверялись; PR/merge не создавались.
- [ ] Слайс #367: приёмка техническими атлетами; наблюдаемые провалы превращаются в ограниченные issues.
- [x] (2026-09-20 08:45Z) Follow-up по окну readiness-фузии заведён как #616 без automation-контракта, чтобы не запускать автодиспетч (см. `Decision Log`). Приоритет и назначение — за владельцем.
- [x] (2026-09-20) Инфраструктура: проверка `sync` падала на PR #614/#615 с `FORBIDDEN` на мутации Projects v2. Первопричина найдена — секрет `ROADMAP_PROJECT_TOKEN` в репозитории отсутствует (`gh secret list` показывает только `CLAUDE_CODE_OAUTH_TOKEN`). Workflow выведен из эксплуатации в PR #618, потому что на мерж он не влиял: обязательная проверка для `main` — только `Contributor-safe pytest`.

## Surprises & Discoveries

**Замороженные метрики оказались не только «легаси отстал».** Изначальная гипотеза по #598 звучала как «дашборд замерзает на дате последней тренировки». Проверка показала более неприятную картину: на API метрики уже перекрывались каноническим снимком, поэтому дефект был виден не там, где его искали.

- **Observed**: `api/routers/dashboard.py` вызывает `project_readiness_snapshot` перед отдачей ответа, и эта функция перекрывает `signals.load.ctl/atl/tsb` значениями из `services/readiness_snapshot.py`. При этом `signals.load.form`, `signals.critical` и `signals.recommendations` вычисляются внутри `models/signals_engine.assemble_signals` от замороженной серии и проекцией не перекрываются. Источник — чтение кода и воспроизведённый payload (таблица в `Artifacts and Notes`).
- **Inferred**: один и тот же ответ может одновременно утверждать «Свежесть, TSB +16.4» и «Критическое переутомление — полный отдых 2-3 дня». Дешёвая опровергающая проверка — собрать payload на временной SQLite с блоком нагрузки и разрывом и сравнить `load.tsb` с `load.form` и `critical` внутри одного ответа.
- **Verified by**: проверка выполнена на временной БД; payload содержал `load.tsb = +16.4` («Свежесть») рядом с `form = «Высокая усталость»` и `critical = «Критическое переутомление / Полный отдых 2-3 дня без тренировок»`. После исправления тот же прогон даёт `form = label = «Свежесть»` и `critical = null`.

**Обрезанное окно занижает витринную метрику даже без разрыва в данных.** Это оказалось независимым от заморозки дефектом с тем же корнем.

- **Observed**: `models/dashboard_summary.calculate_current_status` получал 30-дневный кадр отображения. На ровных 60 днях по 50 TSS это давало CTL 25.5, тогда как канонический расчёт `models/readiness.py::_tsb_metrics` на окне `LOAD_METRICS_WINDOW_DAYS = 90` даёт 38.0. Источник — прямой прогон обеих функций на одном наборе данных.
- **Inferred**: разогрев экспоненциального среднего с постоянной времени `tau_CTL = 42` дня не укладывается в 30-дневное окно, поэтому CTL систематически занижен. Опровергающая проверка — сравнить 30-дневный и 90-дневный кадры на ровной нагрузке без разрыва: если разницы нет, гипотеза неверна.
- **Verified by**: разница воспроизведена (25.5 против 38.0), а после перевода дашборда на каноническое окно значения совпали с `_tsb_metrics` с точностью до 0.1. Занижение на треть затрагивает именно того атлета, который тренируется стабильно.

**Остаточный эффект в readiness-фузии (измерен, вне scope шага 0).**

- **Observed**: `models/signals_engine._readiness_signal` по-прежнему получает 30-дневный кадр отображения. На блоке 3 недели + 14 дней отдыха значение score совпадает (85.0 на обоих окнах, полоса насыщена), но текст доказательства различается: `drivers[tsb].evidence` = «TSB +12.6 (свежесть)» на 30 днях против «TSB +16.4 (свежесть)» на 90 днях. Источник — прямой прогон `_readiness_signal` с двумя кадрами.
- **Inferred**: на легаси-странице число внутри доказательства расходится с заголовочным `signals.load.tsb`. На API это не наблюдаемо, потому что проекция подменяет `signals.readiness.drivers` каноническими. Опровергающая проверка — открыть легаси-страницу на этом сценарии и сравнить текст драйвера с заголовком.
- **Verified by**: расхождение воспроизведено на уровне функции; выход `_readiness_signal` до и после слайса #598 побитово совпадает, то есть слайс этого не вносит и не меняет. Требуется отдельное решение о readiness-окне; наблюдение вынесено в follow-up #616, а не исправлено внутри #598, чтобы не менять вход readiness-фузии без собственных acceptance criteria (non-goal #598).

**Не каждый `datetime.now()` в модуле — атлетская граница.** При закрытии #601 механическая замена «всех `datetime.now()` на `athlete_local_date()`» была бы дефектом.

- **Observed**: `api/planning_service.py` содержит, помимо шести атлетских границ, три сайта `datetime.now().isoformat()` на строках 1492, 3401 и 3547 — это метки времени ревизии плана (`plan_revision`). Источник — `grep -nE` по модулю до и после правки.
- **Inferred**: метка времени фиксирует момент записи артефакта, а не календарный день, к которому относится нагрузка; замена её на атлетскую дату потеряла бы точность наблюдения и сделала бы ревизии неотличимыми внутри суток. Дешёвая опровергающая проверка — посмотреть, участвует ли значение в сравнениях дат плана; `plan_revision` в них не участвует.
- **Verified by**: правка ограничена шестью сайтами, три метки времени сохранены, а структурный тест `test_no_host_clock_athlete_boundaries_remain` фиксирует это разделение: он ищет только `datetime.now().date()` и `date.today()` и после правки находит ноль совпадений, при том что `isoformat()`-сайты остались на месте (проверено отдельным `grep` в PR #617).

**Проверка `sync` падает не из-за диффа.** Оба PR этого дня получили красный `Project roadmap sync`; важно не принять это за регрессию.

- **Observed**: `gh pr checks 614` и `gh pr checks 615` показывают `sync fail`. Лог запуска: `FORBIDDEN`, `message: Resource not accessible by integration` на мутации `updateProjectV2ItemFieldValue` для проекта `PVT_kwHOBymzFc4BbL8C`, элемента `PVTI_lAHOBymzFc4BbL8Czg7yqcQ`, поля статуса `PVTSSF_lAHOBymzFc4BbL8CzhV-ROg` со значением `47fc9ee4` (In progress). Источник — вывод `gh run view --log`.
- **Inferred**: `.github/workflows/project-roadmap-sync.yml` берёт токен как `secrets.ROADMAP_PROJECT_TOKEN || github.token`. Ошибка «not accessible by integration» характерна для случая, когда использован именно `github.token`, а проект принадлежит пользователю (`user(login: rbctmz)`), куда integration-токен писать не может. Значит, секрет `ROADMAP_PROJECT_TOKEN` до этих запусков не дошёл или потерял scope. Проверка наличия и scope секрета — `gh secret list --repo rbctmz/ai_trainer`,
это чтение и оно безопасно. Запускать для этого сам workflow через
`workflow_dispatch` **нельзя**: его dispatch-ветка обходит все issue и PR
проекта и вызывает мутацию для каждого элемента, то есть проверка гипотезы
переписала бы всю дорожную карту. Такая проба требует явного согласия владельца,
снимка состояния проекта и отдельного решения; в этом расследовании она не
запускалась.
- **Verified by**: частично. Диффа в workflow нет — слайсы #598 и #615 не трогают ни `.github/`, ни настройки проекта. Успешные `pull_request`-запуски того же workflow ранее в тот же день (например, 35494509442 в 06:32Z) при разборе лога **не выполняли** никакой мутации проекта, то есть их «success» ничего не доказывает про работоспособность токена. Логи более ранних запусков уже недоступны (`gh run view --log` возвращает 0 строк), поэтому проверить, мутировали ли они проект, не удалось. **Дополнено 2026-09-20, первопричина установлена.** `gh secret list --repo rbctmz/ai_trainer` показывает единственный секрет `CLAUDE_CODE_OAUTH_TOKEN`: `ROADMAP_PROJECT_TOKEN` в репозитории отсутствует, поэтому подстановка всегда падала на `github.token`, который не может писать в user-owned Projects v2. Workflow выведен из эксплуатации в PR #618, раздел `Progress` это отражает. Итог: инфраструктурный дефект, а не регрессия слайса; **Verified by** — вывод `gh secret list` и логи запусков 35500046058 / 35500231382. Прежняя запись `NOT YET` относилась только к моменту, когда секрет ещё не был проверен. Уточнение по наблюдаемости: workflow срабатывает на `pull_request: [opened, reopened, edited, closed]`, но не на `synchronize`, поэтому после последующих пушей проверка `sync` исчезает из списка `gh pr checks` — повторный прогон происходит при редактировании PR, и падение воспроизводится снова.

**Partial brick уже существует как доказательство, но не как session-first состояние.**

- **Observed**: `build_reconciliation` при наличии только одного authoritative external leg сохраняет эту активность в `actual_activities`, ставит родителю `match_status = ambiguous` и evidence «найдена только часть ног»; `project_composite_execution` при этом видит только доступный вид спорта.
- **Inferred**: #609 не должен повторно матчить bike/run. Он должен перевести уже доказанную частичную атрибуцию в отдельный `projection_status = partial`, сохранить bike-факт и не превращать отсутствующий run в кандидата или завершение.
- **Verified by**: дешёвая проверка — существующий код ветки `models/plan_actual_reconciliation.py` (ветка `stable` / `has_all_composite_legs`) и RED fixture `test_partial_brick_preserves_only_observed_leg`. GREEN ещё не выполнен.

## Decision Log

- Decision: #609 строится как чистый composer существующего reconciliation-снимка плюс provider-free read-service, а не как новый matcher или новая таблица.
  Rationale: `models.plan_actual_reconciliation.build_reconciliation` уже владеет приоритетом явных ревизий, кандидатами, фактическими активностями и partial composite evidence. Новый слой должен только нормализовать одну родительскую сессию и назвать использованные ревизии. Дешёвая опровергающая проверка — partial brick с одним external leg: существующий reconciliation уже сохраняет доступную активность при `match_status=ambiguous`, поэтому повторное сопоставление не требуется.
  Date/Author: 2026-09-21, Spec / Architecture Owner (Codex).

- Decision: в DTO #609 `cause` отделён от `deviation` и по умолчанию равен `unknown/no_explicit_cause_evidence`; неоднозначность даёт `needs_confirmation/ambiguous_match`.
  Rationale: величина нагрузки, совпадение вида спорта и свободный текст сами по себе не доказывают причину отклонения. `supported` допустим только с адресуемой структурированной ссылкой на authoritative match lineage, feedback fact или constraint; иначе слой нарушил бы fail-closed границу #609.
  Date/Author: 2026-09-21, Spec / Architecture Owner (Codex).

- Decision: слайс #598 классифицирован как **Class B — Standard**, а не Class A.
  Rationale: публичный контракт не меняется (форма DTO и `web/lib/types.ts` те же, меняются значения внутри существующих полей), нет миграций, нового persistent state, live-provider записи и новых архитектурных границ. Все шесть automatic escalation triggers из `docs/AI_Feature_Development_Workflow.md` проверены поимённо.
  Date/Author: 2026-09-20, Domain / API Implementer (DSH).

- Decision: метрики нагрузки считаются по каноническому окну `LOAD_METRICS_WINDOW_DAYS` = 90 с якорем `athlete_local_date()`, а не по 30-дневному кадру отображения и не по «последней доступной дате».
  Rationale: канонический контур уже зафиксировал это окно с ровно такой семантикой (`models/readiness.py`, issue #134: «метрики не должны зависеть от того, за сколько дней запрошен отчёт»). Вариант «якорь от последней доступной даты» — это текущее поведение (`_daily_load_series` при `as_of=None` уже берёт максимум даты), поэтому он не устраняет дефект по построению. Выбор сверен с каноническим снимком численно.
  Date/Author: 2026-09-20, Domain / API Implementer (DSH).

- Decision: длинный кадр передаётся отдельным параметром, а не переиспользуется из ACWR-кадrа, хотя оба сейчас равны 90 дням.
  Rationale: окно ACWR определяется эмпирическим прогревом, а не литературой: `models/acwr.py` выводит `ACWR_MIN_HISTORY_DAYS` = 84 как `2 × tau_CTL` из проб на постоянной нагрузке и лишь отмечает совпадение с практикой «ACWR показывают не раньше 8–12 недель». Литература там обосновывает формулу EWMA и пороги статусов, но не сам guard. Окно метрик — разогрев EWMA (`tau_CTL` = 42). Связывание сделало бы CTL неявно зависимым от ACWR-константы. Форма параметров повторяет уже принятый в #595 шаблон (`acwr_activities_df` / `acwr_as_of`).
  Date/Author: 2026-09-20, Domain / API Implementer (DSH).

- Decision: follow-up issue про readiness-окно (#616) создан **без** полного automation-контракта.
  Rationale: `.github/workflows/codex-assign.yml` при открытии issue с точным блоком `### Change Class` и остальными обязательными секциями немедленно ставит задачу агенту Codex. Это расходует квоту и нарушает WIP-лимит владельца («один активный Class A слайс плюс не более одного мелкого maintenance item») без его решения. Issue #616 оформлен в стиле соседних слайсов #608/#609/#610 (заголовки второго уровня) и содержит секцию `Dispatch` с явным «автодиспетч не авторизован». Проверено: комментариев от automation в #616 нет.
  Date/Author: 2026-09-20, Domain / API Implementer (DSH).

## Outcomes & Retrospective

Промежуточный итог по шагу 0. Слайс #598 закрыл первый из двух truth prerequisites родительского #607. Воспроизведены и устранены два связанных дефекта: метрики замерзали на дате последней тренировки, и 30-дневное окно занижало витринный CTL на треть. Побочный, но более ценный результат — обнаружено, что API уже маскировал заморозку проекцией из канонического снимка, из-за чего часть payload считалась от одной серии, а часть от другой, и ответ предписывал полный отдых атлету с положительным TSB.

Урок для последующих слайсов: прежде чем называть поверхность сломанной, нужно проверить, не перекрывается ли наблюдаемое значение другим источником в том же ответе. Здесь «очевидный» дефект легаси-страницы оказался лишь половиной картины, а настоящая пользовательская боль жила в API, который выглядел исправным.

Шаг 0 закрыт целиком: #598 и #601 оба поставлены. **Часть 1 слайса #608 поставлена** (PR #620, merge `485cd62`): описательная шкала нагрузки, шим совместимости с прежним словарём провайдера, провенанс и раздельные версии, непредписывающий инвариант. **#609 поставлен** (PR #631, merge commit `440d1795`; head `2ef734b`): каноническая provider-free session projection и её API/TypeScript reuse в Today/Planning/Activity; browser clickthrough не заявлен. **#610 реализован локально и ожидает независимого ревью/owner acceptance:** additive story contract потребляется Today и Coach; composer сохраняет границы plan/fact/evidence и не добавляет запись состояния. Полные проверки и незакрытые accessibility/browser states перечислены выше. Затем — приёмка #367. Часть 2 #608 остаётся отложенной до реального, отдельно специфицированного consumer/composer. Этот документ и промежуточный checkpoint не авторизуют merge.

## Context and Orientation

Проект AI Trainer — это Python-бэкенд и веб-интерфейс. Пользовательские поверхности живут в `web/` (Next.js), доменная логика — в общем Python-слое, который отдаётся через FastAPI в `api/`. Легаси-интерфейс на Streamlit (`app.py`, `ui/pages/*`) остаётся поддерживаемым до паритета и не должен получать новых продуктовых фич; он потребляет те же headless-билдеры, что и API.

Термины, которые встречаются ниже. **TSS** (Training Stress Score) — численная оценка нагрузки одной тренировки. **CTL** (Chronic Training Load, «тренированность») — экспоненциальное среднее дневной нагрузки с постоянной времени 42 дня. **ATL** (Acute Training Load, «усталость») — то же с постоянной времени 7 дней. **TSB** (Training Stress Balance, «форма») — разность CTL и ATL. **EWMA** — экспоненциально взвешенное скользящее среднее; из-за него ряд нужно «разогревать», иначе среднее занижено. **ACWR** — отношение острой нагрузки к хронической. **Brick** — составная тренировка из нескольких последовательных сегментов (например, велосипед, затем бег), которая для атлета является одной сессией. **Fail closed** — при отсутствующих, устаревших или противоречивых данных система честно сообщает о нехватке доказательств вместо того, чтобы выдать уверенное утверждение. **Reconciliation** — сопоставление запланированной сессии с фактическими активностями.

Где сегодня собирается дневное решение. `models/signals_engine.py` содержит `assemble_signals` — общий вход для нагрузки, HRV, сна, готовности и рекомендаций; он же считает CTL/ATL/TSB через `training_load_metrics` и ACWR через `acwr_metrics`. `models/dashboard_summary.py` содержит headless-билдеры дашборда, включая `calculate_current_status` и `project_readiness_snapshot`. `services/readiness_snapshot.py` строит канонический снимок готовности; каноническое окно метрик и функция `_tsb_metrics` живут в `models/readiness.py`. Роутеры — `api/routers/dashboard.py`; легаси-поверхность — `ui/pages/dashboard.py`. Каноническая дата атлета берётся из `utils/athlete_time.athlete_local_date()`, часовой пояс — из настройки `ATHLETE_TIMEZONE`.

## Plan of Work

Шаг 0 — truth prerequisites. Два дефекта, из-за которых дальнейшие слайсы строились бы на неверных числах. #598 исправлен: `calculate_current_status` и `assemble_signals` принимают отдельный длинный кадр и якорь, оба дашборд-эндпоинта и легаси-страница передают каноническое окно и `athlete_local_date()`. #601 также поставлен: шесть решений о календарном дне атлета в `api/planning_service.py` — `_start_week`, окно активных ограничений в `current_status`, `active_plan_overview`, `as_of` для `apply_race_event_overlays` в `build_plan`, `week_by_week_plan` и `_refresh_match_recovery` — переведены на `athlete_local_date()`. Три сайта `datetime.now().isoformat()` (метки `plan_revision`) сознательно оставлены host-clock: это метки времени, а не атлетские границы. Шаг 0 закрыт целиком; work не остаётся.

Слайс #608 — безопасная семантика нагрузки. Локальный ACWR (`models/acwr.py`, добавлен в #593/#595) считал полезное отношение, но его пользовательский словарь содержал safety/risk-лексику: полосы назывались safe, optimal, moderate_risk, high_risk. ACWR сам по себе не устанавливает вероятность травмы. **Часть 1 поставлена** (PR #620, merge `485cd62`): шкала заменена на описательную относительно базы атлета (`below_baseline` / `expected_band` / `elevated` / `strongly_elevated`), прежний словарь провайдера принимается только на входе шимом совместимости, сигнал несёт провенанс (`history_days`, `acute_tau_days`, `chronic_tau_days`), раздельные версии математики и интерпретации, постоянную оговорку и `intervention_eligible: false`. EWMA-математика, окна и пороги не менялись. **Часть 2** — положительный сценарий «предписание разрешено свежими симптомами или ограничениями» — остаётся в #608: ACWR не участвует ни в одном предписании, поэтому реализовывать и проверять сценарий пока не на чем.

Слайс #609 — session-first план/факт. Сегодня план, reconciliation, карточка активности, обратная связь и готовность уже отдают почти все нужные доказательства, но нет единой серверной проекции, которая объясняет одну запланированную сессию против одной объединённой фактической. Работа: определить одну каноническую read-only проекцию поверх существующих доказательств, сохранив стабильный родительский идентификатор плановой сессии, упорядоченные идентификаторы сегментов, идентификаторы фактических активностей, ревизию сопоставления и ревизию доказательств. Brick представляется как одна родительская сессия с упорядоченными сегментами и переходом; частичный brick остаётся незавершённым, доступный сегмент сохраняется, синтетический второй сегмент не выдумывается. Неоднозначные активности дают статус «требуется подтверждение» и не порождают уверенной причины или утверждения о выполнении. Сопоставленная нагрузка, несопоставленная дополнительная нагрузка и итог дня выставляются раздельно и арифметически согласованно. Никакого второго матчера и никакого переписывания исторических сопоставлений. Порядок доставки зафиксирован в slice spec: (1) spec + пять RED fixtures; (2) чистый composer + local service и compatibility cases; (3) additive API/types и переиспользование Today/Planning/Activity. Первый пункт выполнен, следующие не начаты.

Слайс #610 — Today decision story. Композиция плана, факта, состояния, объяснения и следующего действия в основную поверхность с progressive disclosure. Сначала решение, затем объяснение, технические метрики по запросу. Факты, интерпретация и рекомендация остаются разными полями контракта и разным содержимым интерфейса. Противоречивые или недостаточные доказательства завершаются объяснением или вопросом, а не выдуманной причиной и не предписанием. Раскрытие деталей не делает запрос к провайдеру и не запускает альтернативный доменный расчёт.

Слайс #367 — приёмка реальными техническими атлетами. Прогон полного пути, замер времени ответа на вопрос «что/почему/доказательства/дальше» (цель — не более 60 секунд), превращение наблюдаемых провалов в ограниченные issues.

## Concrete Steps

Все команды выполняются из корня репозитория — каталога, содержащего `AGENTS.md` и `pytest.ini`. Виртуальное окружение — `ai_trainer_env`; в CI используется системный `python`.

Слайс #598 (уже выполнен, ветка `fix/issue-598-metrics-anchor`):

    ai_trainer_env/bin/python -m pytest tests/smoke/test_dashboard_metrics_anchor.py -q
    ai_trainer_env/bin/python -m ruff check .
    ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/ -q
    npm --prefix web run contract:extract -- --check

Слайс #608, часть 1 (поставлен, PR #620, merge `485cd62`):

    ai_trainer_env/bin/python -m pytest tests/smoke/test_acwr_semantics.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke/test_api_dashboard_acwr_contract.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke/test_acwr.py -q
    ai_trainer_env/bin/python -m ruff check .
    npm --prefix web run contract:extract -- --check

Для следующего кодового слайса порядок такой: сначала slice spec в `docs/` по шаблону `docs/templates/slice_spec_review_template.md`, затем RED-тест, который падает по правильной причине, затем минимальная реализация, затем focused-набор, затем полный contributor-safe набор, затем web lint/build, если затронут `web/`. Ветка должна содержать номер issue в имени (`fix/issue-<N>-<slug>` или `feat/issue-<N>-<slug>`), а тело PR — строку `Closes #<N>`, иначе projection готовности к merge не сработает.

Слайс #609, первый milestone (текущая ветка `codex/issue-609-session-projection`):

    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest tests/smoke/test_session_projection.py -q
    # RED checkpoint: 5 failed; четыре импорта models.session_projection и
    # один services.session_projection. Иных причин падения нет.

Слайс #609, второй milestone:

    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest tests/smoke/test_session_projection.py -q
    # 9 passed
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest tests/smoke/test_session_projection.py tests/smoke/test_plan_actual_reconciliation.py tests/smoke/test_reconciliation_service_migration.py tests/smoke/test_plan_vs_fact.py tests/smoke/test_feedback_planning_handoff.py tests/smoke/test_activity_card.py tests/smoke/test_api_today.py -q
    # 121 passed
    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m ruff check --no-cache .
    # All checks passed!

Contributor-safe набор запускается из полной временной копии ветки в
записываемом каталоге, потому что системный каталог worktree запрещает legacy-
тестам создавать относительные SQLite-файлы. На полной копии:

    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/ -q
    # 2801 passed, 40 skipped, 38 deselected

## Validation and Acceptance

Приёмка формулируется как наблюдаемое поведение, а не как наличие кода.

Приёмка шага 0 воспроизводится на ветке `fix/issue-598-metrics-anchor`
(PR #614, ревизия `38ed4f0`), а не на ветке этого документа: тест
`tests/smoke/test_dashboard_metrics_anchor.py` и slice spec живут там. На
чистой копии репозитория ветки может не быть, а сама она может переехать или
исчезнуть. Возьмите конкретную ревизию:

    git fetch origin pull/614/head:review-598
    git checkout review-598
    git merge-base --is-ancestor 38ed4f0 HEAD   # должно вернуть 0

и только затем запустите
`ai_trainer_env/bin/python -m pytest tests/smoke/test_dashboard_metrics_anchor.py -q`
и ожидайте `9 passed`. До исправления тот же файл давал `7 failed, 1 passed`:
семь тестов падали, включая `test_api_summary_payload_agrees_with_itself` с
сообщением о том, что `load.form` противоречит `load.tsb`, и
`test_legacy_dashboard_status_is_anchored` с сообщением о замороженном ATL
106.2. Полный набор на той же ветке:
`ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/ -q`
даёт `2801 passed, 13 skipped, 38 deselected`. Прогон `ai_trainer_env/bin/python -m ruff check .` должен закончиться строкой `All checks passed!`, а `npm --prefix web run contract:extract -- --check` — строкой о том, что артефакт актуален.

Поведенческая приёмка для шага 0 воспроизводится на временной базе данных: блок нарастающей нагрузки три недели, затем четырнадцать дней отдыха. Откройте `GET /api/dashboard/summary` и убедитесь, что `signals.load.tsb` положителен, `signals.load.form` совпадает с `signals.load.label` и соответствует зоне `tsb_zone` от собственного `load.tsb`, а `signals.critical.status` не равен «Критическое переутомление». Обратный случай тоже обязателен: тот же атлет через четырнадцать дней отдыха не должен получать рекомендацию «Немедленный отдых» с обоснованием «TSB критически низкий».

Для последующих слайсов критерии приёмки не делегируются внешним issue — ниже
они приведены целиком, чтобы план оставался самодостаточным для того, у кого
есть только этот репозиторий.

**#608 — безопасная семантика нагрузки. Часть 1 поставлена** (PR #620, merge
`485cd62`) и проверяется так:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_acwr_semantics.py -q
    # ожидается 12 passed: описательная шкала, провенанс, раздельные версии,
    # отсутствие риск-лексики в подписях, intervention_eligible is False
    ai_trainer_env/bin/python -m pytest tests/smoke/test_api_dashboard_acwr_contract.py -q
    # ожидается 2 passed: runtime DTO отдаёт шесть новых полей и новую шкалу
    # и не выпускает прежний словарь провайдера в provider_status
    ai_trainer_env/bin/python -m pytest tests/smoke/test_acwr.py -q
    # ожидается 59 passed: численные фикстуры и пороги 0.8 / 1.3 / 1.5 не изменились

Проверка лексики должна быть узкой: репозиторный поиск по `safe` даёт ложные
срабатывания на `_safe_float`, `safe_deliver_active_plan`, `safeRecoveryVariants`
и `web/package-lock.json`, поэтому критерием он служить не может. Ищите риск-слова
только в пользовательских подписях ACWR, а надёжнее — утверждать отрендеренные
подписи полос напрямую в тесте.

**Часть 2 #608 не реализована и автоматически не проверяется.** Положительный
сценарий — предписание разрешено, когда его подтверждают свежие симптомы или
ограничения — теста не имеет, потому что ACWR не участвует ни в одном
предписании: `_recommendations_for_signals` читает только `tsb` и `hrv`.
Проверять сценарий не на чем до появления реального consumer/composer. Решение
владельца записано в issue #608 комментарием от 2026-09-20; PR #620 не закрывает
#608.

**#609 — session-first план/факт.** Матч одиночной сессии даёт одного родителя с
согласованными длительностью и нагрузкой план/факт, идентификаторами активностей
и ревизией доказательств. Brick «велосипед → бег» даёт одного родителя, два
упорядоченных сегмента и итог без двойного счёта. Частичный brick остаётся
незавершённым и не изобретает второй сегмент. Две правдоподобные активности дают
статус «требуется подтверждение» без уверенной причины. Сопоставленная нагрузка,
дополнительная несопоставленная и итог дня выставляются раздельно и сходятся
арифметически. Проекция не делает вызовов провайдера. Команды:
`python -m pytest tests/smoke/test_plan_actual_reconciliation.py
tests/smoke/test_plan_vs_fact.py tests/smoke/test_feedback_planning_handoff.py
tests/smoke/test_activity_card.py tests/smoke/test_api_today.py -q` — ожидается
зелёный прогон на фикстурах одиночной сессии, brick, частичного brick и
неоднозначного матча.

До GREEN отдельно воспроизводится намеренный RED milestone:

    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest tests/smoke/test_session_projection.py -q
    # 5 failed: ModuleNotFoundError только для ещё не реализованных
    # models.session_projection / services.session_projection

Это не регрессия существующего кода и не готовность к merge: тесты фиксируют
будущий контракт, а отсутствующая реализация является ожидаемой причиной RED.

GREEN второго milestone проверяется тем же projection-файлом (`9 passed`) и
focused-набором (`121 passed`). Provider-free тест подменяет клиент функцией,
которая немедленно падает при обращении; проекция успешно строится дважды, а
полные снимки изменяемых SQLite-таблиц до и после совпадают. Explicit confirm и
следующий `user_unmatched` проходят через существующий reconciliation ledger и
возвращают ревизии 1 и 2; composer сам приоритет не вычисляет.

**#610 — Today decision story.** Основная поверхность отвечает на «что / почему /
доказательства / дальше» без перехода на другую страницу; факты, интерпретация и
рекомендация — разные поля контракта и разное содержимое интерфейса; раскрытие
деталей не делает запрос к провайдеру; противоречивые доказательства дают
объяснение или вопрос. Команды: `npm --prefix web run lint && npm --prefix web run build`
плюс изолированная браузерная приёмка `ACCEPTANCE_PORT=8510 ./run_acceptance.sh`.

**#367 — приёмка техническими атлетами.** Модератор фиксирует время ответа на
четыре вопроса (цель — не более 60 секунд), ноль расхождений идентичности сессии и
итогов план/факт между Today, Planning и Activity на одной ревизии доказательств, и
наличие подтверждающих доказательств у каждого предписания. Наблюдаемые провалы
становятся ограниченными issue.

Falsifying scenarios родительского #607, которые обязана воспроизвести приёмка: неоднозначное сопоставление двух правдоподобных активностей не должно давать уверенной причины; частичный brick сохраняет доступный сегмент и не изобретает второй; устаревшая готовность при повышенной нагрузке не должна превращать ACWR в утверждение о риске травмы; свежая положительная готовность при явных негативных симптомах должна показать конфликт, а не молча выбрать один сигнал; одна и та же ревизия доказательств в Today, Planning и Activity должна давать совпадающие идентичность и итоги.

## Idempotence and Recovery

Пересчёт метрик — чистая функция без записи, миграций и сетевых вызовов.
`contract:extract -- --check` ничего не пишет и только сравнивает артефакт с
кодом. Focused-набор работает на временных базах в `tmp_path`.

**Полный contributor-safe набор не изолирован от локальной базы, и это надо
знать.** `tests/conftest.py` автоматически помечает часть файлов в корне
`tests/` маркерами `live`/`debug`, поэтому фильтр
`-m "not live and not debug and not e2e"` их отсеивает — сегодня это 38
тестов. Но запуск `pytest tests/` без фильтра или прямой вызов такого файла
даёт побочный эффект: `tests/test_full_sync_cycle.py` создаёт `Database()` с
дефолтным путём (`Settings.DATABASE_PATH = "ai_trainer.db"`) и записывает
синтетические данные сна за вчерашний день.

- **Observed**: прогон `tests/test_full_sync_cycle.py` против копии рабочей базы
  (`VACUUM INTO`) переписал строку сна за вчерашний день: дневные метрики (общая
  длительность, фазы, счёт) заменились синтетическими значениями теста, а
  провенанс понизился с провайдерского до `legacy_unknown`. Конкретные значения
  и дата здесь намеренно не приводятся — это личные метрики здоровья, и они не
  должны попадать в отслеживаемый документ. Поле `created_at` при этом не
  изменилось, поэтому по нему потерю не заметить.
- **Inferred**: механизм — `sync_sleep_data` обновляет строку, когда источник
  совпадает, и не трогает `created_at`. Опровергающая проверка — сравнить
  строку до и после на копии базы.
- **Verified by**: сравнение выполнено на песочной копии; рабочая база не
  использовалась.

Отсюда правило: запускайте набор с фильтром маркеров, как в примерах выше.
Одного `DATABASE_PATH=<временный путь>` **недостаточно**: он перенаправляет
только `Database()`, а `tests/test_full_sync_cycle.py` в проверочной части и в
резервной ветке записи открывает базу напрямую через
`sqlite3.connect('ai_trainer.db')` по жёстко заданному пути, поэтому такой
прогон всё равно коснётся рабочего кэша. Надёжная изоляция — запуск из
отдельного рабочего каталога без рабочей базы. Никогда не направляйте эти
команды на рабочую `ai_trainer.db`.

Если шаг падает на середине, безопасная точка возврата — чистое дерево на
`origin/main`, но **сначала сохраните работу**. `git checkout -- .`
перезаписывает отслеживаемые файлы из индекса и потому уничтожает
незакоммиченные изменения слайса — ровно тот случай, ради которого этот раздел
и написан. Порядок такой: посмотрите `git status --short` и `git diff`,
сохраните нужное (`git diff > <файл>` либо коммит в черновую ветку), и только
затем восстанавливайте явно выбранные пути (`git checkout -- <путь>`). Ветку
слайса удаляйте лишь после того, как работа опубликована или осознанно
отброшена. Если контрактный артефакт перестал быть свежим, восстановление — `npm --prefix web run contract:extract` без `--check`, но это осознанное изменение контракта и требует объяснения в PR, а не молчаливой регенерации.

Не выполняйте `git stash pop` без необходимости: в этом репозитории лежат два давних stash, не относящихся к текущей работе. Перед переключением ветки проверяйте `git status --short --branch`: рабочая копия должна быть чистой.

## Artifacts and Notes

Все артефакты ниже получены на ветке `fix/issue-598-metrics-anchor` (PR #614),
а не на ветке этого документа: тест `tests/smoke/test_dashboard_metrics_anchor.py`
и slice spec живут там. На ревизии `38ed4f0` значения «после исправления»
перепроверены и совпадают с приведёнными.

Воспроизведение шага 0 до исправления. Одна и та же локальная SQLite, один и тот же день, блок три недели со 100/110/120 TSS, закончившийся четырнадцать дней назад.

    Путь                                              CTL    ATL    TSB
    Канонический snapshot (_tsb_metrics, окно 90)     31.3   14.9   +16.4
    /api/dashboard/summary -> signals.load            31.3   14.9   +16.4
    /api/dashboard/summary -> signals.load.form         -      -    "Высокая усталость"
    /api/dashboard/summary -> signals.critical          -      -    "Критическое переутомление /
                                                                     Полный отдых 2-3 дня"
    /api/dashboard/summary -> recommendations[0]        -      -    "Немедленный отдых.
                                                                     TSB критически низкий (-30+)"
    Легаси ui/pages/dashboard.py                      37.7  106.2   -68.5

После исправления тот же прогон даёт `load.form = "Свежесть"`, совпадающий с `load.label` и зоной от `load.tsb = +16.4`, `signals.critical = {status: null, action: null}` и первую рекомендацию «Пиковая форма! TSB выше +5» вместо предписания отдыха.

Обратная совместимость: вызов `calculate_current_status` без новых параметров по-прежнему даёт CTL 37.7 / ATL 106.2 / TSB -68.5, то есть существующие вызывающие не меняют поведение, а новые параметры аддитивны.

Транскрипт проверок шага 0:

    $ ai_trainer_env/bin/python -m pytest tests/smoke/test_dashboard_metrics_anchor.py -q
    9 passed in 1.32s

    $ ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/ -q
    2801 passed, 13 skipped, 38 deselected, 1 warning in 129.19s

    $ ai_trainer_env/bin/python -m ruff check .
    All checks passed!

    $ npm --prefix web run contract:extract -- --check
    extract-contract: артефакт актуален (tests/contracts/ts_contract.json)

Slice spec шага 0 лежит в `docs/issue_598_dashboard_metrics_anchor_slice_spec.md` на ветке `fix/issue-598-metrics-anchor` и содержит RED-матрицу, Evidence Boundary Matrix и таблицу публичных контрактов.

## Interfaces and Dependencies

К концу шага 0 в `models/signals_engine.py` должна существовать функция со следующими keyword-параметрами (порядок сохраняется, все новые параметры имеют значение по умолчанию `None`, чтобы не менять поведение существующих вызывающих):

    def assemble_signals(
        activities_df: pd.DataFrame | None = None,
        hrv_df: pd.DataFrame | None = None,
        sleep_df: pd.DataFrame | None = None,
        training_status: Any = None,
        health_df: pd.DataFrame | None = None,
        as_of: date | None = None,
        metrics_activities_df: pd.DataFrame | None = None,
        acwr_activities_df: pd.DataFrame | None = None,
        acwr_as_of: date | None = None,
    ) -> dict[str, Any]

`metrics_activities_df` — длинная история только для CTL/ATL/TSB; при `None` используется `activities_df`. `as_of` — якорь, до которого достраиваются нулевые дни отдыха; при `None` ряд заканчивается последней активностью (прежнее поведение).

В `models/dashboard_summary.py`:

    def calculate_current_status(
        activities_df: pd.DataFrame,
        hrv_df: pd.DataFrame,
        sleep_df: pd.DataFrame,
        training_status: dict[str, Any] | None = None,
        acwr_activities_df: pd.DataFrame | None = None,
        acwr_as_of: date | None = None,
        metrics_activities_df: pd.DataFrame | None = None,
        as_of: date | None = None,
    ) -> dict[str, Any]

Границы канонического окна метрик считаются в одном месте, в
`models/readiness.py`:

    def load_metrics_window_bounds(anchor: date) -> tuple[str, str]:
        """Inclusive ISO bounds of the canonical CTL/ATL/TSB window."""

Она возвращает `(anchor - 89, anchor)`. Потребители обязаны брать метрики
именно этим интервалом, а не `Database.get_activities(N)`: тот режет по
включительной границе `today - N` и потому отдаёт `N + 1` календарную дату,
расходясь с каноническим окном на его краю (находка ревью #614). API-роутеры
используют `db.get_activities_between(*load_metrics_window_bounds(anchor))`,
легаси-страница — кэшируемый
`services.data_cache.load_activities_between(start, end)`.

Канонические зависимости, на которые опираются все слайсы: `models/readiness.py::LOAD_METRICS_WINDOW_DAYS` (окно метрик нагрузки, равно 90), `models/readiness.py::_tsb_metrics(activities_df, anchor)` (канонический расчёт CTL/ATL/TSB с якорем), `models/banister.py::tsb_zone(tsb)` (каноническая четырёхзонная классификация формы), `utils/athlete_time.athlete_local_date()` (календарный день атлета) и `services/readiness_snapshot.py::build_readiness_snapshot(db)` (канонический снимок готовности). Новых внешних библиотек этот план не вводит.

## Revision Notes

- (2026-09-23) Третий milestone #609 завершён в изолированной ветке:
  опубликованы API/TS и consumer checkpoints; Today, Planning и Activity теперь
  используют один DTO с общей identity и bucket-итогами. Верификация:
  contributor-safe `2835 passed, 16 skipped, 38 deselected`, Ruff, contract
  extraction/inventory, web lint и production build — зелёные. Browser
  clickthrough оставлен как явное ограничение: имеющийся acceptance launcher
  покрывает Streamlit, не Next.js. Draft PR #631 открыт и прикреплён к задаче;
  merge не выполнялся. GitHub CI и независимое native review ожидают read-back,
  owner acceptance не заявлена.

- (2026-09-22) Второй milestone #609: после двух дополнительных RED-кейсов
  реализованы чистый `models/session_projection.py` и provider-free
  `services/session_projection.py`. Самопроверка добавила отдельный bucket
  `other_matched_tss`, тест multi-session day и отдельный run-only partial,
  сохраняющий identity второй ноги; mixed naive/UTC timestamps нормализуются
  без падения. Зафиксированы focused/Ruff результаты и две неавторитетные
  попытки полного прогона с неверным cwd.

- (2026-09-21) #609 начат по команде владельца в изолированном worktree:
  добавлен bounded Class A slice spec и пять RED-фактур для single, полного и
  частичного brick, ambiguous match и provider-free/non-mutating read. Зафиксирован
  архитектурный выбор «composer + local service поверх canonical reconciliation»;
  GREEN, API и UI отложены до проверки границы.

- (2026-09-20) Исходы второго раунда ревью PR #615 (scoped delta): убраны
  реальные метрики сна из evidence-записи (P1 — в документе остались дата,
  фазы, счёт и провайдер из личной базы; заменены описанием без чисел),
  `Plan of Work` приведён в соответствие с поставленным #601, evidence про
  `sync` согласован с закрытием в PR #618, проверка лексики #608 сужена,
  команды focused-наборов #609 названы файлами, checkout привязан к
  неизменяемой ревизии, изоляция базы уточнена (одного `DATABASE_PATH`
  недостаточно из-за прямых `sqlite3.connect`), revision notes перенесены в
  конец документа. Причина: дельта показала, что план всё ещё не был
  самодостаточным, а одна запись раскрывала личные данные.

- (2026-09-20) Первая версия: создан как живой план инициативы #607 по
  требованию родительского issue; зафиксированы границы слайсов, шаг 0 и
  evidence-записи.
- (2026-09-20) Отмечен шаг 0: слайс #601 поставлен в PR #617, раздел
  `Progress` и `Outcomes & Retrospective` приведены в соответствие, добавлена
  запись о том, что не каждый `datetime.now()` в планировщике является
  атлетской границей.
- (2026-09-20) Исходы первого раунда ревью PR #615: раздел про полный прогон
  переписан по проверенному поведению (изоляция базы), `git checkout -- .`
  убран как безопасный откат, абсолютный путь заменён на корень репозитория,
  критерии приёмки последующих слайсов перенесены внутрь плана вместо
  делегирования issue, проба через `workflow_dispatch` помечена как живая
  запись, провенанс guard 84 исправлен на эмпирический, числа тестов и
  артефакты привязаны к ветке-источнику. Причина правок: ревью показало, что
  план не был самодостаточным и в одном месте давал небезопасную инструкцию.
- (2026-09-20) Проверка `sync` закрыта: секрет `ROADMAP_PROJECT_TOKEN`
  отсутствует, workflow выведен из эксплуатации в PR #618.
- (2026-09-20) Отмечена поставленная часть 1 слайса #608 (PR #620, merge
  `485cd62`): `Progress` разделён на часть 1 и часть 2, `Plan of Work` переписан
  по факту. Причина: план обязан отражать текущее состояние, иначе следующий
  исполнитель считает реализованное нереализованным.
- (2026-09-20) Исходы ревью PR #621: `Outcomes & Retrospective` приведён в
  соответствие с `Progress` (часть 1 поставлена, часть 2 остаётся), в `Concrete
  Steps` добавлены команды поставленной части, а приёмка #608 переписана —
  названы `test_acwr_semantics.py` и `test_api_dashboard_acwr_contract.py` с
  ожидаемыми результатами, положительный corroborated-intervention сценарий
  явно помечен как нереализованный и автоматически непроверяемый. Причина:
  ревью показало, что living-разделы разошлись между собой, а проверка части 1
  не была воспроизводима по одному этому документу; заодно исправлен разорванный
  абзац приёмки #608.
- (2026-09-23) Начат #610: добавлены `docs/issue_610_today_decision_story_slice_spec.md`
  и контрактные RED-тесты. Независимый read-only review выявил неоднозначность
  вокруг отсутствующего свежего injury self-report, риск противоречия compact
  Today и неверно широкое заявление о read-only `/api/today`; все три пункта
  уточнены в spec, #609 fixture исправлена по реальной DTO-форме. Повторный RED:
  пять composer-тестов падают из-за отсутствующего `models.today_decision_story`,
  UI contract — из-за отсутствия приоритета `decision_story.next_action`.
  Coach read-only граница подтверждена: не вызывать из Coach Today builder,
  потому что recovery loop сохраняет решение и может публиковать proposal.
  GREEN ожидает delta read-back; UI реализация остаётся handoff UI-специалисту.
- (2026-09-23) Owner delta read-back #610 принят без нового семантического review
  круга. Закреплены case `status=current` из-за другого wellness-ответа и
  фактура partial session строго по DTO #609 (две плановые ноги, одна фактическая
  с `planned_leg_id`, `leg_index`, `activity_id`). Domain/API GREEN добавил чистый
  `models/today_decision_story.py`, `decision_story` в `/api/today`, read-only
  source adapter и вложение того же DTO в `get_readiness_today` для Coach; Coach
  presenter сохраняет DTO в контексте, prompt запрещает переинтерпретировать
  его action. Добавлен TypeScript contract
  и регенерирован `ts_contract.json`. Проверено: focused tests `36 passed` (один
  исходный source-text UI probe удалён как недостаточное доказательство), Ruff,
  `git diff --check`, contract extraction/check — зелёные. Web lint заблокирован:
  в worktree нет зависимостей, а main-checkout CLI несовместим; web build не запускался.
  Компактный/полный Today
  ещё не реализован; обязательный UI/browser handoff 390/1280 px остаётся перед
  завершением #610. Коммит/PR/merge не создавались.

- (2026-09-23) Supervisor / Integrator собрал backend/API и Today UI в том же
  изолированном worktree. Исправлен action parity дефект: Coach теперь использует
  pre-loop checkpoint и canonical Today proposal/session resolvers; regression
  фиксирует stale pending proposal => `inspect_evidence`. Исправлено сохранение
  поведения `AITools` при legacy construction через `object.__new__`; устаревшая
  source-text проверка compact Today обновлена и поведение проверено браузером.
  На свежей временной копии contributor-safe suite: `2827 passed, 40 skipped,
  39 deselected`; focused `37 passed`; additional focused regressions `50 passed`;
  Ruff, contract freshness/inventory, web lint/build, E2E 390/1280 и
  `git diff --check` зелёные. Рабочая SQLite не использовалась. Отдельные
  screen-reader и loading/empty/error/stale browser состояния не проверялись.
  PR/merge не создавались; далее — независимое ревью и owner gate.
