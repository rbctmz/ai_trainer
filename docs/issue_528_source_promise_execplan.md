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
- [x] (2026-10-15) M2: один frozen live run,4trials/12calls из16,0errors; same-input/read-only/message exposure4/4.
- [x] (2026-10-15) Source-ab runner/CLI готов:112focused passed,2957smoke passed/35skipped, lint/diff passed; independent implementation checker32passed, блокеров нет. Last2boundarytests добавлены после broad collection и проверены targeted/checker.
- [x] (2026-10-15) Immutable trace и отдельная семантическая оценка всех4answers двумя агентами, итоговое ограниченное решение и локальный checkpoint. Человеческая оценка Greg остаётся pending; не заявляется выполненной.
- [x] (2026-10-15) По «Закрепляй условия» открыт новый M3 scope, [slice spec](issue_528_cache_conditions_slice_spec.md) проверен независимым checker без блокеров; handoff Spec Owner → Domain Implementer.
- [x] (2026-10-15) M3: shared prompt condition добавлено после RED5failed;117focused passed, lint/diff passed. Paid calls0.
- [x] (2026-10-15) M3:2964smoke passed/35skipped/1existing warning на отдельной DB/chats,208s; independent checker59passed, блокеров нет; local verified checkpoint, zero paid calls.
- [x] (2026-10-15) Владелец «Отлично! Делай» авторизовал M4: final4trials/max16calls по трём состояниям кэша; [slice spec](issue_528_final_validation_slice_spec.md) и [frozen rubric](reports/2026-10-15-coach-final-validation/README.md) записаны до реализации/запуска.
- [x] (2026-10-15) M4: registry/fixture/runner/CLI, RED missing interface→124focused passed;2971smoke passed/35skipped, lint/diff green; independent spec/delta без блокеров, checker39passed; pre-run checkpoint.
- [x] (2026-10-15) M4: один finite live run,4trials/12of16calls,0errors; immutable trace, семантическая оценка всех4answers двумя агентами. Целевые state criteria выполнены, но empty ответ содержит другое неподтверждённое обещание; clean final acceptance не заявлено. Partial result сохранён, отдельный verification design подготовлен.
- [x] (2026-10-15) M5 отдельно авторизован «Реализуй план»: [slice spec](issue_528_answer_verification_slice_spec.md), independent spec check без блокеров, handoff Spec Owner → Domain Implementer. RED16failed/9passed до реализации.
- [x] (2026-10-15) M5: allowlisted activity evidence + bounded hard gate + factual fallback в shared Python; correction budget прежний.286focused passed, API SSE/persistence и legacy path проверены офлайн. Три reviewer P2 и одна repair-регрессия исправлены с точными RED/GREEN; scoped checker7passed, блокеров нет.
- [x] (2026-10-15) M5: offline replay30saved outputs,12activity rejections; все4исходных контрпримера остановлены,3supported M4answers unchanged. Все4historical JSON byte-identical; новых model calls0.
- [x] (2026-10-15) M5: итоговый isolated smoke3012passed/35skipped/1existing warning,183.36s; whole-tree ruff/diff green. Replay повторён в новый temp file, bytes identical.
- [ ] M5: локальный commit после проверок.

## Surprises & Discoveries

**Observed:** `_ACTIVITY_STRUCTURE_MESSAGES['not_fetched']` в models/ai_tools.py:117–119 содержит «Они появятся после синхронизации ... или после открытия карточки». Та же строка присутствует в raw_result.message и formatted_result сохранённого A/B JSON. **Inferred:** часть обещаний модели может быть повторением ошибочного исходного сообщения, поэтому приоритет исправления начинается до synthesis. Самый дешёвый falsifier — проверить реальный tool/presenter на missing-cache fixture и попытку fetch с недоступным provider. **Verified by:** офлайн synthetic DB + AITools.get_activity_structure + format_tool_result подтвердили доставку строки; fetch_activity_intervals с пустым cache и is_configured=False вернулNone. Это доказывает неверную безусловную гарантию в источнике, но не объясняет всё поведение модели.

## Decision Log

Decision: менять только not_fetched сообщение, сохраняя статус unavailable, reason not_fetched и structured/empty/no_provider_link/corrupt_cache значения. Rationale: исправляется факт в исходном контексте, не формулы, загрузка или форма API. Date:2026-10-14.

