# Streamlit EOL (c): извлечение оставшихся агрегатов в shared-слой (issue #349)

Живой документ по `.agent/PLANS.md`. Самодостаточен для нового исполнителя.

## Purpose / Big Picture

Критерий (c) ADR-0001 требует, чтобы в Streamlit-коде не осталось бизнес-логики
вне shared-слоя. Статус-логика дашборда уже вынесена в `services`
(`calculate_current_status`), но в `ui/pages/` остаются встроенные display-
агрегаты. После этого слайса все они живут в новом
`services/athlete_aggregates.py` с контрактными тестами, а Streamlit-страницы
только потребляют их — без дублирования и без изменения формул.

## Progress

- [x] (2026-08-03) Аудит: статус дашборда уже в shared (`services.calculate_current_status`);
      inline остались только display-агрегаты в dashboard/hrv/activities/sleep.
- [ ] RED: `tests/smoke/test_athlete_aggregates.py` — контракты на фиксированных
      DataFrame + source-гейты «страницы импортируют shared-хелперы».
- [ ] Реализация `services/athlete_aggregates.py` и замена вызовов в 4 страницах.
- [ ] Проверки: focused, smoke, ruff/diff-check; PR; закрытие #349.

## Surprises & Discoveries

- Observation: `ui/pages/dashboard.py:_calculate_current_status` — только
  обёртка над shared `services.calculate_current_status`; основной расчёт уже
  вне Streamlit. Реальный остаток — суммы/средние/groupby в аналитике.
  Evidence: `ui/pages/dashboard.py:18` импортирует headless builder.

## Decision Log

- Decision: новые хелперы — в одном модуле `services/athlete_aggregates.py`
  (чистые pandas-функции без Streamlit-импортов).
  Rationale: агрегаты узкие и display-ориентированные; один модуль проще
  ревьюить и тестировать, чем размазывать по доменным модулям.
  Date/Author: 2026-08-03 / Codex.
- Decision: формулы НЕ меняются — извлечение с эквивалентным поведением;
  эквивалентность доказывается контрактными тестами на фиксированных данных.
  Rationale: issue #349 явно запрещает изменение расчётов.
  Date/Author: 2026-08-03 / Codex.

## Outcomes & Retrospective

Не завершено (в процессе).

## Context and Orientation

`services/data_cache.py` отдаёт DataFrame активностей/HRV/сна в Streamlit.
Извлекаемые куски: totals активностей (count/distance/duration/avg TSS),
ежедневные суммы по дням, baseline/avg RMSSD, корреляции HRV×TSS (same-day,
lag-1, 3-day cumulative), средние по сну. `ui/pages/{dashboard,hrv,activities,sleep}.py`
заменяют inline-выражения вызовами хелперов.

## Plan of Work

1. `services/athlete_aggregates.py`:
   - `activity_totals(df)` → `{count, distance_km, duration_hours, avg_tss}`;
   - `daily_activity_totals(df, columns=...)` → date → sums;
   - `sport_distribution(df)` → `value_counts` как dict;
   - `hrv_baseline_rmssd(df)` → mean;
   - `hrv_training_correlations(combined_df)` → same-day/lag1/3-day;
   - `sleep_averages(df)` → score/hours/efficiency/awakenings.
2. `ui/pages/dashboard.py`: `_render_compact_analytics` использует
   `activity_totals`/`daily_activity_totals`/`sport_distribution`.
3. `ui/pages/hrv.py`: baseline/avg через `hrv_baseline_rmssd`; корреляции —
   через `hrv_training_correlations`.
4. `ui/pages/activities.py`: totals и дневной график через хелперы.
5. `ui/pages/sleep.py`: средние через `sleep_averages`.
6. `tests/smoke/test_athlete_aggregates.py`: эквивалентность на фиксированных
   данных + source-гейты импорта в страницах.

## Concrete Steps

    source ai_trainer_env/bin/activate
    python -m pytest tests/smoke/test_athlete_aggregates.py -q
    python -m pytest tests/smoke -q
    ruff check services/athlete_aggregates.py ui/pages tests/smoke/test_athlete_aggregates.py
    git diff --check

## Validation and Acceptance

Контрактные тесты доказывают, что хелперы возвращают те же значения, что и
прежние inline-выражения, на одинаковых DataFrame; source-гейты подтверждают,
что страницы импортируют shared-хелперы (inline-выражений больше нет). Полный
smoke зелёный; CI ready-to-merge; после мержа #349 закрывается, критерий (c)
аудита EOL становится ближе к выполнению.

## Idempotence and Recovery

Чистое извлечение без изменения БД/схемы. Откат = вернуть inline-выражения;
shared-модуль аддитивен.

## Interfaces and Dependencies

Новый модуль зависит только от `pandas`. Streamlit-страницы импортируют его
локально (как уже делают с `utils.modern_ui`), без новых зависимостей.
