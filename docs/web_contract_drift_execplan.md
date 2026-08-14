# ExecPlan: Детектор совместимости HTTP-ответов API с типами web (web contract drift net)

Этот документ — живой ExecPlan по правилам `.agent/PLANS.md`. Секции `Progress`, `Surprises & Discoveries`, `Decision Log`, `Outcomes & Retrospective` обязаны обновляться по ходу работы.

## Purpose / Big Picture

Фронтенд `web/` описывает JSON-ответы FastAPI рукописным зеркалом `web/lib/types.ts` (1710 строк, 135 экспортов). Если бэкенд переименует, удалит или сменит тип поля, фронтенд узнает об этом только в рантайме. После этой работы в репозитории появится детектор: smoke-тест, который прогоняет реальные HTTP-эндпоинты на подготовленных данных и сверяет наблюдаемые ответы с типами, которые реально использует web. Тест падает, когда: отсутствует обязательное TypeScript-поле; наблюдаемое значение имеет несовместимый тип; значение выходит за закрытое множество литералов. Добавление сервером нового поля — обратно совместимо (ASR-MOD-3) и попадает только в INFO-отчёт, не блокируя слияние.

Формулировка цели сознательно скромная: это детектор совместимости **наблюдаемых** ответов, а не полный верификатор контракта. Конечное состояние — `response_model` на эндпоинтах + OpenAPI-кодогенерация типов; данный механизм — временный мост до него.

Проверить работоспособность можно командой:

    python -m pytest tests/smoke/test_web_contract_drift.py -q

## Progress

- [x] (2026-08-14) Этап 1: реестр `tests/contracts/registry.json` (25 эндпоинтов, 4 исключения из 3 вызовов) + RED inventory-тест → инвентаризатор `web/scripts/inventory-api-calls.mjs` → GREEN (3 теста). Коммиты 54a92e4 (RED), 1d074dd (GREEN).
- [x] (2026-08-14) Этап 2: экстрактор `web/scripts/extract-contract.mjs` + 17 юнит-тестов на fixtures + артефакт `tests/contracts/ts_contract.json` (116 типов от 25 корней, мета с sha256 types.ts и registry.json, `--check`). Коммиты 8fe2683 (RED), a9ec257 (GREEN).
- [x] (2026-08-14) Этап 3: валидатор `tests/contracts/conformance.py` + 18 юнит-тестов (чистый Python, без Node). Коммиты RED+GREEN, итог ce004df.
- [x] (2026-08-14) Этап 4: drift-тест `tests/smoke/test_web_contract_drift.py` — 43 сценария на 4 состояниях (empty/demo/edge_no_plan/edge_sparse), сетевые заглушки + fail-closed guard + доказательный тест. Первый же прогон поймал реальный дрейф (см. Surprises) — фикс 44a4a0f, тест 100ddcd. GREEN + lint + build.
- [x] (2026-08-14) Этап 5: CI job `web-contract` в `.github/workflows/ci.yml` (pytest+python-dotenv, npm ci, `contract:extract --check`, юнит-тесты контракта). Коммит 1f7ab97.
- [x] (2026-08-14) Этап 6: документация (шапка `types.ts`, `AGENTS.md`, живые секции этого документа) + полная валидация.
- [x] (2026-08-14, вторая половина дня) Раунд рецензии Codex: отделение посторонних локальных правок (коммит мейнтейнера 453c8ea), `Record<K,V>`-типизация значений и обязательные литеральные ключи, пустой кортеж как точная длина 0, сверка типа потребителя с реестром, dependency_overrides в фикстуре с восстановлением, test_artifact_is_fresh (sha256 источников против артефакта, без Node). Коммиты d2a9584, 936084e.

## Surprises & Discoveries

- Observation: в `web/lib/types.ts`, помимо базового подсета, фактически есть `Pick<...>` (строка 708), пересечение `A & B` (961), индексированный доступ `PlanningProfile["planning_mode"]` (886), литеральный тип `read_only: true` (863), дискриминированный union объектов `timeline` (619-626), индексная сигнатура `[key: string]: unknown` в `SyncResult` (512) и пустой кортеж `[]` в `WeekByWeekPlan.chart` (1115).
  Evidence: fail-closed падения экстрактора на реальном файле при первом прогоне; каждая конструкция добавлена в подсет и покрыта fixtures-тестом.