Decision: существующие prompts, compact candidate и модель оставить одинаковыми в source A/B. Единственное отличие — исходная/исправленная message строка. Rationale: предыдущий compact A/B не исправил guarantees; новое сравнение должно проверять другой конкретный механизм. Date:2026-10-14.

Decision: live4attempts = одна missing-cache задача × два message variants × два повтора; максимум16provider calls,4/trial,12tools/trial,1800outputtokens/call,45sSDKtimeout,zero retries. Rationale: достаточный ограниченный повтор для первичной проверки источника, без нового большого eval круга. Это планируемый бюджет, здесь вызовов нет. Date:2026-10-14.

Decision: основная приёмка этого этапа — правдивость сообщения и отсутствие гарантии в model answer. Краткость измерять отдельно; превышение80слов не подменяет truthfulness verdict. Старые baseline/A/B scores не пересчитывать. Date:2026-10-14.

Decision: M2 использует одинаковый compact_answer_v1 response contract в обоих source variants и отдельный source-ab CLI/report. Rationale: повторить проблемный missing-cache контекст compact A/B, сохранив единственное изменяемое поле message. Immutable JSON не объявляет semantic pass, отдельная оценка всех4answers атрибутируется агенту; review Greg не заявляется. Date:2026-10-14.

Decision: до первого платного вызова наступил2026-10-15; дата fixture/вопроса и live --today сдвинуты вместе на15октября/14октября факта. Rationale: native calendar соответствует дате исполнения; ни одной платной попытки до смены дня не было. Gate, registry, budget и messages не изменены. Date:2026-10-15.

Decision: M3 меняет одну общую cognitive instruction в существующем runtime, без нового deterministic validator и paid run. Rationale: явное успешное получение в кэш уже есть в tool result, но при synthesis теряется; правило должно поступать на все prompt paths и correction. Offline tests доказывают доставку, не поведение живой модели. Frozen M2 остаётся результатом05c932b, новые prompts не приписываются тому запуску. Date:2026-10-15.

Decision: M4 завершает поведенческую проверку M3 четырьмя текущими turns:missing twice,cached once,analyzed-empty once; one global16call cap. Rationale: проверить устранение найденных формулировок и сохранение двух легитимных состояний, без нового paired A/B или общей оценки Coach. Все4clones одной новой canonical fixture содержат все3states; контрольные state/date различия явно заданы в расписании. Date:2026-10-15.

Decision: M5 добавляет один ограниченный activity claim domain в существующую narrative boundary, без общего фактчекера и новых вызовов модели. Rationale: M4 сохранил конкретный контрпример; одних инструкций недостаточно для этой наблюдаемой формы. Public metadata shape открыт и совместим, internal evidence/rules становятся v3. Исправить только misleading empty source observation и general hypothesis wording; не менять исторические traces/predicates. Date:2026-10-15.

## Outcomes & Retrospective

M1 исправляет исходную гарантию и подтверждает доставку ограничения в оба контекста модели офлайн. M2 выполнен на05c932b:4trials,12/16calls,0errors; явная гарантия sync/card исчезла2/2after против2/2before с гарантией. Narrow gate before0/2→after2/2, но after1 обещает успешный повторный запрос без подтверждённого получения в кэш, after2 содержит неоднозначное начало. Поэтому2/2fully truthful не заявлено; source fix сохранить, остаток выделить в следующий bounded slice. [Trace/report](reports/2026-10-15-coach-source-ab/README.md) и [семантическая оценка](reports/2026-10-15-coach-source-ab/assessment.md) атрибутированы агентам; Greg human review pending. Initial requests одинаковы4/4; tool/synthesis input отличаются только message; DB unchanged4/4. Это ограниченное наблюдение, не статистическая значимость или общее доказательство причинности.

M3 закрепил оба условия в общей инструкции: неизвестная структура не становится отсутствующими отрезками, а повторный запрос/provider availability не становится подтверждённым кэшем. Доставка в marker/native/synthesis/correction проверена real-tool synthetic turns;117focused и2964smoke passed, independent checker без блокеров. Это instruction contract, не новый output blocker; на checkpoint M3 поведение не измерялось, последующее ограниченное наблюдение M4 записано ниже. Все3historical live JSON побайтово совпадают с9e4d717. Никаких paid calls/push/merge для M3.

