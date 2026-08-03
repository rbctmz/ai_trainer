# Методика расчёта Activity TSS

## Обзор

TSS (Training Stress Score) для каждой активности считается в `ActivityProcessor.resolve_tss()` (`data/data_processor.py`), обёртка — `calculate_tss()`. Расчёт запускается:

- при каждой синхронизации Garmin — `services/sync.py::_sync_activities()`;
- при пересчёте уже сохранённых записей по актуальным правилам — `data/database.py::_repair_legacy_activity_tss()`.

Это единственный путь, формирующий `tss`, который использует дашборд, планирование и коуч-логика. Нативный Garmin TSS (`activityTrainingLoad` и т.п.) извлекается отдельно и **не используется** как итоговый `tss` — только как справочное поле (см. ниже).

## FTP / LTHR

`resolve_athlete_ftp_lthr()` (`data/data_processor.py`) берёт `ftp`/`lthr` из последней синхронизированной с Intervals.icu записи `athlete_profile`; для любого поля, которого там нет (или если синка ещё не было), используется статичный `Settings.USER_FTP`/`USER_LTHR` из `.env` (дефолты 250/170).

## Плавательный порог (CSS)

Плавательный TSS считается по темпу (sTSS) относительно индивидуального
порогового темпа плавания — CSS (Critical Swim Speed, функциональный порог
плавания). Значение берётся из Intervals.icu (Settings → Swim → Threshold
pace; Intervals.icu может считать его автоматически из лучших заплывов):

- `services/intervals_icu.py::sync_athlete_profile` читает запись `sportSettings`
  с типом `Swim` и поле `threshold_pace` — это **скорость в м/с** (API
  Intervals.icu всегда хранит скорость в м/с);
