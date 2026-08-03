# Реестр технического долга AI Trainer

- **Статус:** Current
- **Снимок:** 2026-07-28
- **Владелец процесса:** issue-first цикл из
  [`loop_engineering_instruction.md`](loop_engineering_instruction.md)

Это единая точка истины для подтверждённого открытого технического долга.
Исторические аудиты и ExecPlan могут объяснять происхождение пункта, но не
являются параллельными backlog. Перед добавлением долг проверяется по текущему
дереву.

## Правила

- `P0` — риск потери/раскрытия данных или блокирующий production-дефект;
  исправляется немедленно.
- `P1` — высокий риск надёжности, безопасности или эксплуатации; следующий
  hardening-трек.
- `P2` — ограничивает модифицируемость или качество, но имеет рабочий обход.
- `P3` — наблюдение; выполнять только при доказанном пользовательском эффекте.
- Один пункт получает один стабильный `TD-XXX` и проверяемый критерий закрытия.
- Пока пункт не запланирован, владельцем backlog служит этот реестр. Перед
  переводом в работу для пункта создаётся один owner-issue; его ссылка
  добавляется в соответствующий `TD-XXX`, а выполнение идёт по issue-first
  циклу.
- Закрытые пункты перемещаются в журнал ниже; ID не переиспользуются.

## Сводка

| ID | Приоритет | Область | Риск | Следующее действие |
|----|-----------|---------|------|--------------------|
| TD-006 | P2 | Structure | Крупные модули концентрируют churn | Churn-first decomposition |
| TD-008 | P2 | Security | Отозванное значение остаётся в Git history | Решение: rewrite или accepted residual risk |

На дату снимка подтверждённых `P0` нет. Это не означает отсутствие дефектов:
реестр описывает известный долг, а не заменяет issue/bug triage.

## Подтверждённые пункты

### TD-003 — Единая SQLite concurrency policy

- **ASR:** ASR-REL-3, ASR-DEP-2
- **Evidence:** `data/database.py` открывает много независимых
  `sqlite3.connect(...)`; отдельные записи имеют `busy_timeout`, но общей
  journal/WAL/retry policy и race-гейта `sync + coach/planning read` нет.
- **Риск:** конкурирующие job могут получить lock contention или
  недетерминированную деградацию.
- **Граница решения:** сначала измерить contention на временной БД, затем
  зафиксировать connection factory, journal mode и bounded retry. Не менять
  single-user SQLite решение без нового ADR.
- **Закрытие:** race test доказывает отсутствие потери данных и bounded latency
  для согласованного сценария.

### TD-004 — Streamlit EOL / parity

- **ASR:** ASR-MOD-2
- **Evidence:** ADR-0001 оставляет Streamlit maintenance-only до выполнения трёх
  EOL-критериев; `app.py`, `ui/` и `state/manager.py` всё ещё поддерживаются.
- **Риск:** исправления и тексты расходятся между web/API и legacy surface.
- **Граница решения:** инвентаризация оставшихся Streamlit-only пользовательских
  потоков, перенос acceptance runtime либо зафиксированное исключение.
- **Закрытие:** выполнены критерии ADR-0001, удаление/изоляция legacy surface
  оформлены отдельным ExecPlan.

### TD-005 — Отложенные compatibility-срезы M1

- **ASR:** ASR-MOD-3, ASR-PERF-3
- **Evidence:** Outcomes Intervals-primary ExecPlan сознательно отложили:
  локальный пересчёт TSS по потокам Intervals (D2), перевод Garmin на общую
  cursor-таблицу (D3), удаление deprecated `Database.sync_activities` shim (D4).
  Метод `sync_activities` и его тестовые callers остаются в дереве.
- **Риск:** две семантики TSS/окон и legacy write path увеличивают стоимость
  следующих изменений ingest.
- **Граница решения:** три отдельных RED→GREEN issue, не один большой refactor;
  Garmin compatibility и provider-link invariants обязательны.
- **Закрытие:** D2, D3 и D4 закрыты отдельными merge evidence; shim не имеет
  production/test callers.

### TD-006 — Структурные hotspots

- **ASR:** ASR-MOD-1, ASR-MOD-2, ASR-MOD-3
- **Evidence (2026-07-28):** `data/database.py` — 4269 строк,
  `ui/pages/planning.py` — 3340, `models/training_planner.py` — 2413,
  `models/ai_tools.py` — 2006. Размер сам по себе не дефект, но эти файлы
  концентрируют разные причины изменения.
- **Риск:** широкие diff, конфликтующие изменения агентов и дорогой review.
- **Граница решения:** декомпозировать только по подтверждённому churn и
  существующим contract tests; запрет на «разбить файл ради размера».
