# Небольшой сквозной эксперимент Coach (#528)

Этот ExecPlan ведётся по `.agent/PLANS.md`. Это Class A из-за ограниченных платных вызовов; эксперимент дополняет #528, но не закрывает весь issue.

## Purpose / Big Picture

Проверить, выбирает ли настоящий Coach нужные инструменты и даёт ли короткий ответ, опирающийся на полученные данные. Оператор запускает CLI и получает JSON с запросами к модели, результатами инструментов, финальными ответами, проверками свойств и отдельными ошибками выполнения. Три синтетических сценария проверяют структуру плана, структуру выполненной активности и отсутствие кэша отрезков. Это первый baseline для карьерного демо, а не доказательство качества тренировочных рекомендаций.

## Progress

- [x] (2026-10-13) Проверены актуальные #528 и main `23fd7d6`, существующие behavioral/synthetic eval и shared runtime.
- [x] (2026-10-13) Зафиксированы scope, бюджет и критерии.
- [x] (2026-10-13) Независимая проверка спецификации: исправлено P2 ожидание мощности на 128/198 Вт.
- [x] (2026-10-13) RED → GREEN: 27 focused tests passed (12 new runtime/CLI cases плюс 15 existing eval cases); ruff whole tree green с --no-cache.
- [ ] Независимая проверка реализации и broad tests.
- [ ] Live baseline: три сценария × два повтора, максимум 24 вызова без SDK retries.
- [ ] Сохранить очищенный результат и человеческую оценку ответов.

## Surprises & Discoveries

Observed: `services/coach_behavioral_eval.py` оценивает фиксированные ответы; `services/coach_synthetic_eval.py` доставляет фиксированный tool marker в synthesis prompt без модели. Inferred: эти проверки не доказывают самостоятельный выбор инструмента и качество финального текста. Verified by: чтение docstring и путей исполнения обоих модулей.

## Decision Log

Decision: переиспользовать `resolve_turn_tool_results`, `synthesize_ai_chat_response`, narrative evidence gate и bounded correction, как non-streaming ветку API. Rationale: собственный цикл модели исказил бы предмет эксперимента. SSE, chat storage и recovery orchestration не входят в этот прогон. Date: 2026-10-13.

Decision: разрешить только четыре инструмента чтения плана/структуры; новая временная БД на каждый trial, запрет любых других инструментов и проверка logical SQLite snapshot до/после. Rationale: модель не должна вызывать изменения или live ingestion. Date: 2026-10-13.

Decision: использовать явно выбранный configured DeepSeek, до 1800 output tokens на вызов, SDK timeout 45 секунд, zero SDK retries, максимум четыре вызова на trial и 24 на run. User authorization: владелец согласовал предложенный эксперимент с настоящей моделью; бюджет здесь фиксирует конечный объём. Date: 2026-10-13.

Decision: автоматические проверки свойств отдельно от ручной оценки смысла; не объявлять качество доказанным по одному слову или числу. Первые два сценария — development, отсутствие кэша — holdout: сценарий не используется для настройки production prompt. Date: 2026-10-13.

## Outcomes & Retrospective

Offline runner и CLI проходят 27 focused tests. Live результат пока не получен. Отсутствие credentials или provider failure означает INCONCLUSIVE, не низкое качество Coach. Изменение production поведения и автоматические фиксы провалов исключены.

## Context and Orientation

`tests/evals/coach/registry.py` содержит версии фиксированных ответов. `services/coach_synthetic_eval.py::build_synthetic_coach_database` создаёт синтетические checkpoint, активности и interval cache. `models/ai_tools.py::AITools` выполняет настоящие инструменты, `models/coach_tool_presenter.py::format_tool_result` готовит данные для модели. `models/ai_coach_runtime.py` выбирает инструменты и синтезирует ответ. Трасса — сохранённая последовательность видимых запросов/ответов провайдера и выполнения инструментов; скрытые рассуждения не сохраняются. Trial — один вопрос с новой фикстурой и независимым повтором.

## Plan of Work

