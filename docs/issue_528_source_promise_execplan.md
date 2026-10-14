# #528: достоверное сообщение инструмента при отсутствии отрезков

Этот ExecPlan ведётся по `.agent/PLANS.md`. После сохранения плана выполняется M1 без платного запуска. M1 — Class B: узкое исправление совместимого message; полный срез остаётся Class A из-за будущего live сравнения. Базовый код для планирования:52e0e6d, база M1:d53d529, локальная ветка codex/issue-528-runtime-experiment. Issue: https://github.com/rbctmz/ai_trainer/issues/528.

## Purpose / Big Picture

Coach должен честно объяснять отсутствие отрезков, не обещая, что синхронизация обязательно их создаст. Сейчас это обещание уже содержится в результате инструмента, поэтому модель получает недостоверную подсказку до генерации ответа. Исправить исходное сообщение, закрепить путь «tool result → formatter → model context» и измерить, перестал ли Coach повторять гарантию.

## Progress

- [x] (2026-10-14) Прочитаны текущие A/B traces и источник сообщения; гипотеза проверена офлайн на synthetic DB.
- [x] (2026-10-14) Scope, этапы, бюджет и критерии этого плана записаны до реализации.
- [x] (2026-10-14) Заполнен [slice spec](issue_528_source_promise_slice_spec.md), независимый bounded spec check: блокеров нет; handoff Spec Owner → Domain Implementer.
- [x] (2026-10-14) M1: RED/GREEN для сообщения инструмента и его доставки в контекст модели:2failed до исправления,104focused passed после.
- [x] (2026-10-14) M1:104focused passed,2951smoke passed/35skipped, lint/diff checks passed; self-review и independent checker без блокеров.
- [x] (2026-10-14) Владелец авторизовал M2 сообщением «Делай» после представления4trials/16calls бюджета. [M2 slice spec](issue_528_source_comparison_slice_spec.md) заморожен; independent spec check без блокеров, handoff Spec Owner → Domain Implementer.
- [ ] M2: замороженное сравнение исходного/исправленного сообщения,4trials/16calls максимум.
- [x] (2026-10-15) Source-ab runner/CLI готов:112focused passed,2957smoke passed/35skipped, lint/diff passed; independent implementation checker32passed, блокеров нет. Last2boundarytests добавлены после broad collection и проверены targeted/checker.
- [ ] Immutable trace, отдельная human assessment, итоговое решение и локальный проверенный checkpoint.

## Surprises & Discoveries

**Observed:** `_ACTIVITY_STRUCTURE_MESSAGES['not_fetched']` в models/ai_tools.py:117–119 содержит «Они появятся после синхронизации ... или после открытия карточки». Та же строка присутствует в raw_result.message и formatted_result сохранённого A/B JSON. **Inferred:** часть обещаний модели может быть повторением ошибочного исходного сообщения, поэтому приоритет исправления начинается до synthesis. Самый дешёвый falsifier — проверить реальный tool/presenter на missing-cache fixture и попытку fetch с недоступным provider. **Verified by:** офлайн synthetic DB + AITools.get_activity_structure + format_tool_result подтвердили доставку строки; fetch_activity_intervals с пустым cache и is_configured=False вернулNone. Это доказывает неверную безусловную гарантию в источнике, но не объясняет всё поведение модели.

## Decision Log

Decision: менять только not_fetched сообщение, сохраняя статус unavailable, reason not_fetched и structured/empty/no_provider_link/corrupt_cache значения. Rationale: исправляется факт в исходном контексте, не формулы, загрузка или форма API. Date:2026-10-14.

Decision: существующие prompts, compact candidate и модель оставить одинаковыми в source A/B. Единственное отличие — исходная/исправленная message строка. Rationale: предыдущий compact A/B не исправил guarantees; новое сравнение должно проверять другой конкретный механизм. Date:2026-10-14.

Decision: live4attempts = одна missing-cache задача × два message variants × два повтора; максимум16provider calls,4/trial,12tools/trial,1800outputtokens/call,45sSDKtimeout,zero retries. Rationale: достаточный ограниченный повтор для первичной проверки источника, без нового большого eval круга. Это планируемый бюджет, здесь вызовов нет. Date:2026-10-14.

