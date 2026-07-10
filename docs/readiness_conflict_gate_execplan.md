# Salience-gate: детектор конфликта «готовность × плановая сессия»

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md` at the repository root. Строится поверх ExecPlan `docs/readiness_today_execplan.md` (issue #139, смержен): тот дал единую функцию готовности `models/readiness.py::compute_readiness_today`; здесь она используется как вход.

## Purpose / Big Picture

AI Trainer движется от «AI-ассистента, отвечающего на вопросы» к агенту, который сам замечает расхождение состояния спортсмена и плана. Первый продуктовый клин: недовосстановление перед ключевой тренировкой. Для этого нужен детерминированный детектор («salience-gate» — фильтр значимости): он смотрит на готовность сегодня и плановые сессии ближайших дней и either объявляет типизированный конфликт с уликами-числами, either молчит. Молчание — дефолт и полноценный результат: доля дней, когда агент вмешался, станет измеримой метрикой доверия.

После этого изменения появляется отчёт `build_readiness_conflict_report(db)`: если сегодня готовность низкая, а завтра по плану «Качество • вело», отчёт содержит конфликт severity=high с evidence-строками («Готовность 38/100 (low): HRV −15% от базлайна…; через 1 день Качество • вело, TSS 29»). Отчёт аддитивно едет в SSE `meta` каждого чата коуча рядом с `readiness_snapshot`. Никакого LLM внутри: только правила и числа.

Увидеть работу: `python -m pytest tests/smoke -q` зелёный; живой прогон (см. Validation) печатает отчёт по реальной БД с конфликтами или честным «молчанием».

## Progress

- [x] (2026-07-09) Исследование: `session_templates` активного плана уже несут `session_role` ∈ {recovery, easy, long, quality} (`models/training_planner.py`, `_estimate_session_duration_minutes`/`day_roles`) — семантика сессии есть, Issue A для v1 не нужен.
- [x] (2026-07-09) GitHub issue #141 создан.
- [x] (2026-07-09) Milestone 1: `models/readiness_conflicts.py` + 22 смоук-теста (`tests/smoke/test_readiness_conflicts.py`): матрица, гейт данных, горизонт, пропуск отдыха, evidence.
- [x] (2026-07-09) Milestone 2: `api/readiness_conflicts.py::build_readiness_conflict_report(db)` + тесты сборки из seeded БД (конфликт при quality завтра, молчание без плана, data gap на пустой БД).
- [x] (2026-07-09) Milestone 3: `readiness_conflicts` в SSE meta коуча (`api/routers/coach.py`) + тест наличия.
- [x] (2026-07-09) Финальный смоук: 435 passed (базлайн 413). Живой прогон — см. Artifacts. Follow-up `2a61748` дописан в Decision Log `docs/readiness_today_execplan.md`.

## Surprises & Discoveries

- Observation: роль сессии не нужно парсить из названий — планировщик уже пишет `session_role` в каждый шаблон.
  Evidence: живой план 2026-07-09: `roles: {'easy': 14, 'recovery': 8, 'long': 4, 'quality': 2}`.

## Decision Log

- Decision: для детектора данные готовности старше 2 дней выпадают (`max_value_age_days` по умолчанию), в отличие от snapshot-контракта (`None`).
  Rationale: snapshot обязан показать хоть что-то и пометить stale; детектор, который тревожит спортсмена на несвежих данных, ложно-положителен по построению. Нехватка свежих данных → `data_gap: true` и молчание.
  Date/Author: 2026-07-09 / Claude.
- Decision: порог уверенности `MIN_CONFIDENCE = 0.5`: ниже — молчание с `data_gap`.
  Rationale: confidence = доля присутствующих факторов из пяти; при 2 из 5 (например, только сон и TSB) статус готовности слишком шаткий, чтобы вмешиваться. Порог — константа модуля, легко пересмотреть по WoZ-данным.
  Date/Author: 2026-07-09 / Claude.
- Decision: severity будущих сессий в горизонте (1–3 дня) не дисконтируется, но каждая несёт `days_until`.
  Rationale: клин — «недовосстановление ПЕРЕД ключевой сессией», ценность именно в раннем предупреждении; решение о дисконте — за контуром/коучем, детектор факты не взвешивает по времени.
  Date/Author: 2026-07-09 / Claude.
- Decision: дни отдыха (TSS ≤ 0) и роль recovery не конфликтуют ни при какой готовности.
  Rationale: конфликт «низкая готовность × восстановительный день» — это согласие плана и состояния, не расхождение.
  Date/Author: 2026-07-09 / Claude.
- Decision: сегодняшняя сессия входит в горизонт (days_until = 0).
  Rationale: «сегодня качество, а готовность низкая» — самый острый случай клина; исключать его ради «утро уже прошло» преждевременно.
  Date/Author: 2026-07-09 / Claude.
- Decision: follow-up issue #152 сохраняет базовый горизонт 3 дня, но расширяет его до ближайшей quality-сессии, если она находится в пределах 7 дней.
  Rationale: живой прогон 2026-07-10 показал quality-сессию на четвёртый день, невидимую фиксированному горизонту. Ограниченное расширение до ключевой сессии даёт раннее предупреждение без недельного потока обычных alert-кандидатов.
  Date/Author: 2026-07-10 / Codex.

## Outcomes & Retrospective

(2026-07-09) Все milestone выполнены за одну сессию. Детектор чист от LLM, все пороги — именованные константы, каждый конфликт несёт evidence-числа. Живой прогон на реальной БД показал главный дизайн-инвариант в действии: готовность ready (68.8) × ближайшие easy/recovery/long сессии → `silence: true` с человекочитаемым reason — агент молчит, когда план и состояние согласны. Вне scope остались: варианты перепланирования при конфликте (Issue E), прогноз качества (Issue D), доставка конфликта в web-UI (meta уже содержит отчёт — UI может рендерить без изменений API), учёт `days_until` в severity (решение за контуром). Для WoZ-ритуала отчёт готов как источник строк decision_log: silence/data_gap/конфликт — все три исхода логируемы. Follow-up #152 позже добавил bounded lookahead до ближайшей quality-сессии и canonical readiness projection для Dashboard, не меняя severity-матрицу.

## Context and Orientation

Репозиторий `ai_trainer/`: SQLite через `data/database.py::Database`, FastAPI в `api/`, модели в `models/`. Ключевые входы детектора:

- Готовность: `models/readiness.py::compute_readiness_today(sleep_df, hrv_df, health_df, training_df, activities_df, *, today, max_value_age_days)` → `{score: float|None, status: unknown/low/limited/ready/strong, confidence: 0..1, drivers: [{key,label,score,evidence}], factors, missing_inputs, tsb}`. «Драйвер» — фактор с наибольшим вкладом в отклонение от нейтрали, несёт evidence-строку с числами.
- План: активный план хранится в planning checkpoint; `api/planning_service.py::get_active_plan(db)` возвращает `goal_plan` со списками `daily_plan` (кортежи `(datetime, total_tss, parts)` по дням) и `session_templates` (по элементу на день: `date`, `session_role`, `session_focus`, `sport_label`, `phase`, `export_name`). `session_role` ∈ {recovery, easy, long, quality}.

Термины. «Salience-gate» — фильтр значимости: конфликт объявляется только когда расхождение превышает пороги матрицы; иначе выход — «молчание» (`silence: true`). «Горизонт» — сколько дней вперёд смотрим (по умолчанию 3, включая сегодня). «data_gap» — молчание из-за нехватки/несвежести данных, а не из-за отсутствия расхождения.

## Plan of Work

Milestone 1 — `models/readiness_conflicts.py` (чистые функции, без БД):

`upcoming_plan_sessions(goal_plan, *, today, horizon_days=3)` — список сессий с `date` (ISO), `days_until`, `role`, `tss`, `name`, `sport_label`, `phase`. Источник: `daily_plan` (дата и TSS дня) + `session_templates[i]` (роль и название). Дни с TSS ≤ 0 пропускаются (отдых). Роль вне известного набора трактуется как `easy` (консервативно: слабее quality/long, но не немая).

`detect_readiness_conflicts(readiness, sessions, *, today, horizon_days=3)` — отчёт:

    {
      "as_of": "...",             # дата расчёта (из readiness или today)
      "horizon_days": 3,
      "readiness": {"score", "status", "confidence"},
      "sessions_evaluated": [...],
      "conflicts": [
        {"date", "days_until", "severity": "medium"|"high",
         "kind": "low_readiness_quality_session" | ...,
         "session": {"name","role","tss","sport_label"},
         "evidence": ["Готовность 38/100 (low): <драйверы>", "Через 1 день: Качество • вело, TSS 29"]}
      ],
      "silence": bool,            # нет конфликтов
      "data_gap": bool,           # молчание из-за данных
      "reason": str               # человекочитаемое объяснение исхода
    }

Матрица severity (константа `SEVERITY_MATRIX`): quality×low=high, quality×limited=medium, long×low=high, long×limited=medium, easy×low=medium; всё остальное — нет конфликта. Гейт данных: score None или confidence < `MIN_CONFIDENCE` (0.5) → `silence=true, data_gap=true`, конфликты не оцениваются. `kind` строится как `f"{status}_readiness_{role}_session"`.

Тесты Milestone 1 (`tests/smoke/test_readiness_conflicts.py`, синтетика): каждая ячейка матрицы (включая «strong × quality → молчание»), data gap, горизонт (quality через 5 дней при горизонте 3 не оценивается), пропуск дней отдыха, evidence содержит числа и название сессии, `silence`-отчёт имеет reason.

Milestone 2 — `api/readiness_conflicts.py::build_readiness_conflict_report(db, *, horizon_days=3)`: тянет те же DataFrame'ы, что `api/readiness_snapshot.py` (sleep/hrv/daily_health/training_status + activities за `LOAD_METRICS_WINDOW_DAYS`), вызывает `compute_readiness_today` с дефолтной свежестью (2 дня), берёт план через `api.planning_service.get_active_plan`; без плана — `silence=true` с reason «Нет активного плана». Тест: seeded tmp-БД (checkpoint с daily_plan/session_templates по образцу `tests/smoke/test_ai_tools_plan.py::_make_goal_plan` + свежие recovery-данные) → отчёт с ожидаемым конфликтом.

Milestone 3 — `api/routers/coach.py`: в первое SSE-событие `meta` добавить ключ `readiness_conflicts` (аддитивно, рядом с `readiness_snapshot`). Тест: по образцу `tests/smoke/test_readiness_snapshot_contract.py::test_coach_stream_meta_exposes_readiness_snapshot`.

Плюс: дописать в `docs/readiness_today_execplan.md` Decision Log запись о follow-up `2a61748` (распад TSB через дни отдыха) — обещание из ретроспективы #140.

## Concrete Steps

Рабочая директория — worktree ветки `feat/readiness-conflict-gate`.

    ./ai_trainer_env/bin/python -m pytest tests/smoke/test_readiness_conflicts.py -q
    # до реализации: ошибки импорта; после Milestone 1–3: N passed

    ./ai_trainer_env/bin/python -m pytest tests/smoke -q
    # базлайн на старте: 413 passed

## Validation and Acceptance

Живой прогон из корня (после Milestone 2):

    ./ai_trainer_env/bin/python - <<'EOF'
    from data.database import Database
    from api.readiness_conflicts import build_readiness_conflict_report
    import json
    r = build_readiness_conflict_report(Database())
    print(json.dumps(r, ensure_ascii=False, indent=1))
    EOF

Приёмка как поведение: (1) при синтетических данных «готовность low, завтра quality» отчёт содержит ровно один конфликт severity=high с evidence-числами; (2) при «готовность strong» тот же план даёт `silence=true` и reason без конфликтов; (3) при пустой БД — `silence=true, data_gap=true`; (4) SSE meta чата коуча содержит `readiness_conflicts` (смоук-тест); (5) полный смоук ≥ 413 passed.

## Idempotence and Recovery

Изменения аддитивны (новые модули + один новый ключ в meta). Повторный запуск шагов безопасен. Откат — удаление двух новых файлов и ключа в `coach.py`.

## Artifacts and Notes

Живой прогон на реальной БД (2026-07-09), команда из Validation (сокращено):

    "readiness": {"score": 68.8, "status": "ready", "confidence": 0.8},
    "sessions_evaluated": [
      {"date": "2026-07-09", "days_until": 0, "role": "easy", "tss": 8, "name": "Легкая • бег"},
      {"date": "2026-07-10", "days_until": 1, "role": "recovery", "tss": 20, "name": "Восстановление • вело"},
      {"date": "2026-07-11", "days_until": 2, "role": "long", "tss": 20, "name": "Длительная • вело"}
    ],
    "conflicts": [],
    "silence": true,
    "data_gap": false,
    "reason": "Готовность ready (68.8/100) не противоречит сессиям ближайших 3 дн. — вмешательство не требуется."

Смоук-сьюта: 435 passed (базлайн до работы — 413 passed).

## Interfaces and Dependencies

В `models/readiness_conflicts.py` к концу работы существуют:

    MIN_CONFIDENCE: float = 0.5
    SEVERITY_MATRIX: dict[tuple[str, str], str]   # (role, readiness_status) -> severity

    def upcoming_plan_sessions(goal_plan: dict, *, today: date, horizon_days: int = 3) -> list[dict]: ...
    def detect_readiness_conflicts(readiness: dict, sessions: list[dict], *, today: date, horizon_days: int = 3) -> dict: ...

В `api/readiness_conflicts.py`:

    def build_readiness_conflict_report(db: Database, *, horizon_days: int = 3) -> dict: ...

Зависимости: только существующие модули (`models/readiness.py`, `api/planning_service.py`, pandas). Потребитель следующего слоя: контур RecoveryReplanLoop (Issue F) и прогноз качества сессии (Issue D) читают отчёт напрямую — форму `conflicts[*]` не менять без обновления этого плана.
