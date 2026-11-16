# #625 — защита тестовых и служебных входов в SQLite

Этот ExecPlan ведётся по [.agent/PLANS.md](../.agent/PLANS.md). Он описывает
весь срез. M1 принят и merged #734 как b68fc69; M2 принят и merged #738
как 1c2e4c4. Текущий scope — M3: подключение защиты к acceptance и
служебным командам. Личная БД и работающие services вне scope.

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
- [x] (2026-10-28) M2: два review-раунда, исправления и owner merge #738.
- [x] (2026-10-28) M3: owner accepted review и merged #740 как 1fd39a8.
- [ ] M4: локальная synthetic приёмка/совместимость завершены; draft PR, CI, независимое review и owner merge впереди.

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


## M2 native review round 1 — 2026-10-27

Native review on 01b0f978cd22 returned two P1 findings, 1/2 rounds. Both
were reproduced before changes in a tracked synthetic source copy: seven
RED cases. Four child invocations allowed startup flags that disable the
site guard when hidden after option arguments or combined with other flags;
three URI probes with literal LF/CR/TAB returned exit 0 rather than refusing
an unowned child-scope SQLite destination. No personal data or services used.

The child handoff parses Python startup options, skips values of -W/-X and
--check-hash-based-pycs, rejects -I/-S/-E even in combined flags, and stops
at -c/-m, script or --. Tests cover both split and attached option values and
verify that safe startup flags and script arguments remain usable. SQLite URI
parsing rejects literal C0/DEL controls before urlsplit can strip any of them;
valid memory URIs remain supported. These are test-runner changes only.

GREEN: initial 7/7 reviewed reproductions; expanded related contour 323 passed,
1 existing Starlette warning, 19.98s, parent-only SQLite counts 1383/0. Full
contributor-safe and current-head CI pending; their final result belongs in the
PR evidence bundle. Each native finding is answered in its own thread with
fixed-in SHA and verification; a possible second native round is delta-only
and requires its own request. The unresolved HTTP500 investigation remains
#739 and is not asserted to be caused or fixed by these two changes.

## M3 execution — 2026-10-28

M2 #738 merged as 1c2e4c42f628af8965c2afa912c9027f6358dfe8 after
owner acceptance of delta review 2/2. M3 branch starts from that exact main.
M3 applies the accepted M1 contract to acceptance/E2E, diagnostic and
maintenance callers and operator guidance. Product Database._connect remains
unchanged. The parent issue stays open until M4 acceptance.

The first slice characterizes acceptance startup before doctor/seed/server and
provides a private owned root with revalidated child settings; subsequent
slices cover service reset and ordinary demo-family checks, then diagnostic and
maintenance write/preview paths, browser opt-in, and finally integrated
regression plus runbook. Each slice records RED and GREEN without personal data.
Only artificial temporary stores and credential-free subprocesses are allowed;
no live server, provider, user database, .env or backups are read or changed.

M3 acceptance checkpoint: **Observed** baseline run_acceptance.sh accepted an
external synthetic ACCEPTANCE_DB_PATH and invoked a stub runtime, exit 0.
**Inferred** an override could reach doctor/server before ownership validation.
**Verified by** synthetic RED test test_acceptance_refuses_external_database;
no actual server or user DB was used. The new launcher creates a private scope,
rejects external DB/demo/chats overrides before runtime, clears credentials,
passes a verified receipt to the child and rechecks the selected store before
seed/reset. Ordinary product selection/Database._connect are unchanged.

The accepted default synthetic launch reaches an actual Streamlit health check
on a temporary loopback port and is stopped afterward; this is not a browser
acceptance or live-user restart. An initial health attempt exited at Streamlit's
first-run email prompt because HOME was intentionally fresh. Verified against
installed Streamlit configuration, headless mode and disabled usage statistics
remove that prompt; rerun GREEN. Acceptance, child recheck, reset and M2 guard
contour: 75 passed. Full M3 entrypoint coverage, operator backup workflow,
browser/live opt-in and M4 acceptance remain pending.

M3 product demo-family checkpoint: **Observed** real/demo validation accepted
future real database `-wal`, `-shm`, and `-journal` names as separate demo
names. **Inferred** a future sidecar could collide with a demo target.
**Verified by** three synthetic RED cases with no files; all became GREEN after
family validation. Existing product demo/path/acceptance contour: 84 passed,
1 existing Starlette warning. The ordinary product does not receive a scratch
root requirement; only overlapping database families are refused.

M3 maintenance checkpoint: **Observed** direct provider-link apply invoked
preview/write helpers without confirmation, and distance backfill reached its
client before validating a target. **Inferred** explicit operator boundaries
were bypassable through direct Python calls. **Verified by** two synthetic RED
cases with stubs (no database/provider call), then GREEN. Four maintenance
entrypoints now require explicit CLI target, preview read-only, and validate
before apply/provider calls. Owned scratch targets use scope identity; working
writes require --apply, --confirm-working-database, --confirm-stopped and an
existing backup. The helper compares integrity/schema/content fingerprints of
the stopped target and backup; stopped state remains operator-attested.
A synthetic WAL-aware backup matched; an altered source refused the stale
backup. Focused maintenance/acceptance/planning contour: 40 passed, one existing
Starlette warning. Remaining M3: legacy add/clean diagnostics, acceptance/E2E
and live entrypoint guards, operator docs and full integration/CI.