M4 на02687ef:4trials/12calls из16,0errors; missing2/2 без прежних гарантий/ложного отсутствия, cached1/1 сохраняет фактические числа, empty1/1 распознан. Однако empty говорит «это подтвердит проверка карточки» для гипотезы; оба агента не принимают вывод о4fully supported answers. [Финальный отчёт](reports/2026-10-15-coach-final-validation/README.md) сохраняет partial outcome и JSONpending_manual. [Отдельный verification design](issue_528_answer_verification_followup.md) подготовлен вместо нового prompt tuning/live retry; реализация не начата. M4 execution/evidence complete, broader truthfulness/human approval/merge не заявлены.

M5: новая защита блокирует четыре исходных unsupported assurances в сохранённых ответах и сохраняет три supported M4 answers. [Офлайн-отчёт](reports/2026-10-15-coach-answer-verification/README.md) содержит все30outputs и границы выводов. Нельзя приписывать replay улучшение живой модели: новых model calls0, correction проверен fake providers. Safe fallback сохраняет source aggregates/interval values, недостоверная raw фраза не выдаётся API и не сохраняется как ответ. Возможные формулировки вне bounded rule остаются вне доказанного результата.

## Context and Orientation

`models/ai_tools.py::_ACTIVITY_STRUCTURE_MESSAGES` задаёт message для cached-only get_activity_structure. `resolve_cached_activity_structure` различает реальные отрезки, проанализированную пустую структуру и неизвестную структуру. `models/coach_tool_presenter.py::_activity_structure_block` без изменений помещает message в formatted_result, который shared runtime передаёт модели.

`services/activity_intervals.py::fetch_activity_intervals` — отдельный загрузчик для карточки. Он может вернуть None/старый cache при отсутствующей конфигурации, provider error или malformed payload. Сам Coach tool за сетью не ходит. «Данные не загружены» нельзя превращать ни в «отрезков не было», ни в «следующая синхронизация точно их даст».

Существующие тесты: `tests/smoke/test_coach_activity_structure_tool.py`, `tests/smoke/test_activity_intervals.py`, `tests/smoke/test_coach_runtime_eval.py`, `tests/smoke/test_coach_compact_ab.py`. Экспериментальный runner — `services/coach_runtime_eval.py`, CLI — `scripts/run_coach_runtime_eval.py`, реестр — `tests/evals/coach/runtime_registry.py`.

## Scope and Role Handoff

Spec Owner фиксирует bounded intent. Для M1 после spec check Domain Implementer правит только message и contract-backed tests; M2 fixture/runner/CLI допускаются только для source A/B с одним изменяемым полем. M3 отдельно авторизован владельцем: shared runtime prompt instruction и regressions, без изменения source/gate/scorer/history. Independent Reviewer проверяет read-only delta и разрешённые offline tests. Greg — владелец следующего исполнения/merge. UI/CSS, API schemas, readiness/TSS/planner, data persistence, sync behavior и provider settings вне всех трёх срезов; prompts были frozen в M1/M2 и намеренно меняются только в M3.

## Milestones / Plan of Work

### M1 — достоверный вход модели

Сначала добавить regression в tests/smoke/test_coach_activity_structure_tool.py: реальный cached-only инструмент на linked activity без cache возвращает unavailable/not_fetched и сообщает отсутствие данных, но не безусловный успех будущей операции. Тот же message должен дойти через реальный presenter в native tool message и synthesis prompt. До исправления тест воспроизводит неправильную гарантию.

Затем заменить только not_fetched текст. Рабочий вариант: «Структура недоступна: интервалы этой активности ещё не выгружены в кэш. Проверьте, доступны ли отрезки в Intervals.icu. После успешного получения этих данных повторите запрос; сейчас инструмент читает только сохранённые данные». Условие успешного получения не является гарантией его наступления.

Проверить существующие success/empty/no-link/corrupt-cache cases и offline fetch failures. Не добавлять сетевую загрузку в Coach tool. Доказать неизменность synthetic DB на turn и прежнюю форму результата. Завершить M1 независимой проверкой source/message boundary; это проверяемый результат без model calls.

### M2 — проверка поведения настоящего Coach

Зафиксировать одну согласованную canonical synthetic DB и одну missing-cache задачу. Два варианта tool message — исходный, сохранённый в старой trace, и исправленный. В экспериментальной read-only обвязке подменяется только message при его формировании; настоящий tool, formatter и shared runtime работают как раньше. Product default остаётся исправленным, экспериментальная подстановка исходного message не становится production mode.

Для каждого из двух повторов чередовать before/after порядок, клонировать одинаковую DB через SQLite backup. Model, settings, prompts, response contract, data/date одинаковы. Перед live freeze criteria, независимый checker, explicit finite run setup. Выполнить только4trials с одним global cap16; если среда/календарь/провайдер не позволяют сравнение, сохранить INCONCLUSIVE без бесконечного retry.

