# #528: парное сравнение краткого ответа

Живой ExecPlan по `.agent/PLANS.md`; следующий ограниченный milestone после baseline на 5674fd5. Class A: согласованный платный эксперимент, максимум 64 вызова. Спецификация: `docs/issue_528_compact_ab_slice_spec.md`.

## Purpose / Big Picture

Проверить одну гипотезу: явный краткий response contract помогает Coach отвечать на узкий вопрос до 80 слов, сохраняя факты и ограничения. Пользователь сможет увидеть парные ответы A/B, трассы и решение о дальнейшей продуктовой работе. Старый baseline остаётся неизменным, production prompt и API не меняются.

## Progress

- [x] (2026-10-13) Владелец принял представленный A/B план: четыре сценария × два варианта × два повтора, максимум 64 вызова.
- [x] (2026-10-13) Прочитаны existing runner, contract suffix и фикстуры; scope и заранее заданные критерии записаны.
- [x] (2026-10-13) Независимая spec проверка без blockers; отдельно отражаем candidate gate и observed improvement над A.
- [x] (2026-10-13) RED/GREEN: новый runner отсутствовал; 72 focused tests passed, whole-tree ruff green. Contract propagation, одинаковые snapshots, scoring, preflight16 и budget покрыты.
- [ ] Checker реализации, focused/broad проверки.
- [ ] Один live A/B прогон; неизменённый JSON, ручная оценка и решение.

## Surprises & Discoveries

Observed: v1 имеет случайные несогласованности (13 минут cached intervals против 62 минут summary; бег 32.5 км за 62 мин), а production runtime уже принимает `response_contract.prompt_suffix`. Inferred: новый механизм не нужен; фикстуры надо согласовать до парного сравнения. Verified by: чтение `apply_response_contract_to_user_input`, нормализатора и v1 JSON; numeric falsifiers записаны в первом отчёте.

Observed: первое сравнение snapshot hash canonical/clone не совпало, хотя все clone hashes совпали между собой. Inferred: Database startup дополняет missing TSS provenance. Verified by: logical dump diff до/после второго Database(path) показал добавленные tss_type/tss_ftp и пересчёт TSS. Завершаем этот штатный bootstrap до canonical snapshot; одинаковые 16 input hashes подтверждены offline тестом. Рабочая БД и production migration не менялись.

Observed: начальный native system prompt использует реальный athlete calendar. Inferred: переход даты посреди прогона нарушил бы сравнимость. Verified by: тест смены calendar helper после первого trial прекращает дальнейшие model calls с CalendarChangedError; 16 planned trials сохраняются, сравнение INCONCLUSIVE. Calendar guard наблюдает один shared calendar, не подменяет production clock.

## Decision Log

Decision: фиксировать candidate `compact_answer_v1` до model calls, текст «До 80 слов; ответь только на заданный вопрос; сохрани существенные факты и ограничения данных». Использовать существующий suffix в выборе инструментов, synthesis и corrective retry. Ни один ответ не обрезается программно. Date: 2026-10-13.

Decision: четыре v2 сценария: три известных как regression и новый день отдыха как контрольный, без tuning на live ответах. A и B исполняются на клонах одной временной БД, с одинаковым snapshot hash. Для каждого scenario/repeat чередовать AB/BA порядок. Model/settings/date одинаковы в одном запуске. Старое 2/6 не используется как контрольная группа нового датасета. Date: 2026-10-13.

Decision: budget 64 total, 4 provider calls/trial, 12 tool executions/trial, 1800 output tokens/call, 45s SDK timeout, zero SDK retries. Ошибка провайдера сохраняется в denominator, output создаётся эксклюзивно. User accepted presented bounded plan. Date: 2026-10-13.

## Outcomes & Retrospective

Пока результата нет. Автоматический score и смысловая оценка отдельны. Маленькая выборка позволяет выбрать следующий шаг, а не объявить доказанное качество или причинность. Production rollout в этот milestone не входит.

## Context and Orientation

