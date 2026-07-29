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
- [x] (2026-07-29 16:10Z) Follow-up issue #315 зафиксировал живую репродукцию: structured `Neuromuscular Sprints` с ролью `easy`, fatigue `1/1/3` и восстановлением 30 ч давала silence при readiness `limited`.
- [x] (2026-07-29 16:16Z) RED: пять новых контрактных тестов подтвердили отсутствие day-level fatigue projection, конфликта и bounded lookahead; прежние 26 тестов остались зелёными.
- [x] (2026-07-29 16:25Z) GREEN: day projection агрегирует component-wise maximum по `sessions[]`, recovery maximum и источник salience; `limited × structured high-load easy` даёт medium-конфликт, а bounded lookahead ищет ближайшую значимую сессию.
- [x] (2026-07-29 16:42Z) Follow-up #315 final verification: focused readiness 34/34, recovery regression 51/51, smoke 1341 passed / 1 skipped, broad 1387 passed / 3 skipped / 24 deselected, Ruff/compile/diff checks green.
- [x] (2026-07-29 16:44Z) Noise audit on checkpoint #89: only 1 of 29 `easy` days crosses the new threshold — the observed Neuromuscular Sprints on 2026-08-03; latest checkpoint remains #89.
- [ ] (2026-07-29) Publish branch and open the linked PR for #315; CI/review and human merge remain outside the implementation milestone.

## Surprises & Discoveries

- Observation: роль сессии не нужно парсить из названий — планировщик уже пишет `session_role` в каждый шаблон.
  Evidence: живой план 2026-07-09: `roles: {'easy': 14, 'recovery': 8, 'long': 4, 'quality': 2}`.
- Observation: верхние поля day template отражают только `sessions[0]`, поэтому role-only проекция может скрыть стоимость второй тренировки того же дня.
  Evidence: `models/training_planner.py::project_day_scalars`; checkpoint #89 на 2026-08-03 содержит day role `easy`, primary `Neuromuscular Sprints`, aggregate TSS 55 и structured maximum fatigue `1/1/3`.
- Observation: существующий Recovery Replan уже умеет безопасно обработать новый тип конфликта без нового mutation path.
  Evidence: живой pure probe для 2026-08-03 построил recommendation `Recovery Spin`, fatigue снизилась `1/1/3 → 1/0/1`, recovery `30 → 12 ч`; checkpoint и provider state не менялись.

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
- Decision: follow-up #315 сохраняет публичную роль structured-сессии, но для severity-матрицы трактует `easy` как quality-like, когда любой fatigue-компонент не меньше 3 или ожидаемое восстановление не меньше 30 часов.
  Rationale: роль описывает место сессии в расписании, а fatigue vector описывает физиологическую цену. Переписывать catalog role означало бы менять генератор; игнорировать уже сохранённую цену означало бы ложно объявлять план безопасным. Порог использует существующие catalog metadata и не добавляет новую модель.
  Date/Author: 2026-07-29 / Codex.
- Decision: bounded lookahead v2 выбирает ближайшую `quality` или structured high-load `easy` сессию, сохраняя старые quality-specific поля и добавляя общие salience-поля.
  Rationale: старые потребители продолжают видеть честные `horizon_extended_for_quality` и `quality_lookahead_session`, а новые могут объяснить расширение из-за fatigue. Семидневный cap и exclusive boundary не меняются.
  Date/Author: 2026-07-29 / Codex.
- Decision: legacy или malformed fatigue/recovery metadata не повышает salience.
  Rationale: отсутствие доказательства стоимости не должно создавать новый false positive; такие планы сохраняют прежнюю role-only матрицу. Это соответствует ASR-REL-2: data gap деградирует безопасно, а не выдумывается.
  Date/Author: 2026-07-29 / Codex.

## Outcomes & Retrospective

(2026-07-09) Все milestone выполнены за одну сессию. Детектор чист от LLM, все пороги — именованные константы, каждый конфликт несёт evidence-числа. Живой прогон на реальной БД показал главный дизайн-инвариант в действии: готовность ready (68.8) × ближайшие easy/recovery/long сессии → `silence: true` с человекочитаемым reason — агент молчит, когда план и состояние согласны. Вне scope остались: варианты перепланирования при конфликте (Issue E), прогноз качества (Issue D), доставка конфликта в web-UI (meta уже содержит отчёт — UI может рендерить без изменений API), учёт `days_until` в severity (решение за контуром). Для WoZ-ритуала отчёт готов как источник строк decision_log: silence/data_gap/конфликт — все три исхода логируемы. Follow-up #152 позже добавил bounded lookahead до ближайшей quality-сессии и canonical readiness projection для Dashboard, не меняя severity-матрицу.

