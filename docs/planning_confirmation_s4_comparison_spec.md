# S4: замороженное сравнение текущего и предлагаемого плана

Задача #714 / PR #715, родитель #677. Дата: 23 октября 2026.
Явное разрешение владельца: добавить сравнение периодов, параметров, нагрузки и
расписания в #714. Передача UI/Design → Spec / Architecture Owner записана в задаче.
Это расширение Class A, заменяющее candidate-only fallback для нового edit.
Спецификация сама не утверждает реализованный API/UI или успешную приёмку.

## Change Class и границы

Автор: Spec / Architecture Owner. Независимый checker: требуется до передачи
реализации; merge owner: человек-владелец. Candidate baseline:3f75915084cf9c6d6be78a0a66d413d6a7240f3b.
Class A из-за нового API↔web контракта, frozen provenance и сравнения версий.
Native budget всего PR:1/2 (исторический clean9d41e2b), manual; round2 не запускать
до стабильного итогового кандидата. Accepted head: нет; exception:N/A.

Результат: перед сохранением пользователь видит, какой текущий план сравнивается
с каким предложением, что изменяется, что остаётся и какие факты неизвестны.
Состав UI выбирает UI/Design; эта спецификация не выбирает CSS/компоновку.
В scope: shared Python comparison, additive API/TS types, frozen response,
контрактные/доменые тесты и рендер существующего step4.
Не входит: генератор/правила дозировки, медицинская пригодность, перегенерация
старого плана, matching фактических занятий, автоматический перенос тренировок,
provider I/O, live SQLite writes, новая таблица/миграция/backfill, полный redesign.

## Observed / Inferred / Verified by

Observed: в edit пользователь не смог понять изменение по candidate-only экрану;
историю/записи распознал отдельно. Это acceptance finding, а не нарушение прежнего
AC3, который разрешал unavailable-comparison fallback. Ответы не превращаются в
выдуманный процент usability или доказанную причину всех проблем экрана.

Inferred: датированные before/after факты позволят объяснить решение. Дешёвый
опровергающий тест: проверить, не передаются ли они уже целиком frozen DTO.
Verified by: повторён M1 probe на3f75915:8→4нед,999→433TSS, before weekly arrays
без дат; calculation не меняет таблицы, сеть0. Новый осмотр raw synthetic checkpoint
подтвердил сохранённые daily dates, constraint_summary.available_hours и
available_day_indices, session_templates[].sessions, materialized_steps. Поэтому
исходные факты доступны серверу, но отсутствуют в публичном сравнении. Это
characterization, не новый RED будущего контракта и не успешная human acceptance.

## Инварианты источников и идентичности

1. Baseline — только raw latest_checkpoint из BuildInputSnapshot.sources,
   выбранный в той же read-транзакции по lifecycle.base_checkpoint_id/cycle.
   Не MAX(checkpoint), не последующий GET, не сегодняшний planning_profile.
   Сопоставление checkpoint/cycle/revision уже защищает S2; расхождение —
   существующий stale/corrupt исход, не другой baseline.
2. After — final serialized checkpoint после normalize_build_loads, bound
   prescriptions и M4 repairs. Нельзя сравнивать промежуточную генерацию с
   окончательным планом. Projection ничего не меняет в checkpoint или дозировке.
3. Старый raw snapshot не проходит restore_goal_plan_from_checkpoint:
   восстановитель может дополнить/перегенерировать отсутствующие назначения.
   Для сравнения известны только реально сохранённые факты.
4. Сравнение входит в response_json того же retained preview. Confirm получает
   только preview_id/confirm; повтор возвращает исходный comparison, даже когда
   receipt исторический. Никакой повторной сборки сравнения на confirm/replay.
5. Новые dependency reads или новые persistent owners не нужны. Projection
   использует уже захваченный checkpoint и кандидата; version comparison хранится
   внутри поля. Не менять dependency-digest protocol ради presentation extension.

## Public contract: additive comparison v1