- **Закрытие:** для выбранного hotspot issue показывает baseline churn/import
  graph, сохраняет публичные контракты и уменьшает связанность измеримым образом.

### TD-007 — Детерминированный latency-гейт коуча

- **ASR:** ASR-PERF-2
- **Evidence:** SSE `done` возвращает `first_token_ms`, smoke проверяет наличие и
  неотрицательность, но порог 5 секунд остаётся наблюдением.
- **Риск:** latency может деградировать без сигнала CI.
- **Граница решения:** гейтить только контролируемый локальный runtime с mock
  tools/provider; live provider SLA остаётся наблюдаемой метрикой.
- **Закрытие:** детерминированный тест ловит регрессию внутреннего overhead и не
  зависит от внешней сети.

### TD-008 — Политика для отозванного credential в Git history

- **ASR:** ASR-SEC-1
- **Evidence:** full-history audit в #296 обнаружил password-shaped candidate.
  Credential ротирован, текущие archived-копии удалены, event-range и
  current-tree Gitleaks проходят, но старые commits остаются доступными.
- **Риск:** значение больше не даёт доступ, однако история репозитория хранит
  credential-shaped material и не удовлетворяет буквальному «ключи не в git».
- **Граница решения:** отдельный issue сначала сравнивает documented acceptance
  отозванного значения с coordinated history rewrite. Rewrite обязан учитывать
  branches/tags, открытые PR, clones, GitHub caches и повторный full-history
  audit; выполнять его без плана миграции запрещено.
- **Закрытие:** либо validated history rewrite + чистый full-history scan, либо
  явное решение о принятом residual risk с evidence ротации и сроком повторного
  пересмотра.

## Не переносить автоматически

Следующие источники являются входом для повторной проверки, а не открытым
backlog:

- [`architecture/architecture_analysis_add3.md`](architecture/architecture_analysis_add3.md)
  — снимок 2026-07-15; ряд рисков уже закрыт M0–M5 и API contract tests.
- [`code_review_recommendations.md`](code_review_recommendations.md) — аудит с
  привязанными к baseline line numbers; чекбокс не доказывает текущий дефект.
- completed ExecPlans — историческое evidence и явно отложенные решения.

## Журнал закрытия

| ID | Дата | Результат |
|----|------|-----------|
| TD-001 | 2026-07-28 | [#293](https://github.com/rbctmz/ai_trainer/issues/293): stopped-service SQLite Backup API CLI, integrity check, atomic no-clobber backup, sidecar-safe restore, pre-restore rollback и clean-volume domain drill |
| TD-002 | 2026-07-28 | [#295](https://github.com/rbctmz/ai_trainer/issues/295) / [#296](https://github.com/rbctmz/ai_trainer/pull/296): contributor-safe Gitleaks на event range + current tree, immutable pins, runtime synthetic gate, 4 verified exact-fingerprint false positive, ротация и удаление current-tree credential copies; residual history-risk перенесён в TD-008 |
| TD-003 | 2026-08-03 | [#347](https://github.com/rbctmz/ai_trainer/issues/347) / [#348](https://github.com/rbctmz/ai_trainer/pull/348): единый `Database._connect()` (timeout=30, busy_timeout=30000, journal_mode=WAL), все call sites через factory, race writer+reader гейт без потери данных и с bounded latency; smoke 1439 passed |
| TD-004 | 2026-08-03 | Аудит критериев EOL (ADR-0001): (a) acceptance-runtime формально признан dev-инструментом; (b) не выполнен — правки ui/pages до 2026-08-01; (c) не выполнен — встроенные агрегаты в dashboard/hrv/activities/sleep. Решение: maintenance-only, EOL/удаление не назначаются. Док: docs/streamlit_eol_assessment.md; follow-up по (c) — [#349](https://github.com/rbctmz/ai_trainer/issues/349) |
| TD-007 | 2026-08-03 | [#352](https://github.com/rbctmz/ai_trainer/issues/352): детерминированный first-token гейт на локальном mock-runtime (`COACH_FIRST_TOKEN_BUDGET_MS=5000`), live-метрика остаётся наблюдаемой; smoke 1446 passed |
| TD-005 | 2026-08-03 | D4 [#354](https://github.com/rbctmz/ai_trainer/issues/354) (shim `sync_activities` удалён, тесты — через oracle `tests/sync_fixtures.py`), D3 [#355](https://github.com/rbctmz/ai_trainer/issues/355) (окно Garmin-активностей через общую cursor-таблицу, advance только после чистого прогона), D2 [#356](https://github.com/rbctmz/ai_trainer/issues/356) (аудит local-first TSS: контракт пары `tss`+`tss_method` закреплён тестом, ложные формулировки в методологии/ADR-0008 исправлены, потоковый пересчёт — осознанный non-goal) |
