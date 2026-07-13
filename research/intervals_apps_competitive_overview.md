# Приложения Intervals.icu: конкурентный обзор для AI Trainer

Дата среза: 2026-07-13.

## Охват

- Исходный каталог: `intervals_icu_ai_trainer_apps.csv`.
- Фильтр каталога Intervals.icu: категория «ИИ Тренер».
- Всего: 63 приложения, включая 2 уже подключенных к исследованному аккаунту и 61 запись каталога.
- Эталон нашего продукта: `research/ai_trainer_product_profile.md`.
- Правила проверки: `research/comparison_methodology.md`.

## Как читать материалы

Подробные карточки приложений разделены на три группы:

- `research/intervals_apps_batch_1.md`
- `research/intervals_apps_batch_2.md`
- `research/intervals_apps_batch_3.md`

`n/a` означает отсутствие публичного подтверждения, а не доказанное отсутствие функции. Уровень confidence относится к качеству доступных официальных данных.

## Сводные выводы

1. **Обычный AI-чат и генерация плана уже стали commodity.** В каталоге много продуктов с похожим обещанием, а публичные цены узких сервисов часто лежат около $/€5–10 в месяц; зрелые full-stack продукты обычно ближе к $/€15–20.
2. **Рыночный стандарт смещается к полному циклу:** recovery/readiness → изменение плана → доставка тренировки на устройство → post-workout feedback. AI Trainer силен в объяснимом и безопасном изменении плана, но слабее в доставке на мобильные/watch/device surfaces.
3. **Intervals.icu работает как дешевый data/distribution hub.** AI Trainer уже использует его для профиля, гонок A/B/C, plan-fact evidence и legacy-экспорта событий, сохраняя direct Garmin как основной источник. Пробел теперь не в отсутствии интеграции, а в OAuth/onboarding и завершённой last-mile доставке из основного web-контура.
4. **Proactive delivery важнее еще одного dashboard.** Утренние сообщения, post-session review, Telegram/WhatsApp/Discord и push уменьшают необходимость самому открывать web-интерфейс. У AI Trainer backend-сигналы уже есть, но нет такого пользовательского канала.
5. **Human-in-the-loop становится нормой, но редко описан строго.** Несколько продуктов показывают review/approval, однако публично подтвержденная комбинация AI Trainer `signal → conflict → proposal → approve/reject → audit → rollback` остается редкой и защитимой.
6. **Главная позиция AI Trainer — не “еще один AI coach”.** Более четкий тезис: self-hosted, direct Garmin, local data, model choice/Ollama и обратимые действия с доказательствами.

## Наиболее близкие конкуренты

| Продукт | Почему близок | Где конкурент сильнее | Где AI Trainer сильнее |
|---|---|---|---|
| IntervalCoach | Multisport, daily readiness, adaptive plans, AI chat | Breadth recovery signals, mobile, зрелый adaptation runtime | Self-hosting, multi-provider/Ollama, explicit audit/rollback |
| AI Endurance | Science/predictive adaptive planning | Predictive models, integrations, коммерческая зрелость | Local control, provider choice, approval lifecycle |
| Athletica | Multisport plans, readiness, coach workflows | Sports-science maturity, human-coach ecosystem | Self-hosting, Russian-first, reversible AI actions |
| Enduco | Multisport adaptive mobile coach | Native mobile, device breadth, adaptivity UX | Direct Garmin/local data, explainable readiness gate |
| Coach Watts | Plan + recovery + nutrition | Nutrition/fueling layer, integrations, proactivity | Safer mutation governance, local/provider independence |
| Intervals Pro | Chat → analysis → plan → approval → calendar | Telegram/WhatsApp, Intervals-native distribution, power analytics | Direct Garmin, self-hosting, deterministic gate/rollback |
| LeCoach | Adaptive endurance planning and plan-health | Device delivery, polished SaaS lifecycle | Evidence trail, local deployment, model choice |
| PlanWatts | Conversational multisport planning and editing | Intervals/device ecosystem, teams, sharing, low-friction SaaS | Recovery decision safety, audit, rollback, Ollama |
| RestOrTrain | Conversational recovery-aware coach | iOS polish, integrations, proactive/route workflows | Transparent human approval and local data ownership |
| RacePal | Triathlon plans, health signals, adaptive schedule | Consumer mobile, nutrition/race UX | Self-hosting, traceable actions, multi-provider AI |
| RaceMind | Deterministic sports science + LLM explanation | Consumer integrations, push, workout library | Broader AI provider choice and explicit proposal lifecycle |
| Ridium | Cycling-specific contextual AI coach | Focused cycling UX and Intervals integration | Multisport planning, self-hosting, recovery audit/rollback |

