# Readiness-скор: закрепить, что число зависит только от тела и завершённых активностей, а не от плана

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md` at the repository root.

## Purpose / Big Picture

Пользователь видит на дашборде число «Готовность 78/100». Смысл этого числа — «насколько восстановлено тело сегодня»: сон, пульс, HRV и то, что уже сделано. Число не должно меняться от того, что пользователь перенёс или удалил будущую тренировку в календаре: это разные вещи — «как я себя чувствую» и «что мне делать по плану». IntervalCoach в чейнджлоге от 4 июля 2026 (Readiness Score 2.0) сделал это явным правилом: «training plan no longer touches the number», а 22 июня чинил ошибку, когда отсутствие запланированной сессии занижало число восстановления.

Сейчас математика в `models/readiness.py::_tsb_metrics` уже берёт TSS только из завершённых активностей (фильтр по дате «не позже сегодня»), и все потребители кормят её данными из таблицы активностей, а не из плана. То есть поведение уже правильное, но ничем не закреплено: неаккуратный будущий потребитель может скормить плановые строки, и никто не заметит. Цель — аудит всех точек, где считается готовность, и контрактные тесты, которые навсегда запрещают плану влиять на скор.

Проверить работу можно так: `python -m pytest tests/smoke/test_readiness_model.py tests/smoke/test_readiness_snapshot_contract.py -q` зелёные, включая новые тесты «будущая плановая сессия не меняет скор».

## Progress

- [x] (2026-08-06) Создан ExecPlan; найдены потребители `compute_readiness_today`: `services/readiness_snapshot.py`, `api/readiness_conflicts.py`, `models/readiness_conflicts.py`, `models/signals_engine.py`, `models/ai_tools.py`.
- [ ] Milestone 1: аудит потребителей — откуда каждая точка берёт `activities_df`; запись находок.
- [ ] Milestone 2: контрактные тесты «план не влияет на скор».
- [ ] Milestone 3: фикс, если аудит найдёт путь плана в готовность; проверка разделения «готовность» и «рекомендация» в today-snapshot.

## Surprises & Discoveries

- Observation: все известные потребители берут `activities_df` из БД-таблицы завершённых активностей (`Database.get_activities_between` / `get_activities`), а не из plan-строк.
  Evidence: `services/readiness_snapshot.py` (`db.get_activities_between`), `api/readiness_conflicts.py` (`db.get_activities(LOAD_METRICS_WINDOW_DAYS)`), `models/signals_engine.py` (принимает `activities_df` на вход).
- Observation: `_tsb_metrics` дополнительно отсекает всё, что позже сегодняшней даты (`df["date"] <= anchor_ts`), так что даже случайно переданная будущая активность не попадёт в TSB.
  Evidence: `models/readiness.py::_tsb_metrics` (фильтр `df[df["date"] <= anchor_ts]`).

## Decision Log

- Decision: готовность считаем «чистой» мерой восстановления; рекомендация «что делать сегодня» живёт отдельно (today-snapshot/outlook).
  Rationale: повторяем дизайн-решение IntervalCoach (Readiness Score 2.0); смешение «как восстановлен» и «что делать» уже порождало у них класс багов.
  Date/Author: 2026-08-06 / Codex.
- Decision: TSB-фактор остаётся в скоре, но только по завершённым активностям.
  Rationale: накопленная усталость от реально сделанного — легитимный вход «восстановленности»; запрещён только план (будущее), а не прошлое.
  Date/Author: 2026-08-06 / Codex.

## Outcomes & Retrospective

Заполняется по завершении плана.

## Context and Orientation

Готовность (readiness) — число 0–100, которое показывает, насколько тело восстановлено. Оно считается функцией `models/readiness.py::compute_readiness_today`, которая принимает пять таблиц-фреймов: сон, HRV, здоровье (пульс покоя), Garmin readiness и активности. TSB (баланс нагрузки) — разница между долгосрочной и краткосрочной нагрузкой; он входит в скор весом 0.15 и обязан считаться только по завершённым активностям (`date <= сегодня`), никогда по плановым сессиям.

Потребители — места, которые вызывают `compute_readiness_today`:

- `services/readiness_snapshot.py` — строит снапшот для SSE-меты коуча и API (через `api/readiness_snapshot.py`).
- `api/readiness_conflicts.py` и `models/readiness_conflicts.py` — salience-gate: детектор конфликта «готовность × плановая сессия».
- `models/signals_engine.py` — единый набор сигналов для дашборда.
- `models/ai_tools.py` — контекст для AI-коуча.

Таблица завершённых активностей в БД: `Database.get_activities_between(start, end)` (см. `data/database.py`). Плановые сессии живут в другом месте (checkpoints плана, `models/planning_checkpoints.py`) и в готовность попадать не должны. Тесты: `tests/smoke/test_readiness_model.py` (математика модели), `tests/smoke/test_readiness_snapshot_contract.py` (контракт снапшота).

## Plan of Work

### Milestone 1: аудит потребителей

Для каждого потребителя (`services/readiness_snapshot.py`, `api/readiness_conflicts.py`, `models/signals_engine.py`, `models/ai_tools.py`) найдите, откуда строится `activities_df`, и запишите в `Surprises & Discoveries`: таблица БД и функция, которой она читается. Убедитесь, что ни один потребитель не подмешивает plan-строки (например, TSS из `plan_rows` или из checkpoint). Если найдёте такой путь — это находка для Milestone 3.

### Milestone 2: контрактные тесты

В `tests/smoke/test_readiness_model.py` (или новом файле `tests/smoke/test_readiness_plan_purity.py`) добавьте:

- тест: в `activities_df` добавляется строка с будущей датой (`date > anchor`) и большим TSS — score и все факторы не меняются;
- тест: активность вчера/сегодня меняет TSB-фактор и score (убедиться, что TSB вообще участвует);
- тест на уровне снапшота: `services/readiness_snapshot.py::build_readiness_snapshot` возвращает одинаковый `score` до и после добавления будущей плановой сессии в БД (seed: план на завтра с quality-сессией; проверить, что снапшот не изменился).

### Milestone 3: фикс и разделение поверхностей

Если аудит нашёл путь, где план влияет на скор, — отрежьте его (например, фильтром по дате или явным исключением plan-источников) и добавьте регрессионный тест. Дополнительно проверьте `api/today_snapshot.py`: поле готовности в today-снапшоте должно быть тем же числом, что и readiness, а рекомендация («что делать сегодня») — отдельным полем; если рекомендация перезаписывает число готовности — разделите их и зафиксируйте тестом.

## Validation

Команды, которые должны быть зелёными:

    python -m pytest tests/smoke/test_readiness_model.py tests/smoke/test_readiness_snapshot_contract.py tests/smoke/test_readiness_plan_purity.py -q
    python -m pytest tests/smoke -q
    python -m ruff check models/readiness.py services/readiness_snapshot.py api/today_snapshot.py tests/smoke/test_readiness_plan_purity.py

Опциональный живой прогон: на реальной БД с активным планом вызвать readiness-снапшот, затем изменить будущую неделю плана и вызвать снова — score должен остаться тем же.
