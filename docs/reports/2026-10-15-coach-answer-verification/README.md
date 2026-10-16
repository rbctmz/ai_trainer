# #528 M5: проверка известных неподтверждённых утверждений

2026-10-15. Локальная реализация после f1b03ce, [срез](../../issue_528_answer_verification_slice_spec.md), [ExecPlan](../../issue_528_source_promise_execplan.md). Новых вызовов модели: **0**. Это проверка runtime-защиты на сохранённых ответах, не новый live experiment и не оценка общей правдивости Coach.

## Результат для пользователя

Shared narrative gate получает allowlisted activity/date/status/count/interval facts из реального get_activity_structure. Известные формы обещаний о будущей синхронизации, повторном запросе и подтверждении гипотезы больше не выдаются без проверки. Unknown остаётся unknown; analyzed-empty означает результат анализа сохранённых данных. Корректные факты structured и условная проверка с возможностью опровержения сохраняются.

Используется существующее однократное исправление. Повторно ошибочный, пустой ответ или ошибка provider оставляют детерминированный ответ с известными фактами; новых retries нет. API выдаёт токены и сохраняет ответ только после gate. Legacy shared finalizer использует ту же политику. Activity/planning writes не добавлены; обычное сохранение чата остаётся прежним.

Internal evidence/rule версии v3; новый hard reason ACTIVITY_STRUCTURE_CLAIM_UNSUPPORTED. Пять полей public metadata и их открытые string/list[str] типы прежние: API/TS schema, миграции и UI не менялись.

## Офлайн-результат

[offline-replay.json](offline-replay.json) содержит хэши четырёх исходных JSON, хэши реализации, каждый verdict и доставляемый текст. Replay использует сохранённый final_answer и raw tool results, календарь исходного отчёта; readiness_snapshot пустой как в этих synthetic activity сценариях. Correction provider не вызывается. Это не повтор всего исторического runtime с прежними prompts/settings.

| Источник | Сохранённых ответов | Остановлены новым activity rule | Другие замены существующим calendar rule | Без изменения |
| --- | ---: | ---: | ---: | ---: |
| baseline | 6 | 3 | 1 | 2 |
| compact A/B | 16 | 4 | 2 | 10 |
| source A/B | 4 | 4 | 0 | 0 |
| final validation | 4 | 1 | 0 | 3 |
| Всего | 30 | 12 | 3 | 15 |

Все четыре заранее выбранных контрпримера (source before1/before2/after1 и M4 empty) заменены. Дополнительно source after2 остановлен за утверждение отсутствия при unavailable. Три поддержанных M4 ответа (missing1/missing2/structured) сохранены **байт-в-байт**. Все 15 replacement texts проходят повторную проверку тем же gate; это проверка внутренней согласованности, не независимая семантическая оценка.

Все четыре исторических live JSON побайтово совпадают с f1b03ce; старые scores и pending_manual не менялись. Новые 15 pass нельзя трактовать как quality rate: replay не имеет независимых labels для всех 30 ответов, а правило ограничено известными формами.

Воспроизведение из корня checkout без сети/модели, с новым выходным путём (существующий файл не перезаписывается):

Уточнение после native review2026-10-16: исторический replay требует точного совпадения четырёх implementation hashes из offline-replay.json. Они соответствуют реализации2f9db64; base_commit=f1b03ce обозначает исходную базу того изменения. Текущий gatev5 имеет другие хэши: исправленный replay.py остановится до импорта gate и создания output вместо того, чтобы приписать новый verdict старой реализации. Для повторения этого исторического результата нужны четыре implementation-файла из2f9db64 и текущий replay.py с проверкой pins. Сам offline-replay.json, исходные live JSON, scores и ручные оценки не менялись.

```bash
python docs/reports/2026-10-15-coach-answer-verification/replay.py /private/tmp/coach-activity-replay-new.json
```

## Проверки и независимое ревью

Первичный RED: 16 failed / 9 passed, четыре сохранённых unsafe answers проходили старую проверку. Итоговый focused suite: **286 passed**. Он включает реальные tool/presenter synthetic fixtures, mixed date/identity, malformed/conflicting evidence, correction failures, API SSE/persistence и legacy delivery; существующие domains остаются покрыты.

Независимый read-only checker: spec без блокеров; consolidated implementation review нашёл три воспроизведённых P2. Они исправлены: сохранение уже доступных structured отрезков; «можно проверить» не квалифицирует последующую гарантию; отрицательный результат инструмента не становится положительным условием. Четыре точные регрессии сначала упали. Scoped repair review обнаружил одну регрессию положительной формулировки с именем инструмента/«уже»; две RED-регрессии добавлены и исправлены. Финальная scoped проверка семи cases: **7 passed**, блокеров нет. Полный review повторно не запускался.

Ограничение без блокировки: при нескольких активностях одной даты fallback различает строки по дате/числам, но не показывает ID/sport. Это не меняет source evidence и не выдаёт неподдержанные отрезки; возможное улучшение читаемости отдельно. Произвольные перефразировки, цитаты и все формы числовых ошибок не покрыты этим узким правилом.

Итоговый smoke на отдельной synthetic DB/chats: **3012 passed,35 skipped**,183.36s; один существующий Starlette/httpx deprecation warning. Пропуски:22TypeScript extractor/inventory без web/node_modules/typescript,10opt-in fixture regeneration,2pilot/process prerequisites,1socket limitation. Web/API contract shape не менялась; web lint/build не запускались. Whole-tree ruff и git diff --check зелёные. Replay воспроизведён второй раз в новый временный файл: идентичные байты и текущие implementation hashes.

Локальная реализация и replay: **2f9db64**. Dispositions независимого ревью:

- P2 valid structured naming replaced: fixed-in 2f9db64.
- P2 permission to check qualifying a later guarantee: fixed-in 2f9db64.
- P2 negative tool result qualifying a promise: fixed-in 2f9db64.
- P2 repair rejected positive named-tool/«уже» premise: fixed-in 2f9db64.

Push/PR/merge не выполнялись; live effect M5 не измерен. Этап реализации/офлайн-проверки завершён; human merge approval и новый finite live run остаются отдельными решениями.
