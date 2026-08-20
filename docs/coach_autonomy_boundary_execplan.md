# ExecPlan: issue #466 — граница автономии коуча и DDA

Живой ExecPlan по `.agent/PLANS.md` для issue #466. Документ самодостаточен и
должен обновляться по мере выполнения.

## Purpose / Big Picture

После #466 у команды есть проверяемая граница: какие действия коуч может делать
автономно, какие требуют bounded proposal и явного подтверждения, а какие
никогда не должны запускаться из LLM inference. Результат наблюдаем через
ADR-0010, запись в ASR/ADR-каталоге, smoke rot-guard и evidence-backed аудит
реальных mutation paths. Поведение найденной дыры исправляется отдельным issue,
а не скрывается расширением scope архитектурного PR.

## Progress

- [x] (2026-08-20) Прочитаны `.agent/PLANS.md`, canonical feature workflow,
  issue-first loop, ASR catalog, architecture ADD 3.0, ADR-0004 и ADR-0006.
- [x] (2026-08-20) Проведён независимый read-only аудит двумя Luna-сабагентами;
  один прогнал baseline mutation-path suite: 87 passed.
- [x] (2026-08-20) RED: новый
  `tests/smoke/test_coach_autonomy_boundary_docs.py` дал 3 failures, потому что
  ADR-0010 и этот ExecPlan ещё не существовали.
- [x] (2026-08-20) Подтверждён direct-mutation gap в
  `create_plan_constraint`, `retract_plan_constraint`, `repair_plan_day` и
  partial-write риск retract.
- [x] (2026-08-20) Создан separate fix issue #483 с approval-only и
  zero-partial-write acceptance criteria.
- [x] (2026-08-20) Записан ADR-0010 и обновлён ADR registry в ASR catalog.
- [x] (2026-08-20) GREEN: focused architecture suite 6 passed; ruff и
  `git diff --check` чистые; полный contributor-safe pytest: 1964 passed,
  3 skipped, 26 deselected.
- [x] (2026-08-20) Независимый Luna-checker провёл два review rounds; после
  уточнения manual probe provenance и file:line evidence P1/P2 findings нет.

## Surprises & Discoveries

- Observation: proposal gate в `api/routers/coach.py` работает после исполнения
  tool и распознаёт только `raw_result.is_proposal`.
  Evidence: `api/routers/coach.py:157-186`.
- Observation: три constraint/repair tools доступны и native, и marker runtime,
  но сразу пишут в ledger/checkpoint; prompt — единственный intent guard.
  Evidence: `models/ai_tools.py:1327-1371,1453-1570` и
  `models/ai_coach_runtime.py:293-325,396-421,480-497`.
- Observation: retract сначала деактивирует constraint, затем делает recovery.
  Ошибка donor/stale уже не откатывает первую запись.
  Evidence: `models/ai_tools.py:1475-1501` и
  `api/routers/planning.py:195-219`.
- Observation: синтетический native provider смог на пользовательское «ок»
  выбрать `create_plan_constraint`; runtime создал active constraint. Это
  доказывает, что model tool call не может считаться DDA. Probe выполнен
  read-only checker-агентом на temporary SQLite и не добавлен как regression
  test в docs-only diff; воспроизводимый RED входит в acceptance #483.

## Decision Log

- Decision: классифицировать по максимуму риска трёх независимых осей, а не по
  одной обратимости.
  Rationale: append-only checkpoint не уменьшает blast radius и agency creep
  внешней или широко затрагивающей мутации.
  Date/Author: 2026-08-20 / Codex.
- Decision: разрешить автономно только reversible, local, non-executable
  note/node append; mutation исполнимого плана остаётся в ADR-0004 gate.
  Rationale: это сохраняет полезную автономию без неявного изменения тренировок.
  Date/Author: 2026-08-20 / Codex.
- Decision: LLM tool call и vague assent не считаются DDA; DDA возникает на
  отдельном bounded action surface с точным объектом/base.
  Rationale: runtime не может доказать, что выбор модели выражает прямую волю
  пользователя.
  Date/Author: 2026-08-20 / Codex.
