# Planning S4: объяснимое подтверждение

Этот living ExecPlan следует .agent/PLANS.md. Задача#714, родитель#677;
дата2026-10-22 Europe/Moscow. [Спецификация](planning_confirmation_s4_spec.md).
Baseline main00de158; S1/S2/S3/M4 уже слиты. M1 завершён в роли Spec / Architecture Owner;
M2 UI/Design и revision1 реализованы, M3 owner acceptance частична.23October2026
владелец одобрил новое before/after сравнение в #714: C1–C3 завершены, текущая роль Supervisor / Integrator;
Class A для расширения, прежний Class B UI scope сохранён как история.
[Comparison slice spec](planning_confirmation_s4_comparison_spec.md) задаёт C1–C4.

## Purpose / Big Picture

Перед сохранением пользователь понимает цель/период, назначенную нагрузку и
последствия выбора. Различаются ориентир, фактическое назначение и прогноз.
Вопросы проверяются на синтетическом новом плане и изменении, затем владельцем
без подсказок. М1 описывает смысл и доступность данных, не выбирает CSS/компоновку.

## Progress

- [x] (2026-10-22) Сверены origin/main00de158, исходная модель#677 и отсутствие отдельной S4 задачи; создана#714 до tracked M1 edits.
- [x] (2026-10-22) Прочитаны роли/architecture/design workflow, реальные DTO и PlanBuilder; текущая личная рабочая ветка/исследования сохранены.
- [x] (2026-10-22) Изолированный probe: новый8нед/изменение4нед, оба supported; pure capture/calculation не меняют таблицы, prepare меняет только pending, сеть0. Начальный неверный identity-oracle исправлен; это не продуктовый RED.
- [x] (2026-10-22) Информационный spec, источник каждого значения, safe fallback и BDD S4-01…11 подготовлены; UI/API/числовая модель не менялись.
- [x] (2026-10-22) Focused existing compatibility56passed/1existing warning8.51s; probe exit0, Ruff/diff green. Это не новые UI BDD/RED и не full contributor suite.
- [x] (2026-10-22) Independent spec round1/2 READY на7337fb5, zero P1/P2: probe повторён,56 compatibility passed/1existing warning8.43s, Ruff/diff green, HEAD/tree unchanged. M1 завершён, явная передача UI/Design для M2 зафиксирована; native0/2 не запускался.
- [x] (2026-10-22) M2: UI/Design прототип/реализация на46201b3, observable RED→GREEN;55 related E2E, затем14 после contrast-only; final lint/build/контракты green. Independent UI round1/2 READY, zero P1/blocking P2;14 E2E повторены независимо. Передано Supervisor/Integrator для M3.
- [x] (2026-10-22) M3 automated: CI exactd00fb5f SUCCESS (3942 contributor-safe,77 browser,24 contract); картаS4-01…11 и4 real-DOM owner cases. Дополнительный loading/error probe PASS; UI/domain/AC не менялись. Полные наборы не повторяются без изменений; новый evidence head получает стандартный CI.
- [ ] M3 owner comprehension: первое A–D упражнение неуспешно; revision1 period/save понятны, availability проверена с подсказкой, total пояснён. Edit effect не понятен без before/after; сравнение одобрено как расширение. Это не blind first-use study и не completed M3.
- [ ] M3 native review:1/2 clean на9d41e2b, исторический после3f75915; scoped round2/2 оставлен для стабильного итогового кандидата, не для текущего prototype/spec.
- [ ] Owner acceptance / merge: отдельное явное решение после M3, пока не запрошено и не выполнено.
- [x] (2026-10-23) Current UI3f75915: green CI39991604878 и isolated new/edit/replacement/lost-response probe; native1/2 historical, owner comparison finding recorded.
- [x] (2026-10-23) Owner approved Class A comparison; task role handoff to Spec recorded before edits; C1 author specification prepared on raw checkpoint evidence.
- [x] (2026-10-23) C1 independent full+scoped spec check READY at93a37ec; P2 reset wording fixed-in93a37ec; budget2/2, raw characterization and initial contract RED recorded.
- [x] (2026-10-23) C2 independently READY atc7b42f5, malformed-steps P2 fixed-inc7b42f5; local budget2/2. Final clean-head contributor-safe run:3991passed/16skipped/101deselected/7warnings257.11s with venv on PATH. Typed API/TS and frozen integration,26comparison regressions, lint/build/freshness pass.
- [x] (2026-10-23) C3 UI/Design independently READY atc324c9e, local budget2/2: paired periods/parameters/load/calendar, partial/legacy/historical states. Rest-phase P2 fixed-inc324c9e after reproduced RED; final23S4browser tests passed37.61s, independent delta1passed6.31s; lint/build/freshness pass. UI→Integrator handoff recorded in#714. Owner comprehension remains pending.
- [ ] C4 integrated checks, owner remaining cases and scoped native round2/2; acceptance/merge separate.

