# Recovery-proposal: показывать «было → станет» (TSS и длительность) и гарантировать, что замена не тяжелее оригинала

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md` at the repository root.

## Purpose / Big Picture

Когда система замечает, что спортсмен недовосстановлен перед тяжёлой тренировкой, она предлагает заменить эту тренировку более лёгкой. Сейчас пользователь видит перед подтверждением только «Снижение нагрузки · 25 TSS» — без длительности и без сравнения с тем, что было запланировано. После этого изменения пользователь увидит точное «было → станет»: «Было: Качество • вело, 60 TSS, 60 мин → Станет: Восстановительная, 25 TSS, 35 мин (Δ TSS −35, Δ времени −25 мин)». Дополнительно закрепляется гарантия: предложенная замена никогда не тяжелее оригинала по тренировочной нагрузке (TSS); по усталости и часам восстановления такая гарантия уже есть, по TSS явной проверки пока нет.

Проверить работу можно так: запустить `python -m pytest tests/smoke/test_recovery_replan_loop.py -q` (тесты на новые поля и guard) и открыть страницу `/decisions` в web, где виден pending recovery-proposal с числами «было → станет».

Этот пункт взят из разбора чейнджлога IntervalCoach (записи от 5 и 8 июля 2026: proposal показывает «Duration: 90 min (+15 vs planned) · Load: ~85 TSS (vs ~95 planned)», и облегчённая сессия всегда легче заменяемой). Полный разбор — `docs/competitive_analysis_intervalcoach.md`, дополнение 2026-08-06.

## Progress

- [x] (2026-08-06) Создан ExecPlan; прочитаны `models/planning_near_term.py`, `models/recovery_replan.py`, `api/recovery_replan_loop.py`, `web/app/decisions/page.tsx`, `tests/smoke/test_recovery_replan_loop.py`.
- [ ] Milestone 1: поля длительности в `current_session`/`recommended_session` + TSS-guard + тесты.
- [ ] Milestone 2: дельты длительности в `summarize_near_term_draft_rows` и в proposal payload + контрактные тесты.
- [ ] Milestone 3: web-отображение «было → станет» в `/decisions` + lint/build + браузерная проверка.

## Surprises & Discoveries

- Observation: draft-строки near-term редактора уже несут длительность (`duration_minutes`) и текущую/целевую TSS, но `build_recovery_replan_variant` и `_proposal_payload` эти поля выбрасывают.
  Evidence: `models/planning_near_term.py` (строки сборки draft содержат `duration_minutes`, `total_tss`, `current_total_tss`), `models/recovery_replan.py` (`current_session`/`recommended_session` содержат только `tss` и `delta_tss`).
- Observation: у downgrade-варианта `weekly_duration_delta_minutes` в proposal payload всегда `None`, хотя суммарный дельт-счёт по TSS уже есть (`total_delta_tss`).
  Evidence: `api/recovery_replan_loop.py::_proposal_payload` (`"weekly_duration_delta_minutes": None` в ветке downgrade).
- Observation: `_profile_is_nonincreasing` гарантирует только `fatigue_cost` и `expected_recovery_hours`, но не TSS; на практике `_recommendation` возвращает долю от текущей TSS (0.40/0.50/0.60), поэтому TSS-guard — это фиксация существующего поведения тестом, а не новое ограничение.
  Evidence: `models/recovery_replan.py::_recommendation` и `_profile_is_nonincreasing`.

## Decision Log

- Decision: ограничение «не тяжелее» трактуем по TSS и усталости, а не по длительности: длительность может вырасти («длиннее, но легче» — осознанный сценарий).
  Rationale: IntervalCoach прямо описывает longer-but-easier как намеренный результат; ограничение по времени сломало бы этот сценарий.
  Date/Author: 2026-08-06 / Codex.
- Decision: новые поля добавляем аддитивно; существующие ключи (`tss`, `delta_tss`, `options`, `safety_guard`) не переименовываем.
  Rationale: proposal-контракт уже используется web и тестами; смена имён без необходимости = риск регрессий.
  Date/Author: 2026-08-06 / Codex.

## Outcomes & Retrospective

Заполняется по завершении плана.

## Context and Orientation

Поток, который нужно понять: `api/readiness_conflicts.py::build_readiness_conflict_report` находит конфликт «низкая готовность × тяжёлая плановая сессия» (это называется salience-gate: детектор значимости, который молчит, когда всё в порядке). Далее `models/recovery_replan.py::build_recovery_replan_variant` строит один безопасный вариант замены (это называется variant — «вариант»). `api/recovery_replan_loop.py::run_recovery_replan_loop` превращает вариант в proposal — предложение, которое пользователь подтверждает или отклоняет; предложение сохраняется в БД и показывается на `web/app/decisions/page.tsx` (страница «Решения»). Checkpoint — сохранённая версия плана до изменения; после подтверждения пишется новый checkpoint, откат возвращает старый.

TSS — тренировочная нагрузка в баллах (чем больше, тем тяжелее сессия). Draft rows — строки-черновики ближайших дней, которые умеет редактировать `models/planning_near_term.py`; каждая строка знает день, роль (`recovery`/`easy`/`quality`), спорт, TSS и длительность. Ключевые файлы:

- `models/planning_near_term.py` — редактор ближайших дней; `build_near_term_edit_rows`, `build_near_term_edit_draft_rows`, `apply_near_term_day_edits`, `summarize_near_term_draft_rows`.
- `models/recovery_replan.py` — `build_recovery_replan_variant` (строит `current_session`, `recommended_session`, `options`, `safety_guard`), `assert_recovery_replan_safety`, `_profile_is_nonincreasing`.
- `api/recovery_replan_loop.py` — `_proposal_payload` (формирует `params` и `preview` proposal).
- `web/app/decisions/page.tsx` — рендер proposal; `recoverySummary` строится из `proposal.preview?.recommended_session` (сейчас только `name` и `tss`).
- `tests/smoke/test_recovery_replan_loop.py` — контрактные тесты variant/proposal; там уже есть assertion на `recommended_session["tss"]` и `delta_tss`.

## Plan of Work

### Milestone 1: поля длительности в variant + TSS-guard

Прочитайте `models/planning_near_term.py::build_near_term_edit_draft_rows` и `build_near_term_edit_rows` и выясните точные имена ключей для длительности (ожидается `duration_minutes` и, для текущего значения, ключ вида `current_duration_minutes`; если такого нет, берите длительность из шаблона дня, как это делает сам редактор через `_estimate_session_duration_minutes` из `models/training_planner.py`). Запишите найденные ключи в `Surprises & Discoveries`.

В `models/recovery_replan.py::build_recovery_replan_variant`:

- в `current_session` добавьте `duration_minutes` (текущая длительность целевого дня из `target_row`; fallback — `_estimate_session_duration_minutes(current_tss, current_sport, current_role)`);
- в `recommended_session` добавьте `duration_minutes` (из `recommended_row`) и `delta_duration_minutes = duration_minutes - current_duration_minutes`;
- после сборки `recommended_session` добавьте guard: если `recommended_session["tss"] > current_session["tss"]`, поднимите `ValueError("recovery downgrade raised TSS above the original")` — это fail-closed (замена не материализуется);
- в `safety_guard` (если он уже есть — проверьте, как его потребляет `api/recovery_replan_loop.py`) добавьте `planned_tss`, `proposed_tss`, `planned_duration_minutes`, `proposed_duration_minutes`.

Тесты в `tests/smoke/test_recovery_replan_loop.py` (расширьте существующие, не удаляя их): assert, что у `current_session` и `recommended_session` есть числовые `duration_minutes` и корректный `delta_duration_minutes`; assert, что `recommended_session["tss"] <= current_session["tss"]`; добавьте негативный тест, который monkeypatch-ит `models.recovery_replan._recommendation`, чтобы она вернула TSS больше текущей, и проверяет `ValueError`.

### Milestone 2: дельты длительности в summary и payload

В `models/planning_near_term.py::summarize_near_term_draft_rows` добавьте `total_delta_duration_minutes` (сумма по изменённым строкам разности целевой и текущей длительности) и в `changed_rows` добавьте колонку «Δ мин». Если в строке нет ключа текущей длительности, считайте текущую длительность как `_estimate_session_duration_minutes(current_total_tss, sport, role)`.

В `api/recovery_replan_loop.py::_proposal_payload`:

- в `preview["current_session"]` и `preview["recommended_session"]` пробросьте `duration_minutes` и `delta_duration_minutes` из variant (они уже появятся после Milestone 1);
- для downgrade-варианта установите `weekly_duration_delta_minutes` из `variant["draft_summary"]["total_delta_duration_minutes"]` (fallback `None`, если ключа нет).

Контрактные тесты: запустите существующий `run_recovery_replan_loop` на seeded БД (паттерн уже есть в `tests/smoke/test_recovery_replan_loop.py`) и проверьте, что `proposal["preview"]["recommended_session"]["duration_minutes"]` — число, `delta_duration_minutes` корректна, и `weekly_duration_delta_minutes` не `None` для downgrade.

### Milestone 3: web-отображение

В `web/app/decisions/page.tsx` в ветке `selectedRecoveryKind === "downgrade_today"` строка `recoverySummary` должна стать вида: `«{recommended.name} · {recommended.tss} TSS · {recommended.duration_minutes} мин (было {current.tss} TSS · {current.duration_minutes} мин)»`, где `current` — `proposal.preview?.current_session`. Если полей нет — оставить старое поведение (fallback на `name · tss TSS`), чтобы старые proposal без полей не ломали рендер.

Проверка: `npm --prefix web run lint` и `npm --prefix web run build` зелёные; в браузере на `/decisions` с pending recovery-proposal видна строка с обоими числами.

## Validation

Команды, которые должны быть зелёными:

    python -m pytest tests/smoke/test_recovery_replan_loop.py tests/smoke/test_recovery_transfer.py -q
    python -m pytest tests/smoke -q
    python -m ruff check models/recovery_replan.py models/planning_near_term.py api/recovery_replan_loop.py tests/smoke/test_recovery_replan_loop.py
    npm --prefix web run lint
    npm --prefix web run build

Браузерная проверка (если есть рабочая БД с pending proposal; иначе достаточно тестов): запустите `./run_web.sh`, откройте `http://localhost:3000/decisions` и убедитесь, что recovery-proposal показывает «было → станет» с TSS и длительностью.
