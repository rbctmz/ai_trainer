# Исправление двух несогласованностей ежедневного решения — #673

Обе подтверждённые аудитом проблемы исправлены в отдельной рабочей копии. Это проверка на синтетических сохранённых данных и настоящем API/web, а не пилот с атлетами.

Дата: 2026-10-01. Issue: [#673](https://github.com/rbctmz/ai_trainer/issues/673). Ветка: `codex/daily-loop-consistency-20261001`. База: `6d97787f49ce89502bfafed35a6f9f18e1a5e306`. Commit продуктового исправления: **`65881dbcc3c6e5305562d566b22f19686d3b3280`**. Последующие изменения отчёта не меняют продуктовый код. Копия: `/Users/gregkisel/.codex/worktrees/daily-loop-audit-20261001/ai_trainer`.

## Что теперь происходит

**F1, две независимые тренировки.** Today и подготовленный контекст Coach берут исполняемых родителей из сохранённого плана. В дне «велосипед + бег» велосипед остаётся выполненным с его фактом и ревизией, а бег — пока не наблюдаемым. Календарный идентификатор больше не используется вместо идентификатора тренировки, поэтому ложный `data_gap/inspect_evidence` исчезает. Несколько родителей доступны в совместимом необязательном `fact.sessions`; верхний `session_id` пуст, чтобы не выдавать первого родителя за весь день. Учтённая нагрузка объединяется только по непересекающимся фактам; неизвестное значение остаётся неизвестным. У каждого родителя сохраняются причина, отклонение и происхождение фактов. Брик остаётся одним родителем с этапами.

**F2, подпись свежести.** Объяснение признаёт каноническое состояние `fresh` актуальным только при сегодняшнем anchor, подтверждённых первичных измерениях сна, HRV и пульса покоя и отсутствии противоречащих первичных bucket/блокировки. Устаревший, будущий или неизвестный anchor, неполные/provisional/blocked данные и один актуальный TSB не становятся подтверждёнными текущими измерениями. Это подпись доказательств; оценка готовности и разрешение тренироваться не менялись.

**Observed:** реальные исходные Today/канонические readiness DTO давали ложный gap и unknown. **Inferred:** перепутаны идентичность дня/родителя и aggregate freshness/factor-state. **Verified by:** исходный аудит с изменением только ID/состояния; RED 7 failed / 9 passed; реальные сохранённые DTO и финальные регрессии ниже. Изменений CSS, макета, matcher, scoring, схемы базы и правил записи нет.

## Результат шести сценариев

Последний сценарий имеет два варианта — устаревшие данные и противоречащая самооценка травмы; всего семь API-наборов. Во всех наборы Today и подготовленной истории Coach **полностью равны**, все HTTP-ответы успешны, факты родителей и карточек активностей совпадают с каноническими проекциями.

| Сценарий | Проверенный результат |
| --- | --- |
| Обычный день, тренировка ещё не выполнена | `follow_plan`, выполнение пока не найдено, ложной неполноты нет; свежесть current |
| Одна выполненная тренировка | Сохранён единственный родитель и 45 TSS факта; `follow_plan` |
| Велосипед выполнен, независимый бег ещё нет | Два родителя, completed + not_observed, 45 TSS без удвоения; `follow_plan` вместо ложного gap |
| Частично выполненный брик | Один родитель, только подтверждённый велосипедный этап; нет выдуманного бега/перехода |
| Неоднозначное сопоставление | `confirm_match`, кандидаты не превращены в подтверждённые факты |
| Устаревшие данные | `inspect_evidence`; recovery freshness unknown, самооценка stale |
| Текущая противоречащая самооценка травмы | `inspect_evidence`; актуальные измерения остаются current, разрешения тренироваться нет |

Число 45 TSS берётся после обычной нормализации базы при запуске API, а не из ненормализованного seed. Это устраняет ложное различие, обнаруженное при исходном аудите.

## Проверки и независимое ревью

| Проверка | Результат |
| --- | --- |
| Meaningful RED | 7 failed, 9 passed до реализации |
| Целевые регрессии Today / Coach / freshness / реальные сохранённые факты | **85 passed**; отдельно независимый ревьюер получил те же 85 passed |
| Полный contributor-safe pytest | **2973 passed, 18 skipped, 46 deselected**, 1 предупреждение зависимости |
| Ruff по всему репозиторию и whitespace diff | passed |
| TypeScript contract extraction, freshness check, API inventory | passed |
| Web lint и production build | passed на тех же неизменённых TS/artifact файлах кандидата |
| Реальные API-сценарии и каноническая сверка | Все семь вариантов passed; полное равенство Today/Coach story |
| Настоящий API + Next + Chromium | **67 состояний**: 42 Today, 14 раскрытых объяснений, 7 Planning, 4 деталей активностей |

Ruff/focused/broad/API/browser доказательства сохранены. В документальной копии RED stdout убраны только хвостовые пробелы; исходный stdout сохранён во временном evidence root. Отдельные logs web lint/build/contract не сохранялись: успешный прямой вывод наблюдал интегратор (web session 21509, contract session 86686, exit 0). Независимый ревьюер обозначил эти web-проверки как integrator-observed на неизменных TS/artifact, без повторного запуска. Это ограничение сохранённого evidence; текущая удалённая CI не запускалась.

Браузерная проверка покрывает 390 / 978 / 1280 px, светлую и тёмную темы. Ноль ошибок страницы/API, горизонтальной прокрутки и попыток записи из браузера; временные серверы остановлены. Интегратор визуально проверил раскрытое объяснение двух тренировок, обычного дня и брик на 390 px в тёмной теме. Это не проверка озвучивания VoiceOver/NVDA.

Первый полный запуск в worktree упёрся в защиту SQLite: семь старых тестов создают базы по относительному пути. Защиту не ослабляли: кандидат экспортирован во временную папку, хеши исходников сверены. Первый экспорт также исключил публичный `.env.example`, из-за чего один тест шаблона не нашёл файл. Возвращён только публичный tracked шаблон; повторный полный запуск зелёный. Настоящий `.env` и живые базы не копировались. Пропуски включают opt-in регенерацию фикстур, отсутствующие диагностические данные/garth и ограничения проверки процесса/локального сокета; live/debug/e2e исключены штатным marker expression. Реальная браузерная проверка выполнялась отдельно с разрешённым loopback.

Независимое ревью: одна спецификационная проверка, один consolidated full-diff code round, затем scoped delta. Ревьюер ничего не менял в исходниках и не выполнял native approval/merge.

| Замечание | Воспроизведение и disposition |
| --- | --- |
| G1 P2: старый факт с новой ревизией сопоставления | Production-confirm A→B на одном checkpoint между чтениями. `fixed-in 65881db`: revision-head fence делает gap только затронутому родителю, остальные канонические факты сохраняются; свежий снимок даёт B/revision2 |
| G2 P2: некорректная идентичность или смешанные версии родителей | Шесть boundary-вариантов. `fixed-in 65881db`: review + неизвестный общий факт без потери корректного родителя и без исключения |
| S1 P3: некорректный bucket свежести | Пять bucket-вариантов. Принято и `fixed-in 65881db`: unknown без исключения и ложной актуальности |

[Исходный code review](reports/2026-10-01-daily-story-consistency/code-review.md), [scoped delta](reports/2026-10-01-daily-story-consistency/delta-review.md), [финальная сверка доказательств](reports/2026-10-01-daily-story-consistency/evidence-readback.md). Финальная независимая сверка доказательств: **PASS**, восемь хешей совпадают с commit `65881db`, новых блокеров нет; G1/G2/S1 — `fixed-in 65881db`.

## Доказательства и воспроизведение

[Итоговая машинная сверка](reports/2026-10-01-daily-story-consistency/evidence/acceptance-validation.json) содержит результаты сценариев, браузера и SHA256 проверенных продуктовых/тестовых файлов. [Полный зелёный набор](reports/2026-10-01-daily-story-consistency/evidence/broad-confirmed.log), [85 целевых тестов](reports/2026-10-01-daily-story-consistency/evidence/focused-review-final.log), [независимые adversarial probes](reports/2026-10-01-daily-story-consistency/evidence/reviewer-delta.json) сохранены рядом. Там же лежат реальные synthetic API payloads и браузерные тексты. [Две тренировки — экран объяснения](reports/2026-10-01-daily-story-consistency/evidence/screenshots/two-light-explanation.png), [обычный день — актуальные данные](reports/2026-10-01-daily-story-consistency/evidence/screenshots/ordinary-light-explanation.png), [частичный брик — 390 px, тёмная тема](reports/2026-10-01-daily-story-consistency/evidence/screenshots/partial-brick-dark-390.png).

Регрессии находятся в `tests/smoke/test_daily_story_consistency.py`. Использованные launcher/guard/API/browser/probe scripts сохранены **без изменения** в `docs/reports/2026-10-01-daily-story-consistency/tools`; они привязаны к указанным локальным путям. Не запускать их против живой базы и не подменять защиту/credentials. Текущий launcher находится в `/private/tmp/ai-trainer-daily-fix-20261001/run.py`; для полного набора использован `run_broad.py`, указывающий на hash-verified временный export.

    <venv-python> <guarded-run.py> pytest -m 'not live and not debug and not e2e' tests/smoke/test_daily_story_consistency.py tests/smoke/test_today_decision_story.py tests/smoke/test_api_today.py tests/smoke/test_coach_fresh_context.py -q
    <venv-python> <guarded-run_broad.py> pytest -m 'not live and not debug and not e2e' tests/ -q
    <venv-python> <guarded-run.py> python six_scenarios.py
    <venv-python> <guarded-run.py> python browser_audit.py

Python: `/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python`. Последние две команды требуют абсолютного пути к сохранённым scripts или их копий в временном root, как указано в них. API работает на временных synthetic SQLite; provider/DNS/external sockets заблокированы; browser допускает только loopback и read-only запросы. Для повторного запуска сначала сверить текущий SHA с описанным commit.

## Границы результата

Главная рабочая копия и живые данные не изменены. Read adapters сохраняют снимки таблиц planning checkpoints, match ledger, feedback, proposals и recovery episodes; существующая Today/Coach lifecycle-инициализация не объявляется чистым чтением и выполнялась только в временной базе. Fencing обнаруживает изменение ревизий вокруг указанной границы чтения; это не новая транзакционная snapshot-isolation гарантия для произвольных будущих конкурентных записей.

Проверен подготовленный контекст Coach; поток ответа модели не запускался. Качество ответа настоящей LLM, внешний пилот с атлетами и screen reader остаются непроверенными. На момент завершения локального этапа работа была сохранена без push/PR, native review acceptance и merge. Публикация по последующему разрешению описана ниже. Мёрж остаётся решением владельца после отдельного разрешения.

## Публикация PR и первоначальный CI

По отдельному разрешению пользователя ветка опубликована и открыт [PR #675](https://github.com/rbctmz/ai_trainer/pull/675), head 73c363e. Первые Contributor-safe pytest и Web contract artifact прошли. Gitleaks нашёл 30 `generic-api-key` в `evidence/candidate-export.json`: имена файлов с token/auth/key рядом с 64-значными SHA256 вызвали ложные срабатывания. Все 30 значений независимо пересчитаны по временному export и подтверждены как контрольные суммы исходников. Добавлены только commit+path+line и current-tree path+line исключения для этих записей; общий scanner workflow, остальные правила и обнаружение настоящих секретов сохранены. Проверка исключений закреплена существующим secret-scanning contract test. Native review/owner acceptance и merge ещё не выполнены.

Локальная проверка pinned Gitleaks 8.30.1: PR/event history range (два коммита) и безопасный export текущих tracked файлов — без срабатываний; runtime-only synthetic secret по-прежнему обнаруживается. 7 secret-scanning contract tests прошли. Тест дополнительно закрепляет SHA256 всего immutable manifest, поэтому замена любого checksum-значения требует явной повторной проверки. Продуктовые файлы и публичный контракт не менялись.

Независимое bounded CI metadata review: без блокеров; 7 tests passed и real synthetic detection подтверждены. Отчёт: docs/reports/2026-10-01-daily-story-consistency/ci-metadata-review.md. На исходном PR head73c также прошёл Web E2E (Playwright), run36878927667; после metadata push результаты нового head проверяются отдельно.
