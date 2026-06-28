# Заметки проекта Codex — AI Trainer

## Обзор

- **Назначение**: тренировочный кокпит для аналитики Garmin-данных, планирования и AI-коучинга.
- **Текущее состояние**: активная миграция со Streamlit на FastAPI + Next.js.
- **Рабочее правило**: новые продуктовые изменения идут по web-first траектории, но Streamlit остаётся поддерживаемым fallback-контуром до закрытия parity.

## Архитектура во время выполнения

- `web/`: основное направление UI во время миграции. Здесь уже есть dashboard, coach, planning, HRV и activities.
- `api/`: контрактный слой FastAPI для web-фронта. Новые product-flow должны проходить через этот boundary, а не через Streamlit state.
- `app.py`: legacy Streamlit shell. Всё ещё нужен как fallback, acceptance, admin/diagnostic surface и для поведения, которое ещё не доведено до web parity.
- `config/settings.py`: единый источник конфигурации из окружения.
- `services/`: UI-агностичная оркестрация Garmin auth/sync, demo mode, acceptance mode, refresh данных и внешних интеграций.
- `data/`: обёртки Garmin API, ETL и помощники SQLite persistence.
- `models/`: AI providers, coaching runtime, planning logic, Banister/HRV analytics, export helpers и builders структурированного контекста.
- `state/`: Streamlit-oriented state helpers; не использовать `st.session_state` как контракт для новых product-flow.
- `ui/`: legacy Streamlit pages/components. Их стоит поддерживать, ужимать или извлекать из них reusable logic, но не растить как основной product surface.
- `utils/`: общие метрики, визуализации, sleep analytics и Streamlit/theme helpers.

## Поток данных

1. Garmin- и provider-credentials читаются из `.env` через `config/settings.py`.
2. Общая Python-логика в `services/`, `data/` и `models/` загружает и вычисляет activity, HRV, planning и AI context.
3. `api/` публикует это поведение через явные HTTP-контракты для `web/`.
4. `web/` рендерит основной migrated product flow.
5. Streamlit всё ещё использует те же backend/domain-модули для fallback и acceptance-сценариев.

## Политика продуктовых поверхностей

- Для новых product-facing задач предпочитай `api/` + `web/`.
- Держи доменные правила в Python, а не в ad hoc frontend-only логике.
- Изменения в Streamlit допустимы для bugfix, acceptance/admin tooling, compatibility bridges или извлечения reusable logic.
- Не поставляй новые product-фичи только в `ui/pages/*`, если задача не помечена как legacy-only.

## Тестирование и инструменты

- Базовая contributor-safe команда: `python -m pytest tests/smoke -q`
- Более широкий локальный прогон: `python -m pytest -m "not live and not debug" tests/`
- Web/API runtime: `./run_web.sh`
- Legacy Streamlit runtime: `./run.sh`
- Acceptance runtime: `ACCEPTANCE_PORT=8510 ./run_acceptance.sh`

## Опорные документы

- `docs/architecture/adr_0001_web_primary_ui.md`: политика миграции и граница ответственности
- `docs/AI_Feature_Development_Workflow.md`: workflow SpecDD/BDD/TDD/Contract First
- `docs/SPEC_WEB_MIGRATION.md`: scope, фазы и контракты миграции

## Открытые дальнейшие задачи

1. Закрыть parity для сценариев, которые ещё зависят от Streamlit-only UI.
2. Продолжать вынос reusable logic из legacy UI в shared headless модули.
3. Не допускать расхождения между API contracts и предположениями web/frontend.
4. В live Garmin acceptance явно отмечать, что именно проверено: web, Streamlit fallback или оба пути.

## Быстрая справка

- Предпочтительное направление новых product changes: `api/` + `web/`
- Legacy fallback: `streamlit run app.py` или `./run.sh`
- Shared backend/domain source of truth: `services/`, `models/`, `data/`
- Политика миграции: `docs/architecture/adr_0001_web_primary_ui.md`