## Surprises & Discoveries

Observed: публичный синтетический edit8→4 возвращает total999→433,
weekly_tss_delta−566, но preview не содержит старого периода. Inferred: одиночная
дельта не описывает недельное/сопоставимое снижение нагрузки. Verified by:
probe на неизменном main00de158, длины массивов8/4 и фактические даты кандидата.
S4 v1 показывает область/итоги кандидата и отсутствие сравнения; доменная
сопоставимость не вычисляется в React.

Observed: оба режима training_goal с разными горизонтами дают legacy message
«для поддержания формы», при intent=develop; forecast points датированы.
Inferred: message не доказывает результат намерения. Verified by: probe и
_forecast выбирает message только из зоны final_tsb. S4 не меняет модель и не
рендерит этот текст как оценку эффективности; выводит нейтральный сценарий/числа.

Observed: первое сравнение всех raw bytes двух отдельных captures не прошло.
Inferred: start_new создаёт новую cycle identity и связанный fingerprint, даже
при прежних фактических входах. Verified by: источник lifecycle capture и
исправленный semantic oracle на totals/датах/forecast.points проходит. Никакого
дефекта публикации из этого не следует; это ошибка диагностического сравнения.

## Decision Log

2026-10-22 / Spec Owner: S4 v1 остаётся Class B существующего DTO. Если нет старых
дат/сопоставимости, не показывать один delta/процент; для новых физических итогов
или comparison contract нужна отдельная Class A передача. Это предотвращает
новую доменную логику в браузере без обязательного расширения API сейчас.

2026-10-22 / Spec Owner: первый уровень требует значения total/peak TSS и периода,
а не отсутствующих назначенных часов/числа занятий. Доступность остаётся потолком.
Числа и ограничения M4 не заменяют личную пригодность или медицинскую оценку.

2026-10-22 / Spec Owner: не делать автоматический UI вывод о достижении цели из
TSB. Сохранить числовой прогноз, открытые dates/values и нейтральное описание.
UI/Design получает свободу композиции в рамках существующих patterns/tokens.

## Context and Orientation

web/components/planning/PlanBuilder.tsx содержит wizard и локальный transport-state
editing/ready/confirming/uncertain/applied/needs_preview; EntryLoad.tsx показывает
server-owned M4 status/provenance. web/lib/types.ts описывает BuildPreviewResponse,
BuildLifecycle, BuildParameters, PlanWeek, ForecastPoint. Python контракт в
api/planning_build_contract.py и cycle DTO; api/planning_service.py формирует
preview/totals/forecast, а prepare/confirm хранят и публикуют неизменное предложение.

В M1 редактируются только этот план, spec и synthetic report/probe. В M2 UI-роль
может менять только web/ и acceptance fixtures в существующем контракте; schema,
AC, numeric policy/identity не входят в её slice. #713 docs остаётся отдельно.