Новый optional `comparison: PlanBuildComparison | null` в BuiltPlanResponse и
BuiltPlan TS. Every newly prepared v2 response содержит объект; старый pending,
legacy receipt, protocol1 и ранее сохранённые JSON допускают отсутствие/null.
Отсутствие comparison не создаёт нового publication gate. UI честно сообщает
неполноту, старый confirm продолжает следовать S1/S2/M4 guards.

PlanBuildComparison:

    version: "plan-comparison-v1"
    status: "complete" | "partial" | "no_baseline"
    base_checkpoint_id: int | null
    base_cycle_id: str | null
    base_cycle_revision: int | null
    before: PlanComparisonSide | null
    after: PlanComparisonSide
    days: PlanComparisonDay[]
    counts: {added: int, removed: int, changed: int, unchanged: int, unknown: int} | null
    reasons: string[]

`no_baseline` только при start_new без выбранного исходного checkpoint; это не
нулевой старый план. Replacement с closes_cycle_id показывает выбранную старую
версию, но новое cycle namespace и историю не связывает с ней как одну lineage.
`complete` означает полноту перечисленных comparison facts, не безопасность
назначений. Любой неизвестный обязательный факт/день даёт partial и reason.
Unknown names/values в legacy не превращать в defaults.

PlanComparisonSide:

    scope: {start_date: ISO-date, end_date: ISO-date} | null
    parameters: {goal_type, distance, planning_mode, intent, focus, demand:
                 str|null; available_hours: float|null;
                 available_days: string[]|null; events: RaceEvent[]|null}
    total_tss: int | null
    peak_tss: int | null
    schedule_status: "complete" | "partial" | "unavailable"
    reasons: string[]

After parameters — resolved build parameters и applied goal.events.
Before — только saved goal_plan_snapshot: goal/distance через существующее
публичное отображение без defaults; intent из planning_intent; focus из
planning_focus; demand из demand_level; availability из constraint_summary;
events из явно сохранённого списка. Валидный пустой список/0 сохраняется;
отсутствие/null/невалидное значение остаётся null с reason. Текущие user settings
не являются доказательством старой доступности/цели.

Scope — min/max реальных валидных raw daily dates (существующий stored_day
разбирает ISO date/datetime, не подставляет timezone). Не event_date, created_at,
start_week+horizon или rebuild. Конфликтующие/дублированные/неупорядоченные даты
делают schedule partial, не молча сортируются в supposedly complete evidence.
Неполная внутренняя дата не становится отдыхом. Отсутствующие края не угадываются;
известный enclosing lifecycle при противоречии не маскирует сохранённый data gap.
Before bounds должны совпасть с raw cycle bounds из captured ownership; при
противоречии scope=null с reason, не якобы полный укороченный календарь.
After scope равен lifecycle, а не префиксу первой тренировочной недели.

Total/peak — существующая canonical effective-build агрегация над полным
валидным saved daily plan и валидным weekly_summary, охватывающим те же даты,
с округлением один раз. Нельзя суммировать округлённые weekly display numbers
или подставлять top-level legacy total, если полнота/источник не доказаны.
Если saved weekly_summary неполон, peak=null; при полной daily области total
может оставаться известным. race_forecast_loads не тренировочная нагрузка.
Нет scalar delta/процентов или общей «недельной экономии» между разными областями.

## Датированное расписание без угадывания lineage

PlanComparisonDay:

    date: ISO-date
    change: "added" | "removed" | "changed" | "unchanged" | "unknown"
    before: PlanComparisonDayValue
    after: PlanComparisonDayValue

PlanComparisonDayValue:

    state: "scheduled" | "rest" | "outside" | "unknown"
    phase: string | null
    tss: float | null
    sessions: PlanComparisonSession[] | null

PlanComparisonSession содержит kind/sport/role/focus/name (nullable strings),
minutes/tss (nullable finite numbers), transition_minutes (nullable), steps и
legs. Steps используют существующую public projection name/intensity/
segment_kind/duration_seconds/target, без пересчёта target. Legs содержат те же
человекочитаемые поля и steps в сохранённом порядке. Нет raw provider/selection
payload, engine IDs, медицинских интерпретаций или нового workout matching.

