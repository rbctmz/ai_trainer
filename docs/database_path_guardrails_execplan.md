# #625 — защита тестовых и служебных входов в SQLite

Этот ExecPlan ведётся по [.agent/PLANS.md](../.agent/PLANS.md). Он описывает
весь срез. M1 принят владельцем и merged #734 как b68fc69; цель M2 разрешена
26 октября: Domain/API Implementer реализует helper/раннюю pytest isolation.
Acceptance/maintenance M3 и личная БД/services остаются вне текущего scope.

## Purpose / Big Picture


Тестовый запуск должен либо использовать созданную им временную БД, либо
отказать до открытия чужой БД. Обычное приложение продолжает читать и писать
свой store. Результат можно проверить на синтетическом защищённом файле:
ошибочная цель не открывается и не меняется, штатная временная цель работает.

## Progress


- [x] (2026-10-25) Создана цель M1; чистый изолированный worktree, baseline 12615561218bf2b5e5288d3a5ed2f9cf01f11145.
- [x] (2026-10-25) Прочитаны issue/owner decision, workflow, PLANS и ASR/ADD; сверены основные входы.
- [x] (2026-10-25) Synthetic probes повторены, спецификация/инвентарь/RED matrix и self-review готовы; Ruff/58 local links/diff GREEN.
- [x] (2026-10-25) M1 опубликован отдельным draft PR #734; issue #625 актуализирован, current-head CI выполняется.
- [x] (2026-10-26) M1 clean native 1/2 на 2c08b95, owner accepted/merged #734 b68fc69; reviewed/merged trees identical.
- [x] (2026-10-27) M2 helper, bootstrap до Settings/collection, launcher/CI и необходимые fixtures реализованы; focused 238 passed.
- [x] (2026-10-27) M2 self-review/RED→GREEN: focused 310 passed; full 4233 passed /16 skipped /116 deselected. Draft PR #738 опубликован; current-head remote CI проверяется отдельно.
- [ ] M2: independent review и отдельное owner acceptance/merge.
- [ ] M3: acceptance и служебные команды; RED → GREEN.
- [ ] M4: общая synthetic приёмка, совместимость, итоговое review/owner merge.

## Surprises & Discoveries


Observed: после #624 уже существует `config/database_paths.py`; Settings
выбирает абсолютный путь. `tests/conftest.py` всё ещё импортирует Settings
до какой-либо изоляции. `run_acceptance.sh` принимает произвольный
ACCEPTANCE_DB_PATH. Inferred: старый план #625 недостаточен; отрицательное
сравнение с Settings после override может сравнивать уже подменённую цель.
Verified by: probe на baseline 1261556: один legacy case skipped/exit0,
но создал synthetic store с 37 таблицами до инспекции; stub acceptance получил
путь вне session; pure selection изменился после override. Existing demo-path
predicate пропустил имя real sidecar; это characterization predicate, без
демо-seeding/доказательства повреждения. Pure samefile распознал native
symlink/hardlink. Все четыре ignore strings прошли без artifacts. Полного
runtime census не было; AST: 30 прямых вызовов / 27 файлов, не count writes.

## Decision Log


2026-10-25, Spec / Architecture Owner: текущий срез — Class A, поскольку
создаёт границу доступа к персональной БД и контракт между runner/config/CLI.
Прежняя Class B оценка issue историческая. Runtime, UI, schema и личные данные
в M1 не меняются. Существующий pure path resolver переиспользуется; глобальный
guard в `Database._connect` исключён решением владельца #622.

## Outcomes & Retrospective


Author M1 завершён: подготовлены короткий контракт, актуальный inventory и synthetic
probe/evidence. M1 #734 принят владельцем и merged b68fc69 после clean native 1/2 на 2c08b95, zero threads/CI GREEN. Исторические pending snapshots ниже не являются текущим статусом. Broad Python/UI suite локально N/A, product diff отсутствует.
Числа старой разведки сентября не являются текущей runtime-оценкой.
M2 author implementation и локальная приёмка готовы в draft #738; independent review/owner merge, M3/M4 остаются впереди. #625 не закрывается этим этапом.

## Context and Orientation


[Спецификация](database_path_guardrails_slice_spec.md) содержит контракт и
матрицу проверок. `config/database_paths.py` выбирает имена без Settings/SQLite;
`config/settings.py` загружает dotenv при импорте; `data/database.py` создаёт
схему в конструкторе. `tests/conftest.py` исполняется до test modules, но
обычная autouse fixture — уже после импорта и потому слишком поздно.
`run_acceptance.sh` запускает legacy Streamlit; `tests/e2e/conftest.py`
запускает API/web с собственными временными БД. `scripts/backfill_*.py`,
`repair_planning_materialization.py`, legacy `tests/add_*`/`clean_database.py`
— отдельные входы, а не обычные product writers.