## Plan of Work

M1 сверяет публичные поля на pinned синтетических данных. Spec хранит компактный
источник→значение→fallback и проверяемые AC вместо дизайна карточек. Для выявленной
границы correctness требуется независимый read-only checker по committed diff,
не более двух spec rounds. Изменение продукта в M1 запрещено.

M2 после явной передачи использует реальный изолированный browser harness,
фиксирует RED для нового видимого поведения, реализует внутри сохранённого response
и демонстрирует требуемые состояния. Потерянный ответ и historical receipt не
упрощаются ради новой структуры. Перед push обязательны web lint/build.

M3 собирает relevant + whole contributor/contract/browser checks, реальные
скриншоты390/900/1280 в обеих темах и отдельную unaided owner-проверку из spec.
Не считать отсутствие ответа пользователя успехом UX; не менять принятые scopes
для устранения cosmetic review. Native manual на стабильном кандидате, max2;
merge/live-write по явному owner-решению, без admin/force bypass.

## Concrete Steps

Из task worktree с origin/main00de158 и отдельной веткой#714 создать существующие
временные каталоги для DATABASE_PATH/DEMO_DATABASE_PATH/CHATS_DIR. Все источники —
synthetic fixture exposure_db; Python — venv основной папки, PYTHONPATH=.; никаких
.env, logs/ или personal DB. Команды и конкретные результаты — в report README.

    python docs/reports/2026-10-22-planning-confirmation-s4-m1/probe.py
    python -m ruff check docs/reports/2026-10-22-planning-confirmation-s4-m1/probe.py
    python -m pytest tests/smoke/test_planning_entry_integration_m4c.py tests/smoke/test_planning_build_confirmation.py -q -p no:cacheprovider
    git diff --check

Для UI-фазы дополнить named E2E, npm --prefix web run lint/build и extractor
freshness/inventory; если понадобится новый DTO, не начинать его как UI-изменение.

## Validation and Acceptance

M1 выход: опубликованный spec с источниками/fallback, воспроизводимый json/probe,
нулевой network count и no-write pure control, целевой compatibility baseline и
независимый verdict. BDD S4-01…11 сейчас планируется, UI RED/GREEN NOT YET.
Это не требует полного четырёхтысячного набора для docs-only candidate.

M2/M3 выход: пользователь видит данные именно сохранённого предложения, может
объяснить период/TSS/доступность/кнопку; все protocol/legacy/uncertain guards
сохраняются. Приёмка владельцем и automated tests — разные evidence. Числовая
модель/инварианты/личные данные неизменны. Детальные AC — в spec.

## Idempotence and Recovery

Probe каждый раз создаёт и удаляет собственную временную SQLite. Временная
публикация восьминедельного плана — только явная установка synthetic edit fixture;
её нет в athlete DB. Pure capture/calculation read-only, prepare сохраняет лишь
pending. Raw namespace identity не сравнивается. М1 не добавляет persistent state,
поэтому migration/reset/rollback нового хранилища N/A; существующие S1/S2/M4 gates
принимаются как обязательная compatibility, а не заменяются новым workflow engine.

## Outcomes & Retrospective

М1 завершён: spec/characterization, targeted compatibility и независимый READY
на7337fb5. Карта источников/fallback не требует нового API или доменной логики
в React. Явная передача M2 UI/Design — в spec; реализация в этом M1 не выполнялась.
Полноценное UI, owner usability и merge S4 не заявлены. Новые факты и точный
handoff дополняются после проверки; найденные пробелы нельзя решать в CSS/React
доменными догадками. Этот документ создан для запуска M1, с будущими M2/M3 как
последовательностью, а не неявным расширением текущего разрешения.


Обновление2026-10-22: по выполненному независимому review M1 отмечен завершённым;
M2/M3 и unaided owner acceptance остаются следующими этапами. Причина изменения —
запись фактического verdict/test evidence, без пересмотра AC/контрактов/чисел.


