# Единый сигнал «готовность на сегодня»: models/readiness.py с личными базлайнами и TSB

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md` at the repository root.

## Purpose / Big Picture

AI Trainer — тренировочный кокпит на данных Garmin (SQLite, FastAPI, Next.js, легаси Streamlit) с AI-коучем. Продуктовая цель ветки — агентный контур: система сама замечает расхождение состояния спортсмена и плана и предлагает безопасное перепланирование. Первый слой этого контура — один доверяемый, детерминированный, объяснимый сигнал «насколько спортсмен готов сегодня».

Сейчас «готовность» считается в двух местах с противоречащей семантикой. `data/data_processor_phase1.py::calculate_comprehensive_readiness` складывает абсолютные шкалы (HRV по формуле `(rmssd-20)/60`, пульс покоя по шкале от 40 уд/мин) без нагрузочного контекста. `models/signals_engine.py::_readiness_signal` при наличии оценки готовности от Garmin (`training_readiness`) просто возвращает её, игнорируя остальные сигналы. Ни один из них не сравнивает спортсмена с его собственной нормой: сегодняшний пульс покоя 58 при личном базлайне 55 — реальный сигнал недовосстановления — по абсолютной шкале выглядит «хорошо».

После этого изменения появляется `models/readiness.py::compute_readiness_today` — единственная точка расчёта готовности: каждый фактор оценивается по отклонению от личного 28-дневного базлайна, баланс нагрузки (TSB) участвует как фактор, результат содержит score 0–100, статус, факторы с evidence-строками из конкретных чисел («ЧСС покоя 58 против базовых 55, +3») и главные драйверы. Существующие потребители (`api/readiness_snapshot.py`, который уже едет в SSE meta каждого чата коуча, и `signals_engine`) начинают считать через новый модуль, их JSON-контракты не меняются.

Проверить работу можно так: `python -m pytest tests/smoke -q` зелёный, а живой запуск (см. Validation) показывает, что при «зелёном» Garmin readiness и повышенном на +5 уд/мин пульсе покоя итоговый score снижается и в drivers появляется пульс покоя с evidence-строкой.

## Progress

- [x] (2026-07-09) Исследование: прочитаны `api/readiness_snapshot.py`, `models/signals_engine.py`, `data/data_processor_phase1.py::calculate_comprehensive_readiness`, `models/banister.py::get_current_metrics`, тесты `tests/smoke/test_readiness_snapshot_contract.py`.
- [x] (2026-07-09) GitHub issue #139 создан.
- [x] (2026-07-09) Milestone 1: `models/readiness.py` + 9 смоук-тестов математики (`tests/smoke/test_readiness_model.py`); константа окна перенесена (`ai_tools` реэкспортирует).
- [x] (2026-07-09) Milestone 2: `api/readiness_snapshot.py` делегирует модели; контрактные тесты зелёные без правки ожиданий; добавлены аддитивные поля drivers/tsb/confidence.
- [x] (2026-07-09) Milestone 3: `signals_engine._readiness_signal` делегирует модели (source="fusion", drivers в payload); тест старой override-семантики переписан на fusion-инвариант.
- [x] (2026-07-09) Финальный прогон `tests/smoke`: 412 passed (базлайн 403); живая проверка на реальной БД — см. Artifacts.

## Surprises & Discoveries

- Observation: fusion уже существует дважды и противоречит сам себе — Phase1 даёт Garmin readiness вес 15%, signals_engine делает его полным override.
  Evidence: `models/signals_engine.py:125-131` (`if training_value is not None: value = training_value`), `data/data_processor_phase1.py:899-902` (вес 0.15).
- Observation: базлайн HRV в signals_engine — среднее по всему переданному DataFrame (обычно 30 дней, но зависит от вызывающего), а не фиксированное окно.
  Evidence: `models/signals_engine.py:171` (`baseline = df["rmssd"].dropna().mean()`).
- Observation: контракт снапшота требует считать score даже по данным 8-дневной давности (status="stale", но score числовой) — первоначальный дизайн модели отбрасывал значения старше 2 дней и ломал этот тест.
  Evidence: `tests/smoke/test_readiness_snapshot_contract.py::test_readiness_snapshot_stale_data_is_marked_stale` (`assert snapshot["score"] is not None` при данных −8 дней).
- Observation: на реальной БД 28-дневные базлайны заметно отличаются от «интуитивных» недельных сравнений коуча: RHR базлайн 58.8 (коуч сравнивал с 55), HRV базлайн 33.4 (коуч — с 37). Fusion даёт более консервативную и честную точку отсчёта.
  Evidence: живой прогон 2026-07-09 — «Пульс покоя 58.0 против базовых 58.8 (−0.8)», «HRV 35.0 против базовых 33.4 (+4.9%)».

## Decision Log

- Decision: Garmin `training_readiness` — один из факторов (вес 0.15), не override.
  Rationale: принцип «within-athlete trends»: Garmin-оценка непрозрачна и не воспроизводима; наша система должна давать проверяемое число. Override в signals_engine делал остальные сигналы мёртвыми.
  Date/Author: 2026-07-09 / Claude.
- Decision: `stress_score` исключён из fusion v1 (остаётся в snapshot как справочный фактор с score=None).
  Rationale: источник тот же, что HRV (`hrv_data`), сильная корреляция с rmssd — двойной счёт одного сигнала; проще объяснить 5 факторов, чем 6.
  Date/Author: 2026-07-09 / Claude.
- Decision: базлайны считаются только по строкам с датой строго раньше сегодняшней; сегодняшнее значение сравнивается с ними.
  Rationale: семантика «неполного сегодняшнего дня» из issue #126 / PR #128 — сегодняшняя строка не должна влиять на норму, с которой сравнивается.
  Date/Author: 2026-07-09 / Claude.
- Decision: TSB считается на стабильном окне `COACH_LOAD_METRICS_WINDOW_DAYS = 90` (константа в `models/ai_tools.py`, введена PR #135), константу переносим в `models/readiness.py` и реэкспортируем из `ai_tools` для обратной совместимости.
  Rationale: issue #134 — метрики не должны зависеть от окна запроса; один источник истины для константы должен жить в модели, а не в инструментах коуча. Перенос без реэкспорта сломал бы импорты.
  Date/Author: 2026-07-09 / Claude.
- Decision: кусочно-линейные пороги факторов вместо непрерывных формул.
  Rationale: объяснимость важнее гладкости — evidence-строка «HRV −12% от базлайна → 40 баллов» проверяема человеком; непрерывную формулу спортсмену не объяснить. Пороги собраны в одном словаре `FACTOR_BANDS`, менять легко.
  Date/Author: 2026-07-09 / Claude.
- Decision: у `compute_readiness_today` появился параметр `max_value_age_days` (дефолт 2, `None` = без ограничения); `readiness_snapshot` передаёт `None`.
  Rationale: контракт снапшота обязан отдавать score по устаревшим данным, помечая их `stale` — политика свежести принадлежит контракту, а не модели.
  Date/Author: 2026-07-09 / Claude.
- Decision: окно базлайна анкерится к дате текущего значения, а не к «сегодня», и никогда не включает само сравниваемое значение.
  Rationale: когда свежайшая строка отстаёт от сегодняшнего дня, «28 дней до сегодня» включали бы её саму в собственный базлайн.
  Date/Author: 2026-07-09 / Claude.
- Decision: тест `test_assemble_signals_prefers_training_status_readiness` переписан в `test_assemble_signals_fuses_readiness_instead_of_garmin_override`.
  Rationale: тест фиксировал ровно ту семантику (Garmin как override), которую issue #139 убирает по дизайну; новый тест фиксирует fusion-инвариант и наличие drivers.
  Date/Author: 2026-07-09 / Claude.

## Outcomes & Retrospective

(2026-07-09) Все три milestone выполнены за одну сессию. Итог: `models/readiness.py` — единственная точка расчёта готовности; `readiness_snapshot` (SSE meta коуча, dashboard, planning) и `signals_engine` (дашборд) считают через неё; смоук 412 passed (базлайн 403, +9 новых). Живой прогон на реальной БД: score 68.8 «ready», confidence 0.8 (нет Garmin readiness в данных — честно отражено), TSB −18.1 совпадает со стабильным окном #135, каждый фактор с evidence-строкой. Осталось за пределами scope: подключение health_df в вызовы `assemble_signals` из dashboard/planning (сейчас RHR-фактор есть только в snapshot-пути), удаление старого калькулятора Phase1 (другие потребители), выравнивание порогов `_readiness_signal` с моделью. Следующий слой контура — детектор конфликта готовность×плановая сессия (Issue C) поверх `compute_readiness_today`.

## Context and Orientation

Репозиторий: `ai_trainer/`. Данные лежат в SQLite (`ai_trainer.db`), доступ через `data/database.py::Database` (per-query connections). Ключевые методы: `get_sleep_data(days)`, `get_hrv_data(days)`, `get_daily_health(days)`, `get_training_status_history(days)`, `get_activities(days)` — все возвращают pandas DataFrame с колонкой `date`.

Термины. «HRV» — вариабельность сердечного ритма, столбец `rmssd` (мс) в `hrv_data`; выше — лучше, падение относительно личной нормы — признак стресса/недовосстановления. «RHR» — пульс покоя, столбец `resting_hr` в `daily_health`; ниже — лучше, рост на несколько ударов относительно нормы — признак недовосстановления. «TSB» (training stress balance) — «свежесть» из модели Банистера: CTL (хроническая нагрузка, EWMA 42 дня) минус ATL (острая, EWMA 7 дней); считается `models/banister.py::BanisterModel.get_current_metrics(tss_data, dates)` по списку TSS активностей. Отрицательный TSB — накопленная усталость. «Базлайн» — личная норма спортсмена: среднее значение показателя за последние 28 завершённых дней.

Существующий код, который трогаем:

- `api/readiness_snapshot.py::build_readiness_snapshot(db)` — JSON-контракт readiness для API: ключи `score`, `status` (`unknown/stale/low/limited/ready/strong`), `computed_at`, `is_provisional`, `source_completeness`, `factors` (список `{key,label,score,raw_value,source}`), `missing_inputs`, `stale`, `reason`. Уже отдаётся в SSE `meta` каждого чата коуча (`api/routers/coach.py`), в dashboard и planning. Контракт покрыт `tests/smoke/test_readiness_snapshot_contract.py` — эти тесты должны остаться зелёными без правок ожиданий, кроме заведомо аддитивных полей.
- `models/signals_engine.py::assemble_signals(...)` — сборка сигналов для дашборда; внутри `_readiness_signal(sleep_df, hrv_df, training_status)` — то место, где Garmin readiness сейчас перекрывает всё. Покрыт `tests/smoke/test_signals_engine.py`.
- `data/data_processor_phase1.py::Phase1DataProcessor.calculate_comprehensive_readiness` — старый калькулятор; НЕ удаляем (его вызывают другие места), но `readiness_snapshot` и `signals_engine` перестают его использовать.
- `models/ai_tools.py::COACH_LOAD_METRICS_WINDOW_DAYS = 90` — стабильное окно расчёта CTL/ATL/TSB (введено PR #135).

Смежная семантика, которую обязаны уважать: «сегодняшняя строка — неполный день» (issue #126, PR #128): агрегаты по дневным данным не включают сегодня. Для готовности это означает: базлайны строятся по дням строго до сегодняшнего; сегодняшние значения HRV/сна/RHR — валидные утренние показания и используются как «текущее значение».

## Plan of Work

Milestone 1 — модель. Создать `models/readiness.py` с чистой функцией `compute_readiness_today(sleep_df, hrv_df, health_df, training_df, activities_df, *, today: date | None = None) -> dict`. Функция не ходит в БД — принимает DataFrame'ы, чтобы тесты были синтетическими и детерминированными. Внутри:

1. Разрезать каждый дневной DataFrame на «сегодня» (строка с `date == today`) и «историю» (строго раньше). Текущее значение фактора — сегодняшняя строка, если есть, иначе самая свежая историческая не старше 2 дней (тогда `stale_input=True` у фактора).
2. Базлайны: HRV — среднее `rmssd` за последние 28 дней истории (минимум 5 значений, иначе фактор без базлайна использует абсолютную шкалу и помечается `baseline: null`); RHR — аналогично по `resting_hr`.
3. Факторные score 0–100 по кусочным порогам (словарь `FACTOR_BANDS` в модуле):
   - `hrv`: отклонение в процентах от базлайна: ≥ +5% → 85; −5..+5% → 70; −10..−5% → 55; −20..−10% → 40; < −20% → 20. Без базлайна: rmssd ≥ 50 → 75; 35..50 → 60; 25..35 → 45; < 25 → 25.
   - `resting_hr`: разница с базлайном в уд/мин: ≤ 0 → 85; +1..+2 → 70; +3..+4 → 50; +5..+7 → 35; > +7 → 20. Без базлайна: 40..60 → 70; 60..70 → 55; иначе → 40.
   - `sleep`: если есть `sleep_score` — используем его как есть; иначе по часам (`total_sleep_minutes/60`): ≥ 8 → 85; 7..8 → 75; 6..7 → 55; 5..6 → 40; < 5 → 25.
   - `training_readiness`: значение Garmin 0–100 как есть.
   - `tsb`: TSB через `BanisterModel().get_current_metrics` по активностям за 90 дней: > +5 → 85; −10..+5 → 70; −20..−10 → 55; −30..−20 → 35; < −30 → 15.
4. Веса: `hrv 0.30, resting_hr 0.20, sleep 0.20, training_readiness 0.15, tsb 0.15`; отсутствующие факторы выпадают, веса перенормируются. Score — взвешенное среднее, округлённое до 0.1.
5. Статус — те же пороги, что в snapshot: `< 40 low`, `< 60 limited`, `< 75 ready`, иначе `strong`; `unknown`, если нет ни одного фактора.
6. Каждый фактор — словарь `{key, label, score, weight, raw_value, baseline, deviation, evidence, source, stale_input}`. Evidence — короткая русская строка с числами: «RMSSD 35.0 мс против базовых 37.2 (−5.9%)», «ЧСС покоя 58 против базовых 55 (+3)», «TSB −18.1 (усталость выше нормы)».
7. `drivers` — до трёх факторов, отсортированных по «весу × |score − 70|» (вклад в отклонение от нейтрали), каждый с evidence.
8. Верхний уровень: `{score, status, as_of_date, confidence, factors, drivers, missing_inputs, tsb: {ctl, atl, tsb, window_days}}`. `confidence` — доля присутствующих факторов из пяти. `as_of_date` — максимум дат использованных значений (ISO).

Также в Milestone 1: перенести константу окна — в `models/readiness.py` объявить `LOAD_METRICS_WINDOW_DAYS = 90`, в `models/ai_tools.py` заменить объявление на импорт-алиас `COACH_LOAD_METRICS_WINDOW_DAYS = LOAD_METRICS_WINDOW_DAYS`.

Тесты Milestone 1 — новый `tests/smoke/test_readiness_model.py` (маркер `pytest.mark.smoke`, как в соседних файлах), синтетические DataFrame'ы:

- полный набор «всё хорошо» → status ready/strong, все 5 факторов, confidence 1.0;
- «Garmin зелёный (80), но RHR +5 к базлайну и HRV −15%» → score ниже, чем в первом кейсе, drivers содержат resting_hr и hrv с evidence;
- базлайн не включает сегодня: 28 дней RHR 55, сегодня 70 → базлайн 55, deviation +15;
- пустые входы → status unknown, score None, drivers пустые;
- TSB-фактор: активности с большим свежим TSS → tsb-фактор warn/alert диапазона, поле `tsb.window_days == 90`;
- отсутствует Garmin readiness → фактор выпадает, веса перенормированы (score считается по четырём).

Milestone 2 — `api/readiness_snapshot.py`. `build_readiness_snapshot` вместо `Phase1DataProcessor.calculate_comprehensive_readiness` вызывает `compute_readiness_today` (данные тянет теми же методами Database + `get_activities(90)`). Сохранить все существующие ключи контракта; `factors` обогатить полями `baseline`, `deviation`, `evidence`, `weight` (аддитивно); `stress` оставить в factors как справочный (score None, raw из `hrv_data.stress_score`); добавить верхнеуровневые `drivers` и `tsb` (аддитивно). `PRIMARY_INPUTS` не менять (completeness/missing_inputs — по тем же четырём). Проверка: `tests/smoke/test_readiness_snapshot_contract.py` зелёный без изменения ожиданий; при необходимости добавить в него аддитивные проверки новых полей отдельным тестом.

Milestone 3 — `models/signals_engine.py`. `_readiness_signal` принимает дополнительно `activities_df` (прокинуть из `assemble_signals`, где он уже есть) и вызывает `compute_readiness_today`; `value` — итоговый score, `source` — `"fusion"` (при отсутствии данных — прежние fallback-метки), тональности/лейблы — по прежним порогам. Старые ветки `training_status`-override и `_readiness_from_recovery_frames` удалить. `tests/smoke/test_signals_engine.py` может потребовать правки ожиданий source — это осознанное изменение семантики, зафиксировать в Decision Log при выполнении.

## Concrete Steps

Рабочая директория — корень репозитория (или worktree ветки `feat/readiness-today-139`).

    # тесты (TDD: сначала пишем test_readiness_model.py, видим падение)
    ./ai_trainer_env/bin/python -m pytest tests/smoke/test_readiness_model.py -q
    # ожидаемо: ModuleNotFoundError / failures до реализации, N passed после

    # полный смоук после каждого milestone
    ./ai_trainer_env/bin/python -m pytest tests/smoke -q
    # ожидаемо: 403+ passed (базлайн на 2026-07-09: 403 passed)

## Validation and Acceptance

Поведенческая приёмка: после Milestone 2 запустить из корня:

    ./ai_trainer_env/bin/python - <<'EOF'
    from data.database import Database
    from api.readiness_snapshot import build_readiness_snapshot
    s = build_readiness_snapshot(Database())
    print(s["score"], s["status"], s["confidence" if "confidence" in s else "source_completeness"])
    for d in s.get("drivers", []):
        print("-", d["evidence"])
    EOF

Ожидаемо: числовой score, статус из набора low/limited/ready/strong, у каждого драйвера — evidence-строка с конкретными числами и базлайном. Ключевой сценарий-инвариант (проверяется тестом): при Garmin readiness 80 и RHR на +5 уд/мин выше личного базлайна итоговый score строго ниже, чем при том же Garmin readiness и RHR на базлайне — «зелёный Garmin» не маскирует недовосстановление.

## Idempotence and Recovery

Все изменения аддитивны, кроме внутренностей `_readiness_signal` (Milestone 3) — он правится последним, когда модель уже покрыта тестами. Старый калькулятор Phase1 не удаляется. Шаги повторяемы; при падении смоука после milestone — откатить только его файлы, предыдущие milestone'ы остаются валидными.

## Artifacts and Notes

Живой прогон на реальной БД (2026-07-09), команда из Validation:

    score: 68.8 | status: ready | confidence: 0.8 | as_of: 2026-07-09
    tsb: {'ctl': 17.6, 'atl': 35.7, 'tsb': -18.1, 'window_days': 90}
      hrv: score=70.0 weight=0.353 | HRV 35.0 мс против базовых 33.4 (+4.9%)
      resting_hr: score=85.0 weight=0.235 | Пульс покоя 58.0 уд/мин против базовых 58.8 (−0.8 уд/мин)
      sleep: score=61.3 weight=0.235 | Сон: оценка Garmin 61/100
      tsb: score=55.0 weight=0.176 | TSB -18.1 (усталость выше нормы)
      stress: score=None weight=None | Стресс 25/100 (справочно, в fusion не входит)

Смоук-сьюта: 412 passed (базлайн до работы — 403 passed).

## Interfaces and Dependencies

В `models/readiness.py` должны существовать к концу работы:

    LOAD_METRICS_WINDOW_DAYS: int = 90
    BASELINE_WINDOW_DAYS: int = 28
    FACTOR_WEIGHTS: dict[str, float]   # hrv/resting_hr/sleep/training_readiness/tsb
    FACTOR_BANDS: dict[str, ...]       # кусочные пороги, см. Plan of Work

    def compute_readiness_today(
        sleep_df: pd.DataFrame | None,
        hrv_df: pd.DataFrame | None,
        health_df: pd.DataFrame | None,
        training_df: pd.DataFrame | None,
        activities_df: pd.DataFrame | None,
        *,
        today: datetime.date | None = None,
    ) -> dict[str, Any]: ...

Зависимости: pandas, `models/banister.py::BanisterModel` (уже в репо). Новых внешних библиотек нет. Потребители после этой работы: `api/readiness_snapshot.py`, `models/signals_engine.py`; следующий слой (детектор конфликта готовность×сессия, Issue C) будет читать `compute_readiness_today` напрямую — сигнатуру не менять без обновления этого плана.
