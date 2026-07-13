# Intervals.icu Apps: конкурентное исследование, batch 2

Дата проверки: **2026-07-13**. Охват: строки 22–42 файла `intervals_icu_ai_trainer_apps.csv` (Enduco → PaceKeeper AI), 21 приложение. Сравнение сделано с реализованным профилем [AI Trainer](./ai_trainer_product_profile.md), без зачёта roadmap как готовых функций.

Метод: использовались публичные официальные лендинги, pricing/docs/terms/changelog и страницы загрузки. Если официальный сайт недоступен или не раскрывает параметр, поле помечено `n/a`, а не восстанавливается по сторонним обзорам. Цены — публичные на дату проверки, могут зависеть от региона/периода биллинга.

## 1. Enduco

- **URL:** https://enduco.app/
- **Позиционирование:** коммерческий персональный data-driven endurance coach с постоянно адаптирующимся планом и AI Coach Chat.
- **Виды спорта:** бег, велоспорт, триатлон.
- **AI/coaching:** индивидуальные планы по цели и текущей форме, ежедневные подсказки, AI-чат с выбором «характера» тренера; Pro — 10 сообщений/нед., Pro+ — 100.
- **Планы:** сезонные/целевые планы, ограничения по доступному времени, 24/7 адаптация при пропуске или плохом самочувствии, несколько соревнований.
- **Анализ/восстановление:** заявлена оценка ежедневной ситуации и защита от перетренированности; точная модель readiness/HRV публично не раскрыта.
- **Взаимодействие:** нативный in-app AI chat; отдельные мессенджеры/email-coach не подтверждены.
- **Интеграции:** Garmin, Strava, COROS, Apple Watch, Wahoo, Suunto, Zwift; импорт активностей и экспорт структурированных тренировок.
- **Платформы:** iOS, Android; web-поверхность явно не заявлена как основной пользовательский продукт.
- **Цена/проба:** 14 дней бесплатно; Германия: Pro €14.99/мес, Pro+ €21.99/мес (региональные варианты и годовая скидка возможны).
- **Зрелость:** доступный коммерческий продукт, компания endurance coach GmbH; опубликованы privacy/terms и упоминание в исследовании 2025 г.
- **Дифференциаторы:** зрелый мобильный UX, большой device ecosystem, coach chat + непрерывная адаптация, несколько соревнований.
- **Пересечение с AI Trainer:** персональные планы, адаптация, чат, recovery-aware рекомендации, Garmin и структурированные тренировки.
- **Отличие:** Enduco заметно сильнее по мобильности и широте устройств; AI Trainer сильнее по self-hosting, локальному хранению, мультипровайдерности/Ollama и аудируемому approve/reject/rollback recovery-контуру.
- **Источники:** [официальный сайт и pricing](https://enduco.app/), [terms](https://enduco.app/terms-of-use).
- **Confidence:** high.
- **Missing/uncertain:** алгоритм восстановления, наличие Intervals.icu, точные региональные цены и web-доступ.

## 2. EnduroCo

- **URL:** https://www.enduroco.in/
- **Позиционирование:** AI endurance coach, который после каждой выполненной/пропущенной сессии поддерживает актуальный календарь до старта.
- **Виды спорта:** Free — бег; Pro — бег, велоспорт, дуатлон, триатлон.
- **AI/coaching:** генерация плана по истории, доступности и событиям; непрерывная настройка нагрузки, восстановления и прогрессии.
- **Планы:** структурированные power/HR/pace/RPE-сессии, adaptive updates после каждой сессии, реакция на пропуски и изменение приоритетов гонок.
- **Анализ/восстановление:** basic analytics в Free; advanced analytics, load tracking и recovery guidance в Pro.
- **Взаимодействие:** web/mobile product; email support. Разговорный чат и внешние мессенджеры публично не подтверждены.
- **Интеграции:** Intervals.icu, Strava, TrainingPeaks, Garmin, Wahoo; сайт также говорит о существующем watch/bike-computer ecosystem.
- **Платформы:** web, iOS, Android, выполнение на подключённых устройствах.
- **Цена/проба:** Free forever (10 тренировок/мес); Pro $9.99/мес, 7-дневная проба без карты.
- **Зрелость:** запущенный коммерческий SaaS с pricing, guides, journal, contact/legal и мобильными приложениями.
- **Дифференциаторы:** очень низкий входной тариф, полноценный free tier и cross-platform delivery.
- **Пересечение с AI Trainer:** целевые адаптивные планы, load/recovery, Garmin, plan execution loop.
- **Отличие:** шире интеграции и distribution; у AI Trainer лучше подтверждены детерминированные readiness-conflicts, human approval, rollback, local/self-hosted и выбор AI-провайдера.
- **Источники:** [официальный сайт](https://www.enduroco.in/), [pricing](https://www.enduroco.in/pricing), [workflow](https://www.enduroco.in/how-it-works).
- **Confidence:** high.
- **Missing/uncertain:** наличие AI-чата, точная recovery-модель и фактическая доступность приложений по регионам.

## 3. Enzo

- **URL:** https://enzo.bike/
- **Позиционирование:** минималистичный «правильный workout на сегодня» для self-coached cyclist вместо календарного плана.
- **Виды спорта:** велоспорт; walks/hikes/strength/rest используются только как контекст.
- **AI/coaching:** coaching rules выбирают тип тренировки, AI объясняет решение; построено на 73k+ Strava activities.
- **Планы:** не строит многонедельный календарь — генерирует одну сессию под доступные 30 мин–3 ч; post-ride upload влияет на следующий выбор.
- **Анализ/восстановление:** recent intensity distribution, recovery/cross-training context, power/HR streams; при слабых данных — консервативная рекомендация.
- **Взаимодействие:** короткий web workflow «connect → choose time → ride», не чат.
- **Интеграции:** Strava; экспорт в Garmin, Wahoo, Zwift, Rouvy, FIT/ZWO.
- **Платформы:** web; устройства/indoor apps через экспорт.
- **Цена/проба:** старт бесплатно без карты; Founding Member $49/год (первые 100, цена фиксируется).
- **Зрелость:** Early Access/founding cohort, публичный продукт и pricing, но ранняя стадия.
- **Дифференциаторы:** крайне низкое когнитивное трение и one-workout-at-a-time; не создаёт «calendar debt».
- **Пересечение с AI Trainer:** анализ недавней нагрузки, recovery-aware следующий workout, post-session loop, structured workout export.
- **Отличие:** Enzo уже и проще, только cycling/Strava и без долгого плана/чата; AI Trainer — мультиспорт, Garmin-first, полноценный план, HRV/sleep/readiness и контролируемые изменения.
- **Источники:** [официальный сайт, workflow и pricing](https://enzo.bike/).
- **Confidence:** high.
- **Missing/uncertain:** точные free limits, формула recovery и прямой push vs file export для каждого устройства.

## 4. FitMi

- **URL:** https://www.fitmi.xyz/
- **Позиционирование:** прежний title у URL — «Fitness & Meal Planner»; актуальное позиционирование подтвердить нельзя.
- **Виды спорта / AI / планы / анализ / взаимодействие / интеграции / платформы / цена:** n/a.
- **Зрелость:** официальный URL на дату проверки возвращает Vercel `DEPLOYMENT_NOT_FOUND`; TLS-сертификат также просрочен. Вероятно недоступен/заброшен, но причина не подтверждена владельцем.
- **Дифференциаторы:** n/a.
- **Пересечение/отличие с AI Trainer:** содержательно сравнить нельзя; AI Trainer доступен как рабочий репозиторий/self-hosted продукт, тогда как публичная deployment FitMi отсутствует.
- **Источники:** [официальный URL](https://www.fitmi.xyz/) (проверен прямым запросом 2026-07-13).
- **Confidence:** high для недоступности, low для продуктовых характеристик.
- **Missing/uncertain:** практически все поля; нельзя утверждать, что сервис окончательно закрыт.

## 5. freddy

- **URL:** https://freddy.coach/
- **Позиционирование:** personal health MCP server — слой данных для Claude, ChatGPT и любых MCP-агентов, а не отдельный training-plan SaaS.
- **Виды спорта:** agnostic; endurance, strength, rowing и здоровье зависят от источников.
- **AI/coaching:** не поставляет собственную модель/коучинг; даёт выбранному пользователем AI инструменты для запросов о HRV, sleep, load, glucose, power, lifts и трендах.
- **Планы:** встроенной генерации/адаптивного календаря не заявлено; AI-клиент может рассуждать над read-only данными.
- **Анализ/восстановление:** 100+ metrics, cross-source correlations (например glucose×sleep, load×HRV), полный history в Pro.
- **Взаимодействие:** Claude, ChatGPT app, OpenClaw/Hermes и любой MCP client; библиотека prompt recipes.
- **Интеграции:** 21 source/15 live: Apple Health, Health Connect, Garmin, Fitbit, Oura, Polar, Suunto, Ultrahuman, Wahoo, WHOOP, Withings, Intervals.icu, Concept2, Hevy и др.; Dexcom alpha, Runalyze/Lyfta beta.
- **Платформы:** hosted MCP + companion iOS/Android для phone health sync; AI conversation остаётся в клиенте пользователя.
- **Цена/проба:** Free forever — 1 source/7 days; Pro $49/год; lifetime $249.
- **Зрелость:** доступный продукт 2026 г., официальный ChatGPT app/MCP registry, privacy/terms, экспорт CSV и удаление данных.
- **Дифференциаторы:** model/prompt-agnostic MCP, широкий health/wearable graph, portable AI interface, audit/privacy controls.
- **Пересечение с AI Trainer:** BYO AI, запросы к фактическим данным, Garmin/Intervals, HRV/sleep/load analysis.
- **Отличие:** freddy намного шире как data connector, но read-only и без собственного планировщика/recovery mutation loop; AI Trainer замыкает анализ в план, approval и rollback, а также может работать локально с Ollama.
- **Источники:** [официальный сайт, sources и pricing](https://freddy.coach/), [changelog/articles](https://freddy.coach/articles).
- **Confidence:** high.
- **Missing/uncertain:** какие именно MCP tools разрешают тренировочные записи (лендинг подчёркивает read-only).

## 6. ICU Coach (Intelligent Coaching Utility)

- **URL:** https://icucoach.app/
- **Позиционирование:** mobile AI command center поверх Intervals.icu с 15+ отчётами, recovery, nutrition и coach/team mode.
- **Виды спорта:** бег, велоспорт, плавание.
- **AI/coaching:** Gemini/OpenAI BYOK либо Cloud AI; morning report, readiness check, workout/weekly strategy, nutrition, race prediction, mental coaching, Auto Coach.
- **Планы:** AI workout generation и weekly strategy; степень автоматической долгосрочной адаптации публично описана менее чётко, чем отчёты.
- **Анализ/восстановление:** sleep, HRV, RHR, Body Battery, soreness/mood, CTL/ATL/Form, Health Readiness Index и recovery gate.
- **Взаимодействие:** in-app reports/coach; web team dashboard для тренеров. 5 языков. Внешние мессенджеры не заявлены.
- **Интеграции:** Intervals.icu OAuth; через него Garmin/Polar/Suunto/Wahoo/Huawei/COROS; Apple HealthKit и Android Health Connect.
- **Платформы:** iOS 15+, Android 8+, browser coach dashboard.
- **Цена/проба:** 10 дней без карты (10 AI requests/day); Athlete BYOK €1.99/мес (€17.99/год), Cloud €4.99/мес (€44.99/год); coach tiers €19.99–149.99/мес.
- **Зрелость:** коммерчески доступен, юридические страницы обновлены в мае/июне 2026, app downloads и coach dashboard.
- **Дифференциаторы:** чрезвычайно низкая BYOK-цена, mobile health data, nutrition и полноценная multi-athlete/white-label лестница.
- **Пересечение с AI Trainer:** мультипровайдерный AI, readiness/recovery, HRV/sleep, планы и фактическая аналитика.
- **Отличие:** ICU Coach сильнее в mobile, nutrition, coach B2B и Intervals/device breadth; AI Trainer — self-hosting/Ollama, direct Garmin, demo и более строгий auditable approve/reject/rollback mutation lifecycle.
- **Источники:** [features/home](https://icucoach.app/), [pricing](https://icucoach.app/pricing.html), [download/health integrations](https://icucoach.app/download.html), [coach mode](https://icucoach.app/coach.html).
- **Confidence:** high.
- **Missing/uncertain:** насколько Auto Coach автоматически изменяет календарь и есть ли rollback/version history.

## 7. IcuSync

- **URL:** https://icusync.icu/
- **Позиционирование:** hosted MCP bridge, позволяющий разговаривать в Claude с календарём и данными Intervals.icu.
- **Виды спорта:** бег, велоспорт, плавание; шаблон адаптируем и к другим видам.
- **AI/coaching:** модель — Claude пользователя; 15 инструментов для history, activities, fitness/fatigue/form, wellness, curves/zones, best efforts, summaries и календаря.
- **Планы:** Claude строит structured workouts по зонам; пользователь просматривает и пушит/редактирует/удаляет календарные тренировки. Автономный adaptive plan engine не заявлен.
- **Анализ/восстановление:** Intervals wellness, sleep/HRV, fitness/fatigue/form доступны как контекст.
- **Взаимодействие:** Claude web/mobile/desktop через MCP; free Notion workspace; coach может получить view invitation.
- **Интеграции:** Intervals.icu OAuth; через него Garmin, COROS, Wahoo, Suunto, Zwift, Amazfit, Huawei; Polar activities, но без workout push.
- **Платформы:** web/MCP и Claude clients; без отдельного mobile app.
- **Цена/проба:** $20/год; free trial не заявлен.
- **Зрелость:** работающий продукт 2026 г. с changelog, status, docs/legal и отзывами сообщества.
- **Дифференциаторы:** очень дешёвый conversational read/write access, не требует платного Claude plan, no-copy workflow и Notion шаблон.
- **Пересечение с AI Trainer:** AI chat над wellness/training, structured workout creation и calendar write.
- **Отличие:** IcuSync зависит от Claude и Intervals, не имеет собственного recovery gate/plan engine; AI Trainer управляет доменной логикой, локальными данными и несколькими моделями, но не доступен в мобильном Claude.
- **Источники:** [официальный сайт, tools/pricing/platforms](https://icusync.icu/), [safety disclaimer](https://icusync.icu/disclaimer).
- **Confidence:** high.
- **Missing/uncertain:** отдельные лимиты Claude и точный human-confirmation UX при write operations.

## 8. icuvisor.app

- **URL:** https://connect.icuvisor.app/ (hosted), https://icuvisor.app/ (product/docs)
- **Позиционирование:** open-source local-first MCP server/hosted connector для разговора с Intervals.icu из Claude, ChatGPT и других клиентов.
- **Виды спорта:** sport-agnostic в рамках Intervals.icu; примеры — endurance/race planning.
- **AI/coaching:** поставляет короткий, единично-нормализованный контекст AI-клиенту; собственная модель не нужна.
- **Планы:** calendar events/workouts и structured workout authoring; writes/deletes закрыты явными tool preferences/safety gates. Самостоятельная адаптивная периодизация не заявлена.
- **Анализ/восстановление:** activities/intervals, fitness, power/HR/pace curves, wellness, readiness, coach rosters/custom items.
- **Взаимодействие:** Claude, ChatGPT, Cursor и любой MCP client; local binary или hosted HTTPS.
- **Интеграции:** Intervals.icu; downstream device ecosystem через Intervals.
- **Платформы:** signed binary/Dmg/MSI/tar для macOS, Windows, Linux; hosted web connector.
- **Цена/проба:** local MIT-licensed бесплатно; hosted pricing публично не найден.
- **Зрелость:** v1.4.0, stable local-first line, downloads, GitHub/docs/roadmap, Windows packages и hosted OAuth.
- **Дифференциаторы:** минимальная trust boundary, API key остаётся локально, tool profiles compact/core/full, open source и explicit write/delete scope.
- **Пересечение с AI Trainer:** local/private usage, AI over training/readiness, calendar authoring, human safety gates.
- **Отличие:** icuvisor — переиспользуемая инфраструктура/connector, а не готовый coach; AI Trainer содержит собственные расчёты, планы и recovery loop. icuvisor шире по AI-client portability и coach rosters.
- **Источники:** [официальный сайт/downloads](https://icuvisor.app/), [hosted setup/privacy](https://connect.icuvisor.app/), [client/tool profiles](https://icuvisor.app/connect/other-clients/).
- **Confidence:** high.
- **Missing/uncertain:** hosted цена и какие advanced analyzers считаются stable vs optional.

## 9. Interval Insights

- **URL:** https://intervalinsights.cvebbesen.no/
- **Позиционирование:** мобильный AI-анализатор именно интервальных тренировок — «понимать интервалы, а не только splits».
- **Виды спорта:** лендинг иллюстрирует бег; прочие виды не подтверждены.
- **AI/coaching:** классифицирует тип тренировки и раскладывает её на reps/sets/intervals с pace, HR и recovery.
- **Планы:** не заявлены.
- **Анализ/восстановление:** сравнение повторов, drift/consistency/patterns; общий recovery/readiness не заявлен.
- **Взаимодействие:** визуальный mobile analysis; чат не заявлен.
- **Интеграции:** прямой Strava sync.
- **Платформы:** iOS/Android обозначены как `Coming soon`.
- **Цена/проба:** n/a.
- **Зрелость:** pre-launch лендинг; App Store/Google Play ещё не доступны.
- **Дифференциаторы:** узкий interval-first UX, автоматическая сегментация повторов.
- **Пересечение с AI Trainer:** post-workout analytics и HR/pace context.
- **Отличие:** существенно уже и не является тренером/планировщиком; AI Trainer покрывает долгий контур analytics→readiness→plan→replan, но у него нет подтверждённой специализированной AI-сегментации повторов.
- **Источники:** [официальный pre-launch лендинг](https://intervalinsights.cvebbesen.no/).
- **Confidence:** high по заявленным функциям, medium по будущей доступности.
- **Missing/uncertain:** дата запуска, цена, виды спорта, model/provider и глубина анализа.

## 10. Intervals Agent

- **URL:** https://intervals.q5m.ai/
- **Позиционирование:** human-in-the-loop AI planner: из goal + constraints + recent history делает Zwift-ready structured workout.
- **Виды спорта:** публичный UX ориентирован на cycling.
- **AI/coaching:** GPT-5.4 строит сессию из profile, last-minute guidance, training status/readiness; пользователь обязательно review/tune до schedule.
- **Планы:** single-workout generation, one-click scheduling; многонедельная периодизация/автоадаптация не подтверждена.
- **Анализ/восстановление:** recent load/readiness видны planner-у; полноценный recovery dashboard не заявлен.
- **Взаимодействие:** web planner; Discord/Canny/email для feedback/support.
- **Интеграции:** Intervals.icu обязательно; Zwift best experience, Garmin Connect supported, Strava coming soon.
- **Платформы:** web; выполнение на Zwift/Garmin через sync.
- **Цена/проба:** alpha access бесплатно на ограниченное время; lifetime deal и monthly/annual subscription `coming soon`.
- **Зрелость:** alpha, terms прямо предупреждают о смене функций/перерывах; активный build hash и privacy stack (Supabase/OpenAI/Intervals).
- **Дифференциаторы:** чистый generate→review→ride workflow, прозрачный human-in-the-loop и narrow cycling execution.
- **Пересечение с AI Trainer:** data-grounded structured workout, preview before mutation, readiness context.
- **Отличие:** Intervals Agent проще и глубже сфокусирован на одном workout/Intervals/Zwift; AI Trainer имеет многонедельный план, recovery gate, plan versioning/rollback и self-hosted/multi-model architecture.
- **Источники:** [официальный продукт](https://intervals.q5m.ai/), [pricing/alpha status](https://intervals.q5m.ai/pricing), [terms](https://intervals.q5m.ai/terms), [privacy](https://intervals.q5m.ai/privacy).
- **Confidence:** high.
- **Missing/uncertain:** будущая цена, alpha capacity, recovery algorithm и roadmap multi-week planning.

## 11. Intervals.coach

- **URL:** https://intervals.coach/
- **Позиционирование:** marketplace data-driven human coaches + professional tool suite, а не чистый autonomous AI coach.
- **Виды спорта:** endurance, strength, HYROX, CrossFit/hybrid; coach directory — triathlon emphasis.
- **AI/coaching:** AI-assisted strength, HYROX и CrossFit creators; endurance workout library/editor и annual plan/periodization; race/pace/long-run utilities.
- **Планы:** annual training plan с automatic periodization/performance metrics; Training Hub для hybrid планов — coming soon. Адаптация по recovery публично не заявлена.
- **Анализ/восстановление:** performance utilities, но отдельный recovery/readiness контур не заявлен.
- **Взаимодействие:** human coach directory, profiles/reviews/direct contact; email support.
- **Интеграции:** Intervals.icu workout sync.
- **Платформы:** web.
- **Цена/проба:** athlete marketplace бесплатно; Coach €9.99/мес с 7-дневной пробой; Partner Coach €29.99/мес; self-coached/independent discount 30%.
- **Зрелость:** работающий marketplace/tools SaaS, публично 26/50 coach slots; часть модулей ещё coming soon.
- **Дифференциаторы:** сочетание human-coach discovery/reputation и инструментов для endurance+strength+hybrid.
- **Пересечение с AI Trainer:** workout/season planning, AI-assisted generation, Intervals-style data-driven coaching.
- **Отличие:** B2B/marketplace и human relationship — отсутствуют в AI Trainer; AI Trainer гораздо сильнее как личный readiness-aware autonomous assistant с локальной аналитикой.
- **Источники:** [tools](https://www.intervals.coach/tools), [pricing](https://www.intervals.coach/pricing), [coach workflow](https://intervals.coach/for-coaches), [how it works](https://www.intervals.coach/how-it-works).
- **Confidence:** high.
- **Missing/uncertain:** что именно входит в AI для endurance, зрелость upcoming Training Hub и отдельная цена услуг найденных coaches.

## 12. Intervals Pro

- **URL:** https://intervals.pro/
- **Позиционирование:** «coach in WhatsApp» — полный conversational AI coach поверх Intervals.icu с планированием, daily checks и calendar mutations.
- **Виды спорта:** велоспорт, бег, плавание, strength, triathlon/multi-sport.
- **AI/coaching:** persistent memory, анализ full history, daily/morning checks, workout recommendations, research/data modes; модели Anthropic, Google, Perplexity, DeepSeek через direct/OpenRouter routing.
- **Планы:** periodized до 26 недель, race/calendar-aware; structured power/pace/HR sessions; пользовательская approval queue перед записью; ре-план при изменениях.
- **Анализ/восстановление:** power/pace curves, MMP, CTL/ATL/TSB, decoupling/cadence drift, sleep, HRV, training load и wellness.
- **Взаимодействие:** WhatsApp, Telegram и web; proactive morning message/notifications.
- **Интеграции:** Intervals.icu как data layer; через него Garmin, Wahoo, COROS, Polar, Suunto, Amazfit, Huawei, Zwift, MyWhoosh, Rouvy, Concept2, Strava, Oura, WHOOP; Google Calendar и Outlook.
- **Платформы:** responsive web/PWA-like chat + WhatsApp/Telegram; workout devices through Intervals.
- **Цена/проба:** 14 дней без карты; Pro £19.99/мес, unlimited subject to fair use.
- **Зрелость:** один из наиболее зрелых конкурентов группы: 3,500 claimed users, 600+ plans/month, активный weekly-ish changelog и коммерческие/legal контракты Revitt Ltd.
- **Дифференциаторы:** coach в привычных мессенджерах, proactive check-ins, 26-week multi-sport, rich power analysis, approval queue и persistent memory.
- **Пересечение с AI Trainer:** почти полный: чат над health/training, планы, recovery, structured workouts, approval, адаптация и аналитика.
- **Отличие:** Intervals Pro сильнее по channels, ecosystem, power curves, commercial polish и proactivity; AI Trainer сильнее по local/self-hosted privacy, direct Garmin, provider choice/Ollama, deterministic salience gate и явно подтверждённому rollback/audit trail.
- **Источники:** [официальный продукт/features](https://intervals.pro/), [pricing](https://intervals.pro/pricing), [guide](https://intervals.pro/guide), [updates](https://intervals.pro/updates), [terms/integrations/providers](https://intervals.pro/terms).
- **Confidence:** high.
- **Missing/uncertain:** точные fair-use thresholds и насколько все claimed integrations двунаправленные.

## 13. Koda Coach

- **URL:** https://kodacoach.nl/
- **Позиционирование:** AI performance/cycling coach с живым планом, ежедневным fitness check и conversational intake.
- **Виды спорта:** велоспорт; Concept2 фигурирует среди платформ, но полноценная rowing coaching support не подтверждена.
- **AI/coaching:** interactive AI chat, post-ride feedback, цели/промежуточные события, nutrition/mental guidance по отзывам на официальном сайте.
- **Планы:** полностью адаптивный план, мгновенная перекалибровка недели под занятость/погоду/форму; синхронизация календаря.
- **Анализ/восстановление:** form/fatigue, feeling, sleep, HRV и health data; daily dashboard и управление пиком к событию.
- **Взаимодействие:** in-app chat и dashboard.
- **Интеграции:** Intervals.icu; Garmin, Wahoo, Zwift, Hammerhead, Rouvy, MyWhoosh, BikeTerra, Concept2, Strava; health from Garmin/Oura/WHOOP/Amazfit/Polar/Suunto/COROS/Apple Watch/Google Fit.
- **Платформы:** web; delivery на devices/platforms через ecosystem.
- **Цена/проба:** 14 дней; €11.99/мес включая VAT; временная BEAT discount 50% first year до Aug 1.
- **Зрелость:** коммерчески доступный продукт 2026, legal pages и реальная login surface; сравнительно молодой.
- **Дифференциаторы:** сильный cycling persona/relationship UX, Gran Fondo/event focus и широкая wellness/device сеть через Intervals.
- **Пересечение с AI Trainer:** adaptive plan, chat, Garmin/HRV/sleep, fatigue/form, post-session feedback.
- **Отличие:** Koda шире по ecosystem и мягкому conversational coaching; AI Trainer — multi-sport, self-hosted, deterministic/auditable recovery decisions и multi-provider.
- **Источники:** [официальный английский лендинг](https://kodacoach.nl/landing?lang=en), [terms](https://kodacoach.nl/terms-of-service).
- **Confidence:** high.
- **Missing/uncertain:** exact AI provider, automatic-write safeguards, native mobile status и depth beyond cycling.

## 14. LeCoach

- **URL:** https://lecoach.app/
- **Позиционирование:** 24/7 AI cycling & running coach, соединяющий structured long-term plan с reactive chat.
- **Виды спорта:** велоспорт и бег; strength/habits как поддерживающие активности.
- **AI/coaching:** personal chat, plan changes, ride/run and wellness analysis, weekly AI review, execution score, habits/tasks, weight.
- **Планы:** multi-week plans по abilities/preferences/schedule, on-the-fly workout generation, manual editor, automatic response to completed activity/wellness, Plan Health Score/recalculation.
- **Анализ/восстановление:** recovery score, poor-recovery alternative, CTL/eFTP/power profile, plan execution and detailed activity analytics.
- **Взаимодействие:** in-app chat/web; внешние мессенджеры не заявлены.
- **Интеграции:** bidirectional Intervals.icu workouts/activities/wellness; delivery to Zwift, Garmin, Wahoo и другие through Intervals.
- **Платформы:** web.
- **Цена/проба:** 14 дней без карты; early-adopter €6.99/мес, на год €62.91 (€5.24/мес эквивалент).
- **Зрелость:** запущенный paid SaaS, пользователи в 40+ странах (claim), pricing/legal/resources.
- **Дифференциаторы:** один из наиболее полных cycling/run competitors: plan health, recovery/execution scores, manual control, habits и weight в едином UX.
- **Пересечение с AI Trainer:** планы, чат, recovery/readiness, activity analysis, plan-fact и calendar mutations.
- **Отличие:** LeCoach сильнее по polished wellness/plan/execution UX, Intervals ecosystem и привычкам; AI Trainer — direct Garmin/local data, triathlon, provider independence, deterministic approval/rollback.
- **Источники:** [официальный сайт/features](https://lecoach.app/), [pricing](https://lecoach.app/pricing).
- **Confidence:** high.
- **Missing/uncertain:** AI provider, native apps, точная rollback/versioning semantics.

## 15. LoGua KLK

- **URL:** https://loguaklk.com/
- **Позиционирование:** испаноязычный AI coach для power cyclists: «твои данные знают следующую поездку» + social competition.
- **Виды спорта:** велоспорт (gran fondo, TT, stages), ориентирован на power meter.
- **AI/coaching:** weekly plan и daily readjustment на основе actual execution, HRV, sleep, fatigue, event goal; объясняет цель сессии.
- **Планы:** event periodization, available days, automatic recalibration при отклонении/усталости.
- **Анализ/восстановление:** CTL/ATL/TSB, FTP, power curve, ride point-by-point, HRV/sleep/fatigue.
- **Взаимодействие:** web dashboard/coach; social league `Los Picaos` с divisions, 1v1, weekly challenges и road segments.
- **Интеграции:** Intervals.icu one-click; Strava read-only (excluded from AI processing), Polar read, Wahoo direct and plan-to-ELEMNT, Garmin via Intervals (direct coming), FIT/GPX/TCX; iOS/Apple Health coming.
- **Платформы:** web; future iOS.
- **Цена/проба:** Free forever dashboard/Intervals/social; Coach AI $9.99/мес, 7 дней без карты; Team/Coach custom.
- **Зрелость:** open public beta, operator LoGua Labs LLC; claims 1,500+ real activities, service explicitly `AS IS`.
- **Дифференциаторы:** social gamification + AI cycling plan, direct Wahoo, power-first Spanish/LatAm positioning.
- **Пересечение с AI Trainer:** load/form, HRV/sleep, event plan, adaptive daily change, explanation.
- **Отличие:** LoGua сильнее по social/community, Wahoo/Intervals и commercial onboarding; AI Trainer — broader sports, direct Garmin/local privacy, deeper deterministic safety and rollback, multi-model.
- **Источники:** [официальный лендинг/features/pricing/FAQ](https://loguaklk.com/).
- **Confidence:** high.
- **Missing/uncertain:** количество active users, exact AI provider и promised direct Garmin/iOS (не засчитаны как реализованные).

## 16. MiTrAIner

- **URL:** https://www.mitrainer.es/
- **Позиционирование:** испаноязычный 24/7 AI coach для running/triathlon с macroplans, session analysis и Intervals calendar delivery.
- **Виды спорта:** бег и триатлон (следовательно swim/bike/run внутри планов, но sport-level feature parity не раскрыта).
- **AI/coaching:** contextual chat о plan/nutrition/injuries, daily session analysis, Sunday weekly review, рекомендации по full athlete context.
- **Планы:** macrocycle + weeks from chat, HR/pace/power targets, план загружается в Intervals.icu и на GPS watch; заявлена корректировка нагрузки.
- **Анализ/восстановление:** HR, pace, power, HRV, CTL, planned-vs-actual; Suunto sleep/HRV/recovery.
- **Взаимодействие:** web AI chat/dashboard; email только для beta access communications.
- **Интеграции:** Intervals.icu (activities/calendar/zones), Strava enrichment, Withings body composition, Suunto sleep/HRV/recovery/workouts; COROS coming.
- **Платформы:** web.
- **Цена/проба:** регистрация обозначена бесплатной; публичной платной цены нет.
- **Зрелость:** public/private beta wording на одной странице противоречиво (`Beta privada activa`, ниже `Beta abierta`); registration/login существуют.
- **Дифференциаторы:** Spanish-first run/triathlon, Withings body composition, weekly narrative loop.
- **Пересечение с AI Trainer:** run/triathlon planning, AI chat, HRV/load, plan-fact, structured calendar.
- **Отличие:** MiTrAIner шире по Intervals/Withings/Suunto; AI Trainer зрелее по direct Garmin, self-hosting, auditable plan mutation/rollback и provider choice.
- **Источники:** [официальный лендинг](https://www.mitrainer.es/).
- **Confidence:** medium-high.
- **Missing/uncertain:** beta status, paid pricing, AI provider, whether triathlon supports all three disciplines equally, write safeguards.

## 17. Montis.icu Coach

- **URL:** https://www.cliveking.net/
- **Позиционирование:** physiology-governed, deterministic endurance intelligence layer, явно противопоставленный «LLM improvisation».
- **Виды спорта:** endurance broadly; power-heavy markers, examples include cycling and Concept2; exact supported sport matrix n/a.
- **AI/coaching:** 63+ markers, Unified Reporting Framework, Adaptive Decision Engine; natural language is interface, physiology is authority; ChatGPT App, Claude MCP, Gemini BYOK app.
- **Планы:** forecasts microcycles and writes structured sessions to Intervals.icu; separates `can` (capacity) from `should` (phase intent), enforcing recovery/consolidation when needed.
- **Анализ/восстановление:** CTL/ATL/TSB/TSS/ACWR, monotony/strain, HRV/sleep/mood/soreness, recovery, W′ repeatability, decoupling/durability, neural density, power-curve energy-system progression, taper.
- **Взаимодействие:** ChatGPT app, Claude+MCP, Montis app hub/Gemini app; deterministic reports weekly/season/wellness/annual.
- **Интеграции:** полностью зависит от Intervals.icu; downstream Zwift/Garmin и connected platforms; Garmin/HRV4/WHOOP-derived markers when present.
- **Платформы:** web AI apps and MCP; no native mobile app confirmed.
- **Цена/проба:** бесплатно, добровольная supporter model; Gemini app BYOK.
- **Зрелость:** working V5, public roadmap/changelog/GitHub/docs and supporter feedback; independent project rather than conventional paid SaaS.
- **Дифференциаторы:** самая глубокая публично описанная deterministic physiology ontology группы, reproducible reports, open evolution.
- **Пересечение с AI Trainer:** Banister/load, HRV/readiness, deterministic decision layer, microcycle generation and calendar write.
- **Отличие:** Montis гораздо глубже по power/durability/neural/energy-system analytics и AI-client distribution; AI Trainer лучше как integrated self-hosted product with direct Garmin, provider abstraction, explicit preview/approve/reject/rollback and plan version history.
- **Источники:** [официальный product/methodology/setup/pricing statement](https://www.cliveking.net/), [public changelog](https://www.cliveking.net/changelog).
- **Confidence:** high для заявленной архитектуры, medium для independently validated outcomes.
- **Missing/uncertain:** sport coverage, exact license/backend openness, user count and safety semantics of calendar writes.

## 18. MyCyclingTrainer

- **URL:** https://mycyclingtrainer.com/
- **Позиционирование:** all-in-one AI cycling planning, nutrition, analytics, race and equipment management.
- **Виды спорта:** велоспорт (road/MTB/gravel).
- **AI/coaching:** AI plans/workouts, beta training assistant chat with preview/apply/discard actions, weekly AI email, GPX race strategy and nutrition.
- **Планы:** 5-step generation by goal/equipment/hours/days/phase; periodized event plans, secondary events, preferred long day, AI replanning and workout editor.
- **Анализ/восстановление:** CTL/ATL/TSB/TSS/FTP, power curve/W·kg, consistency, compliance, fatigue risk, RPE/feel, performance prediction; recovery is load-centric, HRV/sleep not prominent.
- **Взаимодействие:** web dashboard/chat, in-app notifications, weekly email.
- **Интеграции:** Intervals.icu activity/workout sync; through it Garmin/Wahoo/Zwift; exports ZWO/MRC; GPX input.
- **Платформы:** responsive web/PWA-like site.
- **Цена/проба:** публичной subscription price не найдено; сайт предлагает начать бесплатно и поддержать personal project donation/coffee. Usage limits (например планы в месяц) видны в UI strings, но конкретные квоты n/a.
- **Зрелость:** активно поддерживается: подробный changelog до May 2026, help, terms, bilingual EN/ES; personal/community project.
- **Дифференциаторы:** nutrition + equipment/component maintenance + event GPX prediction в одном cycling cockpit; прозрачный changelog.
- **Пересечение с AI Trainer:** planning, AI chat, CTL/ATL/TSB, plan-fact, preview/apply changes, structured export.
- **Отличие:** MyCyclingTrainer глубже в cycling-specific nutrition/races/equipment/power analytics; AI Trainer шире по sports/recovery HRV/sleep, self-hosted, direct Garmin and auditable rollback.
- **Источники:** [официальный сайт](https://mycyclingtrainer.com/en), [help/features](https://mycyclingtrainer.com/en/help), [changelog](https://mycyclingtrainer.com/changelog), [terms](https://mycyclingtrainer.com/es/terms).
- **Confidence:** high по функциям, medium по цене/квотам.
- **Missing/uncertain:** monetization, exact plan limits, native apps and AI provider.

## 19. MyTrainPal

- **URL:** https://mytrainpal.app/
- **Позиционирование:** broad endurance AI coach с proven plan blueprints, deep activity analysis и отдельным coach tier.
- **Виды спорта:** cycling/running/endurance; публичный hero не дал исчерпывающей sport matrix.
- **AI/coaching:** chat/reviews; анализ W′bal depletion, cardiac decoupling, intensity drift; natural-language scheduling; coach tier adds AI triage, weekly summaries and messaging.
- **Планы:** week-by-week plan, phases Base/Build/Peak/Taper/Recovery/Race, blueprints 80/20/Pfitz/Norwegian, planned-vs-actual and shift actions.
- **Анализ/восстановление:** load/time/distance actuals, performance/interval analysis; точные HRV/sleep/readiness функции не подтверждены.
- **Взаимодействие:** web AI coach; coach-athlete messaging in Coach tier.
- **Интеграции:** Strava, Garmin, Intervals.icu, Apple Health, Zwift, Wahoo and more; bidirectional calendar sync claimed.
- **Платформы:** web; native apps n/a.
- **Цена/проба:** Free с monthly AI credits и core features; Plus $9.99/мес с 1,500 AI chat credits; Coach $24.99/мес.
- **Зрелость:** доступный коммерческий web product с terms updated Mar 2026; main page иногда отдаёт app shell, marketing content индексируется.
- **Дифференциаторы:** broad integrations, research-style blueprints, advanced W′/decoupling analysis and low-priced coach workflow.
- **Пересечение с AI Trainer:** plans/phases, AI chat, plan-fact, Garmin, workout analysis.
- **Отличие:** MyTrainPal шире по ecosystem/coaches and advanced cycling analytics; AI Trainer сильнее по explicit recovery data/gate, local self-hosting, model choice, audit/rollback.
- **Источники:** [официальный сайт/features/pricing](https://mytrainpal.app/), [terms](https://mytrainpal.app/terms-of-service).
- **Confidence:** medium-high.
- **Missing/uncertain:** complete sport list, recovery signals, native apps, credit consumption mechanics and AI provider.

## 20. Norvin

- **URL:** https://norvin.fit/
- **Позиционирование:** adaptive coach для indoor rowing, grounded in British Rowing methodology; terms также указывают current cycling support.
- **Виды спорта:** indoor rowing; cycling supported per terms, но marketing/feature depth сосредоточен на erg.
- **AI/coaching:** daily coaching note, forward-looking post-workout feedback, per-interval analysis, 7 goals and automatic 2K-zone updates; Anthropic Claude integration.
- **Планы:** periodized plan, `Can't Do Today?` skip/shorten/swap, automatic reshape after missed/changed session, flexible duration/reps.
- **Анализ/восстановление:** readiness from training load/RPE/recovery, TSB, rowing-native zones/load, adherence, RPE vs performance, baseline trends.
- **Взаимодействие:** web dashboard and morning note; chat/messaging not claimed.
- **Интеграции:** Intervals.icu, Garmin and ecosystem including Polar/Concept2; FIT/TCX upload, FIT workout export, PM5 setup guidance.
- **Платформы:** web.
- **Цена/проба:** бесплатно during early access; paid plans later, founder pricing promised (not yet published); free one-workout analysis without signup.
- **Зрелость:** early access but unusually complete public product, terms/operator, upload demo and focused methodology.
- **Дифференциаторы:** rowing-native load rather than cycling TSS, PM5/Concept2 execution and excellent narrow sport specificity.
- **Пересечение с AI Trainer:** periodized/adaptive plan, readiness, TSB/load, post-session loop and structured export.
- **Отличие:** Norvin dominates rowing specificity, which AI Trainer does not target; AI Trainer is more mature in HRV/sleep/Garmin health, chat, multi-provider, self-hosting and auditable recovery changes.
- **Источники:** [официальный сайт/features/status](https://norvin.fit/), [terms/sports/provider](https://norvin.fit/terms).
- **Confidence:** high.
- **Missing/uncertain:** future price, depth of cycling support, exact readiness formula and native apps.

## 21. PaceKeeper AI

- **URL:** https://www.pacekeeper.icu/
- **Позиционирование:** local desktop workflow manager между CustomGPT-generated plan и реальным экспортом; прямо говорит, что сам планы не генерирует.
- **Виды спорта:** cycling, running, strength; nutrition plans отдельно.
- **AI/coaching:** specialised ChatGPT GPTs создают training/nutrition/coaching drafts; PaceKeeper validates structure rather than doing physiological AI inference.
- **Планы:** проверка required fields, zone/volume/phase consistency, versioning and traceability; valid plan exports to Intervals.icu/PDF/email.
- **Анализ/восстановление:** activity/recovery analysis не заявлен; health safety специально остаётся ответственностью пользователя/эксперта.
- **Взаимодействие:** desktop app + CustomGPTs; sharing by email/PDF.
- **Интеграции:** Intervals.icu; дальнейшая синхронизация к Garmin/Strava и другим платформам идёт через Intervals.
- **Платформы:** Windows download доступен; macOS/Linux `coming soon`; local rather than cloud; UI на 18 языках.
- **Цена/проба:** n/a на публичном сайте.
- **Зрелость:** работающий Windows-oriented product/download; другие OS ещё не готовы, pricing отсутствует.
- **Дифференциаторы:** validation/versioning/reproducible export and local data sovereignty; очень узкий, но важный reliability layer.
- **Пересечение с AI Trainer:** structured plan, version history, human control and local/private orientation.
- **Отличие:** PaceKeeper не анализирует athlete data и не адаптирует план; AI Trainer — собственно coach/analytics engine. PaceKeeper сильнее в formal schema validation, PDF/email distribution и multilingual desktop packaging.
- **Источники:** [официальный сайт/features/download](https://pacekeeper.icu/).
- **Confidence:** high.
- **Missing/uncertain:** цена/license, текущая Windows version, Intervals API write mode and release dates for macOS/Linux.

## Сводка по группе

### Наиболее прямые конкуренты AI Trainer

1. **Intervals Pro** — максимально близок по полному циклу chat → data analysis → plan → approval → calendar; превосходит по WhatsApp/Telegram, Intervals ecosystem и power analytics.
2. **LeCoach** — близкий cycling/run SaaS с recovery/execution/plan-health scores и адаптивным long-term plan.
3. **Enduco, EnduroCo, Koda, LoGua KLK** — коммерческие adaptive coaches с хорошим device distribution; чаще менее прозрачны в safety/versioning semantics.
4. **Montis.icu** — главный конкурент по объяснимой/deterministic physiology, особенно для power-oriented endurance analytics.
5. **ICU Coach** — сильный mobile/BYOK/coach-team конкурент с nutrition и health integrations.

### Смежные, а не полные конкуренты

- **freddy, IcuSync, icuvisor** — AI data/MCP infrastructure. Они показывают рыночный спрос на «общаться с данными в уже любимом AI-клиенте», но сами обычно не замыкают безопасный adaptive-plan loop.
- **Intervals Agent, Enzo** — превосходно сфокусированные next-workout generators. Урок — один быстрый решаемый вопрос может давать более ясный UX, чем большой dashboard.
- **Intervals.coach** — human marketplace/B2B tools; **PaceKeeper** — validation/versioning/distribution; **Interval Insights** — interval segmentation; **Norvin** — sport-native rowing.
- **FitMi** — публично недоступен, содержательно сравнить нельзя.

### Общие рыночные паттерны

- **Intervals.icu стал главным aggregation/distribution layer:** 16 из 21 приложений явно используют его или зависят от него. AI Trainer уже читает через него профиль, гонки и plan-fact evidence и умеет создавать workout events из legacy Planning; gap — полноценный onboarding и last-mile delivery в основном web-контуре.
- **Messaging beats another dashboard:** WhatsApp/Telegram у Intervals Pro и Claude/MCP у IcuSync/icuvisor сокращают friction. У AI Trainer пока только web.
- **Recovery-aware adaptation — table stakes:** HRV/sleep/fatigue/readiness заявлены у большинства полноценных coaches. Дифференциатор AI Trainer не сам score, а трассируемый `signal → conflict → proposal → approve/reject → rollback`.
- **Human-in-the-loop становится нормой:** Intervals Agent review-before-schedule, Intervals Pro approval queue, icuvisor write scopes, MyCyclingTrainer apply/discard. Это подтверждает правильность approval lifecycle AI Trainer.
- **Коммерческий ориентир:** athlete plans в основном €/$5–20 в месяц; BYOK/MCP connectors — $20–49 в год; free/early-access широко используются для acquisition.
- **Вертикальная специализация выигрывает:** Norvin (rowing), Enzo (today’s ride), Interval Insights (repeat analysis), MyCyclingTrainer (nutrition/equipment/race) легче объясняют immediate value.

### Возможности для дифференциации AI Trainer

1. Упаковать сильную сторону как **«самостоятельный, локальный и обратимый AI coach»**, а не просто ещё один генератор плана.
2. Сделать recovery decision trail пользовательской фичей: показать числа, конфликт, альтернативу, подтверждение и одну кнопку rollback.
3. Довести существующий Intervals.icu слой до production UX: безопасная настройка, web-доставка событий, статус синхронизации и повторяемые без дублей операции.
4. Рассмотреть лёгкий внешний канал (Telegram прежде всего для русскоязычной аудитории) или MCP interface, сохранив approval gates для write actions.
5. Не пытаться сразу догнать весь breadth: отдельный «что делать сегодня и почему?» flow может лучше продемонстрировать existing readiness/replan engine.
