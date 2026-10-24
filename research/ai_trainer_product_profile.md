# AI Trainer: эталонный профиль для конкурентного сравнения

Дата проверки: 2026-10-20; локальный HEAD `fda0c83`. Источник истины: текущий код и документация репозитория. Это профиль реализованного продукта, а не список будущих идей.

## Позиционирование

Персональный self-hosted evidence-first AI-тренер. Intervals.icu — рекомендуемый основной источник активностей и wellness для нового запуска; Garmin Connect — совместимый необязательный источник. Он объединяет нагрузку и восстановление, исполняемые планы, plan-fact review и управляемые изменения. Основной продуктовый путь — FastAPI + Next.js; миграция продолжается, Streamlit остаётся fallback. Планировщик поддерживает бег, велоспорт и триатлон.

## Реализованные возможности

- Инкрементальная синхронизация активностей, сна, HRV, здоровья, Body Battery, training readiness/status и доступных recovery bio-signals из Garmin; локальное хранение в SQLite.
- Intervals-primary путь по персональному API-ключу: активности и wellness → onboarding → первый подтверждённый план. Чтение гонок A/B/C и provider evidence для plan-fact; web Planning доставляет исполняемые события в выбранном окне, изменяя только принадлежащие AI Trainer `external_id`. Профиль FTP/вес/LTHR не импортируется самим Intervals ingestion: без дополнительного Garmin/profile-пути используются явные `USER_*` значения.
- Аналитика нагрузки и формы: TSS, CTL, ATL, TSB, Banister fitness/fatigue, тренды и сравнение периодов.
- Канонический readiness fusion: личные 28-дневные базлайны HRV и resting HR, сон, Garmin readiness и TSB; результат содержит confidence, drivers, evidence, freshness и явные missing inputs.
- Единый signals engine используется dashboard/planning/AI и legacy-поверхностью вместо независимых трактовок нагрузки и восстановления.
- Экран «Сегодня» показывает readiness, сессию дня, факт за вчера и актуальное recovery-предложение; тихое состояние считается полноценным решением.
- Планирование по цели, дистанции, доступным дням/часам, текущей нагрузке и фазам; режимы event goal, rolling training goal и manual; бег, велосипед, триатлон.
- Race-aware planning: явные приоритеты A/B/C, provenance событий, Taper/Race Week, локальные load caps и защищённые даты соревнования/восстановления.
- Preview/confirm перед сохранением, append-only checkpoints и stale-preview guard защищают от применения плана поверх изменившегося состояния.
- Evidence-first plan-fact reconciliation использует стабильные session identities, локальные активности и опциональные данные Intervals.icu; спорные совпадения можно исправить явно.
- Версионированный каталог содержит 22 структурированных стимула. Исполняемые `sessions[]`, scheduler доступных слотов и несколько сессий в день обеспечивают согласованность плана и экспорта; bike-to-run brick имеет отдельно экспортируемые ноги.
- Недельная перебалансировка строится сначала как preview, меняет только будущие сессии, сохраняет защищённые даты и подтверждается по неизменившемуся fingerprint evidence.
- Долговременный ledger ограничений (`sick`, `unavailable`, `forced_rest`, `manual_delete`, `disabled_plan_day`) защищает выбранные даты при последующем replanning.
- Экспорт календаря и структурированных тренировок: ICS, TCX и FIT-compatible CSV.
- AI-чат с инструментами над фактическими данными и активным планом, историей диалогов, потоковым ответом и tool-call transparency.
- Мультипровайдерный AI: OpenAI, Anthropic, DeepSeek, Google Gemini, локальный Ollama и Mock AI для демо.
- Действия коуча через preview/approve/reject: предложения плана сохраняются, применяются только после подтверждения и попадают в журнал решений.
- RecoveryReplan v2: salience gate, `keep`, снижение нагрузки или атомарный перенос ключевой сессии на D+1…D+3 с проверкой доступности, protected dates, spacing и бюджетов; approve/reject и append-only rollback. Перенос остаётся локальным до отдельного подтверждённого delivery-действия.
- Lifecycle плановых циклов: явный текущий/исторический контекст, команды закрытия и event outcomes; чтение не должно неявно выбирать другой цикл. Контракты: `api/routers/planning_cycles.py`, `services/planning_cycles.py`.
- Детерминированный прогноз качества ближайшей ключевой сессии записывается в shadow mode для последующего ручного plan-fact/quality scoring; он намеренно не влияет на решение и пока не имеет web-поверхности.
- Демо/acceptance режим без живого Garmin и AI-ключа; локальный self-hosted Docker-вариант.