Добавить `services/coach_runtime_eval.py` с тонкой обвязкой существующего runtime, read-only инструментами, трассой, лимитами и оценкой. Реестр трёх вопросов находится в `tests/evals/coach/runtime_registry.py`. Добавить `scripts/run_coach_runtime_eval.py`: офлайн scripted smoke без ключей и явно выбранный live provider без fallback на mock. Тесты в `tests/smoke/test_coach_runtime_eval.py` проверяют итоговое поведение, ложноположительные оценки, запрет мутаций, лимиты, ошибки и неизменность БД. Исходные поведенческие предикаты остаются совместимыми. CI уже запускает contributor-safe tests, в которые входят новые offline tests; live baseline вручную, без credentials в CI.

## Concrete Steps

Работать в выделенном checkout `/Users/gregkisel/.codex/worktrees/coach-runtime-eval/ai_trainer`. Использовать `/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python` с cwd этого checkout. Offline тест:

    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python -m pytest tests/smoke/test_coach_runtime_eval.py -q

CLI принимает `--provider scripted|deepseek`, `--today YYYY-MM-DD`, `--repeats 1|2`, `--output PATH`. Live требует `--live`, явного provider и `--env-file` для загрузки имеющихся ключей. Отчёт записывается только в новый файл, без перезаписи. Временная БД удаляется после trial. CLI печатает только компактную сводку, без prompts, keys и raw provider exceptions.

## Validation and Acceptance

Given синтетический план, when модель выбирает `get_workout_structure`, then отчёт содержит реально исполненный инструмент, ответ и проверки. Given факт с кэшем, when Coach объясняет отрезки, then проверяются фактические числа 128 и 198 Вт, краткость и отсутствие целого отказа. Given активность без кэша, when запрошены отрезки, then Coach явно сообщает нехватку данных без придуманной структуры. Эти проверки ограничены и требуют человеческой оценки смысла.

Given попытка mutation/unknown tool, then callable не вызывается, trial падает и БД сохраняется. Given пустой ответ, provider failure либо исчерпание бюджета, then trial — error/inconclusive; он не исключается из знаменателя и не становится quality pass. Given fixed synthetic bad answer, then property fail не маскируется expected-fail в live отчёте. Given повторный запуск, then trials независимы, output не перезаписывается и каждый связан с registry/version/date/provider/model/base SHA.

## Idempotence and Recovery

Не подключать рабочую DB или chats. Никаких live athlete/service credentials в инструментах; только configured AI provider получает синтетический контекст. Temp DB создаётся внутри TemporaryDirectory. Выходной JSON — единственный новый durable артефакт; удаление этого файла и checkout полностью убирает эксперимент. Ошибки провайдера сохраняются как тип ошибки без сырого сообщения; ключи очищаются из видимых provider outputs перед записью.

## ASR / risk traceability

ASR-SEC-1: ключи не выводятся и не сохраняются; ASR-REL-1/3 и ADR-0010: read-only tool gate и неизменность fixture DB; ASR-PERF-2: измеряется полное время trial, не заявляется SSE first-token latency. API, TypeScript, schema и production prompt не меняются. Эксперимент — локальная CLI-граница, не новый product API.

## Artifacts and Notes

Спецификация и consolidated checker записываются в `docs/issue_528_runtime_experiment_slice_spec.md`. Итоговая очищенная сводка и JSON помещаются в `docs/reports/2026-10-13-coach-runtime-eval/`. Baseline не является CI gate для nondeterministic live provider; offline тесты защищают runner.

## Interfaces and Dependencies

Не добавлять зависимости. Использовать stdlib, существующий provider factory, AITools, runtime, narrative gate и synthetic fixture builder. `run_experiment(provider, *, today, repeats)` возвращает JSON-safe report. Provider decorator сохраняет запросы, видимые ответы, длительность и call count. Read-only decorator фильтрует schemas и проверяет имя инструмента до выполнения.

Revision 2026-10-13: первоначальные конечные границы; spec checker выявил неверную числовую гипотезу (260 Вт), исправлена по существующей BIKE_INTERVALS fixture на 128/198.
