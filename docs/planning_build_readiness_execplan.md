# Planning S3 M1: зафиксировать допуск плана к публикации (#677)

Этот living ExecPlan следует `.agent/PLANS.md`. Scope текущего поручения —
только M1: короткий контракт и проверяемые воспроизведения. Он не разрешает
реализовать M2–M4, менять рабочую БД или слить PR. Baseline main на 2026-10-20:
`5f3b738a8b890d1d69ce7793f684277fb00b40dd`.
[Slice spec](planning_build_readiness_slice_spec.md) содержит будущие AC1–AC7,
точные ошибки/совместимость и deferred coverage.

## Purpose / Big Picture

Спортсмен должен подтверждать проверенные задания, а не только недельные числа.
В M1 мы показываем на вымышленных данных, как текущий API сохраняет неполные
занятия, и определяем проверяемую границу для следующей реализации. Техническая
готовность задания отделена от индивидуальной переносимости и развития формы.

## Progress

- [x] (2026-10-20) Проверены main, #677, отдельный незакрытый docs PR #704; создан изолированный managed worktree, runtime основного checkout не затронут.
- [x] (2026-10-20) Прочитаны ASR catalog, ADD3, ADR-0001, Class A workflow, template и S1/S2 protocol/transaction boundaries.
- [x] (2026-10-20) Synthetic HTTP prepare/confirm/replay публикует 17 fallback и 6 infeasible sessions; pure Base/Recovery контроль исключает гипотезу о нехватке порогов.
- [x] (2026-10-20) Сформулированы AC1–AC7: complete prescriptions, consistent load/time, target semantics, shared guard, old receipt compatibility, scientific boundary.
- [x] (2026-10-20) Четыре acceptance assertion RED и bounded pure probes воспроизведены; existing focused baseline 128 passed, новая реализация не заявлена.
- [ ] Независимый read-only checker завершил один spec round; замечания исправлены или явно triaged.
- [ ] Reviewable checkpoint опубликован и #677 обновлена результатом M1; runtime не объявлен исправленным.

## Surprises & Discoveries

Observed: синтетический публичный build возвращает 200 без build_readiness;
confirm возвращает 200 и сохраняет 17 legacy_role_fallback и 6 infeasible занятий.
Inferred: S1/S2 гарантируют точность/актуальность artifact, но не полноту задания.
Verified by: temporary-SQLite HTTP probe из evidence report, без mock materializer,
с повторным 200 replay. Отдельный all-table snapshot нужен для будущего отказа.

Observed: Base easy bike/run/swim с одинаковыми параметрами создаёт 3/3/4 этапа;
Recovery для тех же входов — ноль. Inferred: phase eligibility отсекает Recovery,
несмотря на preferences. Verified by: pure control и `_ALL_TRAINING_PHASES` /
`_single_candidates`; альтернативная гипотеза «нет FTP/темпа» опровергнута.

Observed: composite длительностью 105 мин может иметь legs 70+30.
Inferred: это не обязательно потеря пяти минут. Verified by: materializer явно
хранит transition_minutes=5; спецификация сохраняет переход, не вводит false bug.

## Decision Log

Decision: техническая ready и training_suitability=not_assessed разделены.
Rationale: корректный файл не доказывает тренировочный эффект; не добавляем
самодельный медицинский/процентный safety score. Date/author: 2026-10-20 / Spec owner.

Decision: blocked prepare получает 422 plan_not_ready и не создаёт usable token.
Rationale: минимальный совместимый error envelope вместо второго publish path;
existing UI показывает safe detail, S4 позже отображает session-level причины.
Старый pending требует нового preview, applied receipt возвращается неизменным.
Date/author: 2026-10-20 / Spec owner.

Decision: строгие AssertionError-only XFAIL обозначают четыре текущих behavioral
RED; --runxfail воспроизводит их, а XPASS заставит снять отметку при реализации.
Rationale: spec checkpoint не ломает обычный contributor contour и не объявляет
отсутствующий runtime GREEN. Date/author: 2026-10-20 / Spec owner.

## Context and Orientation

`api/planning_service.py` захватывает frozen inputs, вычисляет final candidate,
строит PreparedPlanBuild и передаёт его `data/planning_build_preview_store.py`.
Последний хранит pending artifact, при confirm проверяет digest/freshness/CAS и
одной транзакцией публикует checkpoint, selection, settings и receipt. Replay
читает receipt, не пересобирает план. `models/workout_catalog.py` строит singles и
composite legs; failed_bounds и materialization_status — факты, а не UI-решение.
`api/planning_build_contract.py` / `web/lib/types.ts` пока не меняются.

