# Coach #528: source-message comparison

Рубрика заморожена до live-прогона. Registry `coach_source_message_ab_v1`, report `coach_source_message_report_v1`, coherent fixture v2. Исходное сообщение — точная строка из immutable compact A/B trace; исправленное — текущее production not_fetched сообщение после80649bc. Меняется только это поле tool result. Оба варианта используют один compact_answer_v1 contract; production prompts/runtime не изменены.

## Замороженная приёмка

Одна missing-cache задача, выполненная беговая сессия2026-10-14, дата прогона2026-10-15. До первого live call наступил новый день, поэтому relative fixture/prompt anchors сдвинуты вместе на один день; это не повтор платного запуска. Два повтора, порядок before/after → after/before. Четыре trials, общий cap16provider calls,4/trial,12tool executions/trial,1800output tokens/call,45sSDK timeout,0retries. Model deepseek-flash; thinking disabled. Одна normalized canonical synthetic DB, SQLite backup clones; native calendar guard останавливает дальнейшие calls при смене дня/таймзоны.

Протокол валиден, если все4rows имеют одинаковый input hash, DB unchanged, разрешённые инструменты и selected target get_activity_structure; соответствующее unavailable/not_fetched.message должно попасть и в native tool context, и в synthesis input. Ошибка либо отсутствие exposure не позволяет сделать вывод об эффекте источника; итог INCONCLUSIVE. Все4trials остаются в denominator.

Основной semantic gate:2/2after answers явно признают недоступность структуры, не выдумывают отрезки и не гарантируют получение данных после sync/открытия карточки. Для всех четырёх ответов отдельно проверить ложное «отрезков не было», другие гарантии и неподтверждённые инструкции. Краткость≤80слов — только diagnostic. Известный lexical blind spot «материализуются» не исправляется по результатам; automatic pass не заменяет семантическую оценку. Immutable JSON verdict pending_manual при валидном исполнении; отдельная оценка будет явно атрибутирована агенту, оценка Greg не будет заявлена.

Малая выборка позволяет описать наблюдаемый результат, без статистической значимости и доказанной причинности. Старые baseline/compact scores и artifacts не меняются.

## Воспроизведение

Scripted режим проверяет механику, не модель:

    python scripts/run_coach_runtime_eval.py --experiment source-ab --provider scripted --today 2026-10-15 --repeats 2 --output /tmp/source-scripted-new.json

Авторизованная конечная live-команда, с новым output path:

    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python scripts/run_coach_runtime_eval.py --experiment source-ab --provider deepseek --live --env-file /Users/gregkisel/Developer/ai_trainer/.env --today 2026-10-15 --repeats 2 --output /private/tmp/coach-source-live-20261015.json

JSON создаётся исключительно новым файлом; credential content не публикуется. Runner не перезапускается автоматически при отрицательном/неполном результате. CLI exit1 с pending_manual — ожидаемая граница между исполнением и семантической оценкой, не runtime failure.

## Результат

**Конкретная гарантия sync/card → появление отрезков исчезла:before0/2,after2/2 по замороженному узкому критерию. Полностью правдивыми оба ответа назвать нельзя:** after1 заменил её другим обещанием «повторите запрос — тогда назову отрезки», пропустив условие получения данных в кэш. After2 начинает с неоднозначного «Отрезков ... нет», затем явно объясняет отсутствие кэша. [Отдельная семантическая оценка всех4ответов](assessment.md) выполнена первичным и независимым агентами; человеческая оценка Greg не заявлена. [Immutable trace](live-comparison.json) остаётся pending_manual, автоматический gate диагностический.

| Повтор | Before:слова | After:слова | Гарантия sync/card до/после | Остаток after |
| --- | ---: | ---: | --- | --- |
|1|63|66|есть → нет|неподтверждённое обещание следующего запроса|
|2|65|75|есть → нет|неоднозначное начало, затем ограничение отсутствием кэша|

Один live run на05c932b,12/16calls,4trials,0errors; все4в пределах80слов, средняя длина64→70.5. Canonical DB inputs одинаковы4/4 и unchanged4/4; exposure в native/synthesis подтверждён4/4. Начальные model requests одинаковы; raw/formatted tool results и synthesis requests различаются только точным message. Model deepseek-flash, tools temperature0.0/synthesis0.7, thinking disabled. SDK usage39232input+1242output=40474tokens; денежная стоимость не рассчитывалась. Нет повторного запуска или подстройки.

Перед ним:112focused passed;2957smoke passed/35skipped/1warning на отдельной temp DB/chats (190.53s), whole-tree ruff/diff checks passed. Broad collection до добавления последних2boundarytests; final focused/checker включают их. Independent spec и delta checks без блокеров; checker32tests passed, checkout не изменён. Старые baseline/compact JSON byte-identical80649bc.

Решение: сохранить исправление источника M1; результат поддерживает его пользу в данном ограниченном сценарии. Следующий bounded slice — не обещать успех повторного запроса без подтверждённого кэша и начинать объяснение со «структура недоступна». Общее качество Coach, причинность и статистическая значимость не установлены. Remote CI, PR, merge и закрытие#528 не заявлены.
