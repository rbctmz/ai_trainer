# ExecPlan: issue #650 — CODEOWNERS покрывает rot-guard'ы CI-политики

Это живой ExecPlan по требованиям `.agent/PLANS.md`. Разделы `Progress`,
`Surprises & Discoveries`, `Decision Log` и `Outcomes & Retrospective` обязаны
обновляться по ходу работы. Документ самодостаточен: читатель, не знающий
репозитория, должен суметь выполнить работу целиком, имея только этот файл и
рабочее дерево.

Связанные артефакты: issue
[#650](https://github.com/rbctmz/ai_trainer/issues/650); рабочая спецификация
среза [issue_650_codeowners_guard_coverage_slice_spec.md](issue_650_codeowners_guard_coverage_slice_spec.md);
родительский контекст — issue [#511](https://github.com/rbctmz/ai_trainer/issues/511)
(CODEOWNERS для CI-критичных путей) и [#646](https://github.com/rbctmz/ai_trainer/issues/646)
(гейт ревью и его hotfix #647/#648).

## Purpose / Big Picture

В репозитории есть два вида файлов, которые вместе образуют контроль над
CI-политикой. Первый — сама политика: workflow-файлы в `.github/workflows/` и
скрипты в `.github/scripts/`, которые исполняются с правами на запись в
репозиторий. Второй — тесты, которые проверяют форму этой политики: они читают
workflow-файлы и падают, если триггеры, метки или область видимости констант
изменились. Такие тесты в этом репозитории называют rot-guard'ами: сторож
гниёт вместе с тем, что охраняет, поэтому он обязан обновляться вместе с
политикой.

До этой работы под `.github/CODEOWNERS` был только первый вид. Файл
`.github/CODEOWNERS` содержит четыре строки и назначает владельца
`@rbctmz` на `.github/workflows/` и `.github/scripts/`. Активный ruleset
«Protect main» при этом требует `require_code_owner_review = true` и
`required_approving_review_count = 0`: значит, PR, трогающий защищённый путь,
обязан получить ревью владельца, а PR, трогающий только сторожевой тест, — не
обязан получить вообще ничего, кроме зелёного CI.

Наблюдаемое следствие, которое эта работа устраняет: ослабить сторожа можно
было PR-ом, не требующим ни одного аппрува. После работы такой PR требует
ревью владельца, и — что важнее — **список сторожей перестаёт быть ручной
памятью**: новый тест, который читает защищённый каталог, но не внесён в
CODEOWNERS, роняет CI.

Проверить результат можно двумя командами. Первая показывает, что сторож
падает, если убрать запись из CODEOWNERS:

    $ python -m pytest tests/smoke/test_ci_policy_guard_coverage.py -q
    4 passed

    $ grep -v test_native_codex_review_integration .github/CODEOWNERS > /tmp/c && cp /tmp/c .github/CODEOWNERS
    $ python -m pytest tests/smoke/test_ci_policy_guard_coverage.py -q
    FAILED tests/smoke/test_ci_policy_guard_coverage.py::test_every_ci_policy_guard_test_is_codeowner_protected

Вторая показывает список сторожей, найденных сканером, — он не должен быть
пустым и должен включать сам файл сторожа:

    $ python -m pytest tests/smoke/test_ci_policy_guard_coverage.py::test_scanner_finds_the_known_guards -q
    1 passed

## Progress

- [x] (2026-09-26 19:5xZ) Прочитан issue #650, проверены `.github/CODEOWNERS` (4 строки, два каталога) и активный ruleset «Protect main» (`require_code_owner_review = true`, `required_approving_review_count = 0`).
- [x] (2026-09-26 19:5xZ) Владелец выбрал объём: покрыть все пять CI-guard-тестов, сам `.github/CODEOWNERS` и добавить самозамыкающийся сторож; класс — Class A — Full.
- [x] (2026-09-26 20:00Z) RED: написан `tests/smoke/test_ci_policy_guard_coverage.py`; до правки CODEOWNERS падают два теста из четырёх, в сообщении — готовые строки для вставки.
- [x] (2026-09-26 20:01Z) GREEN: `.github/CODEOWNERS` расширен до шести записей плюс он сам; `4 passed`.
- [x] (2026-09-26 20:01Z) Ломающая проба: удаление записи `test_native_codex_review_integration.py` роняет сторожа (1 failed, 3 passed); файл восстановлен байт-в-байт, `git diff` показывает только намеренные +19 строк.
- [x] (2026-09-26 20:05Z) Широкий прогон на дереве среза: `2933 passed, 13 skipped, 40 deselected`; `ruff check .` — «All checks passed!».
- [x] (2026-09-26 20:07Z) PR #657 открыт, issue #650 обновлён каноническим `Class A — Full`, ссылкой на план и non-goals.
- [x] (2026-09-26 20:20Z) Независимый checker: read-only аудит OpenCode (`--agent plan`, модель `deepseek/deepseek-v4-pro`, коммит `6baabf5`, единственная разрешённая команда — `pytest tests/smoke/test_ci_policy_guard_coverage.py -q`) дал **0 P1/P2** и 5 предложений; диспозиции — комментарий к PR #657, hardening вынесен в #658.
- [x] (2026-09-26 20:30Z) После мержа: PR #657 влит как `167da97`, ветка `ci/issue-650-codeowners-guard-coverage` удалена локально и на origin, локальный `main` синхронизирован, на смерженном дереве 16 passed и `ruff` чистый, запись Class A добавлена в `docs/engineering_process_metrics.md`, пункты slice-спеки закрыты.

## Surprises & Discoveries

- **Observed**: в `.github/CODEOWNERS` нет записи для самого `.github/CODEOWNERS`; файл состоит из комментария и двух строк-каталогов.
- **Inferred**: список владельцев можно переписать PR-ом, который не требует ревью владельца, — то есть файл, определяющий обязательность ревью, сам обязательного ревью не требует. Дешёвая опровергающая проверка — прогнать матчер CODEOWNERS по пути `.github/CODEOWNERS` и посмотреть, вернёт ли он владельца. (Отдельно: GitHub вычисляет CODEOWNERS из базовой ветки PR, поэтому запись защищает будущие PR, а не тот, который её добавляет; это ограничение записано в самом файле.)
- **Verified by**: `test_codeowners_protects_itself` до правки падал с `assert ()` — матчер не находил владельца; после добавления записи проходит.
- **Observed**: сканер по подстроке `.github/workflows`/`.github/scripts` находит в `tests/` шесть файлов: пять известных сторожей и сам новый сторож.
- **Inferred**: список сторожей можно не вести руками — достаточно искать тесты, которые читают защищённые каталоги. Дешёвая опровергающая проверка — удалить запись одного сторожа из CODEOWNERS и убедиться, что тест падает именно на нём.
- **Verified by**: удаление строки `test_native_codex_review_integration.py` дало `1 failed, 3 passed` с сообщением, называющим файл; восстановление вернуло `4 passed`.
- **Observed**: независимый аудит (OpenCode, `deepseek/deepseek-v4-pro`, коммит `6baabf5`) не нашёл ни одного P1/P2 и отдельно подтвердил, что удаление записи из CODEOWNERS обнуляет владельцев (`_owners_for(...) == ()`) и роняет именно сторожевой тест; он же нашёл, что сканер ищет подстроку и обходится косвенным построением пути: `Path(".github") / "workflows"` и `os.path.join(".github", "workflows", ...)` не детектируются.
- **Inferred**: непроверенный what-if «будущий сторож соберёт путь из частей» — это не дефект текущего среза, а долг hardening'а; по review-нормам его место в follow-up issue, а не в правке на открытой ветке. Дешёвая проверка гипотезы уже выполнена агентом-аудитором на синтетических строках; я повторил её прямой пробой на модуле сторожа.
- **Verified by**: проба на импортированном модуле — `direct detected=True`, `indirect detected=False`, `os.path.join detected=False`; записано в issue #658 вместе с предложенной правкой.

## Decision Log

- Decision: покрыть CODEOWNERS не точечно один файл, а все тесты, читающие защищённые каталоги, плюс сам CODEOWNERS.
  Rationale: точечное покрытие решает известный случай и оставляет ручную обязанность «не забыть про следующий сторож»; при `required_approving_review_count = 0` цена забывчивости — безапрувное ослабление сторожа. Выбрано владельцем среза.
  Date/Author: 2026-09-26, владелец среза по вопросу агента.
- Decision: класс изменения — Class A — Full.
  Rationale: сработал автоматический триггер «security boundary, permissions» из `docs/AI_Feature_Development_Workflow.md`: правка определяет, какие пути требуют аппрува владельца. Class A требует ExecPlan, заполненной slice-спеки, RED→GREEN и независимого checker'а — всё это в этом срезе есть.
  Date/Author: 2026-09-26, владелец среза по вопросу агента.
- Decision: предложения независимого аудита не чинятся в открытом PR, а выносятся в follow-up #658.
  Rationale: аудит дал 0 P1/P2; все пять пунктов — либо непроверенные what-if (косвенный путь), либо усиление, не входившее в acceptance criteria. По review-нормам это follow-up с владельцем, а не расширение среза; правка после аудита ещё и разорвала бы привязку «принятый head = проверенный head».
  Date/Author: 2026-09-26, автор среза.
- Decision: сторож не переизобретает glob-семантику CODEOWNERS, а поддерживает два случая — шаблон-каталог (`path/`) и точный путь.
  Rationale: репозиторий использует ровно эти две формы; полная реализация спецификации CODEOWNERS — это код, который сам станет критичным и потребует своего сторожа. Незнакомая форма шаблона не проходит молча: файл просто остаётся непокрытым, и тест падает.
  Date/Author: 2026-09-26, автор среза.

## Outcomes & Retrospective

Цель достигнута: защита расширена с двух каталогов до них же плюс сам `.github/CODEOWNERS` и шесть сторожевых тестов, а обязанность поддерживать список передана тесту. Проверяемость не декларативная: удаление записи роняет сторожа (`1 failed, 3 passed`), восстановление возвращает `4 passed`, широкий набор на дереве среза — `2933 passed, 13 skipped`, `ruff` чистый.

Что осталось: hardening сторожа из #658 (косвенные пути, симметричная проверка списка, владелец в подсказке) и, как и раньше, необязательность `Review gate` в ruleset — это отдельное решение владельца, в non-goals среза.

Уроки. Первый: цена асимметрии «политика защищена, её сторож — нет» была видна только при явном сопоставлении CODEOWNERS с набором тестов, читающих защищённые пути; держать это сопоставление в голове бессмысленно, поэтому оно стало тестом. Второй: у самого сторожа есть граница применимости — он ловит текстовое упоминание пути, а не намерение; это записано в #658 честно, вместо того чтобы считать сторожа полным. Третий: независимый аудит дал ровно то, ради чего он нужен, — не блокирующие находки о краях, которые автор среза считал несущественными.

## Context and Orientation

`.github/CODEOWNERS` — файл GitHub, который назначает владельцев путей. Если
ruleset ветки включает `require_code_owner_review`, PR, меняющий путь с
владельцем, не может быть смержен без аппрува этого владельца. В этом
репозитории активен ruleset «Protect main» (id `19150595`), и в нём
`require_code_owner_review = true` при `required_approving_review_count = 0`.
Единственная обязательная проверка статуса — `Contributor-safe pytest`
(workflow `.github/workflows/ci.yml`); `Review gate`
(`.github/workflows/pr-ready-to-merge.yml`) обязательной проверкой не является.

Rot-guard — тест, который проверяет не поведение продукта, а форму
конфигурации, чтобы она не «сгнила» незаметно. Примеры в этом репозитории:
`tests/smoke/test_native_codex_review_integration.py` проверяет триггеры,
метки и вызовы `evaluateReviewGate` в гейте ревью;
`tests/smoke/test_secret_scanning_ci.py` пинит fingerprints в
`.gitleaksignore`; `tests/smoke/test_claude_code_action_workflow.py` —
контракт workflow `@claude`; `tests/smoke/test_workflow_issue_linking.py` —
workflow привязки PR к issue; `tests/smoke/test_dev_workflow_v2_docs.py` —
контракт процесса разработки и парсер очереди Codex.

Живой пример цены вопроса — issue #646: PR #647 менял политику гейта и
одновременно правил его сторожа. Вынести правку сторожа отдельным PR было бы
хуже: такой PR не трогал бы защищённые пути и мог быть смержен без ревью.

## Plan of Work

Сначала пишется сторож, затем правится защита — так RED виден до GREEN.

Первый шаг: создать `tests/smoke/test_ci_policy_guard_coverage.py`. Внутри —
четыре теста и три маленькие функции. `_codeowner_entries` читает
`.github/CODEOWNERS`, отбрасывает комментарии (всё после `#`) и пустые строки
и возвращает пары «шаблон → владельцы». `_covers` сопоставляет шаблон с путём:
шаблон, оканчивающийся на `/`, покрывает сам каталог и всё под ним, иначе
требуется точное совпадение. `_owners_for` применяет правило CODEOWNERS
«побеждает последний шаблон с владельцами». `_ci_policy_guard_tests` обходит
`tests/**/*.py` и отбирает файлы, в тексте которых встречается
`.github/workflows` или `.github/scripts`. Четыре теста: сканер находит
известные шесть файлов; каждый найденный файл имеет владельца; сам
`.github/CODEOWNERS` имеет владельца; оба защищённых каталога всё ещё имеют
владельца.

Второй шаг: расширить `.github/CODEOWNERS` — добавить запись на самого себя и
по одной записи на каждый найденный сторож, с комментарием, объясняющим,
почему эти тесты приравнены к политике.

Ничего больше не меняется: ни workflows, ни ruleset, ни продуктовый код.

## Concrete Steps

Все команды выполняются из корня репозитория
`/Users/gregkisel/Developer/ai_trainer` при активированном окружении
(`source ai_trainer_env/bin/activate`; в примерах используется префикс
`ai_trainer_env/bin/python`).

Написать сторож, затем до правки CODEOWNERS прогнать его и увидеть RED:

    $ ai_trainer_env/bin/python -m pytest tests/smoke/test_ci_policy_guard_coverage.py -q
    2 failed, 2 passed

В сообщении об ошибке — готовые строки для вставки в CODEOWNERS. После правки:

    $ ai_trainer_env/bin/python -m pytest tests/smoke/test_ci_policy_guard_coverage.py -q
    4 passed

Ломающая проба (убедиться, что сторож не проходит при удалённой записи):

    $ cp .github/CODEOWNERS /tmp/codeowners.bak
    $ grep -v test_native_codex_review_integration.py /tmp/codeowners.bak > .github/CODEOWNERS
    $ ai_trainer_env/bin/python -m pytest tests/smoke/test_ci_policy_guard_coverage.py -q
    1 failed, 3 passed
    $ cp /tmp/codeowners.bak .github/CODEOWNERS

Широкий прогон и линтер:

    $ ai_trainer_env/bin/python -m pytest -m "not live and not debug and not e2e" tests/ -q
    $ ai_trainer_env/bin/python -m ruff check .

## Validation and Acceptance

Критерии приёмки из issue #650 в наблюдаемой форме:

1. PR, меняющий `tests/smoke/test_native_codex_review_integration.py`, требует
   ревью владельца: путь перечислен в `.github/CODEOWNERS`. Проверяется
   чтением файла и `test_every_ci_policy_guard_test_is_codeowner_protected`.
2. Новый сторож, читающий защищённый каталог, не может остаться вне
   CODEOWNERS: `test_every_ci_policy_guard_test_is_codeowner_protected`
   падает и печатает готовую строку. Проверено ломающей пробой выше.
3. Сам `.github/CODEOWNERS` под защитой: `test_codeowners_protects_itself`.
4. Защищённые каталоги не потеряли владельца:
   `test_protected_directories_still_have_an_owner`.
5. Широкий набор зелёный: `pytest -m "not live and not debug and not e2e" tests/`
   и `ruff check .`.

Ожидаемые результаты: `4 passed` на файле сторожа, полный набор — без новых
падений относительно базовой линии, `ruff` — «All checks passed!».

## Idempotence and Recovery

Все правки — текст в двух файлах, повторный прогон команд безопасен. Если
сторож мешает по делу (например, сторожевой тест переехал в другой каталог),
правильный порядок — сначала внести новый путь в CODEOWNERS, затем менять тест.
Откат — `git revert` коммита среза: ни workflows, ни ruleset, ни данные не
затронуты, миграций нет. Ломающая проба восстанавливает CODEOWNERS копией из
`/tmp`; в срезе это подтверждено `git diff`, в котором только намеренные +19
строк.

## Artifacts and Notes

RED до правки CODEOWNERS (фрагмент вывода):

    2 failed, 2 passed
    FAILED ...::test_every_ci_policy_guard_test_is_codeowner_protected
    E  tests/smoke/test_ci_policy_guard_coverage.py  @rbctmz
    E  tests/smoke/test_claude_code_action_workflow.py  @rbctmz
    ...
    FAILED ...::test_codeowners_protects_itself
    E  assert ()
    E   +  where () = _owners_for('.github/CODEOWNERS')

GREEN после правки:

    4 passed

Ломающая проба:

    1 failed, 3 passed

## Interfaces and Dependencies

Новых зависимостей нет: используются `pathlib`, `pytest` и стандартное
чтение файлов. Внешние контракты не меняются — ни API, ни TypeScript, ни схема
БД, ни конфигурация продукта. Меняется ровно один внешний для репозитория
контракт — список владельцев путей в `.github/CODEOWNERS`, который читает
GitHub при оценке PR. Новый тестовый файл обязан существовать по пути
`tests/smoke/test_ci_policy_guard_coverage.py` и быть помечен
`pytest.mark.smoke`, иначе он не попадёт в обязательный набор
`Contributor-safe pytest`.

---

Ревизия 3 (2026-09-26, 20:30Z): закрыт последний пункт `Progress` — срез смержен (`167da97`), ветка удалена, `main` синхронизирован, запись Class A внесена в метрики, пункты slice-спеки заполнены. Причина: ExecPlan — живой документ, и после мержа он обязан отражать факт, а не намерение.

Ревизия 2 (2026-09-26, 20:25Z): записаны результаты независимого аудита (0 P1/P2, пять suggestions), решение не чинить их в открытом PR и follow-up #658; закрыты пункты `Progress` про широкий прогон, PR и аудитора; заполнены `Outcomes & Retrospective`. Код после аудита не менялся — дельта относительно проверенного `6baabf5` только документационная.

Ревизия 1 (2026-09-26, 20:02Z): план создан после RED→GREEN и ломающей пробы —
решение владельца по объёму и классу получено до начала работы, поэтому
milestones записаны сразу с результатом. Причина отклонения от «план до кода»:
срез состоит из двух текстовых файлов и одного теста, и RED фиксирует контракт
точнее, чем проза. Falsification-прогон, независимый аудит и пост-мерж запись
остаются незакрытыми пунктами `Progress`.