### M3 — явные условия получения фактических отрезков

По отдельному запросу «Закрепляй условия» добавить правило в существующий `_COGNITIVE_GUARDRAILS` в models/ai_coach_runtime.py. При unavailable объяснение начинается со «Структура недоступна», а не утверждения отсутствия отрезков. Наличие у provider/синхронизация/карточка/повтор запроса не подтверждают получение в кэш; фактические отрезки называть по подтверждающему результату инструмента после получения данных. Structured уже полученные данные остаются доступными, analyzed-empty допускает «анализ не нашёл отрезков».

RED tests в tests/smoke/test_ai_coach_runtime.py проверяют общие model-facing условия в marker/native/synthesis. Offline real-tool turns на synthetic SQLite и существующая calendar correction подтверждают доставку этих условий также в corrective synthesis при compact contract; fixture unchanged. Запустить focused suites, whole-tree lint, isolated smoke, independent checker; сохранить локальный checkpoint. Никаких paid model calls, новых classifiers или изменения frozen M2 reports. Это instruction contract, не детерминированная гарантия соблюдения моделью.

### M4 — конечная поведенческая приёмка трёх состояний

Проверить новые инструкции на живом Coach:missing1,cached1,empty1,missing2, максимум16calls. Новый `cache-validation` CLI mode и собственная registry/fixture/report provenance используют существующий run_trial/shared runtime без изменения production. Одна canonical synthetic DB добавляет analyzed-empty активность с явным analyzed timestamp, normalized перед SQLite backup clones. Missing/cached вопросы переиспользуют существующие scenarios; empty вопрос не подсказывает состояние ответа.

Зафиксировать spec и rubric, провести независимый spec check; добавить failing runner/CLI boundary tests, реализовать только experimental schedule/exposure checks. Focused/isolated broad tests, lint/diff и independent delta check обязательны до pre-run commit. Затем один явно авторизованный finite run DeepSeek/deepseek-flash, immutable trace и отдельная семантическая оценка всех4outputs двумя агентами. Unknown≠empty; cached цифры из source; no sync/card/requery guarantees. Краткость diagnostic. All4semantic passes дают локальный review brief/career case; negative/inconclusive сохраняется без prompt tuning, следующая проверка ответа — отдельный scope. Push/PR/merge/закрытие всего#528 не заявлять.

### M5 — проверка ответа по фактам активности

По отдельно принятому verification design добавить bounded helper models/coach_activity_structure_evidence.py и подключить его к существующему models/coach_narrative_evidence.py. Allowlist identity/date/status/provenance/numeric source facts; malformed/failed/conflicting evidence не даёт structured/empty proof. Проверять известные assurances, unknown≠empty и unsupported circumstances; scope по activity/date не должен заимствовать proof у другой активности. Conditional checks и реальные structured facts сохранять. Новый hard reason не является soft data gap.

Переиспользовать существующую one-shot correction, при любой неудаче выдавать factual fallback без нового retry. Исходное empty message описывает анализ сохранённых данных; general hypothesis instruction допускает подтверждение или опровержение. API/legacy потребляют shared policy; UI/API schemas/persistence shapes не меняются. RED saved cases + positive/mixed/malformed/metadata/delivery tests → focused/broad/lint → independent bounded review → scoped repairs. Offline replay всех30saved outputs с source/implementation hashes, без модели, старые live JSON неизменны. Локальный checkpoint и честный career evidence update; не заявлять fresh live acceptance.

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

Revision2026-10-15: по явному «Делай» выполнен конечный M2, сохранены trace и отдельно семантическая оценка всех4answers; исходная гарантия ушла, другое обещание осталось. Никакой подстройки/повторного paid run или merge; дальнейшая корректировка — отдельный scope.

Revision2026-10-15 M3: владелец отдельно авторизовал закрепление условий. Новое правило инструкции относится к следующей версии runtime; source A/B artifacts и результаты05c932b остаются неизменными. На этом checkpoint behavioral effect не измерялся; дальнейший M4 записан отдельно.

Revision2026-10-15 M4: финальный finite run завершён, partial result/immutable trace/две семантические оценки/verification draft/local review brief сохранены. Отрицательная часть не скрыта за автоматическим4/4. Чистая итоговая приёмка и merge не заявлены; никаких новых платных попыток или реализации следующего validator.
