# Competitive Analysis: Blocks as a Product and Architecture Reference

> Дата анализа: 2026-07-15  
> Источники: [Blocks](https://blocks.zone/), read-only handshake и MCP tool discovery через [Blocks MCP](https://blocks.zone/api/mcp).  
> Метод: публичная поверхность продукта плюс авторизованные read-only вызовы `initialize`, `tools/list`, профиля, календаря, каталога, событий и knowledge search. Токены, персональные payload и индивидуальные значения в документ не включены.

## Зачем Blocks полезен проекту

Blocks — не только конкурентный календарь. Для AI Trainer это референс сразу по четырём слоям:

1. исполняемый календарь с несколькими сессиями в один день;
2. каталог переиспользуемых структурированных тренировок;
3. курируемая научная база с provenance;
4. MCP-контракт, через который внешний AI читает данные и предлагает изменения.

IntervalCoach полезен как референс адаптивного планировщика поверх Intervals.icu. Blocks дополняет картину: показывает, как разделить библиотечный workout, календарный экземпляр, фактическую активность, профиль атлета, scientific evidence и tool-calling.

## Что стоит перенять

| Возможность Blocks | Что в ней ценно | Решение для AI Trainer | Приоритет |
|---|---|---|---|
| Несколько тренировок на одну дату | У каждой календарной сессии собственный instance id, спорт, TSS, структура и заметка | Сделать исполняемую сессию канонической единицей плана; разрешить несколько `session_id` на дату; дневные и недельные суммы вычислять из сессий | P0 — текущая граница планировщика |
| Разделение library workout / calendar instance | Одну библиотечную структуру можно использовать многократно, а конкретный экземпляр редактировать независимо | Разделить стабильный `template_key` и календарный `session_id`; хранить immutable prescription snapshot в checkpoint | P0/P1 |
| Workout DSL | `steady` и вложенные `repeat`; длительность или беговая дистанция; зона, интенсивность, cadence | Развивать Workout Catalog как versioned DSL, а не набор текстовых описаний; сохранить детерминированную сериализацию в Intervals.icu | P1 |
| Catalog-first planning | Поиск идёт по каталогу, коллекциям и личной библиотеке; custom workout создаётся только при отсутствии подходящего | Сначала ранжировать существующие шаблоны по phase/role/sport/duration/recency, затем материализовать новый только при fail-closed отсутствии кандидата | P1 |
| Read / update scheduled workout in place | Структура календарной сессии меняется без удаления и пересоздания identity | RecoveryReplan и ручные правки должны сохранять lineage (`replaces`/`supersedes`) и не терять feedback/match history | P1 |
| Scientific knowledge cards | Поиск возвращает `refId`, DOI, evidence level, finding и actionable bottom line; доступен citation graph | Добавить coach knowledge layer: claims о физиологии, питании, taper и восстановлении должны иметь provenance либо явную метку «вне базы» | P1 |
| Раздельные зоны по спорту | Велосипед и бег имеют собственные LTHR/max HR/threshold anchors и абсолютные targets | Расширить athlete profile до sport-specific threshold snapshots; не применять один LTHR ко всем дисциплинам | P1 |
| Readiness без скрытого вердикта | Субъективная шкала, confounders, 7/28-дневные baseline, rolling trend и sample size отделены от интерпретации | Сохранить наш canonical readiness snapshot, но добавить confounders и maturity/evidence; решение остаётся отдельной версионированной политикой | P1/P2 |
| Plan vs actual loop | Completed activity имеет собственный id, detected intervals, athlete note, coach read и sRPE | Связать reconciliation, session feedback, quality forecast и activity evidence одним `session_id`/match lineage | P1/P2 |
| Structured athlete file | Долговечные цели, ограничения, здоровье, предпочтения и agreements отделены от дневного шума | Ввести секционную память атлета с ownership, freshness и provenance; события остаются каноническими данными, а не копируются навечно в память | P2 |
| Event preparation | Событие связывает дату, трассу, погоду, логистику, pacing/fueling и coach notes | После корректного planning core добавить evidence-backed race brief поверх уже существующих A/B/C events | P2 |
| Strength DSL | Упражнения, подходы, повторы/время/дистанция, RPE и supersets — отдельный контракт, не псевдо-TSS | При расширении за endurance не пытаться запихнуть силовую работу в bike/run workout steps; проектировать отдельный session kind | Позже |
| MCP surface | Внешний AI может читать профиль, план, активности, readiness, каталог и knowledge; mutations отделены отдельными tools | Рассматривать собственный MCP как внешний API после стабилизации доменных контрактов; approval-gated mutations должны переиспользовать те же сервисы, что web | Позже |

## Прямые требования к текущему исправлению планировщика

Blocks подтверждает выбранное решение: на одной дате может быть несколько независимых тренировок. Для AI Trainer это означает:

- `session_templates` (или их преемник) — исполняемая правда; `daily_plan.parts` становится производной агрегацией или удаляется из новых контрактов;
- каждая сессия имеет собственные `session_id`, sport, role, target TSS, prescription snapshot и provenance;
- `sum(session TSS by sport/date/week)` точно совпадает с API/UI weekly summary;
- Today, reconciliation, feedback, forecast, RecoveryReplan и delivery принимают несколько сессий на дату;
- brick остаётся одной composite-сессией с bike/run legs и общей lifecycle identity, но рядом с ним на той же дате могут существовать другие сессии;
- старые checkpoints с одной сессией на день читаются без destructive migration;
- календарная доставка и cleanup используют identity/ownership, а не только дату и спорт.

Эти правила должны быть закреплены contract-тестами до изменения materializer. Главный тест-якорь: недельные sport totals равны сумме реально экспортируемых сессий, а ни одна доля run/swim не может быть молча переклеена в bike через `_dominant_sport(parts)`.

## Референсы для activation и brick

Read-only просмотр живых Blocks-структур показал полезную минимальную грамматику, которую можно использовать как дизайн-референс, не копируя конкретные workout payload:

- bike opener: полноценная разминка, несколько коротких race-pace включений с лёгким восстановлением, заминка;
- run opener: разминка, короткие повторы около race pace, лёгкие паузы, заминка;
- pre-race bike shakeout: лёгкое вращение плюс несколько минутных включений;
- pre-race run shakeout: лёгкий бег плюс короткие strides с walk/jog recovery;
- brick: отдельные bike и run prescriptions на одной дате, с явной семантической связью.

Для AI Trainer activation должен стать first-class catalog definition для bike и run, а не `legacy_role_fallback`. Конкретные длительности и интенсивности должны зависеть от профиля, event priority, days-to-race, load state и доступного TSS. Текущая усталость может подавить ближайший brick, но не должна запрещать все брики дальнего макроцикла.

## Scientific knowledge layer

Наиболее ценная часть Blocks MCP — не размер базы сам по себе, а контракт ответа:

- стабильный `refId`;
- DOI;
- evidence level;
- тип и применимость исследования;
- краткий finding;
- отдельный actionable bottom line;
- переход к полному digest и связанным материалам только при необходимости.

Для AI Trainer минимальный полезный срез:

1. retrieval до генерации утверждений о тренировочной физиологии, питании и восстановлении;
2. citations в coach evidence, decision log и race brief;
3. versioned snapshot использованных источников рядом с рекомендацией;
4. явная маркировка `outside_knowledge_base`, если релевантного материала нет;
5. evidence weighting: слабые или конфликтующие данные не должны звучать как правило;
6. отдельные домены для taper/periodization, masters 50+, triathlon/brick/transition, swimming, heat, fueling, readiness и recovery.

Подключать внешнюю KB напрямую как неограниченный runtime dependency необязательно. Сначала нужен внутренний provider-neutral контракт `KnowledgeCard` и read-only tool для Coach; источник можно заменить или комбинировать позже.

## Что у AI Trainer уже сильнее или должно остаться своим

- **Плавание:** MCP-каталог Blocks планирует cycling/running/strength; плавание в наблюдённом календаре часто живёт заметками. Наш swim catalog и structured swim prescription могут стать реальным дифференциатором.
- **Append-only planning:** checkpoints, proposal lifecycle, rollback, decision log и immutable snapshots дают более сильный аудит, чем простое редактирование календарной строки.
- **Recovery decision loop:** readiness → salience gate → proposal → confirm/rollback уже является отдельным объяснимым контуром.
- **Composite brick:** общий parent и legs лучше сохраняют атомарность применения, rollback и delivery, чем две не связанные записи. При этом UI и reconciliation обязаны видеть обе ноги.
- **Garmin + Intervals.icu:** прямой Garmin ingestion и управляемая доставка через Intervals.icu остаются нашим продуктовым путём; Blocks в наблюдённом аккаунте опирался на Strava для факта.
- **Provider-neutral AI:** научная база и MCP не должны привязывать доменную логику к одному LLM.

## Риски, которые Blocks также демонстрирует

1. **Дубли календаря.** Несколько источников могут поставить конкурирующие тренировки на одну дату. Нужны ownership, source, external id, dedup и пользовательский выбор — multi-session не означает «принимать все дубли».
2. **Устаревшая память.** Athlete file может продолжать называть старое событие главной целью после изменения приоритета. Durable memory требует freshness, provenance и синхронизации с canonical events.
3. **Каталог без policy не является планировщиком.** Большая библиотека не решает spacing, ramp, phase fit, readiness и event priority; selector должен оставаться отдельным детерминированным слоем.
4. **Большая KB не гарантирует хороший ответ.** Нужны retrieval discipline, evidence weighting, citation snapshot и проверка применимости к конкретному атлету.
5. **Write-capable MCP расширяет поверхность риска.** Read tools и mutations должны быть разделены; любые изменения профиля, календаря или событий — только после explicit confirmation и с idempotency/ownership guards.

## Рекомендуемая последовательность

1. Закрыть текущую ошибку planning truth: несколько сессий в день, точные sport totals, обратная совместимость и отсутствие silent relabeling.
2. Довести catalog coverage: activation bike/run, feasible fallback, near-term brick fatigue window и race-load semantics.
3. Добавить catalog search/ranking и переиспользование definitions/collections без потери immutable snapshot.
4. Спроектировать provider-neutral `KnowledgeCard` и read-only Coach retrieval с citations.
5. Развести sport-specific thresholds/zones в athlete profile и prescription provenance.
6. Соединить activity intervals, athlete feedback, sRPE и quality forecast в единый post-session evidence loop.
7. Добавить event brief (weather/course/pacing/fueling) и только затем рассматривать внешний AI Trainer MCP.

## Итог

Самые ценные идеи Blocks для ближайшего roadmap — не визуальные и не социальные. Это каноническая session-level модель календаря, catalog-first workout reuse, научная база с проверяемым provenance, sport-specific профиль и замкнутый plan-to-actual loop. Перенимать их нужно через наши существующие сильные стороны: append-only checkpoints, explicit confirmation, decision log, canonical readiness и безопасную доставку.
