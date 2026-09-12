# Slice Spec And Review Template — issue #564 (intervention evidence in the conflict text)

Рабочая спецификация по `docs/templates/slice_spec_review_template.md`; связана с
живым ExecPlan `docs/readiness_input_freshness_execplan.md` (раздел
`Follow-up #564`) и не дублирует формат `.agent/PLANS.md`.

- Issue / PR: [#564](https://github.com/rbctmz/ai_trainer/issues/564) (PR: [#569](https://github.com/rbctmz/ai_trainer/pull/569), merged as `43984fa`)
- Author / checker / merge owner: agent (Domain / API Implementer) / независимый checker на PR (`@codex review`) / rbctmz
- Date: 2026-09-12
- Candidate head SHA: `565a6d3` (отревьюенный и смерженный head; merge-коммит `43984fa`, ветка `codex/issue-564-intervention-evidence` удалена после мержа)

## Change Class

- Class: **A**
- Rationale: аддитивное изменение **cross-module public contract** (факторы/драйверы readiness идут в `/api/today`, `web/lib/types.ts` и `tests/contracts/ts_contract.json`) плюс изменение identity evidence: текст конфликта входит в `_fingerprint` и тем самым в ownership-идентичность Recovery Replan (#552/#557).
- Automatic escalation triggers checked:
  - новый cross-module public contract — **да** (аддитивное поле в факторах и драйверах, Python → TS → контрактный артефакт);
  - identity/provenance, ownership, dedup rules — **да** (текст evidence участвует в хеше предложения; меняется то, какие числа описывают интервенционный вход);
  - data migration / schema — нет (колонки и таблицы не меняются);
  - live-provider write, платные вызовы — нет;
  - security/permissions/secrets — нет;
  - irreversible action — нет: откат = revert коммита; деплойное следствие (инвалидация pending-карточек) описано ниже и совпадает по классу с #557.
- Review budget used: 1 / 2 rounds (раунд 1 на `565a6d3d06` — чистый, находок нет)
- Review trigger mode: automatic (`@codex review` на PR)
- Review acceptance head SHA: `565a6d3` (чистый нативный раунд; смержен merge-коммитом `43984fa`)
- Review budget exception: N/A — бюджет не превышен

## Scope

- Behavior that changes: `models/readiness.py` отдаёт аддитивное `intervention_evidence` для каждого фактора — текст, описывающий **ту же серию**, по которой считался `intervention_score_input` (дедуплицированный базлайн), а при отсутствии дедупликации — равный описательному `evidence`. `models/readiness_conflicts.py::_readiness_evidence` цитирует `intervention_evidence` и перестаёт дублировать лейбл фактора (`HRV: HRV …` → `HRV …`). Описательный канал (`score`/`baseline`/`deviation`/`evidence`) остаётся байт-идентичным.
- Files/modules in scope:
  - `models/readiness.py` (`_deviation_factor`, нормализация факторов);
  - `models/readiness_conflicts.py` (`_readiness_evidence`, склейка лейбла);
  - `web/lib/types.ts` (`ReadinessSnapshotFactor`, `TodayReadinessDriver`);
  - `tests/contracts/ts_contract.json` (регенерация `contract:extract`);
  - `tests/smoke/test_readiness_model.py`, `tests/smoke/test_readiness_conflicts.py`;
  - `docs/issue_564_intervention_evidence_slice_spec.md` (этот файл), `docs/readiness_input_freshness_execplan.md`.

## Non-goals

- Behavior deliberately unchanged: пороги, `FACTOR_WEIGHTS`, базлайны, матрица severity; правила дедупликации (меняется только их *описание* в тексте); описательный канал и его байт-идентичность; `_fingerprint`-состав; UI-разметка `/today` (страница рендерит те же строки, что и раньше); схема БД и миграции; `asr_catalog.md` не переписывается (строка ASR-REL-2 уже покрывает честность evidence).
- Deferred work and owner: любые изменения формата лейблов/локализации текста evidence — вне scope; `#567` (guard отката readiness) уже закрыт и не пересматривается.

## Definition of Done

- [x] Acceptance criteria наблюдаемы (см. RED Matrix).
- [x] Required tests/checks названы и пройдены: focused readiness/конфликты/коуч — `432 passed`; широкий Python-контур — CI `2472 passed, 27 skipped, 26 deselected`, локально в worktree с `node_modules` — `2494 passed, 5 skipped`; `ruff` чисто; web `lint`/`build`/`contract:extract -- --check` зелёные.
- [x] Merge and cleanup owner назначен: rbctmz (мерж — отдельное действие владельца; после мержа — удаление ветки/worktree).

## Public Contracts

- `models/readiness.py::compute_readiness_today` → факторы и драйверы — **changed compatibly**: добавлено `intervention_evidence: str` (в факторах всегда присутствует; в драйверах — как есть). Тесты: `test_readiness_model.py` (дедуп-фикстура и полный набор), контрактный drift-тест.
- `GET /api/today` (проекция `_project_readiness` передаёт `drivers`/`factors` как есть) — **changed compatibly**: поле появляется в payload без изменения существующих.
- `web/lib/types.ts` — **changed compatibly**: `intervention_evidence?: string | null` в `ReadinessSnapshotFactor` и `TodayReadinessDriver`; артефакт `tests/contracts/ts_contract.json` перегенерирован (`contract:extract`), CI-гейт `contract:extract -- --check` проверяет свежесть.
- `models/readiness_conflicts.py::detect_readiness_conflicts` → `conflicts[].evidence` — **changed compatibly по контракту, изменилось содержимое строки**: текст описывает интервенционную серию и не дублирует лейбл. Следствие: `_fingerprint` изменится для тех же входных данных.
- DB schema, `api/`-схемы, event/CLI/конфигурация — unchanged.

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result: если у фактора нет `intervention_evidence` (legacy-payload, синтетические фикстуры), `_readiness_evidence` откатывается на `evidence`; отсутствие дедупликации даёт `intervention_evidence == evidence`, то есть прежний текст.
- Retry/idempotency key: генерация evidence детерминирована входами; повторный прогон даёт тот же текст и тот же `_fingerprint`.
- Rollback procedure and proof: revert коммита возвращает прежний текст и прежний `_fingerprint`; данные не мигрируют, `recovery_decisions`/`coach_proposals` не переписываются.
- Деплойное следствие (тот же класс, что в #557): смена текста меняет fingerprint, поэтому первая полная оценка после выката инвалидирует ранее pending-карточки (`superseded_by_newer_recovery_evidence`); аудит сохраняется, ручные confirm/rollback не затрагиваются.
- [x] Does this add **new persistent state**? Нет.
- [x] Does **full reset** remove every row/artifact/cursor introduced here? N/A — новых артефактов нет.
- [x] Restart and partial-failure recovery are covered: изменение чисто вычислительное, состояние не пишется.

## State Boundaries and Identity

- Source of truth and owner: серии наблюдений и их дедупликация — `models/readiness.py` (интервенционный канал); текст evidence конфликта — `models/readiness_conflicts.py`.
- Stable identity/provenance keys: `_fingerprint` (включает `conflicts[].evidence`) + `rule_version` + evidence head (#552/#557). Новый текст = новая identity для тех же входов, что и приводит к ожидаемой инвалидации pending-карточек при выкате.
- Cursor/checkpoint lifecycle: не затрагивается.
- Concurrency and stale-write behavior: не применимо (чистое чтение/вычисление).

## Evidence Boundary Matrix

| Identity | Time/provenance | Evidence state | Fallback | Expected result / falsifier |
| --- | --- | --- | --- | --- |
| дубликаты в серии наблюдений | today | present | intervention text | текст цитирует дедуплицированный базлайн (`−12.5%`), не legacy (`−5.9%`); falsifier: в тексте legacy-число |
| без дубликатов | today | present | legacy text | `intervention_evidence == evidence` |
| дубликаты есть, но дедуплицированного базлайна мало | today | partial | legacy text | `intervention_score_input == score`, текст остаётся описательным |
| фактор-производное состояние (TSB) | today | present | legacy text | `intervention_evidence == evidence` |
| не-девиационные измерения (сон, readiness) | today | present | legacy text | `intervention_evidence == evidence` |
| legacy/синтетический payload без нового поля | any | partial | `evidence` | рендер не падает и цитирует `evidence` |
| не пригодный к интервенции фактор | outdated/unverified | present | excluded | в тексте его нет (регрессия #557 сохраняется) |

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| Текст интервенционного канала описывает дедуплицированную серию | `test_intervention_evidence_describes_the_deduplicated_series` | `KeyError: 'intervention_evidence'` | `против базовых 45.7 (−12.5%)` при `intervention_score_input == 40.0`, legacy `evidence` не изменился |
| Без дубликатов интервенционный текст равен описательному | `test_intervention_evidence_defaults_to_the_descriptive_text` | `KeyError` | равенство по всем факторам |
| Мало данных после дедупликации — текст остаётся описательным | `test_intervention_evidence_keeps_the_descriptive_text_without_a_dedup_baseline` | `KeyError` | `intervention_score_input == score`, тексты равны |
| Драйверы несут новое поле | `test_driver_payload_carries_intervention_evidence` | `KeyError`/`None` | поле присутствует и равно факторному |
| Конфликт цитирует интервенционную серию | `test_conflict_evidence_quotes_the_intervention_series` | текст содержит `−5.9%` из описательного канала | текст содержит `−12.5%`, legacy-числа нет |
| Лейбл не дублируется | `test_conflict_evidence_does_not_duplicate_the_factor_label` | `HRV: HRV …`, `Сон: Сон …` | `HRV …`, `Сон …` |
| Непригодный фактор по-прежнему не цитируется | существующий `test_conflict_evidence_describes_only_intervention_eligible_factors` | уже зелёный (regression) | зелёный после изменения |

## ASR / ADR Traceability

- ASRs affected: ASR-REL-2 (аудит объясняет то решение, которое реально принято; непригодные факторы не цитируются), ASR-MOD-2 (Python-проекция владеет текстом, React только рендерит).
- ADRs reused: ADR-0008 (provenance ingest) — переиспользуется; новый ADR не требуется, новая архитектурная граница не появляется (поле аддитивно).
- Tactic and trade-off: единый источник текста на сервере, интервенционный канал получает собственное описание. Плата — изменение fingerprint при выкате (ожидаемая инвалидация pending-карточек, как в #557).
- New architecture boundary discovered during review: нет на момент написания.

## Delivery Slices

1. Slice: «текст конфликта описывает интервенционную серию» (#564).
   - RED: тесты в `tests/smoke/test_readiness_model.py` и `tests/smoke/test_readiness_conflicts.py`; ожидаемые падения — отсутствие поля и legacy-число в тексте.
   - GREEN: поле в модели + предпочтение в `_readiness_evidence` + склейка лейбла без дублирования.
   - Refactor/contract refresh: `web/lib/types.ts` + `contract:extract` (артефакт), затем `lint`/`build`/`contract:extract -- --check`.
   - Verification: focused readiness/конфликты/коуч/приёмка, широкий Python-контур, `ruff`, web-проверки.

## Evidence Bundle

- Head SHA: `565a6d3` (merge-коммит `43984fa`; в main попало ровно отревьюенное дерево — `git diff 565a6d3 43984fa` пуст)
- Changed invariants: текст evidence интервенционного канала описывает ту же серию, что и `intervention_score_input`; описательный канал байт-идентичен.
- RED: 7 падений — 4 модельных на отсутствии `intervention_evidence` (`KeyError`), 2 потребительских на цитировании описательного числа и дублировании лейбла, 1 сквозной. Characterization-тест фолбэка на legacy-payload был зелёным до изменения и остался зелёным.
- GREEN: `test_readiness_model.py` + `test_readiness_conflicts.py` — `71 passed`; focused-контур (readiness/конфликты/снапшот/приёмка/версия evidence/loop/today/коуч/briefing/дрейф контракта/экстрактор/инвентарь/UI-контракт/purity/response) — `432 passed`; `ruff check .` чисто; web `lint` — без предупреждений, `build` — успешно, `contract:extract -- --check` — артефакт актуален.
- Broad Python contour: см. запись `Change log` ExecPlan (contributor-safe прогон).
- Lifecycle/probe evidence: один и тот же probe на двух деревьях (`origin/main` и ветка) на фикстуре с дубликатами. **Было:** `Готовность 57.5/100 (limited): HRV: HRV 40.0 мс против базовых 42.5 (−5.9%); Сон: Сон: оценка 30/100 …; Пульс покоя: Пульс покоя 70.0 …`. **Стало:** `Готовность 57.5/100 (limited): HRV 40.0 мс против базовых 45.7 (−12.5%); Сон: оценка 30/100 …; Пульс покоя 70.0 уд/мин …` при том же входе гейта `intervention_score_input = 40.0`. Паритет описательного канала: 4 фикстуры, `score`/`status`/`confidence`/`as_of_date`/`intervention_score` и строки `evidence`/`baseline`/`deviation` — **0 различий** с `origin/main`.
- Changed contracts: аддитивное поле в факторах/драйверах + регенерированный `ts_contract.json` (37 добавленных строк).
- Unresolved review-thread count: 0 (раунд 1 находок не дал, незакрытых тредов нет).
- Residual risks and follow-ups: изменение fingerprint → инвалидация pending-карточек при выкате (задокументировано, класс #557).

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| — | Независимый checker (раунд 1, `565a6d3d06`) находок не дал: `Didn't find any major issues` | — | closed |

## Native Review Rounds

| Round | Reviewed head SHA | Trigger | Findings disposition | Stop / exception decision |
| ---: | --- | --- | --- | --- |
| 1 | `565a6d3d06` | automatic (`@codex review`) | находок нет (`Didn't find any major issues`) | stop: раунд чистый, бюджет 1/2 |
| 2 | — | verification | — | — |

## Final Verdict

- Verdict: READY — раунд пройден и изменение смержено (`43984fa`)
- Blocking findings remaining: нет; описательный канал доказанно байт-идентичен (паритет-проба против `origin/main`, 0 различий на 4 фикстурах)
- Review rounds used: 1 / 2
- Accepted risk or follow-up issue: follow-up не требуется; инвалидация pending-карточек при выкате — ожидаемое следствие, не риск
- Merge owner final gate: rbctmz — acceptance выставлен, PR смержен 2026-09-12
- Post-merge sync/branch/worktree/progress cleanup: выполнено — ветка `codex/issue-564-intervention-evidence` и worktree удалены, позиция Progress закрыта, запись Class A внесена в `docs/engineering_process_metrics.md`