Обновление M2 / 2026-10-22: по явному запросу владельца UI/Design реализовал
информационную модель на существующем frozen DTO. Source46201b3, UI review1/2
READY; подробные границы проверок/fixture failures и8 synthetic screenshots —
[UI evidence](design/evidence/issue-714/README.md). Роль UI/Design завершена;
передача Supervisor/Integrator для M3. Это запись статуса и evidence, без
пересмотра M1 AC/source map, API или числовой политики. Unaided owner usability,
whole acceptance и native0/2 ещё не выполнены; no merge/live writes.


Обновление M3 / 2026-10-22, Supervisor/Integrator: [общий отчёт](reports/2026-10-22-planning-confirmation-s4-m3/README.md) фиксирует S4-01…11 → реально выполненные тесты, отдельные временные loading/error и lost-response probes, четыре неизменяемых кадра для ответа владельца. Два слишком широких диагностических oracle и один неверный локатор исправлены в capture helpers; это не продуктовый RED и не UI fixes. Disabled-provider503 и намеренный ERR_FAILED классифицированы отдельно от unhandled JS.

Пользователю задана одна группа открытых вопросов без ответов/подсказок; ответа пока нет. Автоматические PASS не закрывают этот критерий. Native review после CI может идти независимо, чтобы не задерживать оставшуюся работу; его результат также не закрывает пользовательскую проверку. Новые факты/ответы и review receipts фиксируются в #714/#715 без косметического push после принятого review; реальная блокирующая ошибка потребует воспроизведения и scoped fix. AC/контракты/числовая политика не пересмотрены.


## Comparison extension:23October2026

Purpose: edit should explain actual old→new differences rather than only the
proposed state. The owner rejected the unavailable-comparison fallback for this
decision and explicitly approved a Class A API/UI expansion. The approved source
is issue #714; the comparison spec defines all fields/unknown semantics.

Decision Log: before facts come from the raw selected checkpoint already in
BuildInputSnapshot.sources, after facts from the final serialized candidate. No
restore/rebuild of old data and no current GET enrichment. Per-date content
comparison does not infer moved-session lineage or delete actual history.
Rationale: old/new horizons and identity namespaces can differ. Existing S1/S2
retention/transaction/reset ownership remains. No new table, migration, setting
or provider access. Current complete receipts remain unchanged.

C1 produces docs/planning_confirmation_s4_comparison_spec.md using the slice
template and evidence in docs/reports/2026-10-23-planning-comparison-m1/. It
changes approved scope, not UI/layout/runtime. Independent checker verifies
CMP01…14, additive legacy behavior and raw/final provenance before C2.

C2 edits models/planning_build_comparison.py (new pure function
build_plan_comparison(before_checkpoint, after_checkpoint, parameters, context)),
api/planning_build_contract.py (typed nullable response field),
api/planning_service.py::_calculate_plan_build (call after final checkpoint prescriptions/entry repairs, before final
readiness fingerprint binding), web/lib/types.ts (mirror), and relevant smoke/API/contract tests.
Before editing, handoff Spec→Domain/API in #714. New tests first fail because
comparison is absent. Test chronology and failed probes must be recorded, not
retroactively called RED. Use already-captured sources/context; no new db read
or comparison policy in TypeScript. Refresh contract registry/extracted artifact.

C3 starts only after C2 contract check, with explicit Domain/API→UI/Design
handoff. UI uses paired facts/day change states and existing design tokens,
never client-computed lineage/comparability. Capture distinct new images, leave
original rejected owner screens unchanged. Owner checks go one at a time.

C4 integrates final head, green CI and independent findings, captures remaining
owner results without laundering coached replies as unaided, then requests
only scoped native round2/2 since9d41e2b. Human acceptance/merge are still needed.
The new architecture boundary does not reset the native review budget.

