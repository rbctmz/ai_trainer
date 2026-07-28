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
   проверяет целостность, публикует snapshot атомарно и создаёт pre-restore
   rollback существующего target. Обычный `cp` main-файла не является
   контрактом: committed страницы могут находиться в `-wal`.
3. Схема эволюционирует аддитивно + migrate-on-read (см. ADR-0006, #206) — без alembic.
4. Данные не покидают машину пользователя — приватность как свойство архитектуры, не политики.

## Consequences

- ✅ Нулевая сетевая latency (ASR-PERF-1), деплой одной командой (ASR-DEP-1), тривиальные копии БД для живой приёмки.
- ✅ Обновление/перенос имеют проверяемый offline backup/restore и
  contributor-safe restore drill (ASR-DEP-2, #293).
- ⚠️ SaaS/мульти-атлет потребует пересмотра (известный блокер service-readiness шага 2); contention при параллельных sync+coach — риск из ATAM-карты, WAL-режим и тесты гонок — открытый долг.
- Переход на Postgres — новый ADR с триггером «больше одного атлета на инсталляцию».
