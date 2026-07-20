# ADR 0006: Append-only версии плана

- Status: Accepted (записан задним числом; закреплён контурными треками #154/#209)
- Date: 2026-07-20
- Related: `models/planning_checkpoints.py`, `planning_checkpoints` таблица, ASR-REL-1, ASR-MOD-3

## Context

План эволюционирует: build → adjustment → recovery-replan → rollback. Мутация «текущей строки» стирала бы историю, ломала evidence-first сверку план/факт и делала откат небезопасным.

## Decision

1. Каждый применённый вариант — НОВЫЙ чекпойнт с `parent_checkpoint_id` и `source`; строки никогда не переписываются.
2. Rollback — тоже append (restored revision), не удаление.
3. Применение — fail-closed по точному `base_checkpoint_id` (stale → ошибка без мутации).
4. Совместимость схемы: новые поля аддитивны, старые чекпойнты восстанавливаются migrate-on-read (#206) байт-стабильно.

## Consequences

- ✅ Полный аудит-трейл решений; reconciliation и identity-lineage (#209) опираются на неизменность истории; живая приёмка — на копии файла БД.
- ⚠️ Рост объёма — приемлем для single-athlete SQLite (ADR-0002); компакция — отдельное решение, если понадобится.
