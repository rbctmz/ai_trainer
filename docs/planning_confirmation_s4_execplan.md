# Planning S4: объяснимое подтверждение

Этот living ExecPlan следует .agent/PLANS.md. Задача#714, родитель#677;
дата2026-10-22 Europe/Moscow. [Спецификация](planning_confirmation_s4_spec.md).
Baseline main00de158; S1/S2/S3/M4 уже слиты. M1 завершён в роли Spec / Architecture Owner;
M2 UI/Design завершён; текущая роль Supervisor/Integrator выполняет M3. Class B для будущего UI-поведения на существующих контрактах.

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
- [ ] M3 owner comprehension: запрошены ответы по A/B/C/D; NOT YET, отсутствие ответа не считается успешным. Static screenshot comprehension не заменяет interactive/assistive-technology usability.
- [ ] M3 native review:0/2 на момент этой записи; запрашивается на стабильном итоговом HEAD после CI. Может выполняться параллельно ожиданию owner responses; не заменяет их.
- [ ] Owner acceptance / merge: отдельное явное решение после M3, пока не запрошено и не выполнено.

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
