# Foster load (sRPE × минуты = AU) как вторая валюта нагрузки (#381)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md` at the repository root.

## Purpose / Big Picture

TSS хорош для видов с мощностью (вело), но для бега по пульсу, плавания и зала у нас нет независимой валюты нагрузки. Foster load решает это: `AU = sRPE × длительность(мин)`, где sRPE (0–10) атлет уже ставит после тренировки в существующем фидбеке (`session_feedback.session_rpe_1_10`). После этого изменения AU появляется в карточке завершённой тренировки и в авто-разборе рядом с TSS — без новых полей ввода: только расчёт и отображение.

Проверить работу можно так: `python -m pytest tests/smoke/test_activity_card.py -q` зелёный; в карточке активности с фидбеком RPE 8 и длительностью 60 мин видно «Нагрузка: 480 AU (RPE 8 × 60 мин)».

## Progress

- [x] (2026-08-06) Создан ExecPlan; прочитаны `models/activity_card.py`, `api/routers/activities.py`, `web/app/activities/page.tsx`.
- [x] (2026-08-06) Milestone 1: `foster_load_au` в `models/activity_card.py` + поле `foster_load` в feedback карточки (list + detail) + строка в `build_activity_analysis`.
- [x] (2026-08-06) Milestone 2: web-отображение AU в модалке карточки («нагрузка N AU»).
- [x] (2026-08-06) Milestone 3: тесты 9 passed, полный smoke 1507 passed / 0 failed, ruff/ESLint/build зелёные; PR с `Closes #381`.

## Surprises & Discoveries

- Observation: RPE у нас 1–10 (не 0–10), что полностью совместимо с формулой Фостера; отдельного ввода не требуется — фидбек уже хранит `session_rpe_1_10` и `actual_activity_ids`.
  Evidence: `api/routers/session_feedback.py` (`FeedbackValues.session_rpe_1_10`), `data/database.py` (schema `session_feedback`).

## Decision Log

- Decision: AU считаем как `round(sRPE × duration_minutes)` по завершённой активности (длительность из карточки, не из плана).
  Rationale: Формула Фостера использует фактическую длительность сессии; план мог отличаться от факта.
  Date/Author: 2026-08-06 / Codex.
- Decision: AU — производное поле, хранится только в ответе API/разборе, в БД не пишется.
  Rationale: легко пересчитать; не плодим второй источник истины.
  Date/Author: 2026-08-06 / Codex.

## Outcomes & Retrospective

2026-08-06: #381 реализован. `AU = round(sRPE × duration_minutes)` считается чистой функцией `foster_load_au`, попадает в feedback карточки (`foster_load`) и в авто-разбор («Нагрузка по Фостеру: 480 AU (RPE 8 × 60 мин)»). Работает и для видов без мощности (тест: swim без power, RPE 6 × 30 = 180 AU). В БД ничего не пишется — производное поле. Открыт PR с `Closes #381`.

## Context and Orientation

Карточка тренировки (#379): `models/activity_card.py` содержит чистые функции (grade-маппинг, `feedback_for_activity`, `build_activity_analysis`); `api/routers/activities.py` обогащает активности фидбеком/тегами/заметками; web-модалка — `web/app/activities/page.tsx` (блок «Оценка тренировки»). Фидбек: `session_feedback` с `session_rpe_1_10` (1–10) и `actual_activity_ids`.

## Plan of Work

### Milestone 1: бэкенд

В `models/activity_card.py` добавить `foster_load_au(rpe, duration_minutes) -> int | None` (`round(rpe × duration)`; `None` если RPE или длительности нет). В `api/routers/activities.py` при обогащении карточки (`list_activities` и `get_activity_card`) после `feedback_for_activity` добавить `feedback["foster_load"] = foster_load_au(...)`. В `build_activity_analysis` при наличии RPE добавить строку `- Нагрузка по Фостеру: {au} AU (RPE {rpe} × {duration} мин)`.

### Milestone 2: web

В `web/app/activities/page.tsx` в блоке «Оценка тренировки» рядом с RPE показать `Нагрузка: {foster_load} AU`, если поле есть. В `web/lib/types.ts` — `foster_load?: number | null` в `ActivityFeedback`.

### Milestone 3: тесты и проверки

Расширить `tests/smoke/test_activity_card.py`: юнит `foster_load_au` (RPE 8 × 30 = 240; без RPE/длительности → None); API — фидбек RPE 8, длительность 60 → `item["feedback"]["foster_load"] == 480` и разбор содержит «480 AU»; non-power случай (swim без мощности) — AU считается. Команды: фокусные тесты, полный smoke, ruff, `npm --prefix web run lint`/`build`.

## Validation

Команды, которые должны быть зелёными:

    python -m pytest tests/smoke/test_activity_card.py -q
    python -m pytest tests/smoke -q
    python -m ruff check models/activity_card.py api/routers/activities.py tests/smoke/test_activity_card.py
    npm --prefix web run lint
    npm --prefix web run build
