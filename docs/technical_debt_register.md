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
- Один пункт получает один стабильный `TD-XXX`, owner-issue и проверяемый
  критерий закрытия.
- Закрытые пункты перемещаются в журнал ниже; ID не переиспользуются.

## Сводка

| ID | Приоритет | Область | Риск | Следующее действие |
|----|-----------|---------|------|--------------------|
| TD-001 | P1 | Deployability | Нет проверенного восстановления SQLite | Backup/restore CLI + restore drill |
| TD-002 | P1 | Security | Секреты проверяются только ревью | Secret scan в CI |
| TD-003 | P1 | Reliability | Нет единой SQLite concurrency policy | WAL/retry contract + race gates |
| TD-004 | P1 | Modifiability | Две UI-поверхности продолжают расходиться | Закрыть критерии Streamlit EOL |
| TD-005 | P2 | Data/ingest | В M1 оставлены три compatibility-среза | Разделить и закрыть D2–D4 |
| TD-006 | P2 | Structure | Крупные модули концентрируют churn | Churn-first decomposition |
| TD-007 | P2 | Performance | First-token измеряется, но SLA не гейтится | Детерминированный runtime gate |

На дату снимка подтверждённых `P0` нет. Это не означает отсутствие дефектов:
реестр описывает известный долг, а не заменяет issue/bug triage.

## Подтверждённые пункты

### TD-001 — SQLite backup/restore

- **ASR:** ASR-DEP-2, ASR-REL-3
- **Evidence:** SQLite находится в named volume, но в `scripts/` нет
  backup/restore-команд и автоматического restore drill.
- **Риск:** ошибка оператора, повреждение volume или неудачное обновление могут
  превратить логическую сохранность данных в невосстановимую.
- **Граница решения:** согласованный snapshot/restore для остановленного сервиса,
  проверка целостности и documented rollback; без перехода на Postgres.
- **Закрытие:** временная БД восстанавливается из backup в чистый volume, smoke
  читает канонические активности, provider-links, план и wellness.

### TD-002 — Secret scan в CI

- **ASR:** ASR-SEC-1
- **Evidence:** `.env` исключён из git и ключи не возвращаются API, но workflows
  не запускают gitleaks, detect-secrets или эквивалент.
- **Риск:** случайно добавленный токен обнаружится только на ревью.
- **Граница решения:** contributor-safe scanner без передачи application
  secrets в untrusted PR; baseline допускает только проверенные false positive.
- **Закрытие:** CI блокирует синтетический секрет и проходит на текущем дереве.

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
| — | — | Реестр создан; закрытые исторические находки не переименовывались в TD |
