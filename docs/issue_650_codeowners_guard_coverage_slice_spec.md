# Slice Spec And Review — issue #650 (CODEOWNERS покрывает rot-guard'ы CI-политики)

Рабочая спецификация среза, связанная с
[ExecPlan](issue_650_codeowners_guard_coverage_execplan.md); её таблицы и
чеклисты сознательно не переносятся в строгий формат `.agent/PLANS.md`.

- Issue / PR: [#650](https://github.com/rbctmz/ai_trainer/issues/650) / PR этого среза
- Author / checker / merge owner: автор — Domain/Infrastructure-исполнитель (агент); независимый checker — read-only аудит OpenCode по `docs/opencode_external_reviewer_runbook.md`; merge owner — @rbctmz
- Date: 2026-09-26
- Candidate head SHA: заполняется на финальном head

## Change Class

- Class: A
- Rationale: сработал автоматический триггер «security boundary, permissions» — правка определяет, какие пути требуют аппрува владельца, то есть меняет governance-поверхность ревью, а не только текст.
- Automatic escalation triggers checked: data migration — нет; identity/provenance — нет; live-provider write — нет; security boundary/permissions — **да** (CODEOWNERS и обязательность ревью); irreversible action — нет (полностью обратно `git revert`); новый cross-module public contract — нет (новый тест использует существующие пути).
- Review budget used: 0 / 2 rounds на момент написания спеки (см. Native Review Rounds)
- Review trigger mode: manual (Codex недоступен; независимый раунд — OpenCode read-only аудит, он считается раундом бюджета)
- Review acceptance head SHA: заполняется после аудита
- Review budget exception: N/A на момент написания

## Scope

- Behavior that changes: PR, меняющий `tests/smoke/test_native_codex_review_integration.py` (и четыре других сторожа), перестаёт быть мержабельным без ревью владельца; новый тест, читающий `.github/workflows` или `.github/scripts` и не внесённый в CODEOWNERS, роняет `Contributor-safe pytest`.
- Files/modules in scope: `.github/CODEOWNERS`, `tests/smoke/test_ci_policy_guard_coverage.py`, `docs/issue_650_codeowners_guard_coverage_execplan.md`, `docs/issue_650_codeowners_guard_coverage_slice_spec.md`.

## Non-goals

- Behavior deliberately unchanged: `.github/workflows/*` не меняются; активный ruleset «Protect main» не меняется (`required_approving_review_count` остаётся 0, `Review gate` остаётся необязательной проверкой); продуктовый код, API и `web/` не затрагиваются; список владельцев остаётся @rbctmz.
- Deferred work and owner: перевод остальных необязательных проверок в обязательные и вопрос «должен ли `Review gate` стать required» — это политика, отдельное решение владельца, не этот срез.

## Definition of Done

- [x] Acceptance criteria are observable.
- [x] Required tests/checks are named.
- [x] Merge and cleanup owner is assigned (@rbctmz; ветка удаляется после мержа).

## Public Contracts

| Contract | Change | Where |
| --- | --- | --- |
| GitHub CODEOWNERS (владельцы путей) | **changed compatibly** | `.github/CODEOWNERS`: добавлены `.github/CODEOWNERS` и шесть сторожевых тестов; существующие две записи не тронуты |
| Review obligation для CI-путей | **changed compatibly** (расширение) | PR, трогающий сторожа, теперь требует владельца; ни один путь не потерял владельца |
| `.github/workflows/*` | unchanged | — |
| API / TypeScript / БД / конфигурация продукта | unchanged | — |
| Публичный контракт теста | новый файл `tests/smoke/test_ci_policy_guard_coverage.py`, `pytest.mark.smoke` | обязательный набор `Contributor-safe pytest` |

## Failure, Reset, Rollback, Idempotency

- Failure modes and safe result: если сторож падает — это сигнал, что тест читает защищённый каталог, но не внесён в CODEOWNERS; безопасный результат — падение CI до мержа, а не ослабление защиты. Ложное падение возможно только при переименовании сторожа, и сообщение называет файл и готовую строку для вставки.
- Retry/idempotency key and duplicate behavior: N/A — постоянного состояния и ключей идемпотентности в срезе нет.
- Rollback procedure and proof: `git revert` коммита среза. Проверяемо: до правки CODEOWNERS сторож даёт `2 failed, 2 passed`, после — `4 passed`, значит откат возвращает ровно исходное поведение.
- [x] Does this add **new persistent state**? No — только текст в двух файлах; ни БД, ни кэшей, ни курсоров.
- [x] Does **full reset** remove every row/artifact/cursor introduced here? N/A — нечего удалять.
- [x] Restart and partial-failure recovery are covered. Прогон теста идемпотентен; ломающая проба восстанавливает файл копией и подтверждается `git diff`.

## State Boundaries and Identity

- Source of truth and owner: `.github/CODEOWNERS` в репозитории; исполняет GitHub при оценке PR. Владелец — @rbctmz.
- Stable identity/provenance keys: N/A — сущностей с идентичностью срез не вводит.
- Cursor/checkpoint lifecycle: N/A.
- Concurrency and stale-write behavior: GitHub вычисляет CODEOWNERS из базовой ветки PR, поэтому запись защищает будущие PR, а не тот, который её добавляет; это записано комментарием в самом файле, чтобы читатель не считал это гарантией для текущего PR.

## Evidence Boundary Matrix

N/A — срез не касается evidence, истории, матчинга план-факт или восстановления. Ближайшая по смыслу граница («тест существует, но не внесён в CODEOWNERS») покрыта отдельным тестом и ломающей пробой.

## RED Matrix

| Acceptance criterion / invariant | RED test or probe | Expected failure | GREEN evidence |
| --- | --- | --- | --- |
| Сторож, читающий защищённый каталог, обязан быть в CODEOWNERS (AC1/AC2) | `test_every_ci_policy_guard_test_is_codeowner_protected` | до правки: 6 файлов в сообщении, `assert not [...]` | `4 passed`; ломающая проба с удалённой записью — `1 failed` |
| Сам CODEOWNERS под защитой (AC3) | `test_codeowners_protects_itself` | `assert ()` — матчер не находит владельца | `4 passed` |
| Защищённые каталоги не потеряли владельца (AC4) | `test_protected_directories_still_have_an_owner` | был зелёным до и остаётся зелёным — это регрессионный сторож, а не RED | `4 passed` |
| Сканер не опустел при переименовании сторожей | `test_scanner_finds_the_known_guards` | зелёный до и после; падает при переименовании файла | `4 passed` |

## ASR / ADR Traceability

- ASRs affected from `docs/architecture/asr_catalog.md`: N/A — срез не меняет quality attributes продукта; он про целостность процесса ревью.
- ADRs reused or required: N/A — новой архитектурной границы нет.
- Tactic and trade-off: «защита критичного пути через владельца» — та же тактика, что в #511; trade-off в том, что каждый будущий сторож требует правки CODEOWNERS, и цена забывчивости снята автотестом.
- New architecture boundary discovered during review: NOT YET — проверяется независимым аудитом.

## Delivery Slices

1. Slice: CODEOWNERS покрывает сторожей CI-политики.
   - RED, or characterization baseline for a behavior-preserving refactor: `tests/smoke/test_ci_policy_guard_coverage.py` написан до правки CODEOWNERS; `2 failed, 2 passed`.
   - GREEN: `.github/CODEOWNERS` расширен; `4 passed`.
   - Refactor/contract refresh: не требуется — контрактов продукта срез не трогает.
   - Verification: ломающая проба (удаление записи → `1 failed, 3 passed`), широкий `pytest -m "not live and not debug and not e2e" tests/`, `ruff check .`.

## Evidence Bundle

- Head SHA: заполняется на финальном head
- Changed invariants: PR, меняющий сторожевой тест CI-политики, требует ревью владельца; новый сторож не может остаться вне CODEOWNERS незамеченным
- Focused and broad tests: focused — `tests/smoke/test_ci_policy_guard_coverage.py` (`4 passed`); broad — полный contributor-safe набор и `ruff` (числа вписываются на финальном дереве)
- CI checks/reruns/flakes: заполняется по факту прогона PR
- Lifecycle/probe evidence: ломающая проба с удалением записи CODEOWNERS и восстановлением файла (`git diff` — только намеренные +19 строк)
- Changed contracts: CODEOWNERS (расширение), новый smoke-тест
- Unresolved review-thread count: 0 на момент написания
- Residual risks and follow-ups: GitHub вычисляет CODEOWNERS из базовой ветки, поэтому запись не защищает PR, который её добавляет — этот PR проходит обычным путём; `Review gate` остаётся необязательной проверкой (осознанный non-goal).

## Review Findings

Заполняется после независимого read-only аудита.

| Severity | Evidence and falsifying check | Gate | Owner/status |
| --- | --- | --- | --- |
| | | | |

## Native Review Rounds

| Round | Reviewed head SHA | Trigger | Findings disposition | Stop / exception decision |
| ---: | --- | --- | --- | --- |
| 1 | | manual (OpenCode read-only audit) | | continue / stop |
| 2 | | verification | | stop / exception rationale |

Codex недоступен; независимый раунд проводится OpenCode и считается раундом бюджета. Полный native-бюджет — два full-diff раунда.

## Final Verdict

- Verdict: заполняется после аудита и широкого прогона
- Blocking findings remaining:
- Review rounds used:
- Accepted risk or follow-up issue:
- Merge owner final gate: @rbctmz
- Post-merge sync/branch/worktree/progress cleanup: синхронизировать `main`, удалить ветку среза, обновить `Progress` в ExecPlan, добавить запись метрик Class A
