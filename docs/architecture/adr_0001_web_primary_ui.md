# ADR 0001: Web-First Product Direction During Migration

- Status: Accepted
- Date: 2026-06-27
- Related:
  - `docs/SPEC_WEB_MIGRATION.md`
  - `docs/AI_Feature_Development_Workflow.md`

## Context

AI Trainer started as a Streamlit application. The repository is now in an active migration to a web stack, but that migration is not finished yet.

Streamlit is still a working surface for fallback, acceptance, admin, and any flows that have not reached web parity. At the same time, new product development needs one default direction so the codebase does not split into two competing apps.

The repository now contains:

- `api/`: FastAPI contract layer over the existing Python domain logic
- `web/`: Next.js product UI
- `app.py` + `ui/`: legacy Streamlit surface

Without an explicit decision, feature work will drift between two UIs and duplicate logic.

## Decision

1. `web/` is the primary product direction during migration.
2. `api/` is the product contract boundary for frontend work.
3. Python domain logic remains the source of truth in `services/`, `models/`, `data/`, and shared helpers.
4. `app.py`, `ui/`, and Streamlit-specific state/rendering code stay supported as a fallback/legacy surface until parity is complete.

## Delivery Rules

For new product-facing work during migration:

1. define or update the API contract first
2. implement or refactor backend behavior in shared Python code
3. cover that behavior with backend tests
4. wire the flow into `web/`

## Allowed Streamlit Work

Streamlit changes are allowed when they are one of the following:

- bug fixes
- admin, diagnostic, or acceptance/runtime support
- extracting reusable logic out of Streamlit into shared modules
- temporary compatibility bridges while web parity is still incomplete

## Disallowed Direction

Do not:

- ship new product features only in `ui/pages/*`, unless the task is explicitly a legacy-only fix
- duplicate business logic in both Streamlit and API/web paths
- move product rules into ad hoc frontend-only logic when the rule belongs in Python
- treat `st.session_state` as the long-term contract for new product flows

## Ownership Boundary

- Backend/API/domain: Python (`api/`, `services/`, `models/`, `data/`, shared utilities)
- Frontend/product UX target: web (`web/`)
- Legacy fallback shell during migration: Streamlit (`app.py`, `ui/`, `state/manager.py`)

## Consequences

- Repo docs and onboarding should describe the project as hybrid during migration: web-first for new work, Streamlit still active as fallback.
- `./run_web.sh` should be documented as the preferred path for API/web development, while `./run.sh` and `streamlit run app.py` remain supported legacy paths.
- New specs, ExecPlans, and PRs should describe web behavior first unless the task is explicitly legacy Streamlit maintenance.
- When legacy Streamlit code needs changes, prefer shrinking it toward shared headless services rather than adding more product-specific logic there.

## Streamlit EOL Assessment (added 2026-07-20, Issue #201)

Состояние web-паритета: все ежедневные пользовательские потоки живут в web
(/today, /dashboard, /coach, /decisions, /planning c reconciliation и
delivery, /recovery, /adherence, /hrv, /sleep, /activities). Streamlit-only
остались acceptance/admin-инструменты и отдельные legacy-страницы.

Решение: дату EOL не назначаем — назначаем критерии и режим.

1. Streamlit немедленно переходит в **maintenance-only** (это уже де-факто
   так): багфиксы, acceptance/admin-туллинг, извлечение переиспользуемой
   логики. Новые продуктовые фичи в `ui/pages/*` запрещены (см. Delivery
   Rules выше).
2. Критерии EOL (все три): (a) acceptance-runtime переведён на web или
   явно признан dev-инструментом вне продукта; (b) два полных релизных
   цикла подряд без единого Streamlit-фикса, вызванного пользовательским
   сценарием; (c) в Streamlit-коде не осталось бизнес-логики, не
   извлечённой в shared-слой.
3. Само удаление — отдельный ADR при выполнении критериев, с планом
   миграции `run.sh`/`run_acceptance.sh`.
