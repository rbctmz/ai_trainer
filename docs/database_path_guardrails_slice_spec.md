# #625 M1 — граница временных и рабочих БД

Статус: **draft спецификации, runtime не реализован**, 2026-10-25.
Issue [#625](https://github.com/rbctmz/ai_trainer/issues/625), parent [#622](https://github.com/rbctmz/ai_trainer/issues/622).
Baseline `12615561218bf2b5e5288d3a5ed2f9cf01f11145`; [ExecPlan](database_path_guardrails_execplan.md).
Author: Spec / Architecture Owner; independent checker: pending; merge owner: rbctmz.

## Цель и класс

Тест, acceptance или scratch-диагностика не должны открыть рабочую БД даже для
неявного создания схемы. Fail closed означает отказ до открытия/изменения
непроверенной цели, включая очистку после ошибки. Приложение по-прежнему может
читать и писать свою рабочую БД. **Class A — Full**: новая граница безопасности
персональных данных и cross-module runner/config/CLI contract автоматически
строже прежней Class B оценки в issue. M1 поставляет только spec и evidence.

## Актуальное основание

Observed: #624 уже дал `config/database_paths.py`, абсолютный platform default
и legacy preflight. `Database()` по-прежнему инициализирует схему; autouse
fixture не защищает collection/import. `run_acceptance.sh` разрешает override
вне session root. Inferred: сравнения только с Settings после смены env не
доказывают изоляцию. Verified by: [probe](reports/issue-625-m1/probe.py) и
[evidence](reports/issue-625-m1/evidence.json): legacy pytest exit 0/skip, файл
создан **до** инспекции, 37 таблиц; stub acceptance exit 0 с external-to-session
целью; pure resolver меняет identity после override. Личных данных не было.

AST нашёл 30 прямых zero-argument вызовов в 27 файлах, включая два намеренных
path regression cases. Это **не** число реально открывавших БД тестов и не
доказательство записей каждого файла. Динамически проверен один legacy case;
сентябрьские 17 файлов/99 открытий не переносим на текущий main.

## Инвентарь текущих входов

| Вход на baseline | Наблюдение по исходнику | Handoff |
| --- | --- | --- |
| `tests/conftest.py`, `config/settings.py` | Settings/dotenv импортируются до изоляции; fixture чистит только Intervals credential | M2 bootstrap до import/collection, без secret inheritance |
| `data/database.py:270–291` | constructor создаёт схему, `_connect` включает WAL | Compatibility gate; не добавлять product guard |
| `tests/test_hrv_logic.py:19` и AST список | Default constructor, возможен skip после создания схемы | M2 temp fixtures/test harness; AST не заменяет runtime audit |
| `tests/clean_database.py:14,77,123`; `tests/add_test_data.py`, `add_test_hrv_data.py`, `add_training_data_for_correlation.py` | Неявный selected DB; cleanup удаляет в том числе все HRV rows | M3 scratch default/explicit operator flow, проверка до анализа/записи |
| `scripts/backfill_bike_hr_pairs.py:26–29`, `repair_planning_materialization.py:138` | Остались literal `ai_trainer.db`; dry-run/apply различаются | M3 explicit target, убрать implicit apply, сохранить read-only preview |
| `scripts/backfill_activity_provider_links.py`, `backfill_intervals_distance.py` | Working default; у distance backfill также provider network | M3 shared confirmation до DB/network; доменная логика unchanged |
| `run_acceptance.sh:37–45`, `services/acceptance_mode.py` | Создаётся session, но DB/chats override не доказывает его ownership | M3 проверка parent + child, reset того же validated store |
| `tests/e2e/conftest.py`, `scripts/api_parity_capture.py` | Уже используют temp DB; E2E копирует большую часть env | M3 reuse root, bootstrap identity/credentials/cleanup; не считать доказанно безопасными только по имени |
| `tests/e2e_acceptance_live.py`, `e2e_acceptance_flows.py` | Legacy live browser tools, читают credentials/подключаются к заданному URL | M3 явный live operator opt-in; default не читает credentials/не действует на неизвестный сервер; live запуск в задачу не входит |
| `scripts/sqlite_backup_restore.py` | Existing stopped confirmation, WAL-aware backup/restore/migrate | Reuse operator flow; не заменить его scratch cleanup |
| `.github/workflows/ci.yml` | Contributor env temp paths без общего ownership; web-contract запускает bare pytest | M2 обновить оба contour; M4 проверяет actual opens |

## Контракт защиты

1. **Владелец scratch-области.** Bootstrap создаёт уникальный private root для
   запуска и хранит его identity в памяти. Имя `/tmp`, env-флаг или prefix имени
   не являются разрешением. БД, её SQLite family (main, `-wal`, `-shm`,
   `-journal`) и каталоги cleanup должны принадлежать этому root. Проверка
   применяется до SQLite open/DDL, seeding/reset, удаления и внешнего запроса.
2. **Identity до override.** До подмены DATABASE_PATH сохранить полученные извне
   real/demo candidates и platform/legacy candidates через pure resolver, без
   чтения их содержимого и без импорта Settings. В scratch-режиме `.env` не
   загружается. Любой переданный пользователем DB override вне owned root
   отвергается, а не молча заменяется. Отсутствие override означает выделение
   новых real/demo targets внутри root. CI не имеет исключения по имени пути.
3. **Положительное разрешение.** Разрешены созданные запуском файлы и новые
   отсутствующие targets внутри owned root, а не «всё, кроме известной real».
   Существующий не принадлежащий запуску файл запрещён. Проверка учитывает
   native case/Unicode identity, symlinks родителей и main, hardlinks и все
   sidecars; непересекающиеся будущие family names проверяются даже без файлов.
   Scratch hardlink с неоднозначным ownership (`st_nlink > 1`) запрещён.
   Ошибка stat/resolve/identity — отказ. SQLite URI разбирается до проверки;
   неизвестные schemes/options отклоняются, обычный in-memory store разрешён.
4. **Момент проверки.** Bootstrap pytest работает до импорта Settings и test
   modules, а не через autouse fixture. Harness ограничивает SQLite открытия
   областью запуска и ловит последующий explicit path/URI/Settings override;
   защитный hook живёт в test harness, **не** в `Database._connect`. Поддержан
   обычный contributor-safe вызов pytest; legacy hardcoded paths переводятся
   на tmp fixtures. `--basetemp`/TMPDIR нельзя использовать как разрешение на
   очистку существующего каталога: произвольный существующий basetemp отвергается
   до pytest cleanup; безопасный launcher создаёт собственный leaf. Default
   invocation и launcher должны быть проверены отдельно, без .env/user data.
5. **Acceptance и demo.** `run_acceptance.sh` и web E2E bootstrap получают
   отдельные owned roots и real/demo/chats targets до старта child. Override
   внутри области разрешается лишь при доказанном ownership; внешний/alias
   отвергается до doctor/seed/server. При обычном product demo расширяется
   только существующая `validate_demo_path`: real/demo SQLite families не
   пересекаются; правило owned root не накладывается на обычный product runtime.
6. **Очистка.** Cleanup удаляет только зарегистрированный root этого запуска,
   проверяя его identity повторно. Symlink наружу не обходится; подменённый root
   или неоднозначность дают отказ с сохранением artifacts. Нет wildcard по
   `*.db*`, touch/rm/truncate для проверки ignore. `git check-ignore --no-index
   --stdin` получает только строки; файловые artifacts не создаются.
7. **Служебные записи.** `tests/add_*`, `clean_database.py`, diagnostic и repair/
   backfill entrypoints не наследуют неявную working цель. Scratch режим
   требует owned target. Намеренная работа с существующей БД — отдельный
   operator flow: explicit `--database`, preview и `--apply` (или эквивалент),
   `--confirm-working-database` перед записью, проверенный stopped-service backup
   штатным CLI по runbook. Один флаг не разрешает произвольный cleanup и не
   запускает backup/stop автоматически. Direct Python helper подчиняется тому же
   контракту, не обходя CLI. Read-only preview сохраняет mode=ro и не создаёт
   отсутствующую БД. Network backfill проверяет разрешение до provider call.
8. **Диагностика отказа.** Стабильные причины: `scratch_target_unowned`,
   `scratch_protected_family`, `scratch_identity_unknown`,
   `scratch_cleanup_unowned`, `operator_confirmation_required`. Ошибка содержит
   purpose и reason; stdout/CI не содержит user path, env values, rows или
   traceback с ними. Test отказ ненулевой до collection; CLI operator error —
   exit 2. Operator preview показывает выбранный путь только локально по
   явному запросу; это не публичный CI artifact.

Предлагаемая минимальная поверхность: pure predicates/validation в существующем
`config/database_paths.py`; runner-owned `ScratchScope` и bootstrap в отдельном
`tests`/`scripts` helper, без импорта тестов продуктом. Концептуальные операции:
`create_scratch_scope()`, `scope.validate_target(path, purpose=...)`,
`scope.cleanup()`, `validate_operator_target(path, apply=..., confirmed=...)`.
Точные private имена свободны; env token не заменяет ownership. Не строить
универсальный sandbox или новый глобальный selector.

## Public Contracts

API, TypeScript, database schema/events и product default selection — unchanged.
CLI тестовых/служебных входов intentionally stricter: прежний implicit working
apply перестаёт разрешаться; runbook даёт явную замену. Test/acceptance env и
internal helper — новый cross-module contract, выше; configuration product
runtime не получает нового глобального guard flag. В M1 все контракты только
предложены, кода нового поведения нет.

## Приёмка и RED → GREEN matrix

Все fixtures искусственные; защищённый sentinel расположен вне scratch-root,
но внутри общего test temp. Его main/sidecars и содержимое измеряются до/после.

| Сценарий Given / When | Then / наблюдаемый критерий |
| --- | --- |
| Нет override; ordinary pytest / smoke запускается | Свои temp real/demo; ни одного SQLite open за областью; файл `.env` не прочитан |
| Explicit real path, relative alias, parent/main symlink, hardlink, native case/Unicode alias, URI переданы scratch runner | Отказ до первого SQLite connect/DDL; sentinel и sidecars неизменны; safe reason без path |
| Цель — будущий `real.db-wal/-shm/-journal`, main отсутствует | Family overlap блокируется до создания artifacts |
| Неизвестный/permission-denied путь, dangling link или escape через link/.. | Fail closed, не fallback на другой store; negative case не пишет sentinel |
| Override Settings или explicit sqlite3.connect после bootstrap | Test-only harness блокирует escape; новый default constructor внутри root работает |
| Test module создаёт Database при collection, затем skip/error | Используется owned DB; protected sentinel не открывается даже до fixture |
| Acceptance override вне session / E2E дочерний env указывает на sentinel | Отказ до doctor/network/seed/server; spawned application проверяет собственную границу |
| Штатный product real/demo, distinct families | Чтение/запись, demo seed/reset и рестарт работают; `_connect` unchanged |
| Cleanup дважды / exception / nested external symlink / root заменён | Только owned artifacts; внешний sentinel сохранён, ambiguous cleanup отказал |
| Caller передал existing protected dir как `--basetemp` | Refusal до pytest cleanup, protected dir и marker сохранены |
| Maintenance без confirmation / direct helper / nonexistent read-only input | Exit 2 либо named refusal, нет DB/network write; operator path отдельно проверен на synthetic store |
| `.gitignore` проверяется через stdin без materialization | Результат ignore проверен и нет новых main/WAL/SHM/journal файлов |
| Backup/restore/migrate + concurrency suites | Existing semantics и lifecycle #624 остаются зелёными, без нового backup engine |

Начать с subprocess RED случая «collection открывает sentinel», затем aliases,
повторная подмена и cleanup. M1 characterization не является новым RED или
GREEN защиты. На native macOS выполняются реальные symlink/hardlink/case cases;
Linux — CI; native Windows обязательные поддержанные случаи проверяются там
либо явно остаются NOT RUN, без заявления общей сертификации.

## Границы состояния, rollback и non-goals

Новых таблиц, durable registry, receipts, API/TypeScript contracts и зависимостей
нет. Ownership — память launcher process; children получают только разрешённую
область и сами валидируют её до imports. Interrupted run может оставить private
scratch root; новый запуск его не присваивает и не удаляет автоматически.
Restart с intentional existing scratch требует отдельного operator flow.
Rollback кода не восстанавливает удалённое; потому protected sentinel и отказ
до записи — обязательные доказательства. Backup/restore выполняется существующим
CLI, не средствами cleanup. Full product reset/schema/provider semantics unchanged.

Не входят личная миграция/БД/.env/services, UI, automatic snapshots #623,
off-device #626, защита от root/злонамеренного плагина или произвольного shell
агента. Symlink races проверяются повторной identity перед open/cleanup и
private owned dirs; adversarial OS races не объявляются устранёнными. Нельзя
сократить scope до нескольких grep-вызовов Database и объявить весь pytest safe.

## Поставка и проверка

M1 — эта спецификация, [ExecPlan](database_path_guardrails_execplan.md),
воспроизводимый probe и evidence. M2 — helper + pytest bootstrap/fixtures/CI;
M3 — acceptance/E2E + все найденные diagnostics/maintenance callers и operator
runbook. M4 — full contributor-safe, startup/cleanup failures и combined
`test_database_paths.py`, `test_database_relocation.py`,
`test_database_relocation_drill.py`, `test_sqlite_backup_restore.py`,
`test_sqlite_concurrency_policy.py`; новые focused `test_database_path_guardrails.py`
и `test_scratch_entrypoints.py`. Команды только из isolated synthetic source/env:
`python -m ruff check .`, `python -m pytest -m "not live and not debug and not e2e"
tests/` с CI warning policy; relevant E2E отдельно. Runtime ещё NOT RUN.

ASR-REL-3 / ASR-DEP-2: отказ до потери данных; ASR-SEC-1: без secret/path в CI;
ADR-0002 SQLite и ADR-0007 isolated acceptance переиспользуются. API/schema
unchanged, CLI intentionally stricter; implementation updates AGENTS/operator
docs одной канонической границей + ссылками, не копиями. Слабое место — полнота
entrypoints/child bootstrap; M4 runtime audit, а не AST, является gate.

## Evidence Bundle и завершение M1

Candidate HEAD и remote CI фиксируются в PR body; локально выполнены только
bounded characterization, Ruff и docs/link/diff checks. Broad suite и runtime
GREEN новой защиты — N/A для M1. Persistence/reset matrix выше — требования
M2–M4, а не доказанная доставка. Scope identity × before/after override ×
present/missing/unknown target × fail-closed fallback покрывается RED matrix.
New state/reset migration N/A: M1 не вводит product artifacts.

Definition of Done M1: актуальный source inventory и synthetic evidence,
наблюдаемые AC/failure/reset/compatibility checks, опубликованный spec PR с
явным handoff и назначенным merge owner. Независимое review/owner acceptance
отмечаются отдельно от author completion.

## Review и завершение M1

Self-review проверяет before-import ordering, ownership до env override,
family/alias/cleanup cases, operator escape и ordinary app compatibility.
Independent native review: manual, **0/2**, пока не запрошено; итог pending.
Merge/cleanup owner rbctmz; #625/#622 остаются открытыми. Spec PR не означает,
что работающая защита уже есть. Runtime этап начинается отдельным handoff
после принятой спецификации; branch HEAD/CI фиксируются в PR evidence bundle.
