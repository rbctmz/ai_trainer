# Intervals.icu AI Trainer apps — batch 3 (data rows 43–63)

Дата проверки: **2026-07-13**. Диапазон: 21 запись, от Peaking до WorkoutContext включительно. Baseline сравнения: [`ai_trainer_product_profile.md`](./ai_trainer_product_profile.md), только реализованные функции. `n/a` означает, что в доступном официальном источнике сведений нет; это не утверждение об отсутствии функции.

## 1. Peaking

- **URL:** https://peaking.pro/
- **Позиционирование / спорт:** AI-assisted периодизированные планы для cycling, running, swimming, gym и triathlon, построенные поверх Intervals.icu.
- **AI/coaching и планы:** AI генерирует структуру phase → week → day и структурированные тренировки; недельный AI-анализ, adherence score 0–100; drag-and-drop перенос с повторной синхронизацией.
- **Анализ / recovery:** завершённые активности, wellness (HRV, sleep, weight, Body Battery), FTP/threshold/max HR; отдельная логика изменения плана по readiness публично не описана.
- **Взаимодействие:** web UI; coach portal. Чат и внешние каналы n/a.
- **Интеграции / платформы:** двусторонний OAuth Intervals.icu; импорт CSV Garmin/Strava; ZWO. Web private beta; iOS TestFlight; Android build pending.
- **Цена / зрелость:** private beta, ручное одобрение, «hundreds of users» по сообщению разработчика; в обсуждении упомянуто $102/year, но официальный pricing не найден.
- **Дифференциаторы:** coach multi-athlete portal, adherence scoring, bilingual ES/EN, Intervals-native round trip.
- **Пересечение с AI Trainer:** планы, structured workouts, HRV/sleep, план-факт и AI-анализ. **Отличие:** шире Intervals/device sync и coach portal; AI Trainer сильнее self-hosting, direct Garmin, multi-provider/Ollama, approval journal/rollback.
- **Источники:** [официальный сайт](https://peaking.pro/); [первичное объявление разработчика в Intervals.icu](https://forum.intervals.icu/t/peaking-ai-assisted-training-plans-built-around-intervals-icu-web-live-ios-android-in-testflight/130216).
- **Confidence:** medium. **Missing/uncertain:** точная цена, чат, автоматическая recovery-адаптация, Android availability.

## 2. Peak Watts

- **URL:** https://peakwatts.app/
- **Позиционирование / спорт:** privacy-first мобильный performance + nutrition анализатор и bike computer для cycling, running, triathlon.
- **AI/coaching и планы:** AI-assisted workout builder, библиотека и calendar sync; полноценный AI-чат или генерация многонедельного плана не подтверждены.
- **Анализ / recovery:** physics-based power breakdown, CdA, автоопределение climbs/intervals/laps, durability, curves, fitness/fatigue, recovery, HR и sleep; AI food detection и fueling balance.
- **Взаимодействие:** app UI; чат/мессенджеры n/a.
- **Интеграции / платформы:** iOS/Android; Intervals.icu; sensors, indoor trainers, smart fans, radar, GoPro; прочие sync-платформы не названы.
- **Цена / зрелость:** subscription monthly/annual, конкретная цена n/a; 7-day free trial; запущенный продукт.
- **Дифференциаторы:** локальное хранение на устройстве, аэродинамика/CdA, полноценная запись и навигация, питание и GoPro.
- **Пересечение:** fitness/fatigue/recovery/sleep, workouts. **Отличие:** гораздо сильнее mobile recording, sensors, physics и nutrition; AI Trainer сильнее разговорный коуч, goal planning, безопасные approve/reject/rollback и self-hosting.
- **Источники:** [features/home](https://peakwatts.app/), [terms/trial](https://peakwatts.app/terms/).
- **Confidence:** high. **Missing/uncertain:** сумма подписки, адаптивность долгого плана, каналы общения.

## 3. PeekPace

- **URL:** https://peekpace.com/
- **Позиционирование / спорт:** n/a — публичная страница не индексируется и официальный URL не удалось прочитать.
- **AI/coaching; планы; анализ/recovery; взаимодействие; интеграции; платформы; цена:** n/a.
- **Зрелость:** присутствует в каталоге Intervals.icu, иного подтверждения доступности нет.
- **Пересечение / отличие:** оценить нельзя без выдумывания.
- **Источники:** [официальный URL](https://peekpace.com/), запись Intervals.icu catalog id `332`.
- **Confidence:** low. **Missing/uncertain:** практически весь продуктовый профиль.

## 4. PlanWatts

- **URL:** https://planwatts.cc/
- **Позиционирование / спорт:** conversational AI coach для cycling, running, swimming/triathlon.
- **AI/coaching и планы:** чат, athlete memory, AI workout generation, multi-week Base→Build→Peak→Taper plans, multi-event awareness, day-level edits, post-session analysis; interactive cards; OpenAI/Claude model selection и BYOK.
- **Анализ / recovery:** activity/lap analysis, TSS, CTL/ATL/TSB/PMC, wellness/HRV-aware warnings; recovery decision loop не описан так же строго, как в AI Trainer.
- **Взаимодействие:** web chat; coach teams и notes; внешние мессенджеры n/a.
- **Интеграции / платформы:** OAuth/API Intervals.icu as hub, two-way ATP; Garmin, Strava, Wahoo beta и устройства через Intervals; FIT/ZWO sharing. Web responsive.
- **Цена / зрелость:** Free €0 (50 credits), Supporter €3/mo (150, AI plans), Pro €9/mo (500, model choice); активно выпускается, публичные docs/changelog.
- **Дифференциаторы:** очень близкий прямой конкурент: polished conversational authoring, Intervals ATP, device delivery, coach teams, sharing, multilingual UI.
- **Пересечение:** почти весь core — chat, plans, activity analysis, TSS/form, structured files. **Отличие:** PlanWatts сильнее integrations/device/teams/editor/SaaS; AI Trainer — self-hosted, direct Garmin, больше AI providers/Ollama, explicit proposal approval, audit, rollback и детерминированный readiness gate.
- **Источники:** [home/pricing](https://planwatts.cc/), [official docs/changelog](https://planwatts.cc/docs), [connection docs](https://planwatts.cc/docs/getting-connected).
- **Confidence:** high. **Missing/uncertain:** нативные apps, точный recovery action policy.

## 5. Puncheur APP

- **URL:** https://puncheur.app/
- **Позиционирование / спорт:** title заявляет «Intelligent Cycling Coach»; подробности недоступны из-за ошибки загрузки SPA.
- **AI/coaching; планы; анализ/recovery; взаимодействие; интеграции; платформы; цена:** n/a.
- **Зрелость:** домен работает, но публичная app surface на дату проверки возвращала critical module error.
- **Пересечение / отличие:** вероятное пересечение по cycling coaching, остальное оценить нельзя.
- **Источники:** [официальный сайт](https://puncheur.app/), запись Intervals.icu catalog id `158`.
- **Confidence:** low. **Missing/uncertain:** все функциональные и коммерческие детали.

## 6. RaceMind

- **URL:** https://race-mind.com/index-en.html
- **Позиционирование / спорт:** digital coach для triathlon и running.
- **AI/coaching и планы:** индивидуальные алгоритмические планы; deterministic структура/нагрузка/threshold/performance math; Google Gemini только для coaching texts и chat; библиотека 300+ swim/bike/run/strength/mobility workouts.
- **Анализ / recovery:** training analysis, performance score, Training Readiness.
- **Взаимодействие:** AI chat и push reminders/tips.
- **Интеграции / платформы:** Strava, Garmin Connect, Intervals.icu, Apple HealthKit, Google Health Connect; тип app store/platform и цена n/a.
- **Зрелость:** действующий юридически описанный app/service; public terms актуальны.
- **Дифференциаторы:** ясное разделение deterministic sports science и generative text; strength/mobility library, push.
- **Пересечение:** планы, readiness, activity analysis, AI chat. **Отличие:** шире consumer integrations/push; AI Trainer — multi-provider/local, direct data ownership, approval/audit/rollback.
- **Источники:** [official home](https://race-mind.com/index-en.html), [official terms/service description](https://race-mind.com/terms.html).
- **Confidence:** high for features, low for pricing/platform. **Missing/uncertain:** цена/trial, app availability, насколько планы адаптируются автоматически.

## 7. RacePal

- **URL:** https://www.racepal.com/
- **Позиционирование / спорт:** AI triathlon coach; также cycling и running.
- **AI/coaching и планы:** daily adaptive training, personalized schedules, Coach Corner explanations, race planning/strategy, автоизменение после пропуска или reschedule, race predictions и nutrition guidance.
- **Анализ / recovery:** performance/progress/health analytics, sleep, HRV, stress, recovery, training load.
- **Взаимодействие:** app/web Coach Corner; 24/7 AI; чат как формат не подтверждён.
- **Интеграции / платформы:** direct Garmin и Intervals.icu; iOS, Android, web dashboard.
- **Цена / зрелость:** $12.99/mo или $129.99/year; 1-month full trial; production SaaS/mobile.
- **Дифференциаторы:** triathlon-first, race/nutrition, coach tone customization, commercial mobile polish.
- **Пересечение:** multisport plans, health/readiness, adaptive schedule, analytics. **Отличие:** broader SaaS/mobile and nutrition; AI Trainer — self-hosting, explainable approval lifecycle, rollback, multi-provider/Ollama.
- **Источники:** [home/features/FAQ](https://www.racepal.com/en), [pricing](https://www.racepal.com/en/pricing).
- **Confidence:** high. **Missing/uncertain:** exact chat UI, export formats, human confirmation semantics.

## 8. RestOrTrain

- **URL:** https://restortrain.com/
- **Позиционирование / спорт:** proactive conversational AI coach, cycling-first but supports triathlon/running/swimming/strength load and plans.
- **AI/coaching и планы:** full-history memory, season→workout planning, conversational reshuffling around life, automatic post-ride review, route/GPX pacing, structured workout delivery.
- **Анализ / recovery:** power/HR/load, sleep/recovery, readiness recalculated after rides, explicit train-or-rest; long-term pattern and PR analysis.
- **Взаимодействие:** in-app chat and proactive insights; external channel n/a.
- **Интеграции / платформы:** Garmin, Strava, Wahoo, Hammerhead, Zwift, Rouvy, Intervals.icu, Apple Health; calendar ICS; iOS only, Android in development.
- **Цена / зрелость:** a few questions free; monthly/yearly pricing only in app and region-dependent; 35,000+ users, 4.8/5 and 1,000+ App Store reviews claimed by company.
- **Дифференциаторы:** наиболее зрелый direct AI-coach UX группы, huge integration surface, route/race pacing, proactive feedback.
- **Пересечение:** практически весь recovery→plan→analysis loop. **Отличие:** RestOrTrain commercial iOS/integrations/proactivity; AI Trainer self-hosted, provider-independent and has explicit journaled approval/rollback rather than opaque direct mutation.
- **Источники:** [official home](https://restortrain.com/), [official FAQ](https://www.restortrain.com/faq), [about](https://restortrain.com/about).
- **Confidence:** high. **Missing/uncertain:** actual regional price, exact human-confirmation model, Android date.

## 9. Ride Cave

- **URL:** https://ridecave.com/
- **Позиционирование / спорт:** all-in-one indoor cycling platform; running/rowing only roadmap.
- **AI/coaching и планы:** opt-in Atlas AI chat, ride analysis, custom workouts, image-to-workout, periodized plans, Magic Ride generation.
- **Анализ / recovery:** Data Lab with fitness trends, power curves, distribution and recovery signals; no sleep/HRV source detail.
- **Взаимодействие:** AI chat, group rides with live voice, public/private Discord.
- **Интеграции / платформы:** Strava, Intervals.icu, Wahoo, sensors/FTMS; FIT sync, ZWO/ERG/JSON import/export; browser, iOS/iPad, macOS, Windows.
- **Цена / зрелость:** core including AI and plans free; Cave Crew from $4.99/mo for expanded reports/community/gamification; active complete platform.
- **Дифференциаторы:** actual indoor ride execution, physics/velodromes/routes, groups, rich builder and gamification.
- **Пересечение:** AI coach, plans, load/recovery analysis. **Отличие:** Ride Cave is cycling execution/social platform; AI Trainer is health-aware multisport planner with direct Garmin and safer auditable plan mutations.
- **Источники:** [home](https://ridecave.com/), [features](https://ridecave.com/features), [about/pricing](https://www.ridecave.com/about).
- **Confidence:** high. **Missing/uncertain:** precise readiness inputs and adaptation rules.

## 10. RideCoach

- **URL:** https://ridecoach.eu/
- **Позиционирование / спорт:** AI-enabled training/wellness service; likely cycling-first by name, but privacy policy supports generic sport types.
- **AI/coaching и планы:** AI Q&A, workout generation, insights/summaries; Google Gemini via Vertex AI.
- **Анализ / recovery:** training load, HRV, resting HR, sleep, fatigue/readiness; manual check-ins for energy/motivation/soreness/stress.
- **Взаимодействие:** stored AI chat; other channels n/a.
- **Интеграции / платформы:** Intervals.icu, Strava; web account implied. Native apps n/a.
- **Цена / зрелость:** Stripe trial/subscription exists, but price and duration n/a; Estonia-based production service/legal policy updated 2026-01-08.
- **Дифференциаторы:** subjective daily check-ins combined with wellness; explicit health-data consent.
- **Пересечение:** chat, training/wellness context, readiness and workouts. **Отличие:** Intervals/Strava and subjective check-ins; AI Trainer has direct Garmin, planning engine, approval/audit/rollback and model choice/self-hosting.
- **Источники:** [official site](https://ridecoach.eu/), [official privacy/service data description](https://ridecoach.eu/privacy).
- **Confidence:** medium. **Missing/uncertain:** homepage details, exact sports, plan generation depth, price/trial/platform.

## 11. Ride Intent

- **URL:** https://rideintent.com/
- **Позиционирование / спорт:** decision-support for cyclists: interpret training and say what to do next, not another metrics dashboard.
- **AI/coaching и планы:** rDNA personalization, Today/Capacity/Consequence/Rhythm lenses and workout suggestions; full periodized plan generation/chat not confirmed.
- **Анализ / recovery:** power, HR, load, readiness/recovery; personalized capacity and response patterns.
- **Взаимодействие:** calm Today UI; no chat/external channel.
- **Интеграции / платформы:** Intervals.icu, Apple Health; Strava coming soon. iPhone iOS 17+ via TestFlight; Android waitlist.
- **Цена / зрелость:** free small-batch early-access beta, waitlist (~100+ claimed).
- **Дифференциаторы:** narrow interpretation/next-decision UX and personalized rider response model.
- **Пересечение:** readiness→next action and recovery-aware guidance. **Отличие:** lighter iOS decision layer atop Intervals/Apple Health; AI Trainer offers deeper planning/chat/direct Garmin and auditable mutations.
- **Источники:** [official home](https://rideintent.com/), [official terms](https://www.rideintent.com/terms).
- **Confidence:** high. **Missing/uncertain:** underlying AI method, pricing after beta, plan/workout execution.

## 12. Ridium

- **URL:** https://ridium.app/
- **Позиционирование / спорт:** AI cycling coach turning Intervals.icu metrics into annual and weekly plans.
- **AI/coaching и планы:** context-aware chat, persistent memory, structured weekly plan and annual Base/Build/Peak/Deload periodization; week-by-week adjustment and direct plan edits.
- **Анализ / recovery:** CTL/ATL/TSB, power curve, recent phases, overtraining/recovery suggestions, historical season analysis (Pro).
- **Взаимодействие:** web conversational coach.
- **Интеграции / платформы:** Intervals.icu live; Garmin direct push «soon», TrainingPeaks import planned. Web SaaS.
- **Цена / зрелость:** Free Forever $0; Pro $9.99/mo. Public v2.1, active in 2026.
- **Дифференциаторы:** Intervals-native annual periodization, generous free tier, season comparison/peak timing.
- **Пересечение:** chat, CTL/ATL/TSB, plans, memory and adaptation. **Отличие:** Ridium is polished cycling/Intervals SaaS; AI Trainer multisport/direct Garmin/self-hosted/multi-provider and stronger controlled mutation lifecycle.
- **Источники:** [official home/pricing](https://ridium.app/), [features](https://ridium.app/features), [terms](https://ridium.app/%26/terms).
- **Confidence:** high. **Missing/uncertain:** native mobile, wellness sources beyond Intervals, exact recovery mutation safeguards.

## 13. RoadieTips

- **URL:** https://roadietips.com/
- **Позиционирование / спорт:** вероятно cycling по названию, но официальный сайт не дал индексируемого описания.
- **AI/coaching; планы; анализ/recovery; взаимодействие; интеграции; платформы; цена:** n/a.
- **Зрелость:** только присутствие в Intervals.icu catalog id `161`.
- **Пересечение / отличие:** оценить нельзя.
- **Источники:** [официальный URL](https://roadietips.com/).
- **Confidence:** low. **Missing/uncertain:** весь продуктовый профиль.

## 14. RUNYALA

- **URL:** https://www.runyala.com/
- **Позиционирование / спорт:** page title заявляет AI Sports Coach для running, trail running, cycling, triathlon.
- **AI/coaching; планы; анализ/recovery; взаимодействие; интеграции; платформы; цена:** n/a — SPA не загрузилась (`Failed to fetch dynamically imported module`).
- **Зрелость:** домен и бренд активны, фактическая доступность не подтверждена.
- **Пересечение:** вероятно multisport AI coach; **отличие:** невозможно проверить.
- **Источники:** [official site](https://www.runyala.com/), Intervals.icu catalog id `505`.
- **Confidence:** low. **Missing/uncertain:** все детальные функции и коммерция.

## 15. TrainerDay

- **URL:** https://trainerday.com/
- **Позиционирование / спорт:** mature, affordable structured indoor/outdoor cycling platform.
- **AI/coaching и планы:** deterministic Coach Jack builder (goal/date/hours/intensity, Base/Build/Peak/Event) plus conversational AI Plan Builder with guardrails; huge workout/community plan library and editor.
- **Анализ / recovery:** Strava-based inputs and TSS/zones; HR-controlled Zone 2/HR-ERG. Sleep/HRV/readiness analytics not confirmed.
- **Взаимодействие:** web/app builders; forum/email support, no ongoing AI coaching chat confirmed beyond plan builder.
- **Интеграции / платформы:** Strava, Garmin, TrainingPeaks, Zwift, MyWhoosh, Wahoo, Intervals.icu; iOS, Android, macOS, Windows, web.
- **Цена / зрелость:** Free $0; Pro $4.99/mo or $3.33/mo annual; 30-day money-back guarantee. 100K+ users and 4.8 app rating claimed.
- **Дифференциаторы:** fast actual trainer execution, 40K+ workouts, community, integrations and very low price.
- **Пересечение:** goal plans and structured workout delivery. **Отличие:** TrainerDay far stronger cycling execution/library/platform reach; AI Trainer far stronger recovery/sleep/readiness, analytical AI chat, self-hosting and auditable adaptive changes.
- **Источники:** [home](https://trainerday.com/), [pricing](https://trainerday.com/pricing/), [official plan guide](https://trainerday.com/blog/training-plan-options), [downloads/integrations](https://trainerday.com/download).
- **Confidence:** high. **Missing/uncertain:** adaptation to completed activities/recovery and AI chat scope.

## 16. Trenio

- **URL:** https://trenio.es/
- **Позиционирование / спорт; AI/coaching; plans; analysis/recovery; interaction; integrations; platforms; pricing:** n/a — официальный URL не был доступен индексатору.
- **Зрелость:** присутствует в Intervals.icu catalog id `408`.
- **Пересечение / отличие:** оценить нельзя.
- **Источники:** [official URL](https://trenio.es/).
- **Confidence:** low. **Missing/uncertain:** весь профиль.

## 17. Ultropic

- **URL:** https://www.ultropic.com/
- **Позиционирование / спорт; AI/coaching; plans; analysis/recovery; interaction; integrations; platforms; pricing:** n/a — официальный URL не был доступен/индексируем.
- **Зрелость:** присутствует в Intervals.icu catalog id `422`.
- **Пересечение / отличие:** оценить нельзя.
- **Источники:** [official URL](https://www.ultropic.com/).
- **Confidence:** low. **Missing/uncertain:** весь профиль.

## 18. Velodapt

- **URL:** https://www.velodapt.com/
- **Позиционирование / спорт:** personalized AI workouts for Zwift/cycling (подтверждено title официальной страницы); официальный HTML не раскрывает детали.
- **AI/coaching и планы:** personalized workout generation по physiological profile/readiness; Workout Missions beta добавляет игровые задачи и post-ride scoring. Полные планы/chat n/a.
- **Анализ / recovery:** readiness упоминается разработчиком; подробные recovery signals n/a.
- **Взаимодействие:** web service и Discord community.
- **Интеграции / платформы:** автоматическая отправка workouts в Zwift; Intervals.icu catalog; остальные n/a.
- **Цена / зрелость:** free account и credit model implied; Workout Missions pre-release beta; точная цена n/a.
- **Дифференциаторы:** readiness-personalized one-off Zwift workouts и game-like race missions.
- **Пересечение:** readiness-aware workout suggestion. **Отличие:** Velodapt — узкая Zwift execution/gamification layer; AI Trainer — широкий health/planning/chat/recovery loop.
- **Источники:** [official home](https://www.velodapt.com/); первичное [объявление разработчика о beta](https://forums.zwift.com/t/want-to-test-game-like-workouts-in-zwift/669292).
- **Confidence:** medium-low. **Missing/uncertain:** pricing, AI method, plan/adaptation depth, exact Intervals sync.

## 19. Vin / VinApp Cycling Training

- **URL:** https://play.google.com/store/apps/details?id=es.antplus.xproject&hl=en_US&gl=US
- **Позиционирование / спорт:** structured cycling training and planning for serious riders.
- **AI/coaching; адаптивность; анализ/recovery; взаимодействие; интеграции:** n/a в доступном официальном developer listing.
- **Платформы / зрелость:** Android; in-app purchases; Google Play developer listing shows 10K+ downloads, 5.0 rating / ~1.13K reviews at check time.
- **Цена/trial:** n/a.
- **Дифференциаторы:** established Android cycling app; feature details unavailable.
- **Пересечение:** structured cycling planning. **Отличие:** Android-native; AI Trainer broader analytics/AI/recovery but no native app.
- **Источники:** [Google Play product URL](https://play.google.com/store/apps/details?id=es.antplus.xproject&hl=en_US&gl=US), [official xProject developer listing](https://play.google.com/store/apps/dev?id=5366823345545368794).
- **Confidence:** medium-low. **Missing/uncertain:** almost all functional/pricing details and whether AI is used.

## 20. Vitalstat

- **URL:** https://www.vital-stat.com/
- **Позиционирование / спорт:** AI health intelligence and recovery dashboard, not primarily a training-plan coach.
- **AI/coaching и планы:** daily Morning Briefing, sleep optimization, weekly narratives, AI Health Chat, nutrition photo analysis; training plan generation not confirmed.
- **Анализ / recovery:** sleep stages/score, HRV and 28-day baseline, recovery/strain, ACWR, fitness/fatigue/form, body composition, nutrition. Published recovery weighting: sleep 40%, HRV 25%, restorative sleep 15%, RHR 10%, respiratory rate 10%.
- **Взаимодействие:** in-app AI chat/briefings; social/leaderboards claimed. External channels n/a.
- **Интеграции / платформы:** iOS/Android; Apple Watch/Health, Google Health Connect, Garmin, Polar, Oura, Suunto, Wahoo, Withings, Intervals.icu.
- **Цена / зрелость:** €5.99/mo, €54.99/year, €149.99 lifetime (prices may vary); live App Store/Google Play product.
- **Дифференциаторы:** broad wearable aggregation, nutrition and transparent recovery formula at low price.
- **Пересечение:** sleep/HRV/recovery, load/form and AI explanation. **Отличие:** Vitalstat stronger consumer health/wearables/nutrition/mobile; AI Trainer stronger goal plans, workout generation, reconciliation and controlled replan actions.
- **Источники:** [official home](https://www.vital-stat.com/), [official comparison/method/pricing](https://www.vital-stat.com/compare).
- **Confidence:** high. **Missing/uncertain:** trial, structured workout/planning capability, exact Intervals write support.

## 21. WorkoutContext

- **URL:** https://workoutcontext.fit/
- **Позиционирование / спорт; AI/coaching; plans; analysis/recovery; interaction; integrations; platforms; pricing:** n/a — официальный домен не был доступен/индексируем; поисковые совпадения относятся к одноимённому software class и не использованы.
- **Зрелость:** только присутствие в Intervals.icu catalog id `390`.
- **Пересечение / отличие:** оценить нельзя.
- **Источники:** [official URL](https://workoutcontext.fit/).
- **Confidence:** low. **Missing/uncertain:** весь продуктовый профиль.

## Сводка группы

- **Самые близкие прямые конкуренты AI Trainer:** PlanWatts, RestOrTrain, RacePal, Ridium и RaceMind. У всех есть сочетание персонализированного планирования и анализа данных; PlanWatts/RestOrTrain наиболее близки к разговорному tool-using coach.
- **Сильнейшие integration/mobile позиции:** RestOrTrain, RacePal, Vitalstat, TrainerDay и Peak Watts. AI Trainer уже имеет ограниченную API-интеграцию Intervals.icu (профиль, гонки, plan-fact evidence и legacy workout push), но всё ещё уступает по OAuth/onboarding, Strava/Apple Health/Wahoo/COROS, native mobile и push.
- **Сильнейшие recovery-конкуренты:** Vitalstat (широкий health dashboard и прозрачная формула), RestOrTrain (recovery drives plan), RacePal и Ride Intent. Преимущество AI Trainer — не сам readiness score, а управляемый жизненный цикл `conflict → proposal → approve/reject → audit/rollback`.
- **Сильнейшие execution/workout ecosystems:** TrainerDay и Ride Cave; AI Trainer не конкурирует с ними как indoor player, sensor hub или social ride platform.
- **Защитимые преимущества AI Trainer:** direct Garmin + local SQLite/self-hosting; OpenAI/Anthropic/DeepSeek/Gemini/Ollama choice; demo without credentials; explainable and reversible human-approved mutations. Ни один исследованный публичный профиль не подтвердил всю эту комбинацию.
- **Риск commoditization:** generic AI chat + plan generation уже массовы и недороги/free. Выделять AI Trainer стоит через privacy/control, evidence provenance, safe plan actions, Russian-first UX и direct recovery-to-decision loop, а не просто «AI coach».
- **Качество покрытия:** 12 карточек high/medium confidence, 9 medium-low/low из-за закрытых beta/SPAs/неиндексируемых сайтов. Низкая уверенность означает недостаток публичных данных, а не слабость продукта.
