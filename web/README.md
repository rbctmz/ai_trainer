# AI Trainer — Web (Next.js)

Next.js 14 frontend for AI Trainer. Talks to the FastAPI backend in `../api`
(see `docs/SPEC_WEB_MIGRATION.md`). Streamlit (`../app.py`) stays as the
fallback surface.

## Run (both backend + frontend)

From the repo root:

```bash
./run_web.sh
```

This starts FastAPI on `:8000` and Next.js on `:3000`, and installs web deps on
first run. Open http://localhost:3000 (redirects to `/dashboard`).
API docs: http://localhost:8000/docs.

If a port is already busy, the script exits before launching the stack and asks
you to choose explicit ports:

```bash
API_PORT=8010 WEB_PORT=3010 ./run_web.sh
```

## Run manually

```bash
# backend (repo root)
pip install -r requirements.txt -r requirements-web.txt
PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python \
  uvicorn api.main:app --reload --port 8000

# frontend (web/)
npm install
npm run dev
```

## Stack

- Next.js 14 App Router + TypeScript
- Tailwind CSS (tokens mirror `docs/redesign_guide`)
- SWR for data fetching (dashboard revalidates every 5 min)

## How it connects

The browser always calls same-origin `/api/*`. `next.config.mjs` rewrites those
to the FastAPI backend (`API_BASE_URL`, default `http://127.0.0.1:8000`), so
there are no CORS surprises in dev. Response types live in `lib/types.ts` and
mirror `ui/pages/dashboard.py::_build_dashboard_v2_summary`.

## Layout

```
web/
├── app/
│   ├── layout.tsx
│   ├── page.tsx            # → /dashboard
│   └── dashboard/page.tsx  # SWR client page
├── components/dashboard/   # StatusRow, TodayCard, WeekCard, WeekStrip
└── lib/                    # api.ts (fetcher), types.ts
```