Self-review: тест-inspector первоначально проверял существование файла после
своего SQLite open; это могло дать ложное доказательство. Исправлено до записи
итога: assertion и captured existence идут до inspector, pytest outcome теперь
явно записан как skipped. Передача external target в acceptance подтверждена
только stub, приложение/сервер не запускались. Future alias/cleanup refusal и
Windows НЕ проверены этим probe. Защита только по post-override Settings
отвергнута как недостаточная; positive ownership и ранний harness — выбранный
контракт, а не уже поставленная реализация.

## Plan of Work


M1 завершает только документы и воспроизводимые probes. M2 реализует pure
helper и bootstrap до Settings/collection; автором выступает Domain/API
Implementer. M3 подключает helper к acceptance/maintenance и обновляет
каноническую operator границу. M4 проверяет полный contributor-safe набор,
отказы subprocess, reset/cleanup и обычную запись приложения. Каждый этап
заканчивается отдельным evidence bundle; расширять product surface нельзя.

## Concrete Steps


В изолированном worktree, используя Python с установленными runtime/dev deps:

    python docs/reports/issue-625-m1/probe.py
    git diff --check

Probe читает только tracked исходники через git archive, создаёт уникальный
TemporaryDirectory и дочерний whitelist env без credentials. До product imports
отключает dotenv и ставит audit-hook на SQLite вне принадлежащего probe root;
внешний network и чтение .env блокируются. Защищённая БД здесь — искусственный
sentinel, не копия личной БД. Probe budget: один legacy pytest case, один stub
acceptance launch без Streamlit/server, pure path cases и AST census, ≤60 секунд.
Гипотеза: прежняя строка Settings достаточна для scratch-защиты. Опровержение:
override меняет identity, либо acceptance передаёт external-to-session target,
либо legacy case создаёт БД до skip. Результат не является GREEN новой защиты.

## Validation and Acceptance


M1 принят для передачи, когда source inventory имеет baseline SHA, probes
повторены на финальном дереве, спецификация разрешает ambiguity до реализации,
локальные links и diff проходят, а PR явно остаётся spec-only. Для M2–M4
focused команды и ожидаемые отказы названы в спецификации; broad result нельзя
выводить из AST/probe. Review manual, максимум два native rounds на PR; запрос
отдельным поручением владельца, merge только его решением.

## Idempotence and Recovery


Probe каждый раз создаёт собственный root и удаляет только его. Ошибка дочернего
процесса прекращает эксперимент; нельзя повторять его с личными путями. M1
откатывается удалением docs changes; данные и runtime не изменены. Будущая
защита не перемещает/восстанавливает БД и не вводит persistent registry.

## Artifacts and Notes


`docs/reports/issue-625-m1/probe.py` — воспроизводимый исследовательский helper,
не runtime guard и не regression test. `evidence.json` — агрегаты и synthetic
наблюдения без абсолютных user paths/credentials/данных. Источник #730 outcome
записывается в process metrics в этом содержательном changeset.

## Interfaces and Dependencies


Только stdlib + уже установленные pytest/python-dotenv/runtime dependencies.
Нового API/TS/schema/dependency нет. Предлагаемые helper interfaces и основания
отказа заданы в спецификации; product `Database._connect` не зависит от helper.

Редакция 2026-10-25: создан M1 brief до эксперимента; цель — заменить устаревшую
разведку актуальным воспроизводимым основанием, не начать runtime работу.

Редакция 2026-10-25 после probes: recorded skip/schema, stub acceptance и
ignore-no-artifacts; исправлена проверка pre-inspection existence. Public
contracts/CLI compatibility и остаточная runtime-неопределённость названы явно.

Редакция 2026-10-25 при публикации: draft PR #734 и issue #625 связаны;
нативное review не запрошено, accepted/ready labels не ставились. Author M1
готов, source candidate не содержит runtime изменений; CI outcome — PR bundle.

Редакция 2026-10-26: owner handoff M1 → M2, изолированная ветка codex/issue-625-m2-pytest-isolation от b68fc69. RED cases не запускаются на personal DB.


## M2 runtime implementation and evidence — 2026-10-27