## Повторяющиеся возможности рынка

- Генерация многонедельного или сезонного плана по цели и доступному времени.
- Изменение недели после пропуска, усталости, HRV/sleep/readiness или изменения расписания.
- Чат поверх истории тренировок и post-workout объяснения.
- CTL/ATL/TSB, нагрузка, adherence и race/fitness projections.
- Структурированные тренировки с доставкой через Intervals.icu, Garmin, Wahoo, Zwift или файлы FIT/ZWO/TCX.
- Нативный mobile/watch или хотя бы внешний messaging-канал.
- Бесплатный/дешевый entry tier, trial или BYOK/credit модель.
- Узкая специализация как способ выделиться: rowing, cycling power, today-only workout, indoor execution, nutrition или MCP/data access.

## Дифференциаторы AI Trainer

- Direct Garmin без обязательного внешнего тренировочного хаба.
- Опциональный Intervals.icu слой для профиля, гонок и plan-fact evidence без отказа от локального источника истины.
- Local SQLite и self-hosted Docker deployment.
- OpenAI, Anthropic, DeepSeek, Gemini, Ollama и Mock AI вместо привязки к одному провайдеру.
- Демо/acceptance режим без реальных учетных данных.
- Readiness conflict gate с сохранением доказательств и причины молчания/вмешательства.
- Версионированный каталог структурированных стимулов и консервативные
  bike-to-run bricks с неизменяемыми prescription snapshots.
- Persisted preview/approve/reject и безопасный rollback версии плана.
- Russian-first UX для рынка, который большинство конкурентов не обслуживает как основной.

## Продуктовые пробелы и возможности

1. **P0 — ясно упаковать trust advantage:** вывести decision trail и rollback из технической реализации в главное продуктовое обещание.
2. **P1 — довести существующий Intervals.icu слой до production UX:** onboarding/OAuth либо безопасная настройка ключа, web-доставка workout events, статус синхронизации и идемпотентность повторной отправки.
3. **P1 — proactive channel:** начать с Telegram для русскоязычной аудитории или push/PWA morning briefing; любые write-actions оставить за approval gate.
4. **P1 — закрыть last mile:** надежная доставка структурированных тренировок на Garmin/Wahoo/Zwift и видимый статус синхронизации.
5. **P2 — mobile/PWA surface:** today/readiness/proposal/approve как минимальный мобильный контур, не полный перенос dashboard.
6. **P2 — узкий hero flow «Что делать сегодня и почему?»**, который использует уже существующий readiness/replan engine и объясняет immediate value.
7. **P2 — MCP/external AI access** с read scopes по умолчанию и подтверждением любых изменений.
8. **Не приоритет:** indoor trainer execution, social rides, clubs и большие workout marketplaces — это отдельные категории, где уже есть специализированные игроки.

## Ограничения исследования

- Проверялись публичные официальные страницы без покупки подписок и полного onboarding.
- 63 из 63 карточек имеют источники, confidence и список неопределенностей; часть закрытых beta/SPAs осталась low-confidence.
- Маркетинговые числа пользователей, сигналов и тренировок не были независимо проверены.
- Региональные цены app stores могут отличаться.