- Decision: не исправлять runtime в #466; создать separate fix issue #483.
  Rationale: acceptance #466 прямо требует отдельную задачу при найденной дыре,
  а поведенческий fix затрагивает API/web contract и требует отдельного
  SpecDD→BDD→TDD цикла.
  Date/Author: 2026-08-20 / Codex.

## Outcomes & Retrospective

ADR и rot-guard созданы; runtime gap подтверждён и вынесен в #483. Полный
contributor-safe suite зелёный. Два checker rounds завершены без оставшихся
P1/P2 findings; локальный diff готов к отдельно разрешённой публикации.

## Context and Orientation

`models/ai_tools.py` — реестр и реализация инструментов коуча.
`models/ai_coach_runtime.py` исполняет native function calls и legacy marker
calls. `api/routers/coach.py` стримит чат и сохраняет pending proposal только
для tool-result с `is_proposal`. `api/routers/decisions.py` содержит bounded
approve/reject/rollback. `api/routers/planning.py` содержит direct product/admin
actions, включая constraint, repair, restore и provider delivery.

ADR-0004 требует `Propose → Confirm → Append + rollback` для LLM-мутаций;
ADR-0006 требует append-only версии плана и fail-closed stale base. ADR-0010 не
ослабляет эти гарантии для исполнимого плана, а добавляет трёхосевую
классификацию и формальное DDA.

## ASR / risk traceability

- ASR-REL-1: scope mutation не теряет соседние сессии/дисциплины.
- ASR-REL-3: ошибка apply не оставляет частичный constraint/checkpoint state.
- ASR-MOD-2: explicit action surface отделён от AI explanation/preview.
- ASR-MOD-3: новые proposal/audit fields в будущем должны быть аддитивными.
- ADR-0004/0006: proposal gate и append-only rollback остаются обязательными.

## Mutation-path audit

| Surface | Evidence | Фактическое поведение | Класс ADR-0010 | Вердикт |
|---------|----------|-----------------------|----------------|---------|
| `get_*`, readiness, active plan, constraints | `models/ai_tools.py:111-142` | read-only | A0 | autonomous |
| `propose_plan_build`, `propose_plan_adjustment` | `models/ai_tools.py:1222-1325` | preview, `is_proposal`, без plan persist | A0/A1 | соответствует |
| Coach proposal handling | `api/routers/coach.py:157-186` | сохраняет pending proposal после tool execution | A1 | соответствует только для proposal tools |
| `create_plan_constraint` | `models/ai_tools.py:1327-1371` | сразу сохраняет constraint и может создать checkpoint | A2 | gap: нет DDA/confirm |
| `retract_plan_constraint` | `models/ai_tools.py:1453-1522` | сразу deactivate + recovery checkpoint | A2 | gap: нет DDA; partial-write риск |
| `repair_plan_day` | `models/ai_tools.py:1530-1570` | сразу recovery checkpoint | A2 | gap: нет DDA; incident tool доступен LLM |
| `POST /api/planning/constraints` | `api/routers/planning.py:160-184` | direct explicit product/API action | A2 | допустимо только как user action surface; не давать LLM напрямую |
| `DELETE /constraints/{id}` и `/retract` | `api/routers/planning.py:187-219` | direct explicit API action | A2/A3 | exact target есть; retract требует atomicity fix #483 |
| `POST /api/planning/repair-day` | `api/routers/planning.py:222-237` | direct incident action с optional base | A2 | admin/explicit only; не LLM tool |
| demand/rebalance/bike-TSS confirm routes | `api/routers/planning.py:295-311,493-542` | preview/fingerprint/base confirm | A2 | соответствует |
| `POST /api/planning/adjust`, history restore | `api/routers/planning.py:545-575` | direct product action | A2/A3 | явная UI/API команда; future review должен сохранять bounded scope/base |
| `POST /api/planning/delivery/intervals` | `api/routers/planning.py:382-395`; `web/app/planning/page.tsx:1612-1626` | внешний provider write; web вызывает кнопкой «Отправить план» | A4 | допустимо только как отдельное DDA; запрещено из Coach inference |
| `POST /api/decisions/proposals/{id}/approve` | `api/routers/decisions.py:176-229` | pending-state claim + apply + audit | A2–A4 | канонический confirm pattern |

