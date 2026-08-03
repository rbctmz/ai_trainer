# M4b: Demand control на активном плане — spec (черновик для утверждения)

Это черновик спеки для среза M4b issue [#304](https://github.com/rbctmz/ai_trainer/issues/304) — «Demand control показывает ожидаемый эффект до применения и использует существующий preview → confirm; изменение не должно незаметно переписывать checkpoint». Документ живёт по правилам `.agent/PLANS.md` и `docs/AI_Feature_Development_Workflow.md`; реализация начнётся только после утверждения.

## Purpose / Big Picture

Сейчас активный план показывает сохранённый расчёт недельной нагрузки (M4a), но у атлета нет способа поменять режим нагрузки (Легко / Умеренно / Требовательно / Агрессивно) на уже сохранённом плане с понятным эффектом до применения. После M4b атлет на вкладке «Обзор» выбирает новый уровень, видит новый итог недельной цели и delta TSS до подтверждения, затем явно применяет изменение — и только тогда появляется новый checkpoint с родителем прежнего. Отмена или невыбор ничего не меняют.

Главный инвариант среза: preview никогда не пишет, confirm пишет только при явном действии и защищён от устаревшего checkpoint (stale guard).

## Что уже есть (факты из кода)

- `GET /api/planning/overview` возвращает `weekly_target_explanation` — сохранённую разбивку недельной цели (M4a): `goal_need_tss`, `availability_cap_tss`, `recent_load_tss`, `base_weekly_tss`, `final_target_weekly_tss`, `demand {level, label, multiplier}`.
- В checkpoint сохраняются все входы плана: `goal_type`, `distance`, `planning_mode`, `planning_intent`, `planning_focus`, `events`, `horizon_weeks`, `start_week`, `phases`, `constraint_summary` (в т.ч. `available_hours`, `available_days`), `demand_level`, `demand_multiplier`, `weekly_target_breakdown` (`models/planning_checkpoints.py`, `build_planning_checkpoint`).
- Существующий pipeline сборки `build_plan` (`api/planning_service.py:931`) уже реализует preview → confirm: `persist=False` строит без записи, `persist=True` требует `confirm=True` и сверяет `base_checkpoint_id` (stale → `StalePlanningCheckpointError` → 409). `build_plan` также сохраняет уровень спроса в `user_settings` при `demand is not None and persist`.
- Паттерн stale-защиты с fingerprint уже используется в rebalance: `preview_fingerprint` сверяется при confirm (`api/planning_service.py:2034`).
- В `web/app/planning/page.tsx` режим нагрузки существует только в BuildMode (локальный state + `GET /api/planning/target-preview`); на Overview его нет. `POST /api/planning/demand` существует, но web-клиент его не вызывает.

## Scope (in scope)

1. **Demand control на Overview**: компактный выбор режима нагрузки рядом с блоком «Как рассчитана недельная нагрузка». Текущий сохранённый уровень подсвечен.
2. **Preview до применения**: при выборе уровня сервер (не браузер) считает новый итог недельной цели по сохранённым входам checkpoint + новому спросу и возвращает:
   - новый `final_target_weekly_tss` и `delta_weekly_tss` относительно текущего;
   - строки разбивки с новым multiplier;
   - явный признак, если итог упирается в потолок доступности (`capped`);
   - `base_checkpoint_id` и `preview_fingerprint`.
   Никакой записи при preview.
3. **Confirm**: явная кнопка «Применить и пересобрать» создаёт новый checkpoint через существующий pipeline сборки с теми же входами плана и новым спросом, с provenance `demand_change` (label «Изменение режима нагрузки») и `checkpoint_parent_id` = текущий checkpoint. Уровень спроса сохраняется в `user_settings`, чтобы `status.demand` совпадал с активным планом.
4. **Cancel / no-op**: без confirm активный checkpoint не меняется; при том же уровне confirm запрещён (no-change).
5. **Stale guard**: при изменении активного checkpoint между preview и confirm — 409, ничего не перезаписывается.
6. **Data gap**: нет плана / нет `weekly_target_breakdown` / нет `available_hours` → preview возвращает явный `data_gap`, confirm не создаёт checkpoint.

## Non-goals

- Дневные лимиты доступности и конфликты «день vs план» — остаются data gap (контракта нет, M4a это зафиксировал).
- Stepper/drawer «Изменить план» — это M4c.
- Intervals.icu delivery, формулы нагрузки, reconciliation, Streamlit.
- Изменение whitelist'ов профиля и онбординга.

## Contract First — API

Аддитивные endpoints, сервер сам берёт входы из активного checkpoint:

### `GET /api/planning/demand-preview?level=demanding`

Read-only. Ответ:

```json
{
  "has_plan": true,
  "state": "available",
  "current": { "level": "moderate", "label": "Умеренно", "multiplier": 1.0,
               "final_target_weekly_tss": 420 },
  "preview": { "level": "demanding", "label": "Требовательно", "multiplier": 1.1,
               "final_target_weekly_tss": 420, "delta_weekly_tss": 0,
               "capped": true, "rows": [ ... ], "availability_cap_tss": 420 },
  "base_checkpoint_id": 7,
  "preview_fingerprint": "sha256-..."
}
```

Без плана или без разбивки: `{"has_plan": false, "state": "data_gap", "reason": "..."}` — без синтетических значений.

### `POST /api/planning/demand/confirm`

Body: `{ "level": "demanding", "base_checkpoint_id": 7, "preview_fingerprint": "sha256-..." }`.

- неизвестный level → 422;
- тот же уровень, что в активном checkpoint → 422 `no change`;
- checkpoint сменился (id или fingerprint не совпадают) → 409 `StalePlanningCheckpointError`-сообщение;
- успех → `{ "applied_checkpoint_id": 8, "base_checkpoint_id": 7, "checkpoint_source": "demand_change", "weekly_target": { ... } }`.

## BDD / acceptance

- Given активный план с сохранённой разбивкой недельной цели, When атлет выбирает новый уровень нагрузки, Then preview показывает новый итог, delta TSS и обновлённые строки разбивки; активный checkpoint не изменён (id и snapshot прежние).
- Given показан preview, When атлет нажимает «Применить», Then создаётся новый checkpoint c `checkpoint_source == "demand_change"` и `checkpoint_parent_id == base_checkpoint_id`; overview и `weekly_target_explanation` показывают новый demand; история показывает «Изменение режима нагрузки»; `status.demand.level` совпадает с новым уровнем.
- Given показан preview, When активный checkpoint изменился до confirm, Then confirm возвращает 409 и не создаёт/не перезаписывает checkpoint.
- Given показан preview, When атлет отменяет/не подтверждает, Then активный checkpoint не меняется.
- Given выбран тот же уровень, что в checkpoint, Then preview показывает `delta_weekly_tss == 0`, confirm отклоняется (422), checkpoint не пишется.
- Given новый итог упирается в потолок доступности, Then preview честно показывает `capped: true` и итог = потолку.
- Given нет плана или в checkpoint нет разбивки, Then demand-preview возвращает `data_gap`, confirm не создаёт checkpoint.
- Contract/component gates, smoke (`python -m pytest tests/smoke -q`), `npm --prefix web run lint`, `npm --prefix web run build` зелёные; browser acceptance 1280/390 без body overflow; никакого provider I/O и никакой записи на preview.

## Дизайн-решения и открытые вопросы

### D1: как применять изменение (нужно решение)

**Вариант А (рекомендую): полная пересборка через существующий pipeline с сохранением `start_week`.**
Входы берём из checkpoint, `build_plan` вызывается с сохранённым `start_week` (аддитивный необязательный параметр, default = сегодня → backward compatible), новым `demand` и `persist=True`. Переиспользуется канонический pipeline (никакой новой математики), preview/confirm и stale guard — как есть. Побочный эффект: `apply_planning_constraints` учитывает текущие CTL/TSB, поэтому помимо multiplier итог может немного измениться от текущей формы — но preview показывает это до confirm.

**Вариант Б: минимальное перемасштабирование.** Сохранить `weekly_tss_plan`/фазы/даты как есть, масштабировать по соотношению нового/старого итога (с cap по доступности), пересобрать daily/sessions. Diff меньше и предсказуемее, но это новая бизнес-правило масштабирования вне pipeline — больше кастомной логики и тестов.

### D2: где живёт контрол (нужно решение)

**Вариант А (рекомендую): прямо в Overview** рядом с «Как рассчитана недельная нагрузка» — компактный селектор + preview + «Применить»/«Отмена». Атлет не обязан открывать редактирование, чтобы поменять нагрузку.

**Вариант Б: за кнопкой «Изменить»** — контрол попадает в будущий M4c stepper; в M4b только preview-виджет без confirm. Проще, но не закрывает acceptance «Given demand изменён, preview показывает delta…; cancel не меняет checkpoint» полностью (нет применения).

### D3: issue-контракт (нужно решение)

**Вариант А (рекомендую):** создать GitHub issue «M4b: demand control с preview → confirm» (parent #304, refs #300) с секциями `### ExecPlan`, `### Acceptance criteria`, `### Smoke baseline` — по `docs/loop_engineering_instruction.md`.

**Вариант Б:** держать спеки локально и идти сразу в PR без отдельного issue.

## Файлы (после утверждения)

- `api/planning_service.py` — `demand_preview(db, level)`, `confirm_demand_change(...)`, опциональный `start_week` у `build_plan`;
- `api/routers/planning.py` — `GET /demand-preview`, `POST /demand/confirm`;
- `models/planning_checkpoints.py` — label источника `demand_change`;
- `web/lib/types.ts` — типы demand preview/confirm;
- `web/app/planning/page.tsx` — контрол на Overview;
- `tests/smoke/test_planning_demand_change.py` — RED-гейты первыми;
- `docs/planning_active_plan_ui_execplan.md` — раздел M4b (живой ExecPlan-документ).

## Smoke baseline (после утверждения)

```text
python -m pytest tests/smoke/test_planning_demand_change.py -q
python -m pytest tests/smoke/test_planning_active_plan_overview.py -q
python -m pytest tests/smoke -q
npm --prefix web run lint
npm --prefix web run build
```

Browser acceptance: `/planning` на изолированной БД, активный план, 1280 и 390 px, полный цикл «выбор → preview → подтвердить» и «выбор → отмена», без body overflow и ошибок консоли; никаких кликов по delivery/Intervals.