## Каналы и платформы

- Web-приложение; локальный/self-hosted запуск.
- Нет подтвержденных нативных мобильных приложений, Telegram/Discord/email-коуча или фоновых push-уведомлений.
- UI и документация в первую очередь русскоязычные.
- «Решения», «Восстановление» и shadow-модуль Today являются dev-поверхностями за `NEXT_PUBLIC_SHOW_DEV_TOOLS`; наличие backend-контракта не равно доступному всем пользователям сценарию.

## Коммерческий статус

- В репозитории нет публичной SaaS-тарификации или пробного периода.
- Для рекомендуемого запуска нужен API-ключ Intervals.icu; Garmin credentials необязательны. Для облачного AI нужен ключ провайдера; доступны локальный Ollama и demo/Mock.

## Сильные стороны для матрицы

1. Прямая Garmin-интеграция и контроль над локальными данными.
2. Мультипровайдерность, локальный Ollama и отсутствие vendor lock-in.
3. Объяснимые, журналируемые и обратимые изменения плана с явным подтверждением человека.
4. Связка readiness → конфликт с планом → предложение изменения → approve/reject/rollback.
5. Evidence-first plan-fact и race-aware periodization с append-only provenance и защитой от устаревших подтверждений.
6. Версионированные структурированные prescriptions и консервативные composite bricks, сохраняющиеся через checkpoint/replan/export.
7. Intervals-primary ingestion дополнен совместимым прямым Garmin-путём; локальное хранилище остаётся источником истины продукта.
8. Изолированный demo/acceptance контур и self-hosting.

## Ограничения и пробелы

- Intervals-primary onboarding реализован, но используется персональный API-ключ, а не OAuth. Прямые интеграции Strava/Apple Health/Wahoo/Coros не подтверждены.
- Web-доставка реализована; история/статус доставки и post-delivery reconciliation остаются долгом. Автоматическая отправка recovery transfer не заявлена.
- Нет нативных iOS/Android/watch приложений и фонового пользовательского канала.
- Нет публично подтвержденных продвинутых power-curve/eFTP/rider-profile возможностей.
- Нет публичной социальной/coach marketplace/club функциональности.
- Продукт находится в активной web-миграции и выглядит менее коммерчески зрелым, чем запущенные SaaS-конкуренты.
- Recovery transfer ограничен безопасными кандидатами D+1…D+3 и границей недели; отсутствие подходящего кандидата не должно обходить ограничения.
- Session-quality forecast остаётся shadow/WoZ-контуром и не должен позиционироваться как автоматическая доказанная модель качества.

## Репозиторные источники

- `README.md`
- `api/planning_service.py`
- `api/readiness_snapshot.py`
- `api/readiness_conflicts.py`
- `api/recovery_replan_loop.py`
- `api/session_quality_forecast.py`
- `api/routers/coach.py`, `planning.py`, `decisions.py`, `today.py`
- `services/intervals_icu.py`
- `services/intervals_sync.py`, `services/intervals_plan_delivery.py`
- `api/routers/planning_cycles.py`, `services/planning_cycles.py`, `services/planning_cycle_commands.py`
- `models/training_planner.py`, `models/ai_providers.py`, `models/readiness.py`, `models/signals_engine.py`
- `models/plan_events.py`, `models/plan_actual_reconciliation.py`, `models/session_identity.py`, `models/workout_catalog.py`
- `docs/coach_approval_mutation_lifecycle_execplan.md`
- `docs/recovery_replan_loop_execplan.md`
- `docs/session_quality_forecast_execplan.md`
- `docs/race_priority_periodization_execplan.md`
- `docs/plan_actual_reconciliation_execplan.md`
- `docs/structured_workout_catalog_execplan.md`
- `docs/today_screen_execplan.md`
- `docs/architecture/adr_0001_web_primary_ui.md`