Concrete commands from this worktree, primary venv on PATH, PYTHONPATH=.:

    python docs/reports/2026-10-23-planning-comparison-m1/probe.py
    python -m pytest tests/smoke/test_planning_build_comparison.py -q
    python -m pytest tests/smoke/test_planning_build_confirmation.py tests/smoke/test_planning_build_confirmation_storage.py -q
    npm --prefix web run contract:extract
    npm --prefix web run contract:extract -- --check
    python -m pytest -m e2e tests/e2e/test_planning_confirmation_s4_ui.py tests/e2e/test_planning_build_confirmation_ui.py -q
    npm --prefix web run lint
    npm --prefix web run build
    python -m ruff check .
    python -m pytest -m "not live and not debug and not e2e" tests/

Expected behavior is CMP01…14, not a test count. Future commands/files above
are planned, not claimed already present/passed. Run suites once per meaningful
source boundary; no build concurrently with Next E2E. Pure/protocol tests use
temporary SQLite; never confirm against athlete DB. Failure rolls back existing
transaction. Repeating prepare creates only normal pending ownership; reset
removes that comparison with its existing row.

Outcomes at C1 author draft: scope/contract defined; no production implementation,
no refreshed native result and no complete owner acceptance. Missing before
calendar was verified by the existing pinned probe; raw checkpoint availability
and executable session fields were checked in a second synthetic fixture.


C1 independent round1/2 on dee2422: BLOCK for CMP12 contradicting full-reset
checkpoint deletion. Supervisor independently confirmed database.py5751; spec
corrected, rest/outside semantics and span bound clarified.106-case baseline
already includes cycle full-reset regression; no live reset or source change.
Scoped delta verification pending; native budget remains1/2.


C1 independently READY at93a37ec91feb5b0a4e6f0be913da6e7f27ee63c1, P2 fixed-in93a37ec;
Spec→Domain/API handoff recorded in #714. C2 adds the approved pure comparison,
optional API/TS and original retained response integration; [C2 evidence](reports/2026-10-23-planning-comparison-c2/README.md).
Observed: adding a response field after readiness changed the bound candidate
fingerprint; verified by require_prepared_readiness failure. Integration now
computes comparison after final prescription repairs but before final binding.
No guard weakened and no new dependency reads. Observed: a selected unreadable
baseline is allowed during explicit replacement; reproduced existing S2
regression. Such comparison is partial, not a new publication refusal.
C2 author checkpoint has focused/contract/web checks, independent/broad pending.


C2 independent round1 found P2 malformed raw steps falsely marked complete;
supervisor reproduced and4regressions RED, then structural-only fix.26comparison
and3preflight pass with primary venv on PATH. Full initial suite had3985passes
and1environment failure (run_web.sh subprocess could not resolve python);
affected test was reproduced and fixed by test invocation environment, without
changing product startup. Full correct-environment result and scoped independent
delta check remain pending. Date-keyed reordered-template case added.


## C4 handoff status / 2026-10-23

Supervisor/Integrator received independently READY C3 atc324c9e after the named
rest-phase P2 correction. All local C1/C2/C3 reviews used bounded full+delta
rounds; none replaced or reset native review1/2. C2 final full contributor-safe
run on cleanc7b42f5 passed3991tests; earlier missing bare-python failure was
resolved by test invocation PATH, without startup code changes. C3 final23S4
UI tests passed; related63contour and33source/contract checks remain recorded
at their source boundaries. No reason to repeat the entire contributor suite
for the single UI text rendering fix. Current CI runs on each pushed head.

The already shown paired edit prototype is frozen. Owner response is pending;
remaining replacement/unknown-save comprehension checks follow one at a time.
No owner pass is inferred from tests or silence. Native scoped round2/2 is
reserved until remaining feedback stabilizes source. Review gate currently
expects current-head native review; it is not a code-test failure. Acceptance
label, ready state and merge have not been requested or performed.
