# Streamlit EOL — аудит критериев (TD-004, 2026-08-03)

Аудит критериев из `docs/architecture/adr_0001_web_primary_ui.md`
(«Streamlit EOL Assessment», Issue #201). Решение по удалению Streamlit —
отдельный ADR; этот документ фиксирует, насколько выполнены три критерия,
и фиксирует решение по режиму на текущую дату.

## Критерии и статус

### (a) Acceptance-runtime переведён на web ИЛИ явно признан dev-инструментом

**Статус: выполнен (формально).**

`run_acceptance.sh` по-прежнему запускает Streamlit (`streamlit run app.py`),
но ADR-0001 уже квалифицирует acceptance/admin как разрешённую
maintenance-поверхность, а не продукт. Настоящим документом acceptance-runtime
явно признаётся dev-инструментом вне пользовательского продукта: он служит
техническим тестерам и прогонам, а не атлетам.

Evidence: `run_acceptance.sh` (Streamlit-рантайм, изолированная БД,
`ACCEPTANCE_PORT`), `AGENTS.md` (acceptance/admin — разрешённый Streamlit).

### (b) Два полных релизных цикла подряд без единого Streamlit-фикса

**Статус: не выполнен.**

Правки `ui/pages/` продолжаются:

| Дата | Коммит |
|------|--------|
| 2026-08-01 | `0380619` fix: honor materialized targets in UI FIT/TCX export (#317) |
| 2026-07-13 | `012d44f` fix: prevent single sessions becoming bricks |
| 2026-07-10 | `20cb3f9` refactor: decouple dashboard API from legacy UI |

Всего 79 коммитов, затрагивающих `ui/pages/`, с 2026-05-01. Последний — за
два дня до аудита, поэтому двух «чистых» релизных циклов без user-flow фиксов
нет.

### (c) В Streamlit-коде не осталось бизнес-логики вне shared-слоя

**Статус: не выполнен.**

В `ui/pages/` остаются встроенные расчёты, которых нет в shared-слое:

- `ui/pages/dashboard.py:40` — `_calculate_current_status(...)`;
- `ui/pages/dashboard.py:727-743` — суммы/средние/`groupby` по активностям;
- `ui/pages/hrv.py:76,190,250,340,427` — baseline RMSSD, rolling-агрегаты,
  тренды;
- `ui/pages/activities.py:108-125` — суммы/средние/`groupby`;
- `ui/pages/sleep.py:417-418` — средние по сну.

Только 7 из 8 страниц импортируют `models/services/data`; часть расчётов всё
ещё живёт в Streamlit-представлении.

## Решение (текущая дата)

Критерии (b) и (c) не выполнены → **дата EOL и удаление не назначаются**.
Режим остаётся maintenance-only (как в ADR-0001): багфиксы,
acceptance/admin-туллинг и извлечение логики; новые продуктовые фичи в
`ui/pages/*` запрещены.

Следующие шаги (отдельные issues):

- Довести критерий (c): извлечь оставшиеся агрегаты
  (`dashboard._calculate_current_status`, HRV-тренды, activities/sleep-сводки)
  в shared-модули/API с эквивалентными контрактами.
- Повторный аудит (b) после двух релизных циклов без Streamlit user-flow
  фиксов; при выполнении всех трёх критериев — ADR об удалении.

## Реестр

TD-004 в `docs/technical_debt_register.md` закрыт результатом этого аудита:
критерии не выполнены, режим maintenance-only, follow-up по извлечению
логики вынесен в отдельный issue.