- Observation: `null`/`undefined` в типовой позиции TS — это `LiteralTypeNode`, а не ключевое слово; проверка по `SyntaxKind.NullKeyword` на самом узле не срабатывает.
  Evidence: ошибка `unsupported литерал` на `score: number | null` fixtures-теста.
- Observation: первый же прогон drift-теста нашёл реальный дрейф: `TodayForecastPrediction` в types.ts объявлял плоские `planned_role/planned_sport/planned_tss/planned_duration_minutes`, а API (`Database._deserialize_session_quality_prediction_row`) всегда отдаёт вложенный `planned_session: {date,index,role,sport,tss,duration_minutes}`. Плоские поля не приходили никогда; TSS-бейдж прогноза на «Сегодня» молча не отображался.
  Evidence: `$.forecast.prediction.planned_*: отсутствует обязательное поле` в сценарии `demo-/api/today`; `web/app/today/page.tsx:407` читал несуществующее `forecast.planned_tss`.
- Observation: инвентаризация вызовов вскрыла три эндпоинта, отсутствовавших в первичном ручном реестре: `GET /api/sync` (поллинг статуса в SyncControl), `GET /api/decisions` (shadow-страница), `GET /api/activities/{id}` (инлайн-обёртка — в excluded).
  Evidence: вывод `npm --prefix web run contract:inventory` до заполнения реестра.
- Observation: правка шапки `types.ts` на этапе документации без регенерации артефакта уронила `contract:extract --check` — sha256 источника в мета сразу подсветил забытое действие. Добавлен test_artifact_is_fresh (чистый Python, без Node), чтобы класс ошибок «забыта регенерация» ловился любым pytest-прогоном, а не только CI job'ом.
  Evidence: рецензия Codex [P1]; негативная проверка — тест падает на изменённом `types.ts`, зелёный после восстановления.
- Observation (рецензия Codex): `Record<..., number>` проходил как wildcard — строка удовлетворяла полю-записи; `[]` в union разрешал любой непустой массив; инвентаризация не сверяла тип потребителя с реестром; подмена `dependency_overrides` на уровне модуля протекала в другие тесты.
  Evidence: пять замечаний ревью; все закрыты фиксами d2a9584/936084e с юнит- и негативными проверками (оба порядка запуска TestClient-тестов зелёные).

## Decision Log

- Decision: никакого кодогенерации типов на этом этапе; вместо этого извлечение контракта из существующего `types.ts` и сверка с наблюдаемыми ответами.
  Rationale: почти все эндпоинты возвращают plain dict без `response_model`, поэтому OpenAPI-схема не описывает тела ответов; полное навешивание `response_model` — отдельный большой трек. Мост дешевле и безопаснее.
  Date/Author: 2026-08-14, plan review.
- Decision: неизвестные API-поля — INFO-отчёт, не FAIL (обратная совместимость, ASR-MOD-3). FAIL только: отсутствие обязательного TS-поля; несовместимый тип; значение вне закрытого множества литералов.
  Date/Author: 2026-08-14, рецензия мейнтейнера.
- Decision: извлекать только типы, достижимые от корневых интерфейсов реестра; подсет обязан покрывать `Pick`, пересечения, индексированный доступ, литеральные `true/false`, дженерик `Suggestion<T>`; fail-closed (exit ≠ 0 с файлом:строкой) для неизвестных конструкций внутри достижимого графа.
  Date/Author: 2026-08-14, рецензия мейнтейнера.
- Decision: инвентаризация вызовов — TypeScript Compiler API, не регексы; шаблоны с идентификатором/полем объекта, `encodeURIComponent`, нуль-арные методы (`x.trim()`) и простые тернарники (`cond ? "/api/..." : null`) разрешаются автоматически; неразрешимые выражения требуют аннотации `// api-contract: exclude: <причина>` / `// api-contract: manual: <путь>` или записи в `excluded` реестра.
  Date/Author: 2026-08-14, рецензия мейнтейнера.
- Decision: реестр хранит путь и `query_params` раздельно; сценарии перечисляются явно (состояние, источник параметров пути, ожидаемый код), без произведения «эндпоинт × все состояния»; 404/422 — вне conformance-сверки.
  Date/Author: 2026-08-14, рецензия мейнтейнера.
- Decision: свежесть артефакта проверяется в CI обязательно — отдельный job `web-contract` с `npm ci` и `contract:extract --check`; в job явно ставятся `pytest` и `python-dotenv` (conftest импортирует `Settings`).
  Date/Author: 2026-08-14, рецензия мейнтейнера.