Domain/API Implementer работает по принятому M1, baseline b68fc69. В
`config/database_paths.py` добавлены safe URI parser, SQLite-family predicates и
pre-override candidates capture. `scripts/scratch_runtime.py` создаёт private
root и transient private owner receipt; проверки inode/owner/receipt не позволяют
объекту произвольно присвоить существующий каталог. Cleanup доступен создателю,
не идёт по nested symlink и отказывает при замене root. Продуктовые таблицы,
Settings и Database._connect не меняются.

`tests/conftest.py` вызывает bootstrap до Settings; launcher
`scripts/run_isolated_tests.py` — ещё до pytest/plugin loading. Тестовый audit
проверяет SQLite opens, чтение credentials, non-loopback network и наличие
наследуемого scope/site guard у subprocess env. Custom env без handoff
отказывает, helpers child_environment/fresh_child_environment дают явную
передачу той же либо новой дочерней области. Это защита test runner от ошибок,
не sandbox для hostile shell/native programs. Startup Python с -I/-S/-E,
который отключает site audit, не допускается. Исторические explicit child env
в DB path/migration fixtures подключены к тому же handoff; семантика migrate
без Settings/при invalid DATABASE_PATH сохранена.

Исходный pre-implementation RED dce8844: collector с explicit external
synthetic DATABASE_PATH завершился 0/1 passed; требуемого отказа не было.
Default collector не получал подготовленного scratch store, basetemp guard
отсутствовал, helper imports ещё отсутствовали: 13 failed / 1 passed после
исправления внешней experiment fixture. Самая первая попытка не является
product RED: старый внешний audit запретил создать даже synthetic .env;
он уточнён только внутри принадлежащего experiment root, вне него отказ сохранён.

Observed: первый full contour с начальной защитой дал 7 failed / 4201 passed /
18 skipped / 116 deselected, 329.15s. Все 7 отказов — относительные DB paths в
трёх legacy test files. Inferred: им нужна temp cwd fixture, а не разрешение
checkout как scratch. Verified by: fixture в test_data_management,
test_final_app_integration и test_phase1_sync_methods; focused с этими suites
и backup/restore/migrate/concurrency прошёл. Это исправление tests, не regression
в product writer и не маркировка диагностик для сокрытия failures.

Self-review отдельно воспроизвёл два отказа первоначальной реализации. Объект
ScratchScope с известным inode чужого private directory мог удалить его без
созданного данным запуском receipt (RED DID NOT RAISE); обязательная повторная
проверка receipt перед validate/cleanup закрыла случай. Custom child env терял
site audit (RED DID NOT RAISE); test-only Popen handoff guard и helpers закрыли
его. Синтетические sentinel за пределами дочерней области сохранились после
GREEN. SQLite ~ трактуется буквально, в отличие от Settings expansion; parser
сохраняет native semantics, а memory URI проверен с uri=True и False без файла.

Основной focused: 238 passed / 1 existing Starlette warning, 16.84s; parent
SQLite audit allowed=840 / blocked=0. Негативные дочерние probes проверяют свои
отказы отдельно; parent counters не выдаются за global process-tree census.
Final full contour в работе; для каждого нового изменения повторяется только
затронутый focused, после freeze — полный contributor-safe с CI warning policy.
Source snapshot сравнивается по hashes перед публикацией; после тестов только
docs/evidence не требуют нового runtime RED. Ruff/diff check должны быть GREEN.

Отдельный fresh product probe с disabled dotenv/external containment, без
импорта M2 test hooks: Database() создал synthetic store, INSERT/SELECT вернул
ok, without_M2_test_hooks=true. Это совместно с неизменностью product source
подтверждает обычную запись, а не объявляет личную миграцию выполненной.

Transient root/receipt — test artifacts, не продуктовая БД или durable registry.
Нормальный exit создателя удаляет свой root; interrupted run может оставить
private temp directory, новый bootstrap его автоматически не присваивает.
Мёртвый owner/заменённый root/невалидный receipt дают safe отказ. Windows использует
conservative direct-parent handoff, native Windows/ACL не проверены; macOS native
symlink/hardlink/case/Unicode и Linux CI считаются отдельно. Adversarial OS races
не обещаны. M3 acceptance/maintenance и общий M4 остаются отдельными handoffs.

M1 post-merge: #734 merged b68fc69 on 2026-10-26T11:05:43Z, owner explicitly
accepted clean 1/2 at 2c08b95; zero threads, functional CI/Gitleaks/Review gate
GREEN and CLEAN, exact-head normal merge. Reviewed/merged trees identical;
completed M1 branch deleted, M2 branch created from merged main. Outcome included
here without a new docs-only PR; #625/#622 stay open. Никакой personal DB/.env/
backup/provider/service операции; primary runtime checkout не менялся.

