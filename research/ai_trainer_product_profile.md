# AI Trainer: эталонный профиль для конкурентного сравнения

Дата проверки: 2026-07-13. Источник истины: текущий код и документация репозитория. Это профиль реализованного продукта, а не список будущих идей.

## Позиционирование

Персональный self-hosted evidence-first AI-тренер с прямой синхронизацией Garmin Connect и опциональной API-интеграцией Intervals.icu. Он объединяет аналитику нагрузки и восстановления, планирование, plan-fact review и управляемые изменения плана. Основной продуктовый контур мигрирует на FastAPI + Next.js; Streamlit остается fallback-поверхностью. Целевые виды спорта планировщика: бег, велоспорт и триатлон (включая плавательные сессии в триатлонном плане).

## Реализованные возможности

- Инкрементальная синхронизация активностей, сна, HRV, здоровья, Body Battery, training readiness/status и доступных recovery bio-signals из Garmin; локальное хранение в SQLite.
- Опциональная интеграция Intervals.icu по персональному API-ключу: синхронизация FTP/веса/LTHR, чтение гонок A/B/C, provider evidence для plan-fact и создание запланированных workout events. Отправка событий сейчас доступна в legacy Planning; web-контур использует чтение событий и reconciliation evidence.
- Аналитика нагрузки и формы: TSS, CTL, ATL, TSB, Banister fitness/fatigue, тренды и сравнение периодов.
- Канонический readiness fusion: личные 28-дневные базлайны HRV и resting HR, сон, Garmin readiness и TSB; результат содержит confidence, drivers, evidence, freshness и явные missing inputs.
- Единый signals engine используется dashboard/planning/AI и legacy-поверхностью вместо независимых трактовок нагрузки и восстановления.
- Экран «Сегодня» показывает readiness, сессию дня, факт за вчера и актуальное recovery-предложение; тихое состояние считается полноценным решением.
- Планирование по цели, дистанции, доступным дням/часам, текущей нагрузке и фазам; режимы event goal, rolling training goal и manual; бег, велосипед, триатлон.
- Race-aware planning: явные приоритеты A/B/C, provenance событий, Taper/Race Week, локальные load caps и защищённые даты соревнования/восстановления.
- Preview/confirm перед сохранением, append-only checkpoints и stale-preview guard защищают от применения плана поверх изменившегося состояния.
- Evidence-first plan-fact reconciliation использует стабильные session identities, локальные активности и опциональные данные Intervals.icu; спорные совпадения можно исправить явно.
- Версионированный каталог содержит 19 детерминированных стимулов для bike/run/swim/recovery и материализует точные шаги с сохранённым provenance зон. Триатлонные Build/Peak-недели могут включать один атомарный bike-to-run brick с двумя отдельно экспортируемыми ногами; при недостаточной фактуре или глубокой усталости система консервативно отказывается его создавать.
- Недельная перебалансировка строится сначала как preview, меняет только будущие сессии, сохраняет защищённые даты и подтверждается по неизменившемуся fingerprint evidence.
- Долговременный ledger ограничений (`sick`, `unavailable`, `forced_rest`, `manual_delete`, `disabled_plan_day`) защищает выбранные даты при последующем replanning.
- Экспорт календаря и структурированных тренировок: ICS, TCX и FIT-compatible CSV.
- AI-чат с инструментами над фактическими данными и активным планом, историей диалогов, потоковым ответом и tool-call transparency.
- Мультипровайдерный AI: OpenAI, Anthropic, DeepSeek, Google Gemini, локальный Ollama и Mock AI для демо.
- Действия коуча через preview/approve/reject: предложения плана сохраняются, применяются только после подтверждения и попадают в журнал решений.
- Recovery replan: детерминированный salience gate, объяснимое решение, предложение ослабить конфликтующую сессию, подтверждение/отклонение и безопасный rollback.
- Детерминированный прогноз качества ближайшей ключевой сессии записывается в shadow mode для последующего ручного plan-fact/quality scoring; он намеренно не влияет на решение и пока не имеет web-поверхности.
- Демо/acceptance режим без живого Garmin и AI-ключа; локальный self-hosted Docker-вариант.

## Каналы и платформы

- Web-приложение; локальный/self-hosted запуск.
- Нет подтвержденных нативных мобильных приложений, Telegram/Discord/email-коуча или фоновых push-уведомлений.
- UI и документация в первую очередь русскоязычные.

## Коммерческий статус

- В репозитории нет публичной SaaS-тарификации или пробного периода.
- Требуются собственные учетные данные Garmin и ключ выбранного AI-провайдера, кроме demo/Ollama сценариев. Intervals.icu необязателен и подключается персональным API-ключом.

## Сильные стороны для матрицы

1. Прямая Garmin-интеграция и контроль над локальными данными.
2. Мультипровайдерность, локальный Ollama и отсутствие vendor lock-in.
3. Объяснимые, журналируемые и обратимые изменения плана с явным подтверждением человека.
4. Связка readiness → конфликт с планом → предложение изменения → approve/reject/rollback.
5. Evidence-first plan-fact и race-aware periodization с append-only provenance и защитой от устаревших подтверждений.
6. Версионированные структурированные prescriptions и консервативные composite bricks, сохраняющиеся через checkpoint/replan/export.
7. Прямая Garmin-интеграция дополнена Intervals.icu, но не заменена внешним data hub.
8. Изолированный demo/acceptance контур и self-hosting.

## Ограничения и пробелы

- Garmin-first: Intervals.icu подключён через персональный API-ключ, но это не полноценный OAuth/onboarding-коннектор и не замена прямым интеграциям Strava, Apple Health, Wahoo или Coros.
- Отправка плановых событий в Intervals.icu пока находится в legacy Planning; в основном web-контуре last-mile delivery не завершён.
- Нет нативных iOS/Android/watch приложений и фонового пользовательского канала.
- Нет публично подтвержденных продвинутых power-curve/eFTP/rider-profile возможностей.
- Нет публичной социальной/coach marketplace/club функциональности.
- Продукт находится в активной web-миграции и выглядит менее коммерчески зрелым, чем запущенные SaaS-конкуренты.
- Текущий recovery replan намеренно предлагает keep или downgrade; полноценный перенос ключевой сессии ограничен.
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