`days` — отсортированное объединение календарных дат известных областей двух
сторон, включая внутренние пропуски; при неизвестной области — только
доказанные raw dates без догадки о краях. Каждая сторона
валидирует собственные daily rows и template dates; никакого index zip/подбора
ближайшей даты. Explicit sessions=[] при total_tss=0 означает rest. Отсутствующий
sessions/день/поломанная структура означает unknown; top-level primary template
не заменяет отсутствующие executable sessions. Outside — дата строго вне
полностью известной области стороны; в неполной области это unknown.

Полное сравнение пары выполняется только по одинаковой календарной дате.
Scheduled→rest/outside = removed (назначение, не activity/history),
rest/outside→scheduled = added. Обе scheduled сравниваются по полному public
prescription content: kind/sport/role/focus/name, конечные minutes/TSS,
transition, нормализованные steps/legs, materialization/structure status.
Идентификаторы session/leg/cycle, fingerprint, creation, source/counter и версии
движка не являются содержанием тренировки. Они не делают день changed.
Обычные sessions сравниваются как multiset с сохранением повторений; порядок
legs/steps внутри composite важен. Изменённые target/steps при прежних TSS/minutes
всё равно дают changed. Разный phase тоже changed и должен быть виден.
Обе rest = unchanged при равном phase. Любой unknown = unknown, не unchanged.
Для no_baseline все days unknown (нет доказанного «было0»); UI показывает новый
план без выдуманного счётчика добавленных относительно отсутствующего плана.

Counts считают **календарные дни каждого change**, не тренировки/activities.
UI так их и подписывает. Counts заполнены только при complete обеих сторон;
при partial/no_baseline они null, а доступные day rows остаются доступны без
ложно полного счётчика. Missing stats не отображать как0. Между разными датами не выводить «перенесено»: без
явной подтверждённой связи показываются removed и added. Нет вывода о причине
изменения или выполнении занятий. Для replacement before/after — разные циклы,
сравнение содержимого не создаёт cross-cycle session identity.

Ограничение: не более366 saved daily rows и366 templates на сторону. При
превышении не обрезать молча и не делать выводы об удалённых назначениях:
schedule_status=unavailable, counts=null; доказанные dates противоположной
стороны могут остаться с change=unknown, но большого date expansion нет,
reason=schedule_too_large. Существующий поддержанный16-недельный preview
попадает в предел; runtime/perf проверяется на нём. Numeric comparison не
вызывает provider/AI, не берёт writer lock и не вызывает reconciliation.

## Presentation contract / наблюдаемая приёмка

Edit/replacement до confirm явно различает «Текущий план» и «Предлагаемый».
Период, цель/намерение, доступное время/дни и итог TSS каждой стороны доступны
вместе, с указанием unknown и неизменных значений. Назначения показываются по
датам с before/after: что добавилось, убралось, изменилось и осталось.
Только частичные legacy поля могут использовать unavailable fallback;
новый complete edit не ограничивается «Сохранится новая версия».
При разном периоде обе даты видны рядом с соответствующим итогом, нет вывода
об интенсивности из разницы whole-period totals. TSS не часы и не fitness verdict.
В historical/applied/uncertain режиме labels не называют старую baseline текущим
планом сегодня; содержимое сравнения остаётся тем же, transport actions прежние.

## BDD / RED matrix

