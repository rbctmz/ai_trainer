# Приложения Intervals.icu: конкурентное исследование, batch 1

Дата проверки: **2026-07-13**. Охват: первые 21 строка `intervals_icu_ai_trainer_apps.csv` после заголовка, включая два уже подключённых приложения. Основной источник — официальные сайты, справка и страницы магазинов. Если публичного подтверждения нет, указано `n/a`; маркетинговые заявления не трактуются как независимо подтверждённая эффективность.

## База сравнения: AI Trainer

AI Trainer в текущем репозитории — Garmin-first, self-hosted web-продукт для бега, велоспорта и триатлона. Реализованы локальное хранение, TSS/CTL/ATL/TSB и Banister, HRV/сон/readiness, AI-чат над фактическими данными, планирование и план-факт, а также объяснимый recovery replan через preview/approve/reject/rollback. Ключевые отличия: прямой Garmin, локальные данные, несколько AI-провайдеров и Ollama, журналируемые обратимые действия. Ограничения: нет подтверждённых нативных мобильных/watch-приложений и фонового канала, узкий набор интеграций, активная web-миграция и отсутствие публичного SaaS-прайсинга. Источник: [эталонный профиль AI Trainer](./ai_trainer_product_profile.md).

## Краткая карта группы

| Сегмент | Приложения |
|---|---|
| Прямые full-stack конкуренты | IntervalCoach, AI Endurance, Athletica, Coach Watts, Enduco, RunIAg |
| Разговорный coach поверх Intervals.icu | AI Coach Cloud, Ask My Coach, Brotein.pro, Coach AMA, Coach Fartlek, CoachX |
| Узкие daily-workout / cycling решения | AI Cycling Coach, Aixle, Deeride, DunMove |
| Мобильные/инфраструктурные дополнения | Intervals Companion, Atomic Metrix |
| Running-first | Adapt Run, bowermanOS/athletedata.health, CoachX, Coach Fartlek |
| Слабая или неясная прямая конкуренция | Coach Cedric (широкий athletic coach; виды спорта не раскрыты) |

## Карточки приложений

### 1. IntervalCoach — connected