- Decision: в мета артефакта пишутся sha256 и `types.ts`, и `registry.json` — набор извлекаемых корней зависит от реестра.
  Date/Author: 2026-08-14, рецензия мейнтейнера.
- Decision: сетевые заглушки перечисляются явно + доказательный тест guard'а.
  Rationale: `IntervalsICUClient._request_json` — единая точка egress; `/api/onboarding/planning` при недоступном Intervals деградирует штатно (`degraded_reason`), но локально с реальным `.env` ушёл бы в сеть — поэтому guard патчит egress, а не полагается на отсутствие ключей.
  Date/Author: 2026-08-14, реализация.
- Decision: ValueSpec расширен полем `variants` (дискриминированные union'ы объектов) и wildcard-объектами (индексные сигнатуры, `Record<string, unknown>`); пустой кортеж `[]` снисходительно трактуется как «массив чего угодно».
  Rationale: эти конструкции реально присутствуют в `types.ts`; без них fail-closed падал бы на текущем файле.
  Date/Author: 2026-08-14, реализация.
- Decision: найденный дрейф `TodayForecastPrediction` исправлен правкой `types.ts` + `web/app/today/page.tsx` (не api/) — рантайм API в этом треке не меняется; TSS-бейдж возрождён через `planned_session?.tss`.
  Date/Author: 2026-08-14, реализация (фикс 44a4a0f).
- Decision: `Record<K, V>` — полноценная типизация: закрытый набор литеральных ключей даёт обязательные поля; иначе значения проверяются против `record_values`; `Record<string, unknown>` требует объект, но не проверяет значения; `unknown`/`any` — единственные wildcard. Пустой кортеж `[]` — `array_length: 0`, непустой массив — нарушение.
  Rationale: рецензия Codex [P1/P2] — wildcard на Record пропускал строки вместо записей, `[]` пропускал непустые массивы.
  Date/Author: 2026-08-14, рецензия Codex (фикс d2a9584).
- Decision: инвентаризация сверяет не только путь, но и тип потребителя: для `type_source=lib/types` вызов обязан использовать интерфейс, объявленный в реестре для этого пути.
  Rationale: иначе замена `useSWR<DashboardResponse>` на другой тип осталась бы зелёной, и реестр перестал бы отражать реальность.
  Date/Author: 2026-08-14, рецензия Codex [P1] (фикс 936084e).
- Decision: подмена `dependency_overrides` оформлена module-фикстурой с восстановлением; добавлен test_artifact_is_fresh (sha256 types.ts и registry против мета артефакта).
  Rationale: глобальная подмена при импорте создавала зависимость от порядка тестов; забытая регенерация артефакта должна ловиться любым локальным pytest-прогоном, а не только CI.
  Date/Author: 2026-08-14, рецензия Codex [P1/P2] (фикс 936084e).

## Outcomes & Retrospective

Итог (2026-08-14, все 6 этапов):

- Работающий детектор совместимости: 43 сценария (25 эндпоинтов × применимые состояния) гоняются через TestClient на 4 состояниях данных; нарушения валидации падают с путями вида `$.forecast.prediction.planned_session`; необъявленные API-поля выводятся как INFO и не блокируют слияние.
- Инвентаризация (TS Compiler API, 37 файлов, 61 вызов) гарантирует, что новый GET фронтенда не останется вне реестра; ручная аннотация нужна только для действительно динамических адресов (сейчас один — target-preview).
- Артефакт `ts_contract.json` закоммичен (116 типов от 25 корней); CI job `web-contract` обязательно проверяет его свежесть и гоняет юнит-тесты экстрактора/инвентаризации.
- Ценность доказана сразу: первый прогон поймал реальный дрейф прогноза (плоские `planned_*` никогда не приходили; мёртвый TSS-бейдж) и три пропущенных из ручного реестра эндпоинта.
- Ограничения (заявлены и приняты): проверяется только наблюдаемое в объявленных сценариях; POST-мутации, SSE-чат коуча и инлайн-типы компонентов (4 записи в `excluded` из 3 вызовов) — вне сети; это мост до `response_model` + OpenAPI-кодогенерации.

## Context and Orientation

Репозиторий — AI Trainer: FastAPI-бэкенд в `api/` (роутеры в `api/routers/`), Next.js 14 фронтенд в `web/` (App Router, страницы `web/app/*`, компоненты `web/components/*`), общая логика в `models/`, `services/`, `data/`. Фронтенд вызывает API через модуль `web/lib/api.ts`: `fetcher<T>(path)` (GET), `postJSON/putJSON/deleteJSON` (мутации), все запросы идут same-origin на `/api/*` и несут `?demo=1` через `withDemo()` только когда включён демо-режим. Типы ответов — рукописное зеркало `web/lib/types.ts`; поля в нём snake_case, 1:1 с ключами JSON.

Термины:

- **Контракт-артефакт** (`tests/contracts/ts_contract.json`) — машинописное представление типов из `types.ts`, извлечённое скриптом-экстрактором. Коммитится, чтобы Python-тесты работали без Node.
- **Реестр** (`tests/contracts/registry.json`) — таблица «эндпоинт → корневой TS-тип + сценарии проверки». Единый источник корней и для экстрактора, и для drift-теста.
- **Инвентаризация** — скрипт `web/scripts/inventory-api-calls.mjs`: обходит AST `web/app/**` и `web/components/**`, находит все вызовы `useSWR`/`fetcher`/`postJSON`/`putJSON`/`deleteJSON` с путями `/api/*` и эмитит JSON. Гарантирует, что реестр не «забыл» ни один GET, который делает фронтенд.
- **Conformance-сверка** — прогон эндпоинта через `TestClient` и сравнение JSON-ответа со спецификацией из артефакта.
- **Состояния данных** — подготовленные фикстуры БД: `empty` (пустая temp-БД), `demo` (`services/demo_mode.activate_demo_mode` + `api/routers/system._seed_demo_plan`), `edge_no_plan` / `edge_sparse` (краевые).

Проверенные идиомы тестов (переиспользовать): TestClient + `app.dependency_overrides[get_database]` — `tests/smoke/test_api_planning_router_http_contract.py:39-52`; подмена модульной функции sentinel'ом — там же, строка 75; демо-сид на temp-БД — `tests/smoke/test_api_operational_states.py`.

## Plan of Work

Порядок этапов фиксирован (см. Progress). Каждый этап — RED-тест, затем реализация, затем GREEN, затем коммит. Ниже — состав каждого этапа.

Этап 1 (реестр + инвентаризация). Создать `tests/contracts/registry.json`: секция `endpoints` (ключ — путь с шаблонами `{param}`, значения: `interface`, `scenarios`: список `{state, path_params?, query_params?, expect}`) и секция `excluded` (записи `{path, file?, reason}` для GET-вызовов, которые сознательно вне сети, — например, инлайн-типы страницы коуча). Написать `tests/smoke/test_api_call_inventory.py`: проверка схемы реестра (без Node) и сверка инвентаря с реестром (Node). Реализовать `web/scripts/inventory-api-calls.mjs` на TypeScript Compiler API (`typescript` уже в devDependencies `web/`), скрипт `contract:inventory` в `web/package.json`.

Этап 2 (экстрактор). Fixtures-образцы `tests/contracts/fixtures/*.ts` со всеми конструкциями реального `types.ts`. Юнит-тесты `tests/smoke/test_contract_extractor.py`: запуск скрипта на образце и сравнение emitted JSON. Скрипт `web/scripts/extract-contract.mjs`: читает корни из реестра, обходит `web/lib/types.ts`, извлекает достижимый подграф, пишет `tests/contracts/ts_contract.json` (стабильный формат: сортированные ключи, мета с sha256 `types.ts` и `registry.json`); режим `--check` — побайтовое сравнение, exit 1 при расхождении. Скрипт `contract:extract` в `web/package.json`.

Этап 3 (валидатор). Модуль `tests/contracts/conformance.py`: функция `validate(payload, spec) -> Violations` с семантикой из Purpose. Юнит-тесты `tests/smoke/test_contract_validator.py` (чистый Python, без Node): обязательность, null-против-отсутствия, массивы, закрытые литералы, bool≠number, widening `| string`, wildcard `Record<string, unknown>`, INFO о необъявленных полях.

Этап 4 (drift-тест). `tests/smoke/test_web_contract_drift.py`: фикстуры состояний, сетевые заглушки (`api.planning_service.discover_intervals_events`, точка onboarding-обнаружения стартов — фиксируется аудитом), guard на низкоуровневый egress + доказательный тест guard'а, parametrize по сценариям реестра. Найденный реальный дрейф фиксируется в `types.ts` отдельными коммитами.

Этап 5 (CI). Job `web-contract` в `.github/workflows/ci.yml`: `pip install pytest python-dotenv`, `setup-node`, `npm --prefix web ci`, `npm --prefix web run contract:extract -- --check`, затем `python -m pytest tests/smoke/test_contract_extractor.py tests/smoke/test_api_call_inventory.py -q`.

Этап 6 (документация). Шапка `types.ts`, `AGENTS.md` (команды `contract:extract`/`contract:inventory`), Outcomes ниже, полная валидация.

## Concrete Steps

Рабочая директория для всех команд — корень репозитория.

Виртуальное окружение и зависимости:

    source ai_trainer_env/bin/activate
    python -m pytest tests/smoke/test_api_call_inventory.py -q        # RED до реализации скрипта
    npm --prefix web run contract:inventory                           # печать JSON-инвентаря в stdout
    python -m pytest tests/smoke/test_api_call_inventory.py -q        # GREEN

Ожидаемый вид инвентаря (сокращённо):

    {"files_scanned": 20, "calls": [
      {"file": "web/app/planning/page.tsx", "line": 88, "kind": "useSWR", "method": "GET",
       "paths": [{"path": "/api/planning/status", "query": {}}],
       "type": "PlanningStatus", "type_source": "lib/types", "unresolved": null, "annotated": false},
      {"file": "web/app/coach/page.tsx", "line": 41, "kind": "useSWR", "method": "GET",
       "paths": [{"path": "/api/coach/search", "query": {"q": "{searchQuery}"}},
                 {"path": "/api/coach/history", "query": {}}],
       "type": "{ chats: ChatSummary[]; }", "type_source": "inline", "unresolved": null, "annotated": false}
    ]}

## Validation and Acceptance

- `python -m pytest tests/smoke/test_api_call_inventory.py -q` — зелёный; до реализации скрипта — красный (скрипт обязан существовать, отсутствие = FAIL, а не skip; skip допустим только когда нет Node/`typescript`).
- `python -m pytest tests/smoke/test_contract_validator.py -q` — зелёный без Node.
- С Node: `python -m pytest tests/smoke/test_contract_extractor.py -q` зелёной; `npm --prefix web run contract:extract -- --check` — exit 0; порча артефакта — exit 1.
- `python -m pytest tests/smoke/test_web_contract_drift.py -q` — зелёный по всем сценариям реестра.
- Ручная демонстрация ловли дрейфа (без коммита): переименовать в ответе `/api/dashboard/summary` `has_data` → `hasdata` → FAIL «отсутствует обязательное поле»; добавить новое серверное поле → только INFO; вернуть литерал вне множества → FAIL с путём вида `$.briefing.frequency`.
- Полный контур: `python -m pytest -m "not live and not debug" tests/` и `npm --prefix web run lint && npm --prefix web run build` — без регрессий.

## Idempotence and Recovery

Все новые файлы аддитивны; рантайм `api/` и сериализация ответов не меняются; новых pip/npm-зависимостей нет. Экстрактор и инвентаризатор детерминированы (без таймстампов), повторный запуск даёт идентичные байты. Артефакт и реестр — текстовые JSON в git: откат любого слайса = revert коммита слайса.

## Artifacts and Notes

Ключевые файлы (полный список — в Plan of Work):

- tests/contracts/registry.json — реестр сценариев.
- tests/contracts/ts_contract.json — извлечённый контракт (артефакт).
- web/scripts/inventory-api-calls.mjs, web/scripts/extract-contract.mjs — скрипты Node.
- tests/contracts/conformance.py — валидатор соответствия.
- tests/smoke/test_api_call_inventory.py, test_contract_extractor.py, test_contract_validator.py, test_web_contract_drift.py — тесты.

## Interfaces and Dependencies

В `tests/contracts/conformance.py` определяются:

    def validate(payload: object, spec: dict, path: str = "$") -> list[str]      # нарушения (FAIL)
    def report_extra_fields(payload: object, spec: dict, path: str = "$") -> list[str]  # INFO

Спецификация поля в артефакте (форма фиксируется экстрактором на этапе 2):

    {"kinds": ["string", "null"], "literals": ["daily", "conflicts_only"], "widened": false,
     "optional": false, "items": <спек элемента массива или null>,
     "fields": {"<имя>": <спека>} | null,      # для объектов
     "wildcard": false}                          # true для Record<string, unknown>/unknown/any

Скрипты Node экспортируют CLI: `node web/scripts/extract-contract.mjs [--check]`, `node web/scripts/inventory-api-calls.mjs` (JSON на stdout). Оба используют только `typescript` из devDependencies `web/`.