## Plan of Work

M1 записывает slice spec, этот ExecPlan, ASR traceability, исполняемый report probe
и acceptance suite `tests/smoke/test_planning_build_readiness_spec.py`. Тесты
используют только существующие temporary-DB fixtures и публичный HTTP API.
Pure probe сравнивает фазы, спринты, RPE и composite transition. Не открывать
ai_trainer.db, .env, logs, не обращаться к provider и не импортировать app.py.

Независимый checker читает точный diff и запускает разрешённые ниже проверки.
Допускается одна scoped коррекция в пределах review budget; native review
отдельно и только по явному запросу владельца. Завершение M1 — проверяемая
спецификация с честно оставшимися RED, не исправленный генератор.

## Concrete Steps

Из корня этого worktree использовать существующий Python с dev/API dependencies.
В текущем окружении он расположен в исходном checkout; в чистом окружении
установить requirements.txt, requirements-dev.txt и requirements-web.txt.

    PYTHON=/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python
    "$PYTHON" docs/reports/2026-10-20-planning-readiness-m1/probe.py
    "$PYTHON" -m pytest tests/smoke/test_planning_build_readiness_spec.py -q
    "$PYTHON" -m pytest tests/smoke/test_planning_build_readiness_spec.py --runxfail -q
    "$PYTHON" -m pytest tests/smoke/test_planning_build_confirmation.py tests/smoke/test_planning_cycle_build_v2.py tests/smoke/test_workout_catalog.py tests/smoke/test_workout_catalog_v2.py -q
    "$PYTHON" -m ruff check tests/smoke/test_planning_build_readiness_spec.py docs/reports/2026-10-20-planning-readiness-m1/probe.py
    git diff --check

Команда --runxfail обязана дать четыре assertion failures, не collection/setup
errors. Обычный новый suite обязан дать четыре xfailed, не GREEN реализации.
Результаты и полный путь запуска записать в report README; не угадывать число
baseline passes. Web lint/build не нужны: продуктовые web-файлы не меняются.

## Validation and Acceptance

M1 считается завершённым при связанном source/evidence/AC наборе, воспроизведении
четырёх поведенческих RED, зелёной существующей focused baseline, Ruff/diff checks
и независимом spec verdict без неразобранного blocking finding. Все утверждения
готовности runtime остаются NOT YET. Contract extractor не регенерируется:
HTTP/TS contracts в M1 описаны, но не реализованы.

## Idempotence and Recovery

Каждый experiment создаёт собственный TemporaryDirectory/pytest tmp_path; его
SQLite удаляется после запуска. Тестовая смена времени локальна MonkeyPatch.
Новая таблица/миграция/backup рабочих данных не нужны. Удаление M1 docs/tests
полностью отменяет этот срез; рабочий сервер в исходной ветке не перезапускается.

## ASR / risk traceability

ASR-REL-1/2, ASR-MOD-2/3, ASR-PERF-4 и ASR-DEP-2 связаны с AC5/6 и atomic guard.
ADR-0001 переиспользован: policy в Python, UI потребляет контракт. ASR catalog
получает отдельный planned раздел, без изменения статуса доставленных S1/S2.
Риск: один новый запрет без восстановленной генерации сделает обычный цикл
несобираемым; будущий runtime rollout объединяет guard и допустимые prescriptions.

## Interfaces and Dependencies

Предлагается чистый `assess_plan_build_readiness(goal_plan, response, context)`
в `models/planning_build_readiness.py`, результат JSON-safe assessment. Это имя
будущего интерфейса, модуль в M1 не создаётся. Gate вызывается общим Python
prepare/confirm для Planning и Coach build, не дублируется в React. Точная
канонизация/hash и ошибки описаны в slice spec. Отдельный owner данных не вводится.

## Outcomes & Retrospective

M1 in progress. Evidence/independent verdict/publication дополняются перед
закрытием среза. Следующий handoff: Domain/API — M2 материализация и явная RPE
policy, затем M3 effective load + shared guard; Spec — M4 recent-history entry
policy. Эти шаги не выполняются в текущем M1. UI/Design S4 следует за контрактом.

Revision 2026-10-20: initial M1 contract/evidence checkpoint after #677 dogfood;
сохранение исключено из числа доказательств полноты и научной обоснованности.