## BDD scenarios

Документальный контракт #466:

- Given новая coach capability, when её классифицируют, then таблица явно
  оценивает Reversibility, Blast radius, Agency creep и берёт самый высокий gate.
- Given reversible non-executable note/node, when scope локален и есть audit/
  retract, then действие может быть autonomous.
- Given удаление, FTP/profile change или external write, when действие
  проектируется, then оно имеет bounded preview и отдельный confirm.
- Given «согласен», «ок» или «звучит неплохо», when модель хочет применить
  mutation, then фраза не является авторизацией.
- Given «примени»/«подтверди» для точного актуального preview, when base/fingerprint
  совпадает, then действие может перейти в apply-контур.

Runtime BDD для separate fix issue #483:

- Coach create/retract/repair до approve создают zero writes.
- Stale/missing donor/apply error сохраняют исходные constraint и checkpoint.
- Native и marker paths ведут себя одинаково; replay идемпотентен.

## Plan of Work

Milestone 0 — evidence-first audit: построить call graph AI tools, coach router,
decisions и planning routes; проверить prompt vs deterministic enforcement.
Milestone выполнен: gap подтверждён статически и synthetic native-provider
probe, follow-up #483 создан.

Milestone 1 — Spec/ADR: записать три оси, уровни A0–A4, DDA, негативные фразы,
action matrix и связь с ADR-0004/0006. Зарегистрировать ADR-0010 в ASR catalog.

Milestone 2 — docs TDD: RED до файлов, затем GREEN на узком smoke rot-guard.
Проверить существующий architecture-doc suite.

Milestone 3 — validation/checker: ruff, полный contributor-safe suite, diff
review отдельным агентом. Поведенческие изменения не входят в этот milestone.

## Concrete Steps

Из корня репозитория:

    ai_trainer_env/bin/python -m pytest tests/smoke/test_coach_autonomy_boundary_docs.py -q
    ai_trainer_env/bin/python -m pytest tests/smoke/test_architecture_docs.py -q
    ai_trainer_env/bin/python -m ruff check tests/smoke/test_coach_autonomy_boundary_docs.py
    ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/
    git diff --check

`npm --prefix web run lint && npm --prefix web run build` не требуется: #466 не
меняет `web/`, API contract или TypeScript. Если scope изменится, эти команды и
`contract:extract -- --check` становятся обязательными.

## Validation and Acceptance

Acceptance достигнут, когда ADR-0010 содержит три оси, note/node и
delete/FTP/external-write примеры, DDA positive/negative phrases и правило
повышения gate; каталог регистрирует ADR; аудит обоих роутеров имеет evidence и
ссылается на #483; focused/full contributor-safe tests и ruff зелёные; checker
не находит P1/P2 замечаний.

## Idempotence and Recovery

Изменения docs/test идемпотентны и не трогают БД/provider. Повторные тесты
используют только чтение файлов. Откат — удалить ADR/ExecPlan/test и строку
реестра одним обычным revert; runtime behavior от #466 не зависит.

## Artifacts and Notes

- RED evidence: `3 failed` из-за отсутствующих ADR/ExecPlan до GREEN.
- Independent audit baseline: `87 passed`.
- Manual DDA evidence: independent temporary-SQLite native-provider probe
  («ок» → model-selected `create_plan_constraint`) создал active constraint;
  regression form описана в #483 и намеренно не входит в docs-only #466.
- Full validation: `1964 passed, 3 skipped, 26 deselected`; focused architecture
  suite: `6 passed`; ruff и diff-check clean.
- Follow-up: https://github.com/rbctmz/ai_trainer/issues/483
- Checker: два read-only rounds; итог — P1/P2 findings отсутствуют.

## Interfaces and Dependencies

#466 не меняет runtime interfaces. Нормативный интерфейс для будущих mutation
tools: preview возвращает exact scope, `base_checkpoint_id` и fingerprint;
confirm принимает идентификатор pending proposal и применяет его ровно один
раз. A1 note/node append обязан быть non-executable, attributable и retractable.
