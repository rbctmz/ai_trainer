# Карточка завершённой тренировки: фидбек, grade, теги, разбор (шаг 1 из #379)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md` at the repository root.

## Purpose / Big Picture

После тренировки атлету нужна карточка завершённой активности, где собрано всё, что о ней известно: как тяжело было (RPE), насколько по плану (качество/grade), теги, которые сам атлет вешает на тренировку, и текстовый разбор. Сейчас в списке активностей видно только числа (TSS, длительность, FTP-провенанс), а пост-тренировочный фидбек живёт отдельно на экране «Сегодня» и не связан с карточкой.

После этого изменения атлет может открыть любую завершённую тренировку из `/activities`, увидеть бейдж grade (A–E) и RPE из существующего фидбека, добавить/убрать теги, посмотреть и сохранить разбор («Разобрать» генерирует детерминированный Markdown-текст из реальных чисел) и отредактировать заметку. Это первый шаг предложения #379; шаги 2–4 (Foster load, авто-детект интервалов, личные рекорды) вынесены в бэклог отдельными issues.

Проверить работу можно так: `python -m pytest tests/smoke/test_activity_card.py -q` зелёный, а в браузере на `/activities` клик по строке открывает карточку с фидбеком, тегами и разбором.

## Progress

- [x] (2026-08-06) Создан ExecPlan; прочитаны `api/routers/activities.py`, `data/database.py` (schema session_feedback), `api/session_feedback.py`, `web/app/activities/page.tsx`, `web/lib/types.ts`.
- [x] (2026-08-06) Milestone 1: таблицы `activity_tags`/`activity_coach_notes` + методы БД + `models/activity_card.py` (grade-маппинг, поиск фидбека по `actual_activity_ids`, детерминированный разбор).
- [x] (2026-08-06) Milestone 2: API — поля `feedback`/`tags`/`coach_notes` в списке, endpoints tags/coach-notes/analyze + 5 контрактных тестов.
- [x] (2026-08-06) Milestone 3: web-карточка в `/activities` (клик по строке): фидбек + grade-бейдж, теги, разбор, редактирование заметки; ESLint и build зелёные.
- [x] (2026-08-06) Бэклог: issues для Foster AU, авто-детекта интервалов, best efforts; комментарий в #379.

## Surprises & Discoveries

- Observation: пост-тренировочный фидбек уже хранит `actual_activity_ids_json` — по нему можно найти фидбек для конкретной активности без новой связи.
  Evidence: `data/database.py` (schema `session_feedback`, колонка `actual_activity_ids_json`), `get_latest_session_feedbacks()`.
- Observation: качество исполнения уже зафиксировано шкалой 1–5 (1–2 провал, 3 неоднозначно, 4–5 успех); A–E — это UI-маппинг, а не новая сущность.
  Evidence: `docs/session_quality_forecast_execplan.md`, `models/session_quality_forecast.py::brier_score`.

## Decision Log

- Decision: sRPE/grade не добавляем колонками в `activities` — читаем из `session_feedback` по `actual_activity_ids`; grade — производный бейдж от `quality_rating_1_5`.
  Rationale: не плодить второй источник истины; фидбек уже append-only с провенансом.
  Date/Author: 2026-08-06 / Codex.
- Decision: «Разбор» — детерминированный Markdown из реальных данных, без LLM.
  Rationale: работает офлайн, тестируется смоук-тестами без сети и не противоречит принципу «никаких выдуманных утверждений»; LLM-разбор остаётся за Coach+.
  Date/Author: 2026-08-06 / Codex.
- Decision: теги и заметка — отдельные маленькие таблицы, а не колонки `activities`.
  Rationale: таблица активностей остаётся нетронутой (миграции дешевле), а теги — многие-ко-многим.
  Date/Author: 2026-08-06 / Codex.

## Outcomes & Retrospective

2026-08-06: шаг 1 из #379 реализован. Карточка завершённой тренировки на `/activities` показывает существующий фидбек (RPE + качество + grade-бейдж), теги (новая таблица, add/remove), заметку и детерминированный разбор («Разобрать»). sRPE/grade не продублированы колонками в `activities` — источник истины остаётся `session_feedback`. Полный smoke: 1500 passed, 0 failed; ruff/ESLint/build зелёные. Открыт PR с `Closes #379`.

## Context and Orientation

Активности лежат в SQLite-таблице `activities` (см. `data/database.py`, `_ACTIVITY_COLUMN_ORDER`); список отдаёт `api/routers/activities.py::list_activities`. Пост-тренировочный фидбек живёт в `session_feedback` (RPE 1–10, качество 1–5, `actual_activity_ids`), его читает `Database.get_latest_session_feedbacks()`. Web-список — `web/app/activities/page.tsx` (таблица), типы — `web/lib/types.ts` (`Activity`, `ActivitiesResponse`).

Grade-маппинг: 5→A, 4→B, 3→C, 2→D, 1→E. Разбор — Markdown-текст на русском: длительность, дистанция, TSS (с источником), средний/макс пульс, RPE, качество/grade, готовность на дату (если есть).

## Plan of Work

### Milestone 1: БД и чистая модель

В `data/database.py` добавить таблицы `activity_tags (activity_id, tag, PRIMARY KEY(activity_id, tag))` и `activity_coach_notes (activity_id PRIMARY KEY, body, source, updated_at)`; методы `get_activity_tags`, `add_activity_tag`, `remove_activity_tag`, `get_all_activity_tags() -> dict[str, list[str]]`, `get_activity_coach_notes`, `save_activity_coach_notes`, `get_all_activity_coach_notes() -> dict[str, str]`, `get_activity(activity_id)`. Создать `models/activity_card.py`: `grade_from_quality(q)`, `feedback_for_activity(activity_id, latest_feedbacks)`, `build_activity_analysis(activity, feedback, readiness) -> str` (детерминированный Markdown).

### Milestone 2: API и тесты

В `api/routers/activities.py` в items списка добавить `feedback` (rpe/quality/grade), `tags`, `coach_notes`. Добавить endpoints: `GET /{activity_id}` (детальная карточка), `POST /{activity_id}/tags` (тело `{"tag": str}`), `DELETE /{activity_id}/tags/{tag}`, `PUT /{activity_id}/coach-notes` (тело `{"body": str, "source": str}`), `POST /{activity_id}/analyze` (генерирует и сохраняет разбор). Тесты `tests/smoke/test_activity_card.py`: маппинг grade, поиск фидбека по активности, разбор содержит ключевые числа, контракты endpoints, пустые состояния.

### Milestone 3: web

В `web/lib/types.ts` расширить `Activity` (feedback/tags/coach_notes) и добавить типы запросов. В `web/app/activities/page.tsx` сделать строки кликабельными, открывающими модалку: блок фидбека с бейджем grade, чипы тегов с добавлением/удалением, текстовое поле заметки, кнопка «Разобрать» (POST analyze) и сохранение заметки (PUT). Проверка: `npm --prefix web run lint`, `npm --prefix web run build`.

## Validation

Команды, которые должны быть зелёными:

    python -m pytest tests/smoke/test_activity_card.py -q
    python -m pytest tests/smoke -q
    python -m ruff check models/activity_card.py api/routers/activities.py data/database.py tests/smoke/test_activity_card.py
    npm --prefix web run lint
    npm --prefix web run build

Браузерная проверка: `./run_web.sh`, открыть `/activities`, кликнуть по активности — виден grade/RPE, теги добавляются/удаляются, «Разобрать» пишет разбор, заметка сохраняется.