Редакция 2026-10-27: M2 implementation/RED и полный первый failure contour
зафиксированы; финальные full/CI/native verdict ещё не заявлены.


M2 finalization checkpoint: full-2 дал 42 failed / 4178 passed / 18 skipped /
116 deselected, 291.44s; все failures — Pilot.env без нового child handoff.
После fixture handoff осталось 20 failures в monotonic helper: системный
Python 3.10 при fake HOME не видит user-site dotenv. Отдельная stdlib probe
подтвердила dotenv_with_fake_home=False; site audit теперь не требует dotenv
для stdlib-only child, но по-прежнему блокирует SQLite/file/network escapes.
Pilot + guard focused: 84 passed / 1 historical missing-session skip, 36.05s.
Это synthetic harness compatibility, не provider/live call. Финальный full-3
на замороженных runtime files запускается перед публикацией; результаты и
remote CI будут в одном PR evidence bundle. Base main повторно проверен и
остаётся b68fc69; M1 raw evidence и принятые AC не переписываются.


M2 SQL boundary correction before native review: a synthetic child probe on
f0d306e returned exit0 and outside_child_scope_created=true for both parameterized
ATTACH DATABASE and VACUUM INTO. Connect-only audit was therefore insufficient.
Test-only connection construction now installs a SQLite authorizer after native
initialization and composes caller authorizers; literal owned destinations work,
foreign/unknown destinations fail before file creation even after caller clears
its policy. Direct factory/connect/dbapi2 entrypoints retain early path audit.
The first handle-event prototype was rejected after ProgrammingError (native
Connection.__init__ was not finished); post-construction GuardedConnection plus
connect wiring is covered by cycle storage/read-only/backup regressions. SQLite
temp path is owned; PRAGMA attempts to redirect temp/data directories refuse.
This policy lives entirely in the test harness, never in product _connect.

A separate pure future-name probe observed native_case_insensitive=true and
future_case_family_blocked=false for absent Future.db / future.DB-WAL. Future
namespace keys now conservatively fold case/Unicode ambiguity without selecting
or renaming files; live selection semantics remain unchanged. Added ASCII/Unicode
and uppercase-sidecar regressions. Final related contour: 310 passed /1 existing
Starlette warning, 19.59s; parent SQLite audit allowed=1383/blocked=0.

Full-3 on the earlier connect-only head: 1 failed /4221 passed /16 skipped /
116 deselected, 307.12s. Busy-port fixture could bind now but its shell PATH had
no python command; run_web fell through to a dependency-install attempt, which
external/network containment blocked before API startup. Fixture now prepends
Path(sys.executable).parent and proves busy refusal before any install/start;
product run_web is unchanged. SQL authorizer and future-name corrections require
a new full contour; previous full results do not qualify the final head.

Candidate draft PR #738 is published; no review requested yet, 0/2 native rounds.
The final post-correction full/CI outcome is pending in its evidence bundle.


Final local M2 contour on e47ad37: 4233 passed /16 skipped /116 deselected,
7 existing warnings, 308.05s under CI warning policy. Parent-only SQLite counters:
allowed=28060 /blocked=1 (exercised refusal, not a process-tree census). The 16
runtime Python/YAML files matched the tested source snapshot; product
Database/Settings have no diff. Ruff/diff and 59 local Markdown links GREEN.
Earlier full/focused results above are historical investigation checkpoints.

Observed in e47ad37 Linux CI: Web contract GREEN, Chromium installation GREEN,
but all browser launches looked under the new scratch HOME's empty
.cache/ms-playwright directory. Verified by job 122061698996, run 40466083013:
BrowserType.launch reported Executable doesn't exist inside scratch home.
The E2E job now sets one explicit PLAYWRIGHT_BROWSERS_PATH under runner.temp for
both install and launch. This is a browser executable cache, not a permitted
SQLite namespace; DB policy is unchanged. Only CI YAML/docs changed after the
local full contour, so that Python result remains applicable. Current-head
remote E2E/contributor-safe/contract outcomes are recorded in the PR evidence
bundle, independently from native review and owner merge. No UI behavior changed.

The initial e9e17ba cache configuration was rejected by GitHub workflow
validation before CI jobs: runner context is unavailable in job-level env.
The final configuration supplies the same runner.temp path in the two step-level
env blocks (install and launch), where that context is available. The failed
workflow is recorded, not counted as an E2E rerun or GREEN evidence.
