# Competitive Analysis: IntervalCoach vs AI Trainer

> Дата анализа: 2026-06-20
> Источники: [IntervalCoach Changelog](https://www.intervalcoach.app/en/changelog), [Roadmap (Featurebase)](https://feedback.intervalcoach.app/en/roadmap), [Forum Intervals.icu](https://forum.intervals.icu/t/intervalcoach-ai-workouts-that-adapt-daily-to-your-recovery-and-goals/120045), [App Store](https://apps.apple.com/us/app/intervalcoach-ai-training/id6760976369)

---

## Что такое IntervalCoach

Коммерческий AI-тренер (веб + нативные iOS/macOS/Android-PWA) для велосипедистов, бегунов, триатлетов, пловцов и ходоков. **Ядро архитектуры — НЕ Garmin-native:** работает поверх **Intervals.icu** как источника данных (wellness, активити, power curve, eFTP), а Garmin/Wahoo/Polar/Whoop/Oura/Apple Health подключаются *через* Intervals.icu. Это принципиальное архитектурное отличие от нас.

**Бизнес-модель:** Free (3 AI-тренировки/мес) → Pro ($3/мес, 20 сообщений Coach+) → Max ($8/мес, 200 сообщений + benchmarks + peer comparison + recovery profile + Coach Mode).

---

## Сравнение по ключевым осям

| Ось | IntervalCoach | Наш AI Trainer | Вывод |
|---|---|---|---|
| **Источник данных** | Intervals.icu (агностик к устройству) | Garmin Connect напрямую (+ garth auth) | IC масштабируется на любое устройство бесплатно; мы глубже интегрированы с Garmin |
| **AI-провайдеры** | Google Gemini (фиксированный) | OpenAI/Anthropic/Gemini/DeepSeek/Ollama/Mock (универсальная фабрика) | **Мы сильнее** — мульти-провайдерность, offline через Ollama, demo через Mock |
| **Daily readiness** | 60+ сигналов: HRV, RHR, сон, SpO₂, дыхание, температура запястья, cycle phase, recovery curve, monotony, ACWR, durability | Banister CTL/ATL/TSB + HRV analyzer + sleep metrics | IC значительно богаче по сигналам |
| **Personal recovery curve** | Да — экспоненциальный decay по каждому типу стимула, half-life персонально | Нет | **Главный gap** |
| **Адаптация плана в реальном времени** | Да — daily cron переписывает тренировку при позднем синке recovery; preview/approve flow | Частично — execution-driven corrective microcycle (ветка iteration1) | IC зрелее в рантайм-адаптации; мы развиваем это направление |
| **Workout catalog** | 130+ шаблонов с phase-gating, rotation, recency penalty | Есть training_planner, но масштаб неясен | IC промышленного масштаба |
| **Power curve / eFTP** | Полная: power curve, peak powers, eFTP history с projection plume, rider profile, durability | Базовые метрики | **Сильный gap** |
| **Мультиязычность** | 17 языков (JA/KO — 08.07, SV/NB — 30.07) | Русский | Узкая, но наш аудитория русскоязычная |
| **Coach+ (LLM-чат)** | Да, с tool-calling, approval-gated мутациями, memories с context tags | Да — `ai_tools.py` tool-calling, chat_manager | **Паритет**, мы чуть гибче по провайдерам |
| **Нативные приложения** | iOS/macOS native + Android native (Google Play, 23.06) | Только Streamlit web | Gap, но не критичный для нас |

---

## Где мы объективно сильнее

1. **Мульти-провайдерность AI.** IC привязан к Gemini; у нас абстракция `AIProviderFactory` с 5 провайдерами + offline Ollama + Mock для демо. Это снижает vendor lock-in и даёт privacy-mode (локальная модель).
2. **Глубокая нативная интеграция с Garmin.** IC идёт через Intervals.icu; у нас прямой `garmin_client.py` + `garth_client.py`, что даёт доступ к полям, которые Intervals.icu нормализует/теряет.
3. **Изолированный acceptance/demo режим** для безопасной браузерной верификации без живого логина — у IC этого нет публично.
4. **Русификация domain-первая** — для нашего рынка это преимущество, не долг.

---

## Где IC значительно впереди — и что стоит перенять

### 🔴 Высокий приоритет

**1. Personal recovery curve.** Это подписная фишка Pro/Max: экспоненциальный decay восстановления по каждому стимулу (threshold, VO2max, tempo, endurance), персональный half-life, feed-ится в spacing хард-сессий и readiness. У нас Banister фиксированный.

→ Фит в `models/banister.py` + новый `models/recovery_curve.py`: собирать HRV/RHR/сон-дельты после каждой хард-сессии, фитить exponential decay, публиковать half-life при ≥6 сессиях. Это напрямую усиливает наш `planning_execution.py` (execution-aware spacing уже есть — добавить recovery-aware spacing).

**2. Расширенный signals engine.** У IC единый `assembleDetectorInput` — один источник правды для dashboard, daily cron, Coach+, push, Agent Log. Сигналы: HRV suppression (2+ дня), RHR elevation, chronic sympathetic dominance (HRV suppressed + стабильный — паттерн который обычные метрики пропускают), ACWR (Gabbett 2016), monotony (Foster 1998), load-recovery ratio, durability (EF trending), VO2max declining, menstrual phase.

→ У нас `hrv_analyzer.py` + `sleep_metrics.py` разрозненны. Создать `models/signals_engine.py` с единым `assemble_signals(state)` → `Signal[]` с severity tiers, который читают и dashboard, и планирование, и Coach+ tools. **Это закрывает класс багов «dashboard говорит одно, календарь другое»**, который у IC был главной головной болью полгода.

**3. Phase-aware, polarized training model с periodization.** Base/Build/Peak/Taper/Race Week/Recovery с TSS-таргетами, phase-gating для типов тренировок (Base cap 30min Z4, Build 45min, Peak 60min — по Coggan/Allen), polarized vs pyramidal vs threshold модели, ACWR-driven load reduction.

→ Наш `training_planner.py` (1466 строк) — кандидат на дополнение этой моделью. Это самое ценное, что можно перенять без vendor-зависимости.

**4. Power curve + eFTP + rider profile.** Power curve (5s–60min), peak powers, eFTP history с projection plume (per-athlete regression), rider type (Sprinter/Puncheur/Climber/...), zone progression (fading flag).

→ Если у нас есть power streams из Garmin — это чисто вычислительная работа в `utils/metrics.py` + новая страница аналитики. Высокая ценность для retention.

### 🟡 Средний приоритет

**5. Daily briefing / outlook с preview-approve адаптацией.** У IC morning cron переписывает сегодня's workout, если поздно синкается recovery; пользователь видит «Workout Proposed» и одобряет/отклоняет. Preview-vs-auto toggle.

→ У нас есть `execution_feedback` компонент и planning execution — можно построить `ui/components/daily_briefing.py` поверх существующего StateManager.

**6. Workout catalog с rotation + recency penalty.** 130+ шаблонов, recency penalty по дням И по сессиям (для low-frequency атлетов), phase fit per workout, polarized boost.

→ Расширить `training_planner.py` выборкой с scoring function (recency × phase × focus area × recovery cap).

**7. Agent Log / Decisions.** Timeline каждого решения: readiness call, почему выбран workout, что изменилось, adaptation. У IC это вышло из beta и стало killer-фичей для trust.

→ У нас уже есть `planning_checkpoints` в БД (видно в `database.py`) — это готовая основа. Добавить `ui/pages/decisions.py` поверх checkpoints.

**8. Coach+ memories с context tags.** Заметки атлета с тегами (sport, intensity bucket, day-of-week, indoor/outdoor, expiry), semantic retrieval по контексту вопроса. Weekly cleanup дедупликации.

→ Расширить `models/chat_manager.py` памятью с тегами.

### 🟢 Низкий приоритет / не наш контекст

- **Clubs / leaderboards / public profiles** — социальные фичи, для личного тренера избыточны.
- **Menstrual cycle phase-aware readiness** — научно ценно, но требует данных и заметной работы; отложить.
- **Race pace plans, trail/ultra-specific workouts, Norwegian method** — нишевые sports-science детали; перенять по мере роста спортивной аудитории.
- **Apple Health как источник** — имеет смысл только если уходим от Garmin-only.

---

## Архитектурные выводы

1. **Source-of-truth проблема у IC — наш предупреждение.** Половина их changelog — «dashboard говорил одно, календарь другое, email третье». У нас StateManager + planning_checkpoints позволяют этого избежать, **если** мы построим единый signals engine раньше, чем разрастёмся. Это приоритет №1 архитектурно.

2. **Intervals.icu как data hub — стратегический вопрос.** IC не пишет своё хранилище fitness-модели, они читают Intervals.icu (power curve, eFTP, wellness). Мы храним сами (SQLite). Наш путь даёт оффлайн и контроль, но добавляет работы (power curve, eFTP model — всё писать самим). Решение зависит от того, планируем ли мы multisport/мульти-устройство.

3. **Iterate fast on signals, slow on catalog.** IC шипит 5-15 фиксов/день — большинство это edge cases в planning/scheduling logic. Их темп показывает, что **planning correctness — это бесконечный long tail**. Наша `planning_execution.py` (execution-aware corrective microcycle) — правильное направление; надо закладывать, что багов будет много, и иметь fast-iteration loop (smoke-тесты + acceptance mode).

---

## Топ-5 рекомендаций к действию

| # | Что | Где в коде | Эффект |
|---|---|---|---|
| 1 | Единый signals engine (`assemble_signals`) | Новый `models/signals_engine.py`, читают dashboard/planning/Coach+ | Закрывает класс source-of-truth багов |
| 2 | Personal recovery curve (exp decay half-life) | `models/recovery_curve.py`, интеграция в `planning_execution.py` | Killer-фича, дифференциатор |
| 3 | Power curve + eFTP + rider profile | `utils/metrics.py` + `ui/pages/analytics.py` | Retention, профессиональная глубина |
| 4 | Agent Log поверх planning_checkpoints | `ui/pages/decisions.py` | Trust/прозрачность решений |
| 5 | Daily briefing с preview-approve | `ui/components/daily_briefing.py` + execution layer | UX-паритет с коммерческими rivalами |

Все пять ложатся в существующую архитектуру (StateManager → services → models → ui/pages) и не требуют смены data source или добавления Intervals.icu зависимости.

---

## Дополнение: 2026-07-03 (changelog за 2026-06-20 → 2026-07-03)

> ~70 дней changelog-записей IC вручную не перечитывались с прошлого анализа; ниже — что изменилось и как это соотносится с текущим приоритетом проекта (агентный контур Recovery Replan, issues A–F — см. память `project_agent_contour_recovery_replan`), а не повторный список фич.

### Прямое совпадение с Recovery Replan (issues A–F)

IC за эти две недели шипил ровно то, что мы сейчас проектируем:

- **Readiness Score Breakdown** (3 июля) — «plain language explanations showing what factors influenced the daily readiness number» → наш **Issue F** (объяснение решения + decision_log).
- **Recovery Time Scaling: adjusted based on actual session difficulty rather than session type alone** (3 июля) → наш **Issue D** (фальсифицируемый прогноз качества/нагрузки сессии, не категория по типу).
- **Training Monotony Warning: respects deliberate training patterns like polarized plans or no rest days** (3 июля) → ровно принцип **«молчание — дефолт»** (salience-gate, **Issue C**) — подавление ложных тревог при осознанном паттерне.
- **Weekly Plan Rebalancing: real-time adjustments** (2 июля) → наш **Issue E** (генератор вариантов поверх `planning_near_term`).
- Серия «recovery data changes trigger mid-day adaptation» / «early rest proposal correction withdraws if recovery data changes» (11 июня) → валидирует калибровочную петлю через decision_log, а не оценку «была ли рекомендация оптимальной».

**Вывод:** направление верное — IC независимо приходит к той же архитектуре (readiness fusion → salience-gate → explain → adapt) для того же типа пользователя. Не повод копировать, но сильный внешний сигнал, что мы решаем правильную проблему.

### Параллель с нашими TSB-багами (#54, #61)

За этот период у IC больше 15 changelog-записей класса «источник истины разошёлся между поверхностями»: *CTL Dashboard Sync*, *Recovery Ring Consistency*, *Live Calendar Reading*, *Plan Refresh Caching*, *Weekly Target Breakdown shows actual calculation basis*. Это структурная ловушка любого продукта с несколькими UI-поверхностями поверх одной аналитики.

Мы наступили на тот же класс бага дважды подряд — #54 (TSB zones desync) и #61 (TSB window mismatch между `/summary` и `/widgets`). Прошлый анализ (2026-06-20) уже называл unified `signals_engine`/`assemble_signals()` архитектурным приоритетом №1, но тогда это была гипотеза по чужому changelog. Теперь это подтверждено собственным инцидентом — приоритет стоит поднять из P2 в ближайшую очередь, а не откладывать.

### Новый сигнал: AI Assistant Integration (Max, Beta, 24 июня)

«Connect Claude, ChatGPT, or Cursor to access training data and create workouts» — IC открывает MCP-подобный доступ к своим данным для внешних AI-агентов. Это не наш текущий приоритет (P0 — Recovery Replan), но стратегически заметно: у нас уже есть мультипровайдерный AI-слой (`models/ai_providers.py`); обратный путь — экспонировать *наши* данные наружу через MCP-сервер для Claude Desktop/Cursor — сейчас не рассматривался. Держать в уме как возможный дифференциатор после закрытия текущего клина.

### Новый gap для Issue B (readiness fusion)

**Illness Detection из дыхания/SpO₂/температуры кожи** (16 июня) и **Recovery Profile для всех типов сессий с первого дня** (16 июня) — проверено: `data/garmin_client.py` и `services/sync.py` сейчас respiration rate / SpO₂ / skin temperature не тянут вообще (grep не находит). Garmin Connect API их отдаёт. Потенциально дешёвое расширение входов `models/readiness.py` сверх уже запланированных sleep/HRV/RHR/training_status/TSB — не блокер для первого среза (B→C→min D→F), но кандидат для второй итерации Issue B.

### Что подтвердилось без изменений

Приоритеты из анализа 2026-06-20 (recovery curve, signals engine, power curve/eFTP, agent log, daily briefing) остаются актуальными. Низкоприоритетные пункты (clubs/leaderboards, menstrual cycle, Apple Health) — по-прежнему низкий приоритет; в новых записях больше их вариаций (Coach Mode, Club Event Editing), но это командные/социальные фичи не в духе нашего single-athlete продукта.

---

## Дополнение: 2026-08-06 (changelog за 2026-07-03 → 2026-08-02)

> Окно ~250 записей не перечитывалось с прошлого дополнения. Ниже — что изменилось и как это соотносится с текущим контуром проекта (readiness → conflict gate → recovery replan loop, issues A–F) и ближайшими клиньями (калибровка TSS против IntervalCoach, plan reconciliation, concurrency), а не повторный список фич.

### Прямое совпадение с нашим контуром (issues A–F)

- **Readiness Score 2.0 (4 июля)** — фактически Issue B в их исполнении. Чистая мера восстановления: HRV, RHR, сон, личная recovery curve и morning check-in, каждый фактор против собственного 30-дневного базлайна, и «training plan no longer touches the number» (отдых с восстановленным телом показывает высокий скор). Это дизайн-решение стоит проверить у нас: `compute_readiness_today` не должен смешивать «как восстановлен» и «что делать сегодня» — у IC это была отдельная ошибка (22 июня: recovery ring показывал низкое восстановление из-за отсутствия запланированной сессии).
- **Якорение скора (4–7 июля):** «score anchors once your morning data is in... only moves for a real reason (check-in, genuinely new recovery data mid-day)», до данных — provisional `~`, и «when there's genuinely nothing to go on, we show no number at all instead of a made-up one». Это ровно семантика нашего `readiness_today`/snapshot contract плюс принцип «молчание — дефолт» (Issue C), применённый к самому скору.
- **Единый источник истины (5 июля):** «the coach now talks about your readiness score consistently everywhere... instead of sometimes quoting your device's recovery percentage» — dashboard, briefing, outlook, weekly summary, race-day advice и Coach+ рассуждают от одного 0–100. Подтверждает наш вывод про единый signals engine и закрывает класс source-of-truth багов.
- **Салиенс-гейт дословно (6 июля):** «the "take it easy if you feel off" line no longer appears every single day: it shows up only when a fatigue or recovery signal is actually flagged», и коуч называет конкретный сигнал («HRV is 15% below baseline»), а не «the signals suggested it» — объяснимость из Issue F.
- **Proposal с числами (5–8 июля):** «Duration: 90 min (+15 vs planned) · Load: ~85 TSS (vs ~95 planned)» и «an eased workout is always lighter than the session it replaces, capped to the reduction the coach intended». Это готовая спецификация для Issue D (фальсифицируемый прогноз нагрузки) и для нашего recovery variant builder: замена не может быть тяжелее оригинала.
- **Injury-контур (15, 18 июля):** серьёзная травма (3/4) снимает всю интенсивность, «injured» (4/4) логирует injury day, отдых и постепенный return-to-training ramp; счётчик дней травмы непрерывен. Плюс «коуч читает и check-in, и Intervals.icu, берёт худшее из двух» — паттерн merge субъективных данных из двух источников. Валидирует расширение входов Issue B (sick/injured) и наш `woz_recovery_replan_protocol` (keep/downgrade/ramp).

### Параллель с нашими клиньями (user intent, concurrency, reconciliation)

- **Durable user intent:** удаления через Coach+, rest days и «weekly plan off» записываются durable и уважаются фоновым sync (5, 6, 22 июля) — IC целый месяц чинил класс «фон вернул то, что пользователь убрал». У нас это архитектурно покрыто `planning_checkpoints` + `coach_proposals` lifecycle; урок: любые новые background-пути обязаны идти от последнего checkpoint и уважать user-intent записи (удаление/rest day/disabled plan).
- **Concurrency:** «background syncs wait until an in-progress rebuild finishes» (16 июля) и «the same daily workout could appear twice when morning processing ran twice in parallel» (22 июля) — класс, который мы закрываем TD-003 (unified sqlite concurrency policy). Их баги — наша валидация: планировщик обязан быть идемпотентным, а фоновые задачи не должны гоняться с мутациями.
- **Plan reconciliation:** «weekly TSS target no longer changes on Sunday», «hours match scheduled sessions», «Training Plan page shows the actual plan total, not a recomputed one», «upcoming weeks step up toward your CTL target» (12, 16, 21, 24 июля) — то же семейство, что наши #54/#61 (TSB desync) и `docs/plan_actual_reconciliation_execplan.md`. Их темп показывает: display-пересчёт target отдельно от планирования — это бесконечный источник рассинхрона; нужна одна функция расчёта.

### Новый сигнал: thresholds как source-of-truth с явной диагностикой

- **Правка FTP/threshold pace/HR прямо в приложении** (19 июля) и **предупреждение при расхождении FTP >10%** между Intervals.icu и моделью коучинга (30 июля): post-workout analysis в этом случае говорит «targets themselves were off», а не «you took it easy». Прямое попадание в наш клин калибровки против IntervalCoach (`docs/activity_tss_calibration_execplan.md`). Урок: недостаточно калибровать формулы — продукт обязан *показывать* пользователю расхождение базовых констант (FTP/threshold), иначе провал тренировки выглядит как «не справился». Дешёвый кандидат: пункт про отображение расхождения FTP/зоны в Settings добавить в клин калибровки TSS.
- **Per-sport thresholds:** running power отдельно от cycling FTP (19 июля), progressive overload сравнивает только внутри спорта (30 июля) — паттерн у нас уже частично есть (swim CSS); при расширении мультиспорта держать thresholds per sport, иначе сравнительные тренды бессмысленны.

### MCP/ассистент: подтверждение нашего ADR-0004

- **MCP-коннектор для Max вышел из беты** (7 июля, Settings → Integrations), **новые правила авторизации MCP** (28 июля: identity documents, local redirects для desktop/CLI, сервер называет себя в ответе) и **«ассистент спрашивает перед любым изменением»** (30 июля) — независимо пришли к approval-gated мутациям, ровно наш `coach_approval_mutation_lifecycle`/`docs/architecture/adr_0004_coach_mutations_via_proposals.md`. Подтверждение, что контракт правильный; экспонировать *наши* данные наружу через MCP — по-прежнему будущий дифференциатор, не текущий приоритет.

### Что осталось вне нашего контекста

- Социальное (community races, race catalog/SEO, clubs) и weather/nutrition — по-прежнему не наш контекст. Распознавание личных рекордов в post-workout email (31 июля, beta) — это retention-фича поверх уже зафиксированного gap #3 (power curve); полезен как спецификация: «only genuine efforts count» (фильтр дрейфа измерений: ватт/секунда как шум, новая дистанция — не рекорд).
- Локализация/юниты: 17 языков (JA/KO — 8 июля, SV/NB — 30 июля), «values are converted now, not just the labels» (31 июля) — универсальный урок про юниты (наш клин миль/км тоже должен конвертировать значения, а не подписи), но не приоритет для RU-first продукта.

### Вывод

Контур подтверждается третий раз подряд, теперь на самом зрелом куске: IC за месяц выкристаллизовал ровно нашу форму — единый anchored readiness score → салиенс («молчание — дефолт») → объяснимые proposal с числами → approval-gated мутации (включая MCP-агента). Два практических урока: (1) user-intent записи должны быть durable и уважаться любыми фоновыми задачами — у нас уже есть через checkpoints, следить за новыми background-путями; (2) явная product-facing диагностика расхождения thresholds — дешёвый способ убрать класс «выглядит как провал тренировки» — предложить отдельным пунктом в клине калибровки TSS.

### Статус реализации (2026-08-08)

- **Gap #3 (power curve / best efforts) закрыт** — карточка тренировки показывает «Рекорды» (peaks 5s…60min, Вт/кг, VO₂max 5min) из best-efforts/power-curves Intervals.icu: #382, PR #393 (см. `docs/best_efforts_execplan.md`).
- **Gap «структура тренировки» закрыт** — карточка показывает «Структуру тренировки» (интервалы Intervals.icu): #390, PR #391; и «План vs факт по репетициям»: #383, PR #394 + #395 (см. `docs/plan_vs_fact_execplan.md`).
- **«Only genuine efforts count»** (фильтр дрейфа измерений / новые дистанции) — в коде не реализован, остаётся бэклогом качества рекордов (follow-up к #382).
