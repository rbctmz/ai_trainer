# Диагностика расхождения FTP/порогов между источником и значениями, на которых построены тренировки

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md` at the repository root.

## Purpose / Big Picture

Тренировки строятся как проценты от FTP (функциональный порог мощности — число, показывающее, какую мощность спортсмен может держать около часа). Если FTP в источнике изменился (спортсмен перетестировался, обновил профиль в Intervals.icu), а приложение продолжает считать по старому числу, то все цели в тренировках неверные — слишком лёгкие или невыполнимые, и это выглядит как «тренировка не получилась», хотя виновато устаревшее число. IntervalCoach в чейнджлоге от 30 июля 2026 ввёл предупреждение при расхождении FTP больше 10% и объяснение в разборе тренировки: «targets themselves were off» (неверны сами цели, а не исполнение).

После этого изменения пользователь увидит в карточке профиля и в списке активностей предупреждение вида: «FTP источника 300 Вт, а тренировки/TSS считаются по 250 Вт (+20%) — проверьте синк профиля». Если расхождения нет — предупреждения нет.

Проверить работу можно так: `python -m pytest tests/smoke/test_threshold_drift.py -q` зелёный и в браузере на дашборде/активностях видна подсказка при искусственно созданном расхождении.

## Progress

- [x] (2026-08-06) Создан ExecPlan; прочитаны `data/athlete_profile_store.py`, `data/data_processor.py`, `api/routers/athlete_profile.py`, `services/intervals_icu.py`, `web/components/dashboard/AthleteProfileCard.tsx`, `web/app/activities/page.tsx`.
- [ ] Milestone 1: `models/threshold_drift.py::detect_threshold_drift` + юнит-тесты.
- [ ] Milestone 2: поле `warnings` в `/api/athlete-profile` + контрактные тесты.
- [ ] Milestone 3: web-подсказки в карточке профиля и на странице активностей + lint/build + браузер.

## Surprises & Discoveries

- Observation: у активностей уже хранится FTP, использованный при расчёте TSS (`tss_ftp_used`), и web уже показывает его рядом с источником TSS.
  Evidence: `data/data_processor.py` (поле `tss_ftp_used` в результатах `resolve_tss`), `web/app/activities/page.tsx` («FTP N»).
- Observation: профиль атлета уже хранит `source` и `synced_at`, так что можно отличить «синхронизировано из Intervals.icu» от «fallback из .env».
  Evidence: `data/athlete_profile_store.py` (колонки `source`, `synced_at`), `api/routers/athlete_profile.py` (отдаёт их наружу).

## Decision Log

- Decision: порог предупреждения — 10% (как у IntervalCoach); при меньшем расхождении молчим.
  Rationale: меньше 10% — в пределах нормального шума между тестами; лишние предупреждения обесценивают сигнал.
  Date/Author: 2026-08-06 / Codex.
- Decision: сравниваем FTP профиля (последний синк) с `tss_ftp_used` последней активности не старше 30 дней; если активностей нет или профиля нет — предупреждений нет.
  Rationale: это честное сравнение «что показывает источник» против «чем реально считали»; старые активности могли быть посчитаны до обновления профиля и не показательны.
  Date/Author: 2026-08-06 / Codex.

## Outcomes & Retrospective

Заполняется по завершении плана.

## Context and Orientation

FTP — функциональный порог мощности (ватты); LTHR — лактатный порог пульса. Оба числа приходят из профиля атлета: при подключённом Intervals.icu профиль синхронизируется функцией `services/intervals_icu.py::sync_athlete_profile` в таблицу `athlete_profile` (см. `data/athlete_profile_store.py`); без интеграции используется статический fallback `config/settings.py::USER_FTP`/`USER_LTHR`. Выбор FTP для математики TSS делает `data/data_processor.py::resolve_athlete_tss_profile` (профиль при наличии, иначе fallback). При расчёте TSS активности в её строке сохраняется `tss_ftp_used` — то самое число, которым реально считали.

Публичная поверхность: `api/routers/athlete_profile.py` (GET `/api/athlete-profile` — отдаёт `profile` с `ftp`, `lthr`, `source`, `synced_at`), `web/components/dashboard/AthleteProfileCard.tsx` (карточка «Профиль» на дашборде, показывает FTP), `web/app/activities/page.tsx` (список активностей, показывает «FTP N» у источника TSS).

## Plan of Work

### Milestone 1: детектор расхождения

Создайте `models/threshold_drift.py` с чистой функцией `detect_threshold_drift(database) -> list[dict]`. Логика:

- прочитайте профиль через `database.get_athlete_profile()`; если профиля нет — верните `[]`;
- найдите последнюю активность с непустым `tss_ftp_used` не старше 30 дней (`database.get_activities_between` с сегодня−30 по сегодня); если такой нет — верните `[]`;
- посчитайте расхождение в процентах от меньшего числа: `abs(source - used) / min(source, used) * 100`; если ≥ 10 — добавьте warning `{"kind": "ftp_drift", "source_value": ftp профиля, "used_value": tss_ftp_used, "pct": ..., "message": "FTP источника N Вт, а TSS считались по M Вт (+P%) — проверьте синк профиля"}`;
- для LTHR аналогично, если в активностях есть поле использованного LTHR (если такого поля нет — ограничьтесь FTP и запишите это в `Surprises & Discoveries`).

Юнит-тесты в новом `tests/smoke/test_threshold_drift.py`: seed профиль ftp=250 и активность с `tss_ftp_used=300` → один warning с pct ≥ 10; `tss_ftp_used=260` → пусто; пустая БД → пусто.

### Milestone 2: API

В `api/routers/athlete_profile.py` добавьте в ответ аддитивное поле `warnings` (результат `detect_threshold_drift(db)`). Существующий контракт (`has_data`, `profile`, `operational_state`) не меняйте. Контрактные тесты: ответ содержит `warnings` как список; seeded расхождение даёт непустой список; без расхождения — пустой.

### Milestone 3: web-подсказки

В `web/components/dashboard/AthleteProfileCard.tsx` под значениями FTP выведите предупреждение из `warnings` (жёлтый блок, текст `message` из warning). В `web/app/activities/page.tsx` рядом со строкой «FTP N» добавьте подсказку, если текущий профиль (из `/api/athlete-profile`) расходится с `tss_ftp_used` активности больше чем на 10% — текст: «FTP профиля сейчас N Вт, эта активность посчитана по M Вт». Если `warnings` пуст — ничего не показывать.

Проверка: `npm --prefix web run lint`, `npm --prefix web run build`; в браузере при seed-расхождении видна подсказка, без расхождения — нет.

## Validation

Команды, которые должны быть зелёными:

    python -m pytest tests/smoke/test_threshold_drift.py -q
    python -m pytest tests/smoke -q
    python -m ruff check models/threshold_drift.py api/routers/athlete_profile.py tests/smoke/test_threshold_drift.py
    npm --prefix web run lint
    npm --prefix web run build

Браузерная проверка: `./run_web.sh`, открыть дашборд и страницу активностей; при расхождении FTP видна подсказка, при отсутствии расхождения — нет.
