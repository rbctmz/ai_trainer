# #625 — защита тестовых и служебных входов в SQLite

Этот ExecPlan ведётся по [.agent/PLANS.md](../.agent/PLANS.md). Он описывает
весь срез, но текущая команда владельца разрешает только M1: разведку,
спецификацию и безопасные эксперименты. Runtime-реализация — следующий handoff.

## Purpose / Big Picture


Тестовый запуск должен либо использовать созданную им временную БД, либо
отказать до открытия чужой БД. Обычное приложение продолжает читать и писать
свой store. Результат можно проверить на синтетическом защищённом файле:
ошибочная цель не открывается и не меняется, штатная временная цель работает.

## Progress


- [x] (2026-10-25) Создана цель M1; чистый изолированный worktree, baseline 12615561218bf2b5e5288d3a5ed2f9cf01f11145.
- [x] (2026-10-25) Прочитаны issue/owner decision, workflow, PLANS и ASR/ADD; сверены основные входы.
- [x] (2026-10-25) Synthetic probes повторены, спецификация/инвентарь/RED matrix и self-review готовы; Ruff/58 local links/diff GREEN.
- [ ] M1: публикация отдельного draft PR и current-head CI.
- [ ] M1: независимое review и решение владельца; реализация пока не начинается.
- [ ] M2: ранняя изоляция pytest и общий helper; RED → GREEN.
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


Author M1: подготовлены короткий контракт, актуальный inventory и synthetic
probe/evidence. Публикация/CI pending; independent review и owner acceptance
ещё не выполнены. Broad Python/UI suite локально N/A, product diff отсутствует.
Числа старой разведки сентября не являются текущей runtime-оценкой.
Не объявлять #625 закрытым после spec PR; защитное поведение ещё не поставлено.

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