- каноническая локальная единица — **секунды на 100 метров**,
  `swim_threshold_pace_seconds_per_100m`, с provenance
  `swim_threshold_pace_source`/`swim_threshold_pace_synced_at` (та же схема,
  что у бегового темпа, #308/#362);
- валидный диапазон 50–300 с/100м (1:00–5:00/100м); malformed/ambiguous →
  `None`;
- статичного `.env`-дефолта для CSS **нет**: без синхронизированного значения
  каскад честно остаётся на ЧСС-ветках.

## Каскад по видам спорта

`resolve_tss()` пробует методы по убыванию точности и берёт первый, для которого хватает данных. Длительность для всех формул — `moving_duration_minutes`, если она есть и > 0, иначе `duration_minutes` (`_tss_duration_minutes`).

**Bike:**
1. `power_tss_bike` — Power TSS по `normalized_power` (приоритетно) или `avg_power`
2. `hr_zone_tss_bike` — зонально-взвешенный TSS по ЧСС
3. `hr_tss_bike` — HR TSS по средней ЧСС
4. `heuristic_duration_bike` — эвристика, 60 TSS/час

**Run:**
1. `hr_zone_tss_run` — зонально-взвешенный TSS по ЧСС (мощность бега, даже если есть в данных, в каскаде для run не участвует вообще)
2. `hr_tss_run` — HR TSS
3. `heuristic_duration_run` — эвристика, 50 TSS/час

**Swim:**
1. `pace_tss_swim` — sTSS по темпу (CSS-порог из профиля)
2. `hr_zone_tss_swim`
3. `hr_tss_swim`
4. `heuristic_duration_swim` — эвристика, 25 TSS/час

**Walk:** только эвристика (`heuristic_duration_walk`) — 9 TSS/час для сессий короче 45 мин, иначе 7 TSS/час; минимальный floor 2.0 TSS при движении от 8 минут.

**Strength / Yoga / Other:** эвристика по длительности — 22 TSS/час (strength, yoga), 20 TSS/час (остальное).

## Формулы

- **Power TSS**: `duration_hours × (NP/FTP)² × 100`
- **HR TSS**: `duration_hours × (avg_HR/LTHR)² × 100` — формула Коггана, но на пульсе вместо мощности
- **Swim Pace TSS (sTSS)**: `duration_hours × IF³ × 100`, где
  `IF = CSS-темп / средний темп` (обе величины в секундах на 100 м). Средний
  темп считается из `moving_duration_minutes` и `distance_km`:
  `мин × 60 / (км × 10)` с/100м. Показатель кубический (а не квадратный),
  потому что сопротивление воды делает рост стресса от скорости быстрее, чем
  на суше (TrainingPeaks). Sanity-порог: средний темп должен быть > 30 с/100м.
- **Zone-weighted TSS**: `Σ (время_в_зоне_мин × вес_зоны)` по 5 зонам ЧСС Garmin (`hrTimeInZone_1..5`)

Веса зон (`data/data_processor.py`):

| Зона | Bike | Run | Swim |
|---|---|---|---|
| 1 | 0.20 | 0.45 | 0.0 |
| 2 | 0.35 | 0.70 | 0.4 |
| 3 | 0.65 | 1.00 | 0.5 |
| 4 | 0.95 | 1.20 | 0.6 |
| 5 | 1.30 | 1.50 | 1.8 |

Плавательные веса применяются только когда `pace_tss_swim` недоступен (нет CSS
в профиле или нет дистанции/темпа): ЧСС в воде систематически занижается
(ниже ЧСС-потолок из-за охлаждения и dive reflex, неточный wrist-HR), поэтому
приоритет у темпа.

## Что сохраняется, но не участвует в расчёте

- `source_tss` / `garmin_training_load` — нативный Garmin `activityTrainingLoad`/`trainingLoad`/`trainingStressScore`/`activityTrainingStressScore` (первое ненулевое значение по этому приоритету). Хранится для сравнения, никогда не подмешивается в `tss`. С ADR-0008 `source_tss` дополнительно трактуется как legacy-проекция нагрузки **первичного** источника (см. «Provider-fallback как исключение» ниже); Garmin `trainingLoad`/`garmin_training_load` при этом по-прежнему НИКОГДА не становится каноническим `tss`.
- `MetricsCalculator.training_stress_score()` в `utils/metrics.py` — отдельная реализация классического power-only TSS Коггана (+ NP через rolling⁴). Инстанцируется в `models/ai_data_context.py`, но её методы нигде не вызываются — мёртвый код, не влияет на реальный расчёт.

## Сравнение с внешними источниками (пример 2026-07-08)

Три активности за 2026-07-08, сопоставлены по `external_id` (Intervals.icu) = `activity_id` (наша БД):

| Активность | Наш `tss` | Метод | Garmin `trainingLoad` | Intervals.icu `icu_training_load` |
|---|---|---|---|---|
| Бег, 25 мин | 28.2 | hr_zone_tss_run | 71.4 | 31 (= hr_load; power_load отсутствует) |
| Вело #1, 10:46 | 26.1 | power_tss_bike (NP=127) | 91.6 | 29 (power_load=29, hr_load=22) |
| Вело #2, 19:00 | 38.1 | power_tss_bike (NP=141) | 56.9 | 43 (power_load=43, hr_load=17) |
| **Сумма** | **92.4** | | **219.9** | **103** |

Наш расчёт и Intervals.icu используют одну и ту же формулу Коггана и близки друг к другу (~11% разницы); оба заметно ниже Garmin `trainingLoad`, который считается закрытым алгоритмом Firstbeat (EPOC-based) — это отдельная метрика, не TSS в классическом смысле, сравнивать её 1:1 некорректно.

Источник расхождения с Intervals.icu на этих трёх активностях:

- **NP считается по-разному.** Garmin отдаёт готовое `normPower` в самой активности (127 и 141 Вт на двух велозаездах), Intervals.icu пересчитывает NP заново из потока мощности своим алгоритмом (`icu_weighted_avg_watts` = 133 и 147 Вт — на ~5% выше в обоих случаях). FTP (159) и LTHR (163) в обеих системах совпадают точно — расхождение не в профиле атлета.
- **`moving_time` определяется чуть по-разному** (разные пороги автопаузы): у Intervals.icu на 13–63 секунды длиннее на этих заездах — вклад в разницу TSS второстепенный по сравнению с NP.
- **Для бега разные зональные сетки ЧСС** при идентичном сыром HR-потоке (avg_HR=150, LTHR=163, длительность ~1500 с совпадают в обеих системах): у нас 5 зон Garmin, у Intervals.icu — 7-зонная модель Коггана. Разные границы зон и веса дают разную взвешенную сумму.

## Решение (2026-07-09)

Рассматривали замену локального каскада на приоритетное использование `icu_training_load` из Intervals.icu API (аналогично тому, как уже подтягиваются FTP/LTHR). Решили **оставить текущий локальный каскад как есть**: он полностью оффлайн и детерминирован, не зависит от сети/лимитов Intervals.icu на каждый sync, а расхождение с Intervals.icu небольшое и объяснимое (см. выше) — не похоже на баг. Возвращаться к вопросу, если расхождение станет мешать работе над клином «недовосстановление + перепланирование» (readiness/replanning agent contour), либо если появится более показательный откалиброванный пример через IntervalCoach.

## Provider-fallback как исключение (ADR-0008, 2026-07-22)

Решение 2026-07-09 (локальный каскад offline/детерминирован) остаётся в силе для
Garmin-primary пути. Трек Intervals-primary (`docs/intervals_primary_handoff_execplan.md`,
ADR `docs/architecture/adr_0008_intervals_activity_ingestion.md`, #269) вводит одно
**точечное исключение — ТОЛЬКО для Intervals**:

- **Local-first, fallback только при отсутствии локального результата.** Контракт
  `_normalize_intervals` потребляет уже вычисленную ПАРУ `tss`+`tss_method`, если
  строка её несёт (например, обогащённый адаптер или reconciliation-строка с
  локальным расчётом), — она приоритетна и не подменяется провайдерским. Текущий
  list-адаптер (`list_activities`) потоков мощности/ЧСС НЕ получает и локальный
  каскад с FTP/LTHR не гоняет, поэтому для его «голых» строк
  `icu_training_load` становится каноническим `tss`, но ЯВНО маркируется
  `tss_method="intervals_icu_provider_fallback"` (провайдерский fallback, не
  локальный расчёт). Потоковый пересчёт по Intervals — осознанный non-goal
  (решение 2026-07-09: локальный каскад остаётся офлайн/детерминированным).
  Local-first-контракт закреплён тестом
  `test_normalize_intervals_local_first_tss_not_bypassed`.
- Нативная нагрузка каждого источника хранится ПО СВЯЗИ в
  `activity_provider_links.provider_tss` (Garmin-link и Intervals-link — раздельно).
  `activities.source_tss` — legacy-проекция нагрузки первичного источника
  (`PRIMARY_ACTIVITY_SOURCE`); канонический носитель нагрузки — `tss`+`tss_method`
  либо per-link `provider_tss`.
- Garmin `trainingLoad` (Firstbeat/EPOC) — по-прежнему НЕ TSS и НИКОГДА не
  канонический `tss`: для Garmin остаётся локальный каскад/heuristic, provider-fallback
  к Garmin-нагрузке не применяется.
- Выбор авторитетного источника канонических полей и `source_tss` — детерминированный
  и order-independent (`Garmin→Intervals ≡ Intervals→Garmin`), см. ADR-0008 п.4 и
  `tests/smoke/test_activity_ingest.py`.

## Связанные документы

- `docs/intervals_primary_handoff_execplan.md` / `docs/architecture/adr_0008_intervals_activity_ingestion.md` — provider-link модель приёма активностей из нескольких источников; provider-fallback Intervals как явное исключение (#269).
- `docs/activity_tss_semantics_execplan.md` — отделение Garmin `trainingLoad` от `tss` (issue #32/#33 и далее).
- `docs/activity_tss_reconciliation_execplan.md` — введение source-backed резолвера вместо наивной кросс-спортовой формулы.
- `docs/activity_tss_calibration_execplan.md` — калибровка формул по видам спорта против IntervalCoach.