Decision: основная приёмка этого этапа — правдивость сообщения и отсутствие гарантии в model answer. Краткость измерять отдельно; превышение80слов не подменяет truthfulness verdict. Старые baseline/A/B scores не пересчитывать. Date:2026-10-14.

Decision: M2 использует одинаковый compact_answer_v1 response contract в обоих source variants и отдельный source-ab CLI/report. Rationale: повторить проблемный missing-cache контекст compact A/B, сохранив единственное изменяемое поле message. Immutable JSON не объявляет semantic pass, отдельная оценка всех4answers атрибутируется агенту; review Greg не заявляется. Date:2026-10-14.

Decision: до первого платного вызова наступил2026-10-15; дата fixture/вопроса и live --today сдвинуты вместе на15октября/14октября факта. Rationale: native calendar соответствует дате исполнения; ни одной платной попытки до смены дня не было. Gate, registry, budget и messages не изменены. Date:2026-10-15.

## Outcomes & Retrospective

M1 исправляет исходную гарантию и подтверждает доставку ограничения в оба контекста модели офлайн. Real synthetic DB native+synthesis probe сохранил одинаковый logical hash; внешних вызовов нет. Independent checker:21passed, блокеров нет, checkout не изменён reviewer. M2 ещё не выполнен. Источник ошибочной гарантии воспроизведён; краткость остаётся отдельной гипотезой. Исправление источника не гарантирует исчезновения всех неподтверждённых утверждений модели.

## Context and Orientation

`models/ai_tools.py::_ACTIVITY_STRUCTURE_MESSAGES` задаёт message для cached-only get_activity_structure. `resolve_cached_activity_structure` различает реальные отрезки, проанализированную пустую структуру и неизвестную структуру. `models/coach_tool_presenter.py::_activity_structure_block` без изменений помещает message в formatted_result, который shared runtime передаёт модели.

`services/activity_intervals.py::fetch_activity_intervals` — отдельный загрузчик для карточки. Он может вернуть None/старый cache при отсутствующей конфигурации, provider error или malformed payload. Сам Coach tool за сетью не ходит. «Данные не загружены» нельзя превращать ни в «отрезков не было», ни в «следующая синхронизация точно их даст».

Существующие тесты: `tests/smoke/test_coach_activity_structure_tool.py`, `tests/smoke/test_activity_intervals.py`, `tests/smoke/test_coach_runtime_eval.py`, `tests/smoke/test_coach_compact_ab.py`. Экспериментальный runner — `services/coach_runtime_eval.py`, CLI — `scripts/run_coach_runtime_eval.py`, реестр — `tests/evals/coach/runtime_registry.py`.

## Scope and Role Handoff

Spec Owner фиксирует данный bounded intent. После spec check Domain Implementer правит только message и contract-backed tests; fixture/runner/CLI изменения допускаются только для source A/B с одним изменяемым полем. Independent Reviewer проверяет read-only delta и разрешённые offline tests. Greg — владелец следующего исполнения/merge. UI/CSS, API schemas, readiness/TSS/planner, data persistence, sync behavior, prompts и provider settings в срез не входят.

## Milestones / Plan of Work

### M1 — достоверный вход модели

Сначала добавить regression в tests/smoke/test_coach_activity_structure_tool.py: реальный cached-only инструмент на linked activity без cache возвращает unavailable/not_fetched и сообщает отсутствие данных, но не безусловный успех будущей операции. Тот же message должен дойти через реальный presenter в native tool message и synthesis prompt. До исправления тест воспроизводит неправильную гарантию.

Затем заменить только not_fetched текст. Рабочий вариант: «Структура недоступна: интервалы этой активности ещё не выгружены в кэш. Проверьте, доступны ли отрезки в Intervals.icu. После успешного получения этих данных повторите запрос; сейчас инструмент читает только сохранённые данные». Условие успешного получения не является гарантией его наступления.

Проверить существующие success/empty/no-link/corrupt-cache cases и offline fetch failures. Не добавлять сетевую загрузку в Coach tool. Доказать неизменность synthetic DB на turn и прежнюю форму результата. Завершить M1 независимой проверкой source/message boundary; это проверяемый результат без model calls.

### M2 — проверка поведения настоящего Coach

