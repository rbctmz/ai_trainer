# Закрыть TD-005/D3: Garmin-синк на общей cursor-таблице (issue #355)

Живой документ по `.agent/PLANS.md`; самодостаточен.

## Purpose / Big Picture

Intervals уже работает через `sync_cursors` (`services/sync_cursor.run_windowed_sync`,
window from cursor, cursor-after-clean-batch), а Garmin-окно в
`services/sync.py::resolve_sync_window` строится по `get_latest_data_dates()`
(последние даты по таблицам) — две семантики окон. После D3 окно домена
активностей Garmin считается от общей cursor-таблицы (`provider="garmin",
domain="activities"`), курсор двигается только после чистого прогона, а
backward-compatible поведение (пересинк граничного дня, bootstrap 30 дней)
сохраняется.

## Progress

- [x] (2026-08-03) Аудит: `run_windowed_sync`/`resolve_window_from_cursor` для
      Intervals; Garmin-флоу в `services/sync.py` (resolve_sync_window → `_sync_activities`,
      без курсора).
- [x] (2026-08-03) RED: 6 гейтов (окно по курсору, bootstrap, full reload,
      fail-closed на битом курсоре, advance только при clean, цикл на реальной БД).
- [x] (2026-08-03) Реализация: cursor-ветка в `resolve_sync_window` +
      `_advance_garmin_activity_cursor` в Garmin-флоу.
- [x] (2026-08-03) Проверки: focused 6 passed, smoke 1453 passed, ruff/diff-check
      зелёные.

## Surprises & Discoveries

- Observation: `_sync_activities` намеренно продолжает работу при per-activity
  сбоях (M1-T3b), поэтому «чистый прогон» для advance = отсутствие фатальной
  ошибки fetch, а не отсутствие warnings.
  Evidence: `services/sync.py::_sync_activities` (warnings-контракт).

## Decision Log

- Decision: курсор Garmin-активностей — ключ `("garmin", "activities")`;
  инкрементальное окно = `resolve_window_from_cursor(cursor, overlap_days=1,
  bootstrap_days=DEFAULT_SYNC_DAYS)`; без курсора — текущий bootstrap (30 дней).
  Rationale: единая семантика с Intervals; overlap=1 повторяет сегодняшний
  пересинк граничного дня.
  Date/Author: 2026-08-03 / Codex.
- Decision: курсор двигается до конца окна после успешного прогона, когда нет
  фатальной ошибки fetch; per-activity warnings не блокируют (M1-T3b).
  Rationale: dirty-chunk семантика из ADR: ошибка получения данных → нет
  advance; обработанный (пусть с warnings) batch → advance.
  Date/Author: 2026-08-03 / Codex.
- Decision: явный `days` (full reload) и wellness-домены не меняются в этом срезе.
  Rationale: full reload — осознанное полное перечитывание; wellness остаётся
  на общем окне прогона (отдельная работа, если понадобятся свои курсоры).
  Date/Author: 2026-08-03 / Codex.

## Outcomes & Retrospective

Не завершено (в процессе).

## Context and Orientation

`services/sync.py::resolve_sync_window(database, days)` выбирает окно Garmin-синка:
explicit `days` → full reload; иначе `get_latest_data_dates()` (fallback 30 дней).
`data.database.py` даёт `get_sync_cursor(provider, domain)` /
`set_sync_cursor(provider, domain, date)` (монотонно). `services/sync_cursor.py`
даёт `resolve_window_from_cursor`. `services/sync.py` зовёт `_sync_activities`
(общий ingest) и затем wellness-загрузку.

## Plan of Work

1. `resolve_sync_window`: в incremental-ветке сначала пробовать курсор
   `("garmin", "activities")` (если у database есть `get_sync_cursor` и значение
   есть) → `resolve_window_from_cursor(..., overlap_days=1, bootstrap_days=30)`;
   иначе текущее поведение.
2. После успешного activity-фетча и `_sync_activities`: advance курсора до
   `end_date` через `database.set_sync_cursor("garmin", "activities", ...)`.
   При фатальной ошибке fetch — без advance.
3. Гейты в `tests/smoke/test_garmin_cursor_window.py`.

## Concrete Steps

    source ai_trainer_env/bin/activate
    python -m pytest tests/smoke/test_garmin_cursor_window.py \
      tests/smoke/test_sync_incremental.py -q
    python -m pytest tests/smoke -q
    git diff --check

## Validation and Acceptance

Окно Garmin совпадает с курсорным окном (start = cursor+1 с пересинком границы);
повторный чистый прогон двигает курсор монотонно; ошибка fetch не двигает;
без курсора поведение = прежний bootstrap; full reload (`days`) не меняется.
Полный smoke зелёный; CI ready-to-merge; после мержа #355 закрыт (D3 из TD-005).

## Idempotence and Recovery

Повторные прогоны идемпотентны (upsert + монотонный курсор). Откат = вернуть
старую ветку resolve_sync_window и убрать advance.