- **URL:** [intervalcoach.app](https://www.intervalcoach.app/)
- **Позиционирование / спорт:** полнофункциональный recovery-aware AI coach; велоспорт, бег, trail, триатлон, плавание, силовые, а также walking/hiking в on-demand генераторе.
- **AI/coaching:** weekly plan, Coach+ chat, post-workout feedback, nutrition, race pacing, proactive nudges, goal projection. Заявлено чтение 60+ сигналов и 7 типов реального изменения тренировки.
- **Адаптация:** ежедневная автоматическая корректировка по HRV, сну, RHR, RPE и нагрузке; rest/cap/swap/reduce/extend и другие действия; изменения доходят до head unit через интеграции.
- **Аналитика / восстановление:** fitness/fatigue, power-duration curve, W/kg, pace progression, monotony, ACWR, durability, load/recovery, peer benchmarks.
- **Взаимодействие:** web, iOS, Android, AI-чат, daily/weekly email, клубы и human-coach access.
- **Интеграции / платформы:** Intervals.icu как основной источник; Apple/Google Health, Whoop, Garmin, Polar, Wahoo, Oura; Zwift и устройства через sync.
- **Цена / доступность:** free tier; платные уровни от **€3/мес** по title pricing page; 14 дней без карты. Pro/Max различаются глубиной планирования, chat limits и benchmarks. Активный коммерческий продукт с docs/changelog/roadmap.
- **Дифференциаторы:** широкая мультиспортивность, реальные автоматические изменения сегодняшней сессии, мобильные каналы, email, community и human coach.
- **Пересечение с AI Trainer:** очень высокое — планирование, readiness, recovery-aware изменение, чат, аналитика, план-факт.
- **Отличие от AI Trainer:** значительно шире интеграции и каналы, автоматический push на устройства и коммерческая зрелость; AI Trainer сильнее в self-hosting, локальных данных, мультипровайдерности и явном approve/reject/rollback вместо фоновой автоматизации.
- **Источники:** [официальная главная](https://www.intervalcoach.app/en), [pricing](https://www.intervalcoach.app/en/pricing).
- **Confidence:** high. **Missing/uncertain:** точные региональные цены Pro/Max динамически не отрендерились; подтверждён только публичный минимум «от €3/мес».

### 2. Intervals.icu Companion — connected

- **URL:** [App Store](https://apps.apple.com/us/app/intervals-icu-companion/id6739638454)
- **Позиционирование / спорт:** сторонний мобильный клиент Intervals.icu для всех поддерживаемых там видов спорта; не AI-coach.
- **AI/coaching и планы:** не генерирует AI-планы. Дает календарь/библиотеку, отправляет запланированные structured workouts на Apple Watch; встроенная Apple Intelligence-интерпретация readiness/sleep была удалена как неудачная.
- **Аналитика / восстановление:** CTL/ATL/form и прогноз будущей формы, HRV/readiness/sleep/RHR, custom charts/widgets, splits/zones, activity details.
- **Взаимодействие:** iPhone/iPad/Apple Watch/macOS, widgets, complications, push; личные сообщения coaches/athletes, комментарии и feed.
- **Интеграции:** двусторонние Intervals.icu ↔ Apple Health, Apple Watch workout sync, FIT import; косвенно переносит Garmin и другие активности из Intervals.icu в Apple Health.
- **Цена / доступность:** бесплатно, добровольные tips $9.99/$19.99; v3.2.3, 27 App Store ratings, 4.8/5 на дату проверки. Независимый hobby project.
- **Дифференциаторы:** глубокая Apple-native оболочка для Intervals.icu и двусторонний health/workout bridge.
- **Пересечение с AI Trainer:** аналитика нагрузки/readiness и просмотр планов.
- **Отличие от AI Trainer:** не конкурент по AI-коучингу; это сильный ориентир для мобильного UX, watch delivery, widgets, push и community. AI Trainer даёт коучинг/планирование, Companion — мобильную доставку и визуализацию.
- **Источник:** [официальная App Store page](https://apps.apple.com/us/app/intervals-icu-companion/id6739638454).
- **Confidence:** high. **Missing/uncertain:** Android отсутствует; точной аудитории кроме App Store ratings нет.

### 3. Adapt Run

- **URL:** [adaptrun.app](https://adaptrun.app/)
- **Позиционирование / спорт:** running-only adaptive platform: план, VDOT-зоны, route discovery, analytics, social/community, live location и guided Apple Watch workouts.
- **AI/coaching и планы:** smart plan в free; Premium — AI post-workout analysis, adaptive adjustments, personalized insights, route generation, AWCR planning, live audio coaching на пяти языках.
- **Аналитика / восстановление:** readiness из fatigue/recovery/consistency/stability, load, pace, elevation, HR и долгосрочный прогресс.
- **Взаимодействие / платформы:** iOS/Android, Apple Watch, live audio, social connections/community и private live tracking.
- **Интеграции:** Garmin, Polar, Suunto, Wahoo, Apple Health, Android Health Connect; официальная страница не подтверждает Intervals.icu как рабочую интеграцию.
- **Цена / доступность:** free; Premium **$4.99/мес или $39.99/год**, 14-day trial. Публично доступный коммерческий продукт.
- **Дифференциаторы:** очень низкая цена, route/race map, social/live tracking и live wrist/audio execution.
- **Пересечение с AI Trainer:** running plans, readiness/load, workout analysis, adaptive correction.
- **Отличие от AI Trainer:** сильнее mobile/on-workout experience, маршруты и social; AI Trainer мультиспорт, глубже в объяснимом recovery loop и локальном контроле данных.
- **Источники:** [product](https://adaptrun.app/), [pricing](https://adaptrun.app/pricing), [terms](https://adaptrun.app/terms-of-service).
- **Confidence:** high. **Missing/uncertain:** механика AI и фактическая глубина автоматической перестройки публично не раскрыты.

### 4. Advanced Endurance Coach by RunIAg

- **URL:** [runiag.com](https://www.runiag.com/)
- **Позиционирование / спорт:** испаноязычный/латиноамериканский AI endurance coach; бег, велоспорт, триатлон до Ironman.
- **AI/coaching и планы:** 24/7 coach, адаптивные периодизированные планы до 32 недель, race strategy, pace/nutrition guidance, calculators/predictors.
- **Аналитика / восстановление:** VO₂max, TSB/load balance, zones, performance tracking; заявлены recovery insights и предотвращение перегруза.
- **Взаимодействие / платформы:** web; conversational coach. Нативные приложения и proactive messaging публично не подтверждены.
- **Интеграции:** Garmin, Coros, Strava; multidevice sync заявлен. Intervals.icu присутствует в каталоге, но отдельной официальной integration page в найденных материалах нет.
- **Цена / доступность:** 7-day free trial без карты; точная публичная цена `n/a`. На Ironman page упоминается дополнительный 30-day benefit для «Pionero» plan.
- **Дифференциаторы:** race hubs с altitude/course context, широкий набор бесплатных endurance calculators, сильное triathlon/long-course позиционирование.
- **Пересечение с AI Trainer:** мультиспорт-планы, load/readiness, AI coach, Garmin и race preparation.
- **Отличие от AI Trainer:** RunIAg выглядит SaaS и больше ориентирован на race content/Spanish market; AI Trainer — self-hosted, аудируемые действия и более прозрачный локальный recovery pipeline.
- **Источники:** [Ironman training app](https://runiag.com/ironman-training-app), [FTP tool/product description](https://runiag.com/tools/ftp-calculator), [events](https://runiag.com/events).
- **Confidence:** medium-high. **Missing/uncertain:** цена, mobile platforms, точная глубина post-workout/recovery automation.

### 5. AI Coach Cloud

- **URL:** [Sharma Automation — AI Coach](https://sharmaautomation.com/ai-coach) / публичное описание на [главной](https://www.sharmaautomation.com/)
- **Позиционирование / спорт:** full-stack conversational coach для endurance athletes поверх Intervals.icu; конкретный список видов спорта не опубликован.
- **AI/coaching и планы:** Claude-agent читает историю, ведёт чат, анализирует recovery и пишет workouts обратно в календарь Intervals.icu; заявлено, что может возражать против неверного плана.
- **Аналитика / восстановление:** fitness dashboard, HRV/sleep/fatigue context; детализация метрик и правил `n/a`.
- **Взаимодействие / платформы:** browser SaaS, no Discord/install/CLI; conversational chat.
- **Интеграции:** Intervals.icu source of truth; Garmin, Wahoo, Zwift и Apple Watch upstream через него; Stripe/Supabase/Railway — техническая инфраструктура, не пользовательские fitness integrations.
- **Цена / доступность:** 7-day trial; точная подписка `n/a`. Официально описан как live production SaaS.
- **Дифференциаторы:** минимальный signup и узкий agentic flow «прочитать → обсудить → записать workout».
- **Пересечение с AI Trainer:** почти прямое — data-aware chat, recovery context, планирование и запись изменения.
- **Отличие от AI Trainer:** Intervals-first hosted SaaS и один Claude stack; AI Trainer Garmin-first/self-hosted, несколько LLM и явный approval/rollback journal.
- **Источник:** [официальная страница разработчика](https://www.sharmaautomation.com/).
- **Confidence:** medium-high. **Missing/uncertain:** виды спорта, подписка, mobile, алгоритмы и масштаб использования.

### 6. AI Cycling Coach

- **URL:** [ai-cycling-workout-planner.vercel.app](https://ai-cycling-workout-planner.vercel.app/)
- **Позиционирование / спорт:** cycling-only daily workout planner на базе Intervals.icu.
- **AI/coaching и планы:** выбирает workout по FTP/TSB/HRV/sleep, строит 7-day plan по TSS и build/recovery rhythm, позволяет regenerate и менять intensity; indoor/outdoor.
- **Аналитика / восстановление:** использует CTL/ATL/TSB, HRV, sleep и FTP; отдельная глубокая activity analytics не заявлена.
- **Взаимодействие / платформы:** web; чат или proactive notifications не подтверждены.
- **Интеграции:** Intervals.icu only; ZWO output; auto-sync к Wahoo/Garmin через Intervals.icu.
- **Цена / доступность:** `n/a`; страница открыта и предлагает Get Started, но юридические/коммерческие сведения и maturity signals минимальны.
- **Дифференциаторы:** крайне простой pipeline data-in → condition-based workout → ZWO/device.
- **Пересечение с AI Trainer:** cycling planning и readiness/load-aware выбор сессии.
- **Отличие от AI Trainer:** гораздо уже и проще, но быстрее доставляет ZWO на cycling stack; AI Trainer мультиспорт, чат, план-факт и аудируемый replan.
- **Источник:** [официальная страница](https://ai-cycling-workout-planner.vercel.app/).
- **Confidence:** medium. **Missing/uncertain:** компания, цена, реальная автоматизация device sync, пользовательская база.

### 7. AI Endurance

- **URL:** [aiendurance.com](https://aiendurance.com/)
- **Позиционирование / спорт:** predictive ML «Digital Twin» для бега, велоспорта и триатлона.
- **AI/coaching и планы:** персональная neural network учится отклику спортсмена, прогнозирует performance и переоптимизирует plan после тренировок; AI coach читает second-by-second данные и может менять plan в чате.
- **Адаптация / восстановление:** обновление модели каждые 24h; HRV/rMSSD, RHR, DFA α1, cardio/orthopedic recovery, missed workout и distribution-aware recommendations.
- **Аналитика:** race/performance predictions, zones, critical power/pace, nutrition/macros, goal priorities; наука и методология публично документированы заметно лучше большинства группы.
- **Взаимодействие / платформы:** web, iOS, Android, собственный chat; также ChatGPT/Claude через AI assistant integrations/MCP.
- **Интеграции:** Garmin, Suunto, Coros, Polar, Wahoo, Hammerhead, Intervals.icu, Strava, Stryd, Oura, Whoop; export в Garmin/Coros/Wahoo/Hammerhead/TrainingPeaks/Intervals/Nolio/Zwift/Rouvy/TrainerDay.
- **Цена / доступность:** **$20/мес или $200/год**, 14 days без карты. Зрелый коммерческий продукт, работает несколько лет.
- **Дифференциаторы:** per-athlete predictive model, published science, performance prediction и очень широкий bidirectional execution stack.
- **Пересечение с AI Trainer:** максимально высокое — план, recovery, analytics, chat, replan, мультиспорт.
- **Отличие от AI Trainer:** сильнее predictive ML, integrations и device execution; AI Trainer сильнее в локальности, provider choice и человеко-контролируемом журналируемом mutation lifecycle.
- **Источники:** [product](https://aiendurance.com/en), [FAQ](https://aiendurance.com/en/faq), [pricing](https://aiendurance.com/en/pricing), [privacy/data fields](https://aiendurance.com/en/privacypolicy).
- **Confidence:** high. **Missing/uncertain:** независимая валидация индивидуальной точности вне опубликованных/цитируемых материалов продукта.

### 8. Aixle

- **URL:** [aixle.net](https://aixle.net/)
- **Позиционирование / спорт:** daily optimizer для indoor cycling (Zwift/MyWhoosh) поверх Intervals.icu.
- **AI/coaching и планы:** каждое утро выдаёт три workout options с объяснением «why»; daily auto-generation и calendar upload.
- **Аналитика / восстановление:** CTL/TSB, fatigue, HRV, sleep и health metrics; отдельная post-workout analytics не заявлена.
- **Взаимодействие / платформы:** web dashboard + daily email на EN/JA/FR/ES/DE; .zwo execution.
- **Интеграции:** Intervals.icu; Zwift/MyWhoosh через calendar/ZWO workflow.
- **Цена / доступность:** 7 days free без Stripe, затем **$3.99/мес**; заявлены 30+ active indoor cyclist testers.
- **Дифференциаторы:** три объяснённых варианта вместо одного предписания; очень доступная цена; email-first habit.
- **Пересечение с AI Trainer:** readiness/load-aware workout recommendation.
- **Отличие от AI Trainer:** узкий cycling daily decision и автоматическая email/Zwift доставка; AI Trainer шире, глубже по план-факту и recovery governance.
- **Источник:** [официальная страница](https://aixle.net/).
- **Confidence:** high для заявленных функций, medium для зрелости. **Missing/uncertain:** native apps, масштаб за пределами 30+ testers, глубина long-term planning.

### 9. Ask My Coach

- **URL:** [askmycoach.app](https://askmycoach.app/)
- **Позиционирование / спорт:** connector, который отдаёт данные Intervals.icu в Claude и ChatGPT для персонализированных вопросов; виды спорта наследуются от данных Intervals.icu.
- **AI/coaching:** conversational analysis в выбранном generic assistant. Публичного подтверждения генерации/записи structured plans, recovery automation или post-workout pipeline нет.
- **Аналитика / восстановление:** определяется доступными skills и данными Intervals.icu; собственный readiness engine не заявлен.
- **Взаимодействие / платформы:** Claude/ChatGPT; web account. Есть режимы «For Athletes» и «For Coaches».
- **Интеграции:** Intervals.icu + Claude/ChatGPT.
- **Цена / доступность:** free; публичный v1.4.0, status page и changelog указывают на работающий небольшой продукт.
- **Дифференциаторы:** минимальный слой, не заставляющий менять привычный AI-интерфейс.
- **Пересечение с AI Trainer:** data-grounded chat.
- **Отличие от AI Trainer:** не полноценная planning/analytics platform; AI Trainer имеет собственные детерминированные сигналы, план и safe actions, а Ask My Coach выигрывает простотой и использованием Claude/ChatGPT как UI.
- **Источник:** [официальная главная](https://askmycoach.app/).
- **Confidence:** high по базовой функции, medium по skills. **Missing/uncertain:** точный набор read/write tools, limits и политика стоимости AI assistant.

### 10. Athletica

- **URL:** [athletica.ai](https://athletica.ai/)
- **Позиционирование / спорт:** sports-science-backed adaptive AI plans для triathlon, duathlon, running, cycling, rowing и HYROX.
- **AI/coaching и планы:** динамический план по physiology/goals/schedule, Workout Wizard для swap, baseline tests/zones, curated sport-science AI chat. Chat объясняет/советует, но официально не изменяет план без пользователя.
- **Аналитика / восстановление:** fitness/fatigue/recovery, HRV/sleep, compliance и workout feedback; low HRV warnings.
- **Взаимодействие / платформы:** web, AI chat; Coach Connect добавляет human coach. Нативные apps в изученных источниках не подтверждены.
- **Интеграции:** Garmin, Strava, Coros, Wahoo, Concept2; Intervals.icu и Apple Watch/Watchletic как bridges.
- **Цена / доступность:** 2 weeks free; **$19.90/мес, $99/6 мес, $189/год**. Компания и продукт существуют несколько лет, есть support center и coach ecosystem.
- **Дифференциаторы:** physiology experts/HIITScience, curated knowledge base, широкий спорт (rowing/HYROX), сочетание AI и human coach.
- **Пересечение с AI Trainer:** планы, recovery, Garmin, chat, plan adjustment и human approval ethos.
- **Отличие от AI Trainer:** шире sports/integrations и коммерчески зрелее; AI Trainer более прозрачен в mutation audit/rollback, self-hosted и мультипровайдерен.
- **Источники:** [product/pricing](https://athletica.ai/), [pricing detail](https://athletica.ai/pricing), [getting started](https://support.athletica.ai/hc/en-us/articles/21647844256411-How-to-Get-Started-with-Athletica-Connect-Your-Data-and-Set-Up-Your-Plan), [privacy/data](https://athletica.ai/privacy-policy).
- **Confidence:** high. **Missing/uncertain:** автоматичность части recovery adjustments и различия новой/legacy platform.

### 11. Atomic Metrix

- **URL:** [atomicmetrix.com](https://www.atomicmetrix.com/)
- **Позиционирование / спорт:** «agentic sports OS» и аналитический слой для primarily cycling/running с 100+ tools и MCP.
- **AI/coaching и планы:** AI/manual plan creation, personalized curve targets/availability, Agent умеет анализировать, планировать, менять и отправлять workouts/routes через natural language.
- **Аналитика / восстановление:** streaming activity detail, interval detection, power/HR coupling, CTL/ATL/TSB projections, power/speed evidence curves, HRV and recovery context.
- **Взаимодействие / платформы:** iOS/iPad/watchOS/macOS, собственный Agent, Discord; работает внутри Claude, ChatGPT, Gemini, Cursor и других MCP clients.
- **Интеграции:** Strava, Intervals.icu, Apple/Google Health, Oura, Polar; Garmin/Coros помечены Soon. Workout library ~3,000; ZWO/device/route exports.
- **Цена / доступность:** account creation доступна; публичная цена/trial `n/a`. © 2026, iVenture backing, active blog и downloadable apps; ранний, но заметно продуктовый stage.
- **Дифференциаторы:** MCP-first agentic architecture, evidence-linked analytics, route planning и огромная workout library.
- **Пересечение с AI Trainer:** analytics, AI tools, plans, recovery and structured exports.
- **Отличие от AI Trainer:** Atomic — интеграционный sports OS с mobile/watch/MCP; AI Trainer — Garmin-first private coach с более строгим approval journal и локальной моделью данных.
- **Источники:** [официальная главная](https://www.atomicmetrix.com/en), [training plans guide](https://www.atomicmetrix.com/en/blog/training-plans).
- **Confidence:** high для функций, medium для коммерческой доступности. **Missing/uncertain:** pricing, точный спорт scope, какие из 100+ tools доступны каждому tier.

### 12. bowermanOS → athletedata.health

- **URL:** каталог ведёт на [bowermanos.vercel.app](https://bowermanos.vercel.app/), который на дату проверки редиректит на [athletedata.health](https://www.athletedata.health/).
- **Позиционирование / спорт:** proactive cross-stack AI coach для runners, cyclists, triathletes и hybrid athletes; исходный bowermanOS стартовал как race-plan beta.
- **AI/coaching и планы:** читает приложения, строит/переписывает план, пишет первым, меняет сессию по recovery и доставляет structured workout на watch; заявлены long-term context и cross-training coordination.
- **Аналитика / восстановление:** training load/readiness/recovery, HRV trends, WHOOP/Garmin context, workout review; детальная методика не раскрыта.
- **Взаимодействие / платформы:** web dashboard + proactive text; watch delivery. Точный messaging channel на публичной странице не назван.
- **Интеграции:** Garmin, WHOOP, Strava, Oura, Hevy; также Apple Health, Intervals.icu, TrainingPeaks, MyFitnessPal и др.; device push к Garmin/Coros.
- **Цена / доступность:** first week free; **$299/year** показано на странице (расчётный недисконтированный monthly эквивалент из «save $169/year» — около $39/month, но прямую monthly цену лучше перепроверить). Страница заявляет 2,000+ athletes; это self-reported.
- **Дифференциаторы:** coach texts first, cross-endurance + strength/nutrition stack, proactive plan rewrite.
- **Пересечение с AI Trainer:** recovery-aware proactive coaching, planning, activity/recovery analysis.
- **Отличие от AI Trainer:** гораздо шире integrations и proactive delivery; AI Trainer дешевле/контролируемее как self-hosted и не изменяет план без явного approval.
- **Источники:** [текущий официальный destination](https://www.athletedata.health/), [origin story/public beta post](https://www.linkedin.com/posts/danielstadelmann_ai-is-going-to-replace-you-i-dont-see-activity-7450435954680643584-Iyea).
- **Confidence:** medium-high. **Missing/uncertain:** отношения брендов bowermanOS и athletedata формально не объяснены на redirect page; messaging channel и exact monthly price.

### 13. Brotein.pro

- **URL:** [brotein.pro](https://brotein.pro/)
- **Позиционирование / спорт:** AI endurance coach на Garmin data через Intervals.icu; running, cycling, triathlon.
- **AI/coaching и планы:** 24/7 chat о training/pacing/fueling/recovery, weekly adaptive plans, workout reviews, race strategy и long-term memory.
- **Адаптация / восстановление:** daily readiness из sleep/HRV/TSB, автоматическая недельная перестройка при изменении формы/жизни.
- **Аналитика:** per-km splits, intervals, pace, HR, cadence, load и coach review.
- **Взаимодействие / платформы:** native iPhone, Android APK (Google Play verification in progress), browser; push/voice на iPhone заявлены.
- **Интеграции:** Garmin → Intervals.icu → Brotein.pro; reads workouts, wellness, HR, cadence, power, sleep, HRV.
- **Цена / доступность:** free to start, no card; точная paid price `n/a`. iOS App Store listing и Android APK; Android Play listing ещё не опубликован на дату проверки.
- **Дифференциаторы:** mobile-first AI coach при очень простой Intervals architecture; plain-language coaching вместо dashboard-first UX.
- **Пересечение с AI Trainer:** очень высокое — Garmin, plan, readiness, chat, workout analysis.
- **Отличие от AI Trainer:** native mobile/voice/push и Intervals hub; AI Trainer имеет собственный direct Garmin ingestion, local/self-hosted privacy, provider choice и auditable safe actions.
- **Источник:** [официальная страница](https://brotein.pro/) и её публичный app bundle/FAQ, проверенные 2026-07-13.
- **Confidence:** high для функций страницы, medium для maturity. **Missing/uncertain:** paid pricing, размер аудитории, степень автоизменения календаря.

### 14. Coach AMA

- **URL:** [coach-ama.com](https://coach-ama.com/)
- **Позиционирование / спорт:** private-beta personal cycling coach в Discord на данных Intervals.icu.
- **AI/coaching и планы:** читает каждую поездку, отвечает 24/7, каждое воскресенье перестраивает неделю к race goals, делает post-ride debrief и tactics briefs.
- **Адаптация / восстановление:** утром учитывает sleep, RHR, HRV и вчерашнюю load; меняет тип/день сессии и предупреждает про health signals.
- **Аналитика:** power, HR, interval execution, weekly volume/TSS/form curve.
- **Взаимодействие / платформы:** Discord-first; waitlist/manual approval.
- **Интеграции:** Intervals.icu; через него power/HR/sleep data. Другие прямые integrations не заявлены.
- **Цена / доступность:** **free during private beta**, limited spots, applications approved manually.
- **Дифференциаторы:** сильное ощущение «личного канала тренера», proactive Discord и weekly human-like cadence.
- **Пересечение с AI Trainer:** cycling plan, readiness conflict, workout analysis, replan и chat.
- **Отличие от AI Trainer:** лучше background/proactive relationship и конкретный messaging channel; AI Trainer шире по спорту и сильнее по approval/rollback/self-hosting.
- **Источник:** [официальная главная](https://coach-ama.com/).
- **Confidence:** high. **Missing/uncertain:** underlying model, export/device writeback, post-beta pricing и масштаб beta.

### 15. Coach Cedric

- **URL:** [coachcedric.com.au](https://www.coachcedric.com.au/)
- **Позиционирование / спорт:** широкий «AI-powered athletic coach» с выбором coaching style; конкретные виды спорта `n/a`.
- **AI/coaching и планы:** 24/7 WhatsApp, personalized structured programs, feedback/motivation, ручная тонкая настройка плана в диалоге.
- **Аналитика / восстановление:** TSS, CTL, ATL, TSB; uses real data. HRV/sleep/readiness публично не заявлены.
- **Взаимодействие / платформы:** WhatsApp + membership web.
- **Интеграции:** Strava, Garmin, Wahoo, Fitbit; запись workout обратно на устройство не подтверждена.
- **Цена / доступность:** Pro Coach **от $3.99/мес**, Super Coach **от $5.99/мес**; публичный signup/login, © 2026 Luke Media Pty Ltd.
- **Дифференциаторы:** очень дешёвый WhatsApp-native coach и selectable personas/styles.
- **Пересечение с AI Trainer:** data-aware chat, structured programs, CTL/ATL/TSB.
- **Отличие от AI Trainer:** сильнее everyday channel; AI Trainer глубже в recovery/readiness, planning contracts и safe mutations.
- **Источник:** [официальная главная](https://www.coachcedric.com.au/).
- **Confidence:** medium-high. **Missing/uncertain:** sports, currency обозначена только знаком `$`, trial, recovery signals, device delivery.

### 16. Coach Fartlek

- **URL:** [fartlek.io](https://fartlek.io/)
- **Позиционирование / спорт:** proactive running-only AI coach для 5K–marathon, ориентирован на серьёзных бегунов.
- **AI/coaching и планы:** строит blocks/weekly plan, помнит всю историю разговоров и решений, адаптирует в real time, делает weekly follow-up, pre-workout reminders и post-run check-ins.
- **Аналитика / восстановление:** history, thresholds/zones, load/fatigue/form, RHR/HRV, illness/injury and subjective constraints.
- **Взаимодействие / платформы:** iOS/Android, proactive messages inside app; limited beta.
- **Интеграции:** Intervals.icu mandatory; Garmin, Coros, Suunto и Polar data приходят через него.
- **Цена / доступность:** free trial, затем **$9.99/мес**, cancel anytime; limited beta/waitlist.
- **Дифференциаторы:** long-term conversational memory и coach-initiated contact, а не только reactive chat.
- **Пересечение с AI Trainer:** беговой plan, HRV/load, illness-aware adjustment, conversation memory.
- **Отличие от AI Trainer:** сильнее mobile proactive relationship; AI Trainer мультиспорт, self-hosted и имеет auditable approval/rollback.
- **Источники:** [официальная главная](https://fartlek.io/en), [Intervals setup guide](https://fartlek.io/en/intervals-icu-guide).
- **Confidence:** high. **Missing/uncertain:** точная длина trial, device workout writeback и размер beta.

### 17. Coach Watts

- **URL:** [coachwatts.com](https://coachwatts.com/)
- **Позиционирование / спорт:** AI endurance «Digital Twin», объединяющий training, recovery и nutrition; примеры преимущественно cycling/triathlon, но полный sport list не формализован.
- **AI/coaching и планы:** adaptive periodized plans, smart workout analysis, persistent athlete profile, daily actions, goals и proactive overreaching alerts.
- **Аналитика / восстановление:** fitness/recovery, HRV/sleep/load, context over history, glycogen «Fuel Tank», metabolic horizon, carbs/hydration/sodium windows.
- **Взаимодействие / платформы:** web dashboard/coach, Discord community; отдельные native apps не подтверждены.
- **Интеграции:** Garmin, Strava, Rouvy, Intervals.icu, WHOOP, Oura и «20+» включая nutrition sources.
- **Цена / доступность:** Free; Supporter **$8.99/мес**; Pro **$14.99/мес**; 14-day money-back guarantee. При этом homepage одновременно содержит «Join the waitlist», поэтому open enrollment следует проверить.
- **Дифференциаторы:** наиболее развитая в группе связка training + fueling/glycogen model + recovery.
- **Пересечение с AI Trainer:** plans, readiness, persistent context, post-workout AI, proactive conflict detection.
- **Отличие от AI Trainer:** nutrition intelligence и ширина integrations; AI Trainer локальнее, прозрачнее по safety lifecycle и не выдаёт модельный glycogen как отдельный продуктовый слой.
- **Источник:** [официальная главная/pricing](https://coachwatts.com/).
- **Confidence:** high для заявлений сайта, medium для availability. **Missing/uncertain:** sport scope, waitlist vs immediate signup, независимая validation fuel model.

### 18. CoachX

- **URL:** [coachx.run](https://coachx.run/)
- **Позиционирование / спорт:** running-specialized conversational coach с 8 coaching methodologies и watch sync.
- **AI/coaching и планы:** periodized plans, natural-language workout creation/change, real-time replanning, bring-your-own plan, after-run analysis.
- **Аналитика / восстановление:** pace/HR/splits, completion vs targets, CTL/ATL/TSB, HRV/RHR/sleep/readiness и injuries/life context.
- **Взаимодействие / платформы:** web chat; Watchletic for Apple Watch; собственный iOS/Android recorder помечен Launching soon.
- **Интеграции:** Intervals.icu bridge к Garmin/Wahoo/Coros/Polar/Suunto; Watchletic; bidirectional structured workout sync.
- **Цена / доступность:** Free 5 msgs/day; Standard **$4.99/мес** 50/day; Pro **$9.99/мес** 200/day; первый месяц Standard free без карты.
- **Дифференциаторы:** явный выбор одной из восьми школ, очень низкая цена и instant chat-to-watch workflow.
- **Пересечение с AI Trainer:** data-aware chat, running plan, recovery, activity analysis, replan.
- **Отличие от AI Trainer:** running-only, но лучше device delivery и UX around coaching styles; AI Trainer multisport, self-hosted и безопаснее по action governance.
- **Источники:** [официальная главная/pricing](https://coachx.run/), [how it works](https://coachx.run/guide/how-it-works/).
- **Confidence:** high. **Missing/uncertain:** качество соблюдения каждой методологии и дата native mobile launch.

### 19. Deeride

- **URL:** [deeride.pl](https://www.deeride.pl/)
- **Позиционирование / спорт:** browser-based indoor cycling platform, одновременно trainer controller и AI workout generator.
- **AI/coaching и планы:** персональный plan по цели, fitness и available time; structured execution. Conversational chat или automatic recovery replan не заявлены.
- **Аналитика / восстановление:** live power, HR, cadence и performance; отдельный HRV/sleep/readiness layer не подтверждён.
- **Взаимодействие / платформы:** PWA в браузере; real-time workout screen.
- **Интеграции:** Bluetooth FTMS/FE-C, smart trainers/sensors, Strava и Intervals.icu sync.
- **Цена / доступность:** free, no subscription/no credit card; публичный app launch. Масштаб пользователей `n/a`.
- **Дифференциаторы:** объединяет генерацию и прямое ERG/simulation control без dongle/app store.
- **Пересечение с AI Trainer:** cycling plan, performance tracking, Intervals output.
- **Отличие от AI Trainer:** execution platform для smart trainer, а не holistic coach; AI Trainer намного сильнее в recovery, dialogue и longitudinal planning.
- **Источник:** [официальная главная](https://www.deeride.pl/).
- **Confidence:** high. **Missing/uncertain:** алгоритм AI plan, advanced analytics, business sustainability.

### 20. DunMove

- **URL:** [app.dunmove.com](https://app.dunmove.com/)
- **Позиционирование / спорт:** free, non-commercial, transparent rule/math-based cycling plan generator, прямо дистанцируется от AI black box.
- **Планы / адаптация:** до 12 месяцев, FTP-based, weekly build/recovery/taper, A/B events, daily time budgets; move/edit/recalculate/new plan вручную. Более 5,000 workouts.
- **Аналитика / восстановление:** load, LTL/STL/Fresh, weekly projections; HRV/sleep/readiness и post-workout AI coach отсутствуют.
- **Взаимодействие / платформы:** responsive web, iCal subscription; chat/proactive messages `n/a`.
- **Интеграции:** .zwo/.erg, soon .fit, iCal; Zwift, TrainerRoad, Intervals.icu, Garmin/Wahoo indirectly.
- **Цена / доступность:** полностью free, donations optional; private non-commercial project.
- **Дифференциаторы:** no subscription, explainable deterministic structure, long horizon и большая workout DB.
- **Пересечение с AI Trainer:** cycling plan, load/form, calendar/files.
- **Отличие от AI Trainer:** не AI-coach и не recovery-aware; полезный ориентир по прозрачности/минимальной сложности. AI Trainer добавляет live data, chat и controlled replan.
- **Источники:** [официальная главная](https://app.dunmove.com/), [pricing](https://app.dunmove.com/pricing), [why](https://app.dunmove.com/why).
- **Confidence:** high. **Missing/uncertain:** долгосрочное финансирование и дата FIT export.

### 21. Enduco

- **URL:** [enduco.app](https://enduco.app/)
- **Позиционирование / спорт:** Germany-based smart endurance platform; текущая homepage заявляет cycling, running и triathlon.
- **AI/coaching и планы:** индивидуальный season/race plan, 24/7 adaptation, configurable adaptivity, adjustable workouts, multiple goals, AI Coach Chat с выбираемым coach/persona.
- **Аналитика / восстановление:** feedback on completed sessions, daily situation, power/pace/HR/RPE, thresholds FTP/FTHR/TPace, internal/external load; exact HRV/readiness automation на текущей странице не детализирована.
- **Взаимодействие / платформы:** iOS/Android, AI chat, calendar sync, digital athlete partners.
- **Интеграции:** Garmin, Zwift, Strava, Coros, Apple Watch, Wahoo, Suunto; import completed sessions и export planned protocols.
- **Цена / доступность:** 14-day trial; Pro **€14.99/мес** (10 chat messages/week), Pro+ **€21.99/мес** (100/week); yearly saves 30%, regional variation. V7, 5+ years adaptive systems, GDPR claim and active partnerships.
- **Дифференциаторы:** выбор степени адаптивности между plan stability и maximum adaptation, athlete/creator personas и mature mobile product.
- **Пересечение с AI Trainer:** multisport plan, activity feedback, chat, adaptive replanning, integrations.
- **Отличие от AI Trainer:** mobile SaaS и шире devices; AI Trainer лучше в direct Garmin/local privacy, deterministic readiness conflict и reversible approved changes.
- **Источники:** [официальная главная/pricing](https://enduco.app/), [V7 relaunch](https://enduco.app/blog/relaunch-with-strategy-enduco-launches-version-7-featuring-new-technology-and-creator-collaborations), [V7 details](https://enduco.app/blog/enduco-v7-is-here-faster-smarter-more-intuitive).
- **Confidence:** medium-high. **Missing/uncertain:** старый июльский материал 2025 говорил «triathlon soon», текущая homepage уже заявляет triathlon; текущая страница принята как более свежий источник, но фактический depth swimming/triathlon нужно проверить в app.

## Сводные выводы для AI Trainer

1. **Главный рыночный стандарт уже не просто “сгенерировать план”.** Сильнейшие продукты связывают recovery signals → конкретную корректировку → доставку на устройство → post-workout feedback. AI Trainer уже имеет наиболее сложную часть — объяснимый recovery decision loop, но уступает в последней миле: mobile/watch/push/device sync.
2. **Intervals.icu стал дешёвым интеграционным хабом для небольших AI-coach продуктов.** Aixle, Coach AMA, Coach Fartlek, CoachX, Brotein.pro и AI Coach Cloud экономят на прямых vendor APIs. AI Trainer отличается direct Garmin/local ownership, но ограничивает рынок одной экосистемой.
3. **Proactive channel — заметный дифференциатор.** IntervalCoach, Coach AMA, Coach Fartlek и athletedata не ждут вопроса: пишут утром, после сессии или при риске. У AI Trainer нет фонового пользовательского канала, хотя backend-сигналы для него уже существуют.
4. **Human control оформлен по-разному.** Большинство либо меняет план автоматически, либо даёт chat command. Athletica подчёркивает, что chat только советует; AI Trainer имеет редкую сильную комбинацию preview/approve/reject/rollback и audit journal. Это стоит превратить в публичное trust-позиционирование.
5. **Цена массового сегмента низкая.** Узкие продукты стоят $3.99–9.99/мес; зрелые full-stack — примерно $15–20/мес. Self-hosted AI Trainer не имеет SaaS price и требует API credentials, поэтому его value proposition логичнее строить вокруг privacy/control/no vendor lock-in, а не только “AI coach дешевле человека”.
6. **Самые опасные прямые конкуренты:** AI Endurance (predictive model/science/integrations), IntervalCoach (daily adaptation/product breadth), Athletica (maturity/sports science/human coach), Enduco (mobile/adaptivity UX) и Coach Watts (training+nutrition). Самые полезные UX-референсы: Coach AMA/Fartlek для proactivity, Companion для Apple surface, CoachX для chat-to-watch и Atomic Metrix для MCP/tool architecture.

## Пробелы исследования

- Не создавались платные аккаунты и не проходился onboarding; сравниваются публично заявленные функции, а не проверенная работа алгоритмов.
- Для AI Cycling Coach, AI Coach Cloud, Atomic Metrix и RunIAg точная цена не найдена; для Coach Watts доступность конфликтует с waitlist copy.
- Маркетинговые counts («60+ signals», «2,000+ athletes», «3,000/5,000 workouts») сохранены как заявления продуктов, не как независимые факты.
- Store availability и региональные цены могут различаться; цены приведены в валюте официальной страницы на дату проверки.