| ID | Given / When / Then | Проверка |
| --- | --- | --- |
| CMP01 | Complete edit8→4: обе frozen области/параметры/999 и433 видны со своими датами; delta−566 не weekly claim | Новый domain/API assertion сначала RED: comparison отсутствует |
| CMP02 | Одинаковый период, меняется доступность/цель: paired facts old/new; unchanged fields не пропали | domain + browser |
| CMP03 | Один календарный день изменён, другие прежние; даты важнее array index | day projection cases |
| CMP04 | Сдвинутые/частично пересекающиеся/disjoint горизонты | explicit outside, no index pairing/no moved label |
| CMP05 | Actual rest0≠missing day/sessions/null/invalid/duplicate dates | partial + unknown, never fabricated rest/remove |
| CMP06 | Multiple sessions/composite; IDs/engine versions изменились, content прежний; targets/steps изменились при той же сумме | unchanged for identity-only; changed for prescription; duplicate multiplicity and leg order preserved |
| CMP07 | Missing old availability/goal/weekly rows/daily scope; old source restore could regenerate | raw-only data gaps; monkeypatch restore запрещён comparison builder |
| CMP08 | Start_new без baseline и replacement с выбранным baseline | no_baseline vs own scoped before, no zero plan/cross-cycle IDs |
| CMP09 | Preview создан, current изменился/закрылся; old receipt повторён | frozen bytes retained; stale before first confirm; historical replay not reactivated |
| CMP10 | Lost confirm response; retry/restart; injected failure | same identity/comparison; no duplicate checkpoint; atomic rollback unchanged |
| CMP11 | Старые pending/receipt/protocol1 без поля; malformed/partial optional response | читаемы/unknown, no new gate/current lookup |
| CMP12 | Чистый расчёт/prepare/full reset | calculation all tables unchanged; prepare только existing pending owner; reset removes retained comparison with row, checkpoint history untouched |
| CMP13 |16weeks/366bound/overflow366, no providers, real raw sums vs rounded displays | bounded result/reason; no silent truncation; existing preview budget <10s |
| CMP14 |390/900/1280 light/dark, keyboard, unknown-save lock | observable paired values, local scroll only, old actions/alerts retained |

Тесты реализации: tests/smoke/test_planning_build_comparison.py (pure/domain),
новый API response/replay coverage в существующих confirmation/cycle modules,
tests/e2e/test_planning_confirmation_s4_ui.py (реальное edit/replacement),
API↔TS extractor/registry. Matrix требует independent checker, затем честный
RED→GREEN. Будущий test method name не считается уже выполненным evidence.
Owner проверка после UI: понимает, чем отличаются обе версии и последствия
подтверждения. Предыдущие ответы/подсказки сохраняются как историческое evidence.

## Failure / reset / rollback / identity

Новых таблиц/cursor/settings/команд нет. Comparison живёт внутри существующего
pending response/receipt и стареет/удаляется с ними. Full reset использует
существующий lifecycle owner. Read-only projection не чинит старый checkpoint;
при неполноте даёт reasons/partial, не отказывает готовому M4 plan по новым
порогам. Failure во время расчёта не меняет current; confirm transaction и
rollback принадлежат S1/S2. Corruption нового comparison JSON не оправдывает
чтение свежего baseline на replay. UI не может изменить compare facts.

## ASR / ADR / delivery / evidence

ASR-REL-1/2: history не теряется; unknown/stale/frozen replay честны.
ASR-MOD-2/3: pure Python policy, additive API/TS, legacy JSON без backfill.
ASR-PERF-4: уже captured inputs, bounded projection вне writer transaction.
ADR-0001/0002/0005/0006/0009 переиспользованы; новый ADR:N/A — отдельного storage,
transport или decision authority не возникает.

C1 Spec/Architecture: этот slice spec + updated ExecPlan/AC, raw evidence,
independent review. C2 Domain/API: typed contract + RED→GREEN pure comparison,
frozen response/receipt integration, API/TS extraction и regression. C3 UI/Design:
paired rendering в approved contract, real browser/prototype. C4 Integrator:
whole checks/current CI, remaining owner scenarios, native scoped round2/2,
явное human review acceptance/merge. Новые milestones не сбрасывают review ledger.

Definition of Done: CMP01…14 доказаны; exact provenance и missing-data границы
проверены; green relevant/broad/contract/web; owner feedback и coaching записаны
честно; ноль открытых P1, P2 disposed, merge только владельцем. Пока DoD НЕ выполнен.
Evidence bundle: docs/reports/2026-10-23-planning-comparison-m1/README.md.
Changed runtime contracts: планируются additive, пока unchanged. Review findings:
NOT YET; unresolved new review threads:N/A; final verdict:AUTHOR DRAFT, не READY.
