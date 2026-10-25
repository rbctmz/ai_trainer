# ADR 0002: SQLite как primary store

- Status: Accepted (записан задним числом, решение действует с начала проекта)
- Date: 2026-07-20
- Related: `data/database.py`, `docker-compose.yml`,
  `scripts/sqlite_backup_restore.py`, ASR-PERF-1, ASR-DEP-1/2, #293

## Context

Все данные атлета (активности, health-сигналы, чекпойнты плана, журналы решений) живут в одном локальном SQLite-файле. Альтернатива — Postgres — дала бы конкурентную запись, миграции и сетевой доступ, но потребовала бы отдельный сервис.

## Decision

SQLite остаётся primary store, пока продукт — single-athlete инсталляция (локальная или self-hosted). Границы решения:

1. Один пользователь-писатель; конкурентность ограничена «sync + чтение», не «много писателей».
2. Файл в named volume; backup/restore выполняется при остановленном сервисе
   через `scripts/sqlite_backup_restore.py`. CLI использует SQLite Backup API,
   проверяет целостность, публикует новый snapshot atomic no-clobber операцией,
   карантинирует sidecars до atomic restore и создаёт pre-restore rollback
   существующего target. Обычный `cp` main-файла не является контрактом:
   committed страницы могут находиться в `-wal`.
3. Схема эволюционирует аддитивно + migrate-on-read (см. ADR-0006, #206) — без alembic.
4. Данные не покидают машину пользователя — приватность как свойство архитектуры, не политики.

## Consequences

- ✅ Нулевая сетевая latency (ASR-PERF-1), деплой одной командой (ASR-DEP-1), тривиальные копии БД для живой приёмки.
- ✅ Обновление/перенос имеют проверяемый offline backup/restore и
  contributor-safe restore drill (ASR-DEP-2, #293).
- ⚠️ SaaS/мульти-атлет потребует пересмотра (известный блокер service-readiness шага 2); contention при параллельных sync+coach — риск из ATAM-карты, WAL-режим и тесты гонок — открытый долг.
- Переход на Postgres — новый ADR с триггером «больше одного атлета на инсталляцию».


## Bare-metal runtime path and offline relocation (#624, M1–M2)

Принятая спецификация #724 (merge `276eec6`) уточняет размещение bare-metal
store без смены SQLite ownership/concurrency. M1 (#726, merge 89fa21a) использует OS data
directory (macOS Application Support, Linux XDG data home, Windows LocalAppData),
сохраняет явный DATABASE_PATH и Docker `/data/ai_trainer.db`. Import Settings
только разрешает путь; default opening/API startup выполняют legacy preflight.
Обнаружение отдельного старого store отказывает до создания нового; исходник
не переносится. Explicit Database(path) не получает глобального guard в _connect.
M2 добавляет явный offline migrate к существующему backup/restore CLI:
read-only plan, WAL-aware rollback, полная logical/schema verification и atomic
no-clobber target. Успех — copied_not_activated; source/config не меняются.
Это candidate implementation с synthetic tests, не live relocation acceptance.
Activation/restart/reset/post-write rollback drill остаётся M3. Новых схем,
selector/receipt или backup engines нет; operator quiescence обязательна.