(2026-07-29, follow-up #315) Gate теперь использует сохранённые catalog fatigue/recovery metadata, не меняя генератор и public role. Живой checkpoint #89 перестал давать ложное silence для Neuromuscular Sprints: при hypothetical unchanged readiness `limited` отчёт создаёт medium-конфликт с числами, а существующий Recovery Replan строит component-wise safer downgrade. Noise audit показал один promoted `easy`-день из 29, поэтому bounded policy исправляет наблюдавшийся false silence без широкого роста alert-кандидатов. Локальная реализация завершена: focused 34/34, recovery 51/51, smoke 1341/1, broad 1387/3; остаются публикация, CI/review и human merge.

## Context and Orientation

Репозиторий `ai_trainer/`: SQLite через `data/database.py::Database`, FastAPI в `api/`, модели в `models/`. Ключевые входы детектора:

- Готовность: `models/readiness.py::compute_readiness_today(sleep_df, hrv_df, health_df, training_df, activities_df, *, today, max_value_age_days)` → `{score: float|None, status: unknown/low/limited/ready/strong, confidence: 0..1, drivers: [{key,label,score,evidence}], factors, missing_inputs, tsb}`. «Драйвер» — фактор с наибольшим вкладом в отклонение от нейтрали, несёт evidence-строку с числами.
- План: активный план хранится в planning checkpoint; `api/planning_service.py::get_active_plan(db)` возвращает `goal_plan` со списками `daily_plan` (кортежи `(datetime, total_tss, parts)` по дням) и `session_templates`. Каждый day template содержит верхние поля primary session и `sessions[]` со всеми исполнимыми тренировками дня. Structured session несёт `fatigue_cost` как три числа (metabolic, musculoskeletal, neuromuscular) и `expected_recovery_hours`. `session_role` ∈ {recovery, easy, long, quality}.

Термины. «Salience-gate» — фильтр значимости: конфликт объявляется только когда расхождение превышает пороги матрицы; иначе выход — «молчание» (`silence: true`). «Structured high-load» — сессия с любым fatigue-компонентом ≥3 или ожидаемым восстановлением ≥30 ч. «Горизонт» — сколько дней вперёд смотрим (по умолчанию 3, включая сегодня). «data_gap» — молчание из-за нехватки/несвежести данных, а не из-за отсутствия расхождения.

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

Follow-up #315 — в `models/readiness_conflicts.py` агрегировать structured load по всем mapping-элементам `session_templates[i]["sessions"]`; если их нет, использовать верхние поля legacy/day template. Вектор дня строится component-wise maximum, recovery — maximum. Поля `load_salient` и `salience_source` объясняют, почему обычная role была повышена только для матрицы. `detect_readiness_conflicts` сохраняет `session.role`, но для `easy + load_salient` применяет quality severity и отдельный kind `*_high_load_easy_session`. `resolve_effective_horizon` ищет ближайшую quality или high-load easy session, а API публикует общие salience-lookahead поля рядом с legacy quality-полями.

## Concrete Steps

Рабочая директория — worktree ветки `feat/readiness-conflict-gate`.

    ./ai_trainer_env/bin/python -m pytest tests/smoke/test_readiness_conflicts.py -q
    # до реализации: ошибки импорта; после Milestone 1–3: N passed

    ./ai_trainer_env/bin/python -m pytest tests/smoke -q
    # базлайн на старте: 413 passed

Команды follow-up #315:

    ./ai_trainer_env/bin/python -m pytest tests/smoke/test_readiness_conflicts.py -q
    ./ai_trainer_env/bin/python -m pytest tests/smoke/test_recovery_replan_loop.py tests/smoke/test_recovery_replan_materialization_p1.py -q
    ./ai_trainer_env/bin/python -m pytest tests/smoke -q
    ./ai_trainer_env/bin/python -m pytest -m "not live and not debug" tests/

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

Follow-up #315 добавляет: (6) `limited × easy` остаётся silence для legacy/обычной нагрузки; (7) `limited × easy` с fatigue `1/1/3` или recovery 30 ч даёт medium-конфликт и evidence с числами; (8) multi-session day проецирует component-wise maximum и правильный источник нагрузки; (9) такая сессия на D+4 расширяет bounded horizon до пяти дней; (10) pure-прогон Recovery Replan строит более безопасную материализованную рекомендацию без записи в БД.

Фактическая финальная проверка follow-up #315:

    focused readiness: 34 passed
    recovery regression: 51 passed
    smoke: 1341 passed, 1 skipped
    broad not-live/not-debug: 1387 passed, 3 skipped, 24 deselected
    Ruff, Python compileall, git diff --check: passed
    checkpoint #89 noise audit: 1 / 29 easy days promoted

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

Follow-up #315 добавляет именованные пороги `HIGH_FATIGUE_COMPONENT = 3` и `HIGH_RECOVERY_HOURS = 30`. Элемент `upcoming_plan_sessions` аддитивно несёт `fatigue_cost`, `expected_recovery_hours`, `load_salient` и nullable `salience_source`. `resolve_effective_horizon` возвращает старые `extended_for_quality`/`quality_session` и новые `extended_for_salience`/`salience_session`; policy id — `base_plus_nearest_significant`.

В `api/readiness_conflicts.py`:

    def build_readiness_conflict_report(db: Database, *, horizon_days: int = 3) -> dict: ...

Зависимости: только существующие модули (`models/readiness.py`, `api/planning_service.py`, pandas). Потребитель следующего слоя: контур RecoveryReplanLoop (Issue F) и прогноз качества сессии (Issue D) читают отчёт напрямую — форму `conflicts[*]` не менять без обновления этого плана.

Revision note (2026-07-29 / Codex): документ обновлён для follow-up issue #315 после живой репродукции role-only false silence. Добавлены structured-load contract, RED→GREEN evidence, решения о совместимости, новая bounded lookahead policy, финальные test counts и noise audit.
