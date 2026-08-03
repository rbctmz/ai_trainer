# Закрыть TD-003: единая SQLite concurrency policy (WAL + bounded retry + race gate)

Живой документ по `.agent/PLANS.md`. Самодостаточен: новый исполнитель может
продолжить, имея только дерево репозитория и этот файл.

## Purpose / Big Picture

`data/database.py` открывает ~20 независимых `sqlite3.connect(...)` с разной
конфигурацией: часть без `busy_timeout`, часть с `timeout=30` +
`busy_timeout=30000`. Нет общей journal/WAL-политики и race-гейта
«пишущий sync + читающие coach/planning». После TD-003 любое соединение идёт
через единый factory с WAL и bounded busy-wait, а регрессионный race-тест
доказывает отсутствие потери данных и ограниченную задержку на временной БД.

## Progress

- [x] (2026-08-03) Аудит `data/database.py`: 20+ bare `sqlite3.connect`, два
      «хороших» места с `timeout=30`/`busy_timeout=30000`, WAL нигде не включён.
- [x] (2026-08-03) RED-гейты: WAL включён, busy_timeout единый, race writer+reader без потерь (4 гейта).
- [x] (2026-08-03) Реализация `Database._connect()` + замена 71 call site (bare и timeout-варианты).
- [x] (2026-08-03) Доки: debt register TD-003 → журнал закрытых, ASR-REL-3 evidence.
- [x] (2026-08-03) Проверки: focused 4 passed, smoke 1439 passed, ruff/diff-check зелёные.

## Surprises & Discoveries

- Observation: у TD-001 restore уже есть sidecar-safe логика (`-wal`/`-shm`
  quarantine), поэтому переход на WAL не ломает backup/restore — sidecar-ы
  обрабатываются штатно.
  Evidence: `docs/td_001_sqlite_backup_restore_execplan.md` (sidecar quarantine).
- Observation: миграция схемы уже учитывает конкурентную инициализацию двух
  процессов («duplicate column name» — idempotent), значит WAL/retry не меняет
  семантику миграции.
  Evidence: `data/database.py` (`ALTER TABLE ... duplicate column name`).

## Decision Log

- Decision: единый factory `Database._connect()` — `timeout=30`,
  `PRAGMA busy_timeout=30000`, `PRAGMA journal_mode=WAL`; все call sites идут
  через него.
  Rationale: busy_timeout — bounded retry, WAL даёт читателям согласованный
  snapshot без блокировки писателя; одна точка настройки вместо разнобоя.
  Date/Author: 2026-08-03 / Codex.
- Decision: замена всех bare-connect, включая read-only introspection.
  Rationale: одна политика без исключений; WAL на чтении безопасен.
  Date/Author: 2026-08-03 / Codex.
- Decision: race-гейт — writer-поток (N вставок с commit) + reader-поток
  (повторные чтения) на временной БД; assert полной видимости и bounded
  wall-time.
  Rationale: закрытие TD-003 требует «отсутствие потери данных и bounded
  latency для согласованного сценария» (реестр долга).
  Date/Author: 2026-08-03 / Codex.

## Outcomes & Retrospective

Не завершено (в процессе).

## Context and Orientation

`data/database.py` — единственный data-слой: публичный класс `Database`,
конструктор вызывает `init_tables()`. Соединения открываются прямо внутри
методов. `config/settings.py` задаёт `DATABASE_PATH`. Ожидаемый объём:
один factory-метод, механическая замена вызовов, новый smoke-тест, правки
`docs/technical_debt_register.md` и `docs/architecture/asr_catalog.md`.

## Plan of Work

1. `tests/smoke/test_sqlite_concurrency_policy.py`:
   - `PRAGMA journal_mode` == `wal` после `Database(tmp)` и после
     `db._connect()`;
   - `PRAGMA busy_timeout` == `30000` на factory-соединении;
   - race-гейт: writer вставляет 200 активностей с коммитом, reader читает
     счётчик в цикле; после join — 200 строк, wall-time < 60 c.
2. `data/database.py`: добавить `_connect()`; заменить все
   `sqlite3.connect(self.db_path)` и «хорошие» места с timeout/busy_timeout на
   `self._connect()` (row_factory остаётся у вызывающих).
3. Доки: реестр долга TD-003 → журнал закрытых с evidence; asr_catalog —
   ASR-REL-3/ASR-DEP-2 ссылка на race-гейт.

## Concrete Steps

    source ai_trainer_env/bin/activate
    python -m pytest tests/smoke/test_sqlite_concurrency_policy.py -q
    python -m pytest tests/smoke -q
    git diff --check

## Validation and Acceptance

Полный smoke зелёный; race-гейт доказывает отсутствие потери данных при
параллельной записи/чтении и bounded latency; `PRAGMA journal_mode` = `wal`;
CI на PR показывает ready-to-merge; после мержа TD-003 закрывается в реестре.

## Idempotence and Recovery

WAL включается идемпотентно (персистится в файле БД). Повторные прогоны
безопасны; откат = вернуть bare-connect. Взаимодействие с TD-001 (sidecar
quarantine) уже учтено.

## Interfaces and Dependencies

В `data/database.py`:

    def _connect(self) -> sqlite3.Connection:
        """Единая SQLite concurrency policy (TD-003): timeout=30,
        busy_timeout=30000, journal_mode=WAL."""
        ...

Без third-party зависимостей. `sqlite_backup_restore.py` не меняется.
