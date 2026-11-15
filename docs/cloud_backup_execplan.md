# Подключить проверенные облачные копии без второго runtime (#626 / #752)


Живой ExecPlan по `.agent/PLANS.md`; контракт —
[cloud_backup_slice_spec.md](cloud_backup_slice_spec.md). Текущая работа — только
M2 transport/CLI (#754) после принятого M1 #753. M3 остаётся отдельным этапом;
реализация не разрешает live activation.

## Purpose / Big Picture


После потери Mac атлет сможет получить проверенную SQLite из зашифрованного
Cloud.ru repository. Тренер запускается как раньше; отдельное фоновое задание
копирует только готовые локальные снимки и сообщает давность защиты. Repository —
набор зашифрованных объектов restic, а manifest — описание конкретного SQLite
snapshot с hash и отпечатками таблиц. Вместо самописной криптографии используется
restic, вместо сервера задач — штатное расписание macOS.

## Progress


- [x] 2026-11-14: synthetic Cloud.ru/restic round-trip завершён, exact objects
  удалены; evidence в #626 comment 6879508968. Это не full acceptance.
- [x] 2026-11-14: current main a661c802584f проверен; создана ветка
  codex/issue-626-cloud-backup-spec, M1 issue #752, сформулирован контракт.
- [x] 2026-11-14: 60 relative links / diff check GREEN; independent full+delta
  review READY на a32e497, один P2 fixed; после этого только evidence/progress.
- [x] M1: clean native review 1/2 и explicit owner acceptance; handoff в M2.
- [x] 2026-11-14: M1 #753 merged 1c6f18bb9882 после clean native 1/2,
  explicit owner acceptance и GREEN gate/CLEAN; #752 закрыта, trees совпали.
  Local main synced, известная task branch удалена после восстановления approval
  availability; primary #731 не изменялся. M2 issue #754, отдельная ветка.
- [x] 2026-11-14: M2 initial RED — 24 failures (23 missing cloud module,
  1 missing plist template), scratch SQLite allowed=16 / blocked=0.
  Это absence-of-feature RED, не утверждение о 24 воспроизведённых domain bugs.
- [x] M2: shared transport/CLI и macOS schedule template; 60 focused PASS,
  включая настоящий restic local repository (без облака/личных ключей).
- [x] M2: broad contour4452 PASS /16 skipped /124 deselected;
  independent scoped delta READY на89e2a8f; draft PR #755.
- [x] 2026-11-15: M2 #755 merged27e5405, clean native1/2 наb339cd8,
  explicit owner acceptance6897592867, CI1343/Review gate GREEN/CLEAN;
  reviewed/merge tree e23dfc6378ee55fb8bca446add530da588904e2c совпал.
  #754/#756 закрыты; local main synced, task branch удалена, worktree сохранён.
- [ ] M3 #757: shared status API/web, domain drill и итоговая synthetic приёмка;
  отдельный [M3 slice spec](cloud_backup_m3_slice_spec.md), base27e5405.
- [x] 2026-11-15: M3 spec checker READY, no blocking gaps. API initial5RED
  (404/missing DTO), then10focusedPASS; GET no SQLite/config in demo/no writes.
- [x] 2026-11-15: remote drill7RED after fixture correction; domain/API20PASS,
  M2+drill59PASS, including actual encrypted LOCAL restic and two fresh app reads.
  Foreign/corrupt/lock/write/interruption and removed-local/receipt probes pass.
- [ ] M3 UI handoff: CloudBackupStatus contract is available; browser RED/GREEN,
  contract freshness, full checks, screenshots and final checker remain.
- [x] M3 UI: consumer handoff, browser missing-component RED→40focusedPASS,
  8synthetic screenshots, web lint/build/contract freshness and24contract tests green.
- [x] Broad baseline:4488PASS/16skipped/156deselected,407.06s, scratch31299/0;
  fullE2E132PASS,287.12s, scratch261/0. 35 overwritten old PNGs restored;
  new issue757 screenshots retained. Final Python rerun follows phase correction.
- [x] aa1d61b fixes checker P2: author2RED→7phase/refusalPASS; checker deltaREADY,
  82PASS plus four independent probes. NativeLOCAL full-domain RTO4.362s,
  source/local snapshots/receipt absent and two fresh app reader projections equal.
- [ ] Completion audit lost-source hourly path:1RED, correction and scoped
  verification pending; default/source eligibility remains mandatory.
- [ ] Отдельное решение Greg о retention/recovery custody и live activation.

## Surprises & Discoveries


Observed (M3): full WAL-mode domain fixture initially failed the fake uploader's
readback: `_validate_pair` rejected extra SQLite sidecar files. Inferred: test
double may copy more than real restic's explicit two filenames. Verified by:
staging validation passed, failure trace was pair membership; fake copying only
snapshot.db/manifest.json made existing upload pass. Production transport was
unchanged;7new failures then came from absent drill/cadence, not fixture setup.

Observed (M3): API GET10PASS and domain/API20PASS, including no source DB and
fresh-process full-domain readers. Inferred: independent drill can recover with
lost local artifacts. Verified by: native encrypted LOCAL repository restored
after source/local backup/receipt deletion, same checkpoint/cycle/decision/match/
feedback/readiness/provider/manual projections in two fresh app processes.
This does not establish live Cloud.ru/Keychain/scheduler or personal RTO.


Observed: restic 0.19.1 вернул успешный no-cache restore synthetic snapshot за
1.651 с; wrong-password exit 12, 6 remote objects STANDARD. Inferred: transport
совместим с выбранным Cloud.ru для малого artifact; cheap falsifier — скачать
и сравнить bytes/schema/rows, не ограничиться upload exit. Verified by: сравнения
и штатный SQLite restore прошли, результат записан в issue. Реальная БД/RTO и
domain evidence этим не доказаны.

Observed: services/automatic_snapshots.py держит namespace_lock вокруг publication
и retention, сохраняет version-1 manifest с fingerprint; snapshot_runtime.py
обновляет last_checked_at даже без нового generation. Inferred: независимый
uploader может переиспользовать ready pair без live SQLite/нового engine, но
нельзя держать lock во время сети или считать upload временем покрытия данных.
Verified by: прочитаны _run/_retain/namespace_lock и BackupRuntime.check;
concurrent staging/freshness integration tests включены в M2 synthetic contour.

Observed (M2): две дополнительные race-проверки сначала вернули ready при
переключении dataset_origin во время snapshot и изменении config после initial
binding. Inferred: initial eligibility не доказывает eligibility самого artifact
и стабильность config до staging. Verified by: обе проверки RED (2 failed),
затем проверка origin внутри staging SQLite и digest исходного config дали
47 focused PASS, scratch allowed=114 / blocked=0. Более поздние тесты и итоговый
контур записываются ниже; эти числа относятся только к этому checkpoint.

Observed: ADR-0002 запрещает вынос данных за Mac, а владелец выбрал cloud backup.
Inferred: нужно явное узкое opt-in исключение для ciphertext, не молчаливое
переопределение privacy. Verified by: пункт 4 ADR и owner scope; addendum Proposed,
его принятие/live activation ещё не заявлены.

## Decision Log


2026-11-14, Spec Owner: один restic S3 transport; native LaunchAgent запускает
короткую команду, а не ещё один тренер. Owner отверг второй runtime.

2026-11-14, Spec Owner proposal: fresh check_snapshot существующим online engine
перед каждой hourly отправкой последнего validated snapshot; отдельная
remote readback verification; monthly isolated drill. RPO измеряется по local
checked generation, а не upload timestamp. Это сохраняет честное состояние при
остановленном локальном backup и при отсутствии новых строк.

2026-11-14, Spec Owner proposal: нет автоматического cloud prune в v1. Локальная
14-day/8-week/reset protection unchanged; ранние cloud copies не исчезают при reset.
Рост и стоимость требуют явного owner acceptance перед рабочим включением.

## Context and Orientation


services/sqlite_snapshot_core.py содержит inspect_database и SQLite Backup API.
services/automatic_snapshots.py создаёт immutable snapshot.db/manifest.json в
BACKUP_DIR/<source_namespace>/snapshots/<snapshot_id>, защищает каталог OS lock
и применяет local retention. Source namespace идентифицирует выбранный локальный
путь; generation — fingerprint схемы/типизированных строк, а не дата файла.
services/snapshot_runtime.py вызывает этот сервис после важных commits и при
периодических проверках. Их договорённость не меняется.

api/routers/backup.py и api/backup_contract.py обслуживают local status/check,
web/components/BackupStatusBanner.tsx показывает существующий warning.
scripts/sqlite_backup_restore.py восстанавливает выбранный снимок лишь при
operator stopped confirmation и сохраняет rollback существующей цели.
tests/smoke/test_database_relocation_drill.py и test_snapshot_retention.py
содержат actual domain fixtures/readers; заимствовать их, не заменять голыми
COUNT(*) искусственных таблиц. #625 guards изолируют тесты до imports.

## Plan of Work


M1 заканчивается проверяемым документом и draft PR. Не читать user .env/SQLite/
Keychain, не менять запущенные сервисы, не создавать рабочий repository.
Перед реализацией согласовать policy в companion spec; разработка не является
личным rollout. Native review запрашивается отдельно, максимум два раунда.

M2 добавляет services/cloud_backups.py с prepare/run/read-status/drill boundary
и scripts/cloud_backup.py с explicit config; CLI не импортирует personal defaults.
Config содержит явный database_path + namespace binding, требует local backup
opt-in и совпадение выбранного real store; отсутствующая/неизвестная/demo source
отказывает без создания DB/network. Enabled run сначала вызывает существующий
bounded check_snapshot(reason='cloud_upload'), затем берёт готовую пару.
Disabled/status пути не открывают source. Config/receipt/lock/staging — private
operator data вне Git и SQLite. Settings
лишь разрешает путь cloud config без создания файлов. Сначала RED на no-opt-in,
foreign paths, bad manifest/binding, retention race и timeout; затем reuse пары
под namespace lock, restic subprocess вне lock, readback и atomic receipt.
Метаданные не дают разрешения на чтение произвольного пути. Child env содержит
только выбранные credentials в памяти; diagnostic output фиксирован и очищен.

В том же M2 добавить deploy/macos/ai-trainer-cloud-backup.plist.example и runbook
ручной установки. RunAtLoad + hourly calendar, explicit executable/config paths,
без секретов в plist и KeepAlive. Пропуски при sleep/off не обещают coverage;
никакой автоматической установки job, init или чтения working config в CI.

M3 добавляет CloudBackupStatus отдельно от BackupStatus в api/backup_contract.py,
GET /api/backup/cloud/status в api/routers/backup.py, TypeScript mirror/scenarios
и существующий web warning consumer после Domain → UI handoff. Shared reader
сверяет current namespace/generation и timestamps; GET не делает network/write
и не использует get_backup_database/get_database/Database constructor: только
pure selected-path identity и read-only operational files, без source init/migration.
Затем acceptance восстанавливает actual domains из remote fixture при удалённых
локальных originals/receipt, через fresh readers в новой owned DB. Monthly drill
сверяет весь manifest и обновляет отдельный last_drill_at; failed drill явно виден.

## Concrete Steps


Команды выполняются в корне отдельного checkout. M1: git diff --check и проверка
relative Markdown links четырёх изменённых документов; product tests N/A.
До push зафиксировать independent checker и dispositions. Draft PR закрывает
только #752, ссылается на #626 и не закрывает общую задачу преждевременно.

Для M2/M3 следующие команды — будущий план, а не выполненные проверки:

    python scripts/run_isolated_tests.py tests/smoke/test_cloud_backups.py -q
    python scripts/run_isolated_tests.py tests/smoke/test_cloud_backup_drill.py -q
    python scripts/run_isolated_tests.py tests/smoke/test_automatic_snapshots.py tests/smoke/test_snapshot_retention.py tests/smoke/test_backup_api.py tests/smoke/test_database_relocation_drill.py -q
    python -m ruff check .
    python scripts/run_isolated_tests.py -m "not live and not debug and not e2e" tests/

Web slice также требует npm --prefix web run contract:extract, lint/build и
изолированный Playwright scenario нового status. Runtime CLI в M2: python
scripts/cloud_backup.py status|run --config /absolute/private/config.json;
status read-only, run — explicit operator operation; drill добавляется в M3.
Все test children
используют scripts.scratch_pytest.child_environment/fresh_child_environment;
никаких owner credentials, launchctl или real Cloud.ru по умолчанию.

## Validation and Acceptance


M1 проверяется против scope/AC #752 и companion matrix. Независимый reviewer
читает exact diff и repository contracts, не private evidence/credentials.
Будущие M2 failures должны наблюдаться до implementation; guards/default-off,
race/kill/state loss и safe diagnostics проверяются synthetic subprocess tests.
Проверенный внешний restic — dependency characterization, не новый product RED.

M3 full-domain drill сохраняет IDs/raw JSON/checkpoint/cycle/decision/match/
feedback/readiness/provider evidence через shared readers после restore/restart;
hash/integrity alone недостаточны для overall acceptance. RPO ≤24ч и RTO ≤30мин
имеют условия/измерение из companion spec. Сравнить source/rollback sentinels
до/после failure и reset. Live Cloud.ru probe выполняется только с owner-approved
synthetic prefix; fake S3/transport doubles в CI не считаются live evidence.

## Idempotence and Recovery


Upload/retry не удаляет source, local snapshots и remote history. Успех хранится
после exact snapshot readback; kill до receipt даёт unknown/degraded и допускает
безопасный повтор. Missing/corrupt receipt не даёт init/adoption/cleanup permission.
Config disable/unload job останавливает будущие попытки и сохраняет repository,
password и снимки. Restic lock contention не лечится автоматическим unlock.
Все процессы/deadlines и staging принадлежат только текущему запуску.

Потеря ноутбука использует независимо сохранённые URL/ID/password и новые S3 keys;
restore идёт в новый temp. Личная activation требует отдельного конкретного
preview/backup/rollback и owner confirmation, не команды из этого плана.

## Artifacts and Notes


14.11.2026 synthetic experiment: 2-table fixture, bytes/hash/schema equality,
wrong password refused, 6 STANDARD objects removed. Полный receipt находится
только у оператора; public summary — #626 comment 6879508968. Не публиковать
local filenames/Key ID/Key Secret/password/request headers из private logs.
M1 checker на a661c802584f..0f6c23f нашёл один blocking P2: uploader-only hourly
поверх local daily check допускает 24ч59м задержки raw write. Cheap datetime
counterexample и независимое чтение check_due подтвердили timing risk. Fix:
reuse fresh check_snapshot перед staging с явным owner-bound source; остальные
гейты не расширялись. Fixed-in a32e497; scoped delta checker READY, чистое дерево
до/после. Native 0/2; после verdict добавлено только evidence/progress.

M2: initial RED `988d1a2`, implementation checkpoint `c5b2e71`. Независимый
full-diff checker воспроизвёл два P2: non-string receipt timestamp вызывал
traceback; foreign/version-invalid local manifest сохранял ready. Исправлены
строгим разбором дат и metadata-only проверкой manifest без SQLite/network;
добавлены regression cases. Self-review отдельно дал RED реального enabled CLI
worker: dispatch через `__main__` мешал staging и смешивал exception classes.
Canonical module dispatch исправлен, public worker synthetic regression GREEN.
Final focused contour 60 PASS, scratch148/0; ruff GREEN. Scoped checker delta
`c5b2e71..89e2a8f` READY, оба P2 fixed-in89e2a8f, reviewer tree clean до/после.
Native GitHub review 0/2, не запрашивался.

Первый смежный прогон:240 PASS и localhost-bind permission refusal. Первый
полный прогон выявил сломанную системную Node25 dependency (`libsimdjson.30`);
дешёвый falsifier `node --version` отказал вне pytest, а существующий Node22.23.4
дал24 PASS на inventory/extractor без изменения системы. Первый full run:
4417 PASS /16 skipped /124 deselected,6 failures +18 setup errors от Node25;
он не считается GREEN. Повтор всего contributor-safe контура на финальном
code HEAD89e2a8f с Node22 и permitted localhost:4452 PASS /16 skipped /
124 deselected за327.89s, scratch30384 allowed /1 blocked (сам contour GREEN).
Ни guard, ни системные зависимости ради тестов не отключались/не менялись.
GitHub CI для89e2a8f при записи ещё выполнялся; contract/secret scan GREEN.
Draft [PR #755](https://github.com/rbctmz/ai_trainer/pull/755) закрывает только
#754. Локальные результаты не подменяют CI/native/owner/live gates.

## Interfaces and Dependencies / ASR traceability


Единственная новая внешняя runtime dependency — установленный restic, initial
tested version 0.19.1. AWS CLI используется оператором, продукт не требует его
для transport. macOS Keychain/LaunchAgent — dogfood v1; Windows/Linux/Docker
scheduling не заявляются. Shared Python выдаёт CloudBackupStatus/receipt и
стабильные reason codes; UI не вычисляет freshness и не читает секреты.
ASR-DEP-2/REL-3/SEC-1/MOD-2, ADR-0001/0002/0007; изменение privacy boundary
предложено в ADR-0002, не объявлено принятым. Новый общий framework не нужен.

## Outcomes & Retrospective


M1 #753 merged, #752 закрыта. M2 реализует shared operator service, фиксированный
restic transport, config resolver, CLI status/run и неустановленный LaunchAgent
template. [Операторская инструкция](cloud_backup_operator.md) описывает отдельную
activation boundary. M3 API/web/full-domain drill, рабочие password/schedule,
personal DB migration и activation не выполнены. Стоимость и recovery ownership
не подменяются успешным маленьким transport probe.

### CI investigation 2026-11-15 — scoped Class B harness repair

Observed: #755 code head89e2a8f CI GREEN. Docs-only bc7fa94 CI1341:
Python4425/43/124, contract/secret scan GREEN; E2E99 PASS /1 failed in
planning confirmation1280-light. Helper indexed athlete_day without checking
HTTP status. No api.log/artifact survived this scenario failure. Error response
and original cause are therefore unknown, not a proven cloud transport defect.

Verified by: all6 target variants PASS; two consecutive whole-S4 runs46 PASS.
Synthetic500 concurrent API reads with3000 read-only SQLite open/closes PASS.
Adding actual synthetic writes reproduced one parent scratch guard refusal at
sidecar nlink inspection, but another500 API requests all returned200; this does
not establish the original CI cause. No guard/product change was made.

Confirmed diagnostic defect (related #739): call-phase test failures did not
automatically capture WebStack logs before module fixture cleanup. New isolated
pytest subprocess regression:2 expected RED /1 PASS →3 PASS after hook fix.
Failures now retain assertion text, API/Next logs, URL, browser errors and image
in unique artifact directories; capture failure cannot mask the original test
failure. The context helper asserts HTTP200/body and required field; no response
fallback, retry, skip or relaxed assertion was added. Runtime/schema/API/web
behavior and ownership guards unchanged. Final full E2E/CI results are recorded
in #755; an eventual green retry is not proof of the original cause being fixed.

После диагностического изменения full local E2E dd9a1df:97 PASS /3 failed.
Все три synthetic artifacts теперь сохранились. API tracebacks для planning
close refresh и двух recovery readbacks показывают ScratchPathError в
scratch_runtime.py125, именно на type/nlink inspection. Это воспроизведённый
новый отказ с причиной в guard, а не доказательство исходного bc7fa94 failure.

Новый evidence разрешает узкий Class A repair #756 в том же PR (fresh scope,
не третий полный M2 review): одно full revalidation только regular optional
sidecar сnlink0. Main/hardlink/external alias/root/inspection refusals сохранены.
Контракт уточнён в database_path_guardrails_slice_spec.md; deterministic3 RED
→74 focused guard/diagnostics PASS, включая негативные replacement cases.
Личные paths/SQLite/.env/credentials и product Database/API/web не меняются.
Итоговый checker/full E2E/CI pending. #739 не объявляется целиком закрытой:
baseline comparison и причины иных исторических failures сюда не включены.

Revision 2026-11-14: начальный v1 plan после synthetic совместимости; выбран
один transport и no-prune policy proposal, чтобы исключить лишние engines/сервисы.
Revision 2026-11-14 после checker: добавлен fresh local check перед hourly upload
для соблюдения RPO и явный запрет source initialization в status/GET.
Revision 2026-11-14 M2: реализация и два checker fixes, RED→GREEN/public worker
evidence, operator runbook и фактические результаты отдельных тестовых контуров.
Revision 2026-11-15 M3: #757 spec/API/drill/UI implemented in separate checkpoints;
API5RED→10PASS, drill7RED→GREEN, native encrypted full-domain recovery and browser
RED→40PASS. Independent checker found one phase-evidence P2 atd1e3d31; author2RED
confirms timeout/receipt failure. Durable drill_pending and preservation of the
committed upload receipt are the narrow correction; final checks/delta pending.
First browser attempt was denied localhost binding by sandbox; permitted retry
reached actual missing-component RED. First Python contract run accidentally
used broken system Node25; repeated with existing Node22 gives24PASS. No system
dependencies or test guards changed. Web lint/build and contract artifact are green.
