# Slice Spec — Issue #608: безопасная семантика нагрузки (ACWR без предсказания травмы)

Class A по шаблону `docs/templates/slice_spec_review_template.md`.

- Issue / PR: #608 / #620
- Author / checker / merge owner: Domain / API Implementer (DSH) / независимый checker — TBD / human merge owner (rbctmz)
- Date: 2026-09-20
- Candidate head SHA: `b035da5` + финальный prep-коммит (уточняется перед review)
- Parent: #607 (Daily decision loop v1), слайс 1
- ExecPlan: `docs/daily_decision_loop_execplan.md` (в `main`, коммит `0da0017`)

## Change Class

- Class: **A — Full** (как назначено в #608).
- Rationale: меняется публичный словарь доменного сигнала и его семантика
  безопасности. Затрагивает Python-домен, runtime DTO API и пользовательские
  подписи; требует явного плана совместимости, потому что провайдер присылает
  значения прежнего словаря.
- Automatic escalation triggers checked: новый cross-module public contract — да
  (замена публичного enum), поэтому Class A. Миграции и persistence — нет.
  Live-provider write — нет. Security — нет.
- Review budget used: 0 / 2 rounds
- Review trigger mode: manual
- Review acceptance head SHA: TBD
- Review budget exception: N/A

## Scope

### Проблема (Observed)

`models/acwr.py` отдавал статус из риск-словаря и подписывал его риск-языком:
`safe` / `optimal` / `moderate_risk` / `high_risk` с подписями «Недостаточная
нагрузка», «Оптимальная зона», «Умеренный риск», «Высокий риск». Отношение острой
нагрузки к хронической само по себе **не устанавливает вероятность травмы**, поэтому
«Умеренный риск» и «Высокий риск» — утверждение, которого данные не поддерживают, а
`safe` в обратную сторону объявляет низкое отношение безопасным, хотя это лишь ниже
обычной базы атлета.

### Behavior that changes

Шкала заменяется на описательную относительно базы атлета:

| Старое | Новое | Подпись | Почему |
| --- | --- | --- | --- |
| `safe` | `below_baseline` | «Ниже обычной базы» | не доказательство недотренированности |
| `optimal` | `expected_band` | «В пределах обычного» | диапазон, а не оптимум здоровья |
| `moderate_risk` | `elevated` | «Повышенная нагрузка» | отношение, а не риск |
| `high_risk` | `strongly_elevated` | «Значительно выше базы» | не вероятность травмы |

Тоны (`neutral` / `success` / `warning` / `danger`) сохраняются: это визуальный вес,
а не утверждение о здоровье. Пороги `0.8` / `1.3` / `1.5` и математика EWMA **не
меняются**. Переименованы также идентификаторы порогов, чтобы вне шима
совместимости в модуле не оставалось риск-лексики.

Сигнал получает шесть новых полей: `acute_tau_days` (7), `chronic_tau_days` (42),
`calculation_version`, `semantics_version`, `limitation`, `intervention_eligible`.

### Files/modules in scope

- `models/acwr.py` — шкала, шим совместимости, поля сигнала;
- `tests/smoke/test_acwr_semantics.py` — новый контракт (RED→GREEN);
- `tests/smoke/test_acwr.py` — перевод ожиданий на новую шкалу, числа те же;
- `tests/smoke/test_api_dashboard_acwr_contract.py` — route-level контракт DTO;
- `docs/issue_608_safe_workload_semantics_slice_spec.md` — этот документ.

### Границы приёмки (решение владельца)

Критерий «предписание разрешено, когда его подтверждают свежие симптомы или
ограничения» **не реализуется этим слайсом**: ACWR не участвует ни в одном
предписании — `_recommendations_for_signals` читает только `tsb` и `hrv`, а
`load.acwr` лишь прикрепляется к сигналу (проверено чтением функции и grep).
Реализовывать положительный сценарий не на чем. Поэтому #620 — первый слайс с
`Refs #608`, а #608 остаётся открытым до появления реального consumer/composer.
Сужение приёмки записано отдельным owner-комментарием в #608; одной записи в ветке
для изменения acceptance недостаточно.

## Non-goals

- Behavior deliberately unchanged: математика EWMA, окна acute/chronic, пороги и
  канонический источник нагрузки (#608 non-goal).
- Нет медицинского диагноза, модели травмы и injury-probability score.
- Нет авто-мутации плана в этом слайсе.
- Нет редизайна страницы Today и нет новых полей в `web/`.
- Нет новых интеграций с провайдерами.
- Deferred work and owner: положительный corroborated-intervention сценарий —
  внутри #608, владелец Domain / API Implementer, до появления потребителя ACWR.

## Definition of Done

- [x] Acceptance criteria are observable (см. RED Matrix).
- [x] Required tests/checks are named (см. Evidence Bundle).
- [ ] Merge and cleanup owner is assigned (human merge owner).

## Public Contracts

Провайдер (Intervals.icu) присылает `acwr_status` в **прежнем** словаре. Поэтому:

- `provider_status_from_training_status` и сверка продолжают **принимать** старые
  строки и отображают их в новую шкалу отдельной таблицей соответствия
  (`ACWR_PROVIDER_LEGACY_STATUS`);
- **старый словарь допустим только на входе.** Публичное поле `provider_status`
  обязано нести новую шкалу: провайдерский `high_risk` выходит как
  `strongly_elevated`. Иначе риск-лексика возвращается в DTO в обход acceptance
  criteria; это закреплено тестом `test_provider_status_is_never_legacy`;
- шим серверный, а не браузерный: `web/` не читает `acwr` вообще (проверено grep
  по `web/`), поэтому молчаливого восстановления старых значений на клиенте быть
  не может.

| Contract | Status | Evidence |
| --- | --- | --- |
| `signals.load.acwr` в runtime DTO: `status`, `label`, `provider_status` | **breaking** — значения enum заменены | `tests/smoke/test_api_dashboard_acwr_contract.py` |
| `signals.load.acwr`: шесть новых полей | **changed compatibly** — поля добавлены, существующие не удалены | тот же файл |
| `tests/contracts/ts_contract.json` | **unchanged** — вложенный сигнал типизирован общим словарём, экстрактор значения enum не перечисляет | `npm --prefix web run contract:extract -- --check` |
| REST-эндпоинты (`/api/dashboard/summary`, `/widgets`) | **unchanged** — форма ответа та же | `tests/smoke/test_api_dashboard.py` |
| База данных, события, CLI, конфигурация | **unchanged** | — |

`contract:extract` этот сдвиг не видит, поэтому runtime-контракт закрыт отдельным
route-level тестом, а не экстрактором.

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result: короткая история или низкая хроническая нагрузка
  дают `value=None` со стабильной причиной (`insufficient_history`,
  `chronic_load_too_low`) и полным провенансом; исключений нет.
- Retry/idempotency key and duplicate behavior: расчёт чистый, без I/O; повторный
  вызов даёт тот же результат.
- Rollback procedure and proof: revert коммита; данные не менялись, состояние не
  персистится, поэтому откат не требует миграций.
- [x] Does this add **new persistent state**? Нет — только поля ответа.
- [x] Does **full reset** remove every row/artifact/cursor introduced here?
  Не применимо: новых строк, артефактов и курсоров нет.
- [x] Restart and partial-failure recovery are covered. Не применимо: состояние не
  пишется.

## State Boundaries and Identity

- Source of truth and owner: дневной ряд нагрузки; владелец —
  `models/acwr.py` (шкала) и `models/banister.py` (константы EWMA).
- Stable identity/provenance keys: `calculation_version` (математика) и
  `semantics_version` (интерпретация) версионируются раздельно;
  `acute_tau_days` / `chronic_tau_days` фиксируют модель, к которой относится
  значение.
- Cursor/checkpoint lifecycle: не применимо.
- Concurrency and stale-write behavior: только чтение.

## Evidence Boundary Matrix

| Identity | Time/provenance | Evidence state | Fallback | Expected result / falsifier |
| --- | --- | --- | --- | --- |
| n/a (агрегат) | история ≥ 84 дней, CTL ≥ 5 | present | allowed | описательная зона + провенанс; фальсификатор — риск-лексика в подписи |
| n/a | история < 84 дней | partial | fail closed | `value=None`, `insufficient_history`, `intervention_eligible=False` |
| n/a | CTL < 5 | partial | fail closed | `value=None`, `chronic_load_too_low` |
| n/a | провайдер прислал прежний словарь | present | allowed (вход) | наружу новая шкала; фальсификатор — `high_risk` в `provider_status` |
| n/a | провайдер прислал неизвестную строку | missing | fail closed | `cross_check=no_provider_value`, наш статус не подменяется |

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| Ни один пользовательский статус не называет зону safe/optimal/dangerous/injury | `test_no_risk_vocabulary_in_user_facing_status` | текущие подписи содержат «риск» | подписи описательные |
| Низкое отношение — ниже базы, а не доказательство недотренированности | `test_low_ratio_reads_as_below_baseline` | статус `safe` | `below_baseline` |
| Высокое отношение — повышенная нагрузка, а не вероятность травмы | `test_high_ratio_reads_as_elevated_not_injury` | статус `high_risk`, подпись «Высокий риск» | `strongly_elevated` |
| Ровная нагрузка — ожидаемый диапазон | `test_steady_ratio_reads_as_expected_band` | статус `optimal` | `expected_band` |
| Провенанс: `history_days`, `acute_tau_days`, `chronic_tau_days` | `test_signal_exposes_provenance` | полей нет | 7 и 42, история равна длине ряда |
| Версии разделены | `test_versions_are_separate` | поля нет | оба поля есть и различаются |
| Ограничение и отказ в data-gap | `test_limitation_present_in_data_gap` | поля нет | `limitation` есть, `intervention_eligible=False`, провенанс на месте |
| ACWR-единственный вход не даёт предписания | `test_acwr_alone_cannot_prescribe` | поля нет | `intervention_eligible is False` |
| Изменение только ACWR не меняет рекомендации | `test_acwr_change_does_not_move_recommendations` | (зелёный до и после — инвариант) | рекомендации идентичны |
| Старый словарь не возвращается в `provider_status` | `test_provider_status_is_never_legacy` | старый словарь проходит наружу | только новая шкала |
| Численные значения не меняются | `test_numeric_fixtures_unchanged` | (зелёный до и после) | отношения и пороги те же |
| Сверка с прежним словарём работает | `test_provider_legacy_vocabulary_still_compares` | (зелёный до и после) | сверка через шим |
| Runtime DTO отдаёт новую шкалу и шесть полей | `test_dashboard_summary_acwr_contract` | полей нет, enum старый | route-level контракт |

## ASR / ADR Traceability

- ASRs affected from `docs/architecture/asr_catalog.md`: `ASR-REL-2` (недостающие,
  устаревшие и конфликтующие данные завершаются детерминированным
  не-предписывающим результатом), `ASR-MOD-2` (семантика безопасности
  серверная), `ASR-MOD-3` (явный план совместимости для смены enum).
- ADRs reused or required: `ADR-0001` — общий Python + API; Streamlit своей копии
  логики не получает.
- Tactic and trade-off: описательная шкала снижает риск ложного медицинского
  утверждения ценой потери привычных слов; совместимость обеспечена серверным
  шимом, а не молчаливым переименованием на клиенте.
- New architecture boundary discovered during review: нет.

## Delivery Slices

1. Slice: описательная шкала, шим совместимости, поля сигнала.
   - RED: `tests/smoke/test_acwr_semantics.py` — `11 failed, 1 passed` на
     `54085bb`; проход — интеграционный инвариант, обязанный быть зелёным.
   - GREEN: `b035da5` — `12 passed`.
   - Refactor/contract refresh: `tests/smoke/test_acwr.py` переведён на новую
     шкалу; `contract:extract -- --check` подтверждает, что артефакт свежий.
   - Verification: focused `71 passed`; contributor-safe `2817 passed`; Ruff.

## Evidence Bundle

- Head SHA: `b035da5` + финальный prep-коммит.
- Changed invariants: публичный enum статуса ACWR; старый словарь не выходит
  наружу; ACWR не влияет на рекомендации.
- Focused and broad tests: `tests/smoke/test_acwr_semantics.py` (12),
  `tests/smoke/test_acwr.py` (59), focused consumers (26), contributor-safe
  (`2817 passed, 13 skipped, 38 deselected`).
- CI checks/reruns/flakes: `Contributor-safe pytest`, `Gitleaks`, `link`,
  `Web contract artifact`, `Web E2E` — зелёные на `b035da5`; повторов и флейков нет.
- Lifecycle/probe evidence: не применимо (состояние не пишется).
- Changed contracts: `signals.load.acwr` — breaking по значениям enum,
  compatible по составу полей; TS-артефакт unchanged.
- Unresolved review-thread count: 0 (ревью ещё не запрашивалось).
- Residual risks and follow-ups: положительный corroborated-intervention сценарий
  остаётся в #608; #608 не закрывается этим PR.

## Review Findings

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| — | Ревью не запрашивалось | — | TBD |

## Native Review Rounds

| Round | Reviewed head SHA | Trigger | Findings disposition | Stop / exception decision |
| ---: | --- | --- | --- | --- |
| 1 | TBD | manual | TBD | continue / stop |
| 2 | TBD | verification | TBD | stop / exception rationale |

После раунда 2 новый полный нативный раунд не запрашивается без новой
архитектурной границы, документированного решения merge owner и лейбла
`review-budget-exception`.

## Final Verdict

- Verdict: **READY WITH OWNED FOLLOW-UP** (после зелёного CI на финальной голове).
- Blocking findings remaining: нет.
- Review rounds used: 0 / 2.
- Accepted risk or follow-up issue: #608 остаётся открытым — положительный
  corroborated-intervention сценарий не реализован и принадлежит #608.
- Merge owner final gate: `status: review accepted`; мерж — squash не требуется,
  персональных данных в истории ветки нет.
- Post-merge sync/branch/worktree/progress cleanup: обновить ExecPlan (слайс 1
  поставлен), синхронизировать `main`, удалить локальную ветку.