M3 E2E and parity checkpoint: two legacy live browser probes read synthetic
credentials without opt-in in RED. They now require an explicit named URL and
--confirm-live-acceptance before credentials, browser, output or network; no
live probe was executed. E2E creates a child owned session scope, verifies
DB/demo/chats in parent and in child site startup, and cleanup rechecks the
session identity. Parity capture bootstraps before Settings, uses an owned
child scope, and validates cleanup. Combined focused: 94 passed; forced E2E
setup failure: 1 passed. Synthetic TestClient capture returned 37 endpoints;
non-200: planning/build-context 422 and planning/events 503, so this is safety
and execution evidence, not a claim all endpoints succeeded or baseline parity.

M3 standalone and legacy checkpoint: **Observed** a standalone diagnostic,
run without pytest, accepted a synthetic external DATABASE_PATH and added
37 schema tables to the sentinel store. **Inferred** pytest-only bootstrap
could not protect direct script execution. **Verified by** a credential-free
subprocess against an owned synthetic sentinel: before 38 tables total; after
startup guard, 1 unchanged sentinel table and nonzero exit. Twenty-one legacy
standalone test files with implicit Database() now bootstrap before product
imports. No personal path was accessed. Legacy add/cleanup scripts now use a
private synthetic store by default, guard explicit working writes, and preview
without writes. Cleanup preserves similar non-test identifiers and HRV unless
separately selected. Direct generator bodies also refuse an unvalidated path.
Focused contour: 190 passed, one existing Starlette warning. The first local
attempt's socket bind was sandbox-denied; a permitted isolated loopback rerun
passed, including actual temporary Streamlit health. No user service was run.

M3 integrated author checks on code tree 6a05198: focused 195 passed. An
operator-flow test accepts a matching synthetic backup; direct generator body
calls with an unvalidated path refuse before Database. Imports of the two
repair modules do not load application Settings before their gate. An earlier
complete contributor-safe snapshot produced 4281 passed / 16 skipped / 116
deselected (its shell wrapper then exited nonzero because `status` is read-only
in zsh; the pytest summary itself reported no failures). A final full repeat
on 6a05198 is recorded separately below.

Browser E2E on the matching synthetic code snapshot: 91 passed, 1 failed in
`test_edit_different_horizon_has_dated_before_and_after[900-light]`: after the
cycle-close success message, the expected no-current-cycle heading did not
appear within 5 s. One isolated repeat of that exact test passed. The cause is
not established and this is not a green full-E2E claim or evidence linking it
to #739. No browser test used the user's service or database.

Final contributor-safe run against identical code/test contents of 6a05198:
4286 passed, 16 skipped, 116 deselected, 7 warnings, exit 0 in 311.79 s.
Ruff, diff check and 55 local documentation links passed. Snapshot comparison
found no mismatch in all 46 changed code/test files. Browser limitation above
remains open; the remote current-head CI and independent review are separate.

## M4 acceptance started — 2026-10-28

M3 owner accepted and merged #740 as 1fd39a82a61f9358971e93c7ec36cffe08ed1721;
reviewed and merged trees match. M4 branch starts from that main. The issue
#625 remains open pending the complete synthetic acceptance and independent
review. #741 tracks an existing UI refresh problem separately.

First combined specified contour on the isolated source at 1fd39a8: 291
passed, 1 Starlette warning in 19.22s; test audit reported 839 allowed SQLite
connections, 0 blocked in the parent process. This does not by itself certify
all subprocess connections. An exploratory ordinary product run without the
scratch guard used two artificial stores, TestClient demo seed/clear, and a
synthetic marker in the real store; the marker survived and both routes returned
200. The outer test process still blocked network/SQLite outside its private
root; this is not live service or personal DB evidence. Reproducible acceptance
and complete runtime audit, full suite, E2E and native Windows assessment remain
pending.

M4 reproducible product compatibility probe:
`docs/reports/issue-625-m4/product_compatibility_probe.py`. It owns a private
root, starts two credential-free ordinary product Python processes without the
scratch runtime guard, records and bounds actual SQLite opens with a probe-only
pre-import audit hook, blocks network/dotenv, seeds demo, restarts, clears demo,
and verifies an independent synthetic real-store marker survives. Run from an
isolated source snapshot: seed 18 opens PASS; restart/clear 8 opens PASS. The
probe is acceptance instrumentation, not a new product guard. The pre-existing
normal product `_connect` remains unchanged. `git check-ignore --no-index
--stdin` separately matched the four SQLite family names without creating any
files. Complete suite and browser checks are running; native Windows is NOT RUN.

M4 author acceptance on synthetic source snapshot: combined 291 passed; full
contributor-safe 4286 passed / 16 skipped / 116 deselected, 7 warnings,
315.09s; browser E2E 92 passed, one warning, 237.97s. Probe-only ordinary
product lifecycle/restart and git-ignore stdin evidence above remain separate.
Runtime audit reported 28116 SQLite opens and zero denials in the main full
pytest process; E2E parent reported 261/0. These counts are process-local, not
an aggregate claim for every child. Targeted child escape tests and early child
bootstrap are the child evidence. 819 tracked source/config files in the test
snapshot match this branch byte-for-byte; changes since the tested main are the
acceptance probe and documentation. Ruff and diff check pass. Native macOS was
used; Linux is remote CI pending and native Windows/ACL NOT RUN. Previous #741
E2E symptom is not declared diagnosed or fixed by this green run. Evidence map:
[acceptance matrix](reports/issue-625-m4/acceptance_matrix.md).
