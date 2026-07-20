# ADR 0003: Канонический readiness/signals snapshot

- Status: Accepted (закрепляет #139/#152/#153)
- Date: 2026-07-20
- Related: `models/readiness.py::compute_readiness_today`, `models/dashboard_summary.py::project_readiness_snapshot`, ASR-MOD-2

## Context

До #139 fusion готовности существовал дважды с противоречащей семантикой; дашборд считал метрики на своём окне и расходился с каноном (класс багов #134: «одна метрика — разные окна» всплывает на каждой поверхности отдельно).

## Decision

1. `compute_readiness_today` — ЕДИНСТВЕННАЯ точка fusion (HRV/RHR/сон/Garmin readiness/TSB, веса и пороги в одном месте).
2. Каждая поверхность (dashboard, /today, коуч-meta, гейт конфликтов) ПРОЕЦИРУЕТ канонический snapshot с provenance (`readiness_source: canonical_snapshot`), а не пересчитывает.
3. Новая поверхность обязана на ревью показать, что читает snapshot, — это пункт чек-листа, рождённый уроком #152/#153.

## Consequences

- ✅ Trust gap между поверхностями закрыт классом; изменение формулы — одна правка.
- ⚠️ Snapshot — точка сцепления: его контракт меняется только аддитивно.