`services/coach_runtime_eval.py` уже оборачивает shared runtime и создаёт временную БД per trial. `tests/evals/coach/runtime_registry.py` — lightweight registry, безопасный для preflight без imports Settings. `scripts/run_coach_runtime_eval.py` делает explicit live opt-in, zero retries и сохраняет JSON. Сравнение добавляет `--experiment compact-ab`; `baseline` остаётся default. A — текущий формат, B — тот же runtime с одним response contract. Fixture — искусственные данные; snapshot hash — hash полного logical SQLite dump. Callback создания БД даёт run_trial копию одной canonical fixture через SQLite backup, а не копирование live/WAL файлов.

## Plan of Work

Расширить trial optional response_contract и fixture factory без изменения baseline defaults. Добавить frozen v2 registry, согласованный fixture builder и парный runner с одним global budget. Grade v2 сохраняет existing правила, отдельно проверяет day-off, ключевые шаги плана и небезусловную трактовку future fetch; эти предикаты — оценка, не production blocker. CLI сохраняет полный preflight report для 16 trials и metadata candidate/fixture/order. Новый тестовый модуль проверяет intentional behaviors сначала RED, потом GREEN. Не менять модели, UI, schema или live activity services.

## Concrete Steps

Checkout `/Users/gregkisel/.codex/worktrees/coach-runtime-eval/ai_trainer`, interpreter `/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python`.

    python -m pytest tests/smoke/test_coach_compact_ab.py tests/smoke/test_coach_runtime_eval.py -q
    python scripts/run_coach_runtime_eval.py --experiment compact-ab --provider scripted --today 2026-10-13 --repeats 2 --output /tmp/compact-scripted-new.json
    python scripts/run_coach_runtime_eval.py --experiment compact-ab --provider deepseek --live --env-file /path/to/private/.env --today YYYY-MM-DD --repeats 2 --output /tmp/compact-live-new.json

Live date должна совпадать с текущим production calendar; начальный native system prompt использует реальные часы. API/SSE orchestration в эксперимент не входит. Каждая trial имеет variant, scenario_id, repeat и одинаковый input snapshot; system prompt и tools остаются production, suffix записан в trace.

## Validation and Acceptance

Given suffix B, when native selection, synthesis и correction вызываются, then suffix реально присутствует в запросах; A его не получает. Given same canonical fixture, when оба варианта проходят turn, then input hashes одинаковы и после tools БД неизменна. Given ответ с правильными numbers плюс unsupported facts/guarantee, then узкий numeric pass не объявляется общей корректностью; ручная оценка обязательна.

Кандидат успешен только при 8/8 ответов до 80 слов, нужных инструментах и сохранённых существенных фактах; обе missing-cache попытки честно обозначают data gap без выдуманных отрезков/гарантии будущей синхронизации, обе control-rest попытки корректны; forbidden tools/writes отсутствуют. Ошибки выполнения — INCONCLUSIVE, не качество. Проигрыш B фиксируется без tuning/retry до зелёного.

## Idempotence and Recovery

Только synthetic temp DB. Canonical DB создаётся один раз и все clones берутся через SQLite backup; cleanup TemporaryDirectory. Credential redaction и exclusive JSON прежние. Старые traces immutable. Один final live запуск с пределом 64; новый budget не применяется к default baseline (24). Production rollout, push/merge и внешние записи исключены из согласованного эксперимента.

## ASR / risk traceability

ASR-SEC-1 trace redaction; ASR-REL-1/3 snapshot isolation; ASR-PERF-2 duration only. ADR-0001 shared Python; ADR-0010 A0-only tools. Тот же локальный экспериментальный CLI, не новая product architecture. Разница A/B ограничена suffix; fixture version одна для обоих. Initial system clock и sampling недетерминированы, результаты интерпретируются осторожно.

## Artifacts and Interfaces

`run_trial` получает optional contract и fixture factory. `run_comparison` возвращает JSON-safe report с общим denominator 16 и отдельной сводкой A/B. Fixture/registry/report/candidate версии pin; model/date/cap/base SHA сохранены. Отчёт `docs/reports/2026-10-13-coach-compact-ab/README.md` и immutable JSON; история baseline untouched. Зависимости новые не нужны.

Revision 2026-10-13: первоначальные границы принятого A/B плана, без изменения критериев после просмотра результатов.