Зафиксировать одну согласованную canonical synthetic DB и одну missing-cache задачу. Два варианта tool message — исходный, сохранённый в старой trace, и исправленный. В экспериментальной read-only обвязке подменяется только message при его формировании; настоящий tool, formatter и shared runtime работают как раньше. Product default остаётся исправленным, экспериментальная подстановка исходного message не становится production mode.

Для каждого из двух повторов чередовать before/after порядок, клонировать одинаковую DB через SQLite backup. Model, settings, prompts, response contract, data/date одинаковы. Перед live freeze criteria, независимый checker, explicit finite run setup. Выполнить только4trials с одним global cap16; если среда/календарь/провайдер не позволяют сравнение, сохранить INCONCLUSIVE без бесконечного retry.

## Concrete Steps

Работать в `/Users/gregkisel/.codex/worktrees/coach-runtime-eval/ai_trainer`; использовать `/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python` либо активированный эквивалентный venv.

    python -m pytest tests/smoke/test_coach_activity_structure_tool.py tests/smoke/test_activity_intervals.py tests/smoke/test_coach_runtime_eval.py tests/smoke/test_coach_compact_ab.py -q
    python -m ruff check .

В текущем sandbox использовать -p no:cacheprovider и ruff --no-cache. Broad smoke требует отдельного writable DATABASE_PATH/CHATS_DIR в новом temp каталоге, чтобы не создавать default DB в checkout. Source-comparison mode — `--experiment source-ab`, точно2repeats. Конкретная finite live CLI команда и frozen acceptance записаны в reports/2026-10-15-coach-source-ab/README.md; compact-ab не является заменой этого эксперимента.

## Validation and Acceptance

Given linked activity без interval cache, when вызван Coach tool, then unavailable/not_fetched сохраняется, отрезки не выдуманы и message не гарантирует fetch success. Given такой результат, when presenter/native/synthesis получают его, then доставляется именно исправленное ограничение. Given unconfigured/error/malformed provider, when offline fetch probe выполняется, then источник не обещает появление данных и cached-only tool не инициирует сеть. Given реальные cached intervals, then числа/структура прежние; given analyzed-empty, then «отрезков нет» остаётся отличным от missing-data.

Source/model stage успешен только если2/2 after answers признают отсутствие структуры, не выдумывают отрезки и не гарантируют успешную синхронизацию/открытие карточки. Все четыре planned trials в denominator; ошибки выполнения — INCONCLUSIVE. Человеческая оценка всех четырёх ответов обязательна: lexical guarantee predicate уже пропускал формы «материализуются». Word count — diagnostic, а не новый blocker правдивости этого этапа. Не считать до/после causal proof при малой выборке; сообщить наблюдения и границы.

## Idempotence, Failure and Recovery

Рабочая DB/чаты/персональные данные не участвуют. Temporary canonical DB и per-trial clones очищаются после run. Unknown/mutation tools отклоняются до callable; logical hashes до/после одинаковы. JSON создаётся только новым файлом, без overwrite. Credentials не выводятся, SDK retries0, call count конечный. Если M2 не подтверждает expected behavior, оставить отрицательный отчёт и триаж остатка; не менять predicates/prompts по ходу run. Reset удаляет только экспериментальные output artifacts, не product state. Merge требует отдельного решения владельца.

## ASR / ADR Traceability

ASR-REL-2: data gap остаётся неизвестностью; ASR-SEC-1: traces без секретов; ASR-REL-1/3: read-only synthetic turn без потери данных. ADR-0001: shared Python source; ADR-0010: A0-only tools, никаких external activity writes. API/TS/DB contract shape не меняется; message текст — совместимое исправление недостоверного значения.

## Artifacts and Interfaces

Отдельный будущий slice spec, RED/GREEN evidence, immutable source-comparison JSON и human assessment. Новое source-comparison report имеет собственную registry/version/provenance, source-message variants и same-input hash; старые baseline/compact-ab files immutable. Переиспользовать run_trial, recording provider, read-only tools и budget guard. Существующий baseline cap24 и compact-ab cap64 не повышаются. No new dependency/framework.

Revision2026-10-14: после запроса «Что дальше?» выполнен M1; paid M2 остаётся отдельным следующим этапом. RED/GREEN, probe и независимая проверка записаны в slice spec.
