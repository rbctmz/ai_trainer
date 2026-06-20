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
| **Мультиязычность** | 13 языков | Русский | Узкая, но наш аудитория русскоязычная |
| **Coach+ (LLM-чат)** | Да, с tool-calling, approval-gated мутациями, memories с context tags | Да — `ai_tools.py` tool-calling, chat_manager | **Паритет**, мы чуть гибче по провайдерам |
| **Нативные приложения** | iOS/macOS/Android-PWA | Только Streamlit web | Gap, но не критичный для нас |

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
