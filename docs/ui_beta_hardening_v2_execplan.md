# UI beta hardening v2 — living ExecPlan

This ExecPlan is a living document. It is maintained under `.agent/PLANS.md`.
Milestones: M1 (#265) drill-down Обзор → detail pages; M2 (#266) Coach dialog
lifecycle; M3 (#267) mobile overflow; M4 (#268) dev-tools discoverability and
trust/accessibility polish.

## Purpose / Big Picture

The athlete treats `/activities`, `/sleep`, and `/hrv` as detail views of
«Обзор»: they enter through a meaningful card on the dashboard, always see a
path back, and the primary nav keeps «Обзор» active. After M1 the technical
`Разделы · Активности · Сон · HRV` row is gone and every entry is a real
clickable card with keyboard support and a visible hover/focus state.

## Progress

- [x] (2026-08-03) Inspected #265, dashboard page/components, Nav active-state logic, and the three detail pages.
- [x] (2026-08-03) M1 (#265) implemented: whole-card links for Сон/HRV/Активности, SectionLinks removed, `DrillDownHeader` («← Обзор») on all three detail pages, nav keeps «Обзор» active via a dashboard-child route group.
- [ ] M2 (#266), M3 (#267), M4 (#268) — separate milestones.

## Surprises & Discoveries

- Observation: the dashboard already has whole-card `Link` patterns (`TodayCard`, `WeekCard`), so the drill-down cards reuse the established markup instead of inventing a new one.
  Evidence: `web/components/dashboard/WeekCard.tsx` wraps content in `next/link`.
- Observation: `DashboardWidgets` carries no activity totals, and `/api/activities?days=30` already returns server-computed totals (count, distance, duration, TSS) — the Activities card needs one existing request, no new aggregate endpoint.
  Evidence: `web/lib/types.ts` `DashboardWidgets` (no activities) vs `ActivitiesResponse.totals`.

## Decision Log

- Decision: implement M1 directly under the existing structured issue #265 (it already has scope/files/acceptance); create no duplicate issue.
  Rationale: issue-first contract is already satisfied by #265.
  Date/Author: 2026-08-03 / Codex.
- Decision: add a small shared `web/components/ui/DrillDownHeader.tsx` («← Обзор» link + title) used by all three detail pages.
  Rationale: three identical headers justify one component; the back link targets `/dashboard` directly, so returning never depends on browser history.
  Date/Author: 2026-08-03 / Codex.
- Decision: make the whole Sleep card, the HRV metric card, and a new Activities card clickable `Link`s (block-level, with hover/focus ring and accessible name), removing `SectionLinks`.
  Rationale: matches the issue acceptance (click the whole card) and reuses existing card-link patterns.
  Date/Author: 2026-08-03 / Codex.
- Decision: the Activities card fetches the existing `/api/activities?days=30` for totals (one request on the dashboard); no backend change.
  Rationale: issue allows a new aggregate only if the entry cannot be built without network duplication; the existing endpoint already computes totals server-side.
  Date/Author: 2026-08-03 / Codex.
- Decision: `Nav.tsx` treats `/activities`, `/sleep`, `/hrv` as a dashboard route group so «Обзор» stays highlighted there.
  Rationale: those pages are detail sections of the dashboard; the primary four-item set is unchanged.
  Date/Author: 2026-08-03 / Codex.

## Outcomes & Retrospective

Not completed yet (M1 in progress).

## Context and Orientation

`web/app/dashboard/page.tsx` renders the «Обзор» page and currently shows a
technical `SectionLinks` row. `web/components/dashboard/SleepWidget.tsx` and
`StatusRow.tsx` render the Сон and HRV cards; `web/app/{activities,sleep,hrv}/page.tsx`
are the detail pages. `web/components/Nav.tsx` computes active state as
`pathname === href || pathname.startsWith(href + "/")`, so detail routes do not
keep «Обзор» active today. «← Обзор» means a `next/link` to `/dashboard` —
deliberately not `router.back()`.

## Plan of Work

1. `web/components/Nav.tsx`: add a small dashboard-children set (`/activities`,
   `/sleep`, `/hrv`) that keeps «Обзор» active.
2. New `web/components/ui/DrillDownHeader.tsx`: back link to `/dashboard`
   («← Обзор») plus an `h1` title; replace the bare `<h1>` in all three detail pages.
3. `web/components/dashboard/SleepWidget.tsx`: wrap the card in a `Link` to
   `/sleep` (block-level, hover/focus ring).
4. `web/components/dashboard/StatusRow.tsx`: the HRV metric becomes a whole-card
   `Link` to `/hrv` (other metrics stay plain cards).
5. New `web/components/dashboard/ActivitiesWidget.tsx`: fetches
   `/api/activities?days=30`, shows count/distance/duration/Σ TSS as a card
   `Link` to `/activities`; render it in place of `SectionLinks` on the dashboard.
6. Remove `SectionLinks` from `web/app/dashboard/page.tsx`.

## Concrete Steps

From `/Users/gregkisel/Developer/ai_trainer`:

    source ai_trainer_env/bin/activate
    python -m pytest tests/smoke/test_ui_beta_v2_m1_drilldowns.py -q
    python -m pytest tests/smoke -q
    npm --prefix web run lint
    npm --prefix web run build

## Validation and Acceptance

- Clicking the whole Сон card opens `/sleep`; the whole HRV card opens `/hrv`;
  the Activities card opens `/activities`; `Разделы · Активности · Сон · HRV` no
  longer exists anywhere.
- On each detail route «← Обзор» is visible and returns to `/dashboard`
  (a `Link`, not browser history); «Обзор» stays highlighted in the primary nav.
- Card links have keyboard focus and a visible focus/hover state.
- Smoke `python -m pytest tests/smoke -q` passes (environment socket skip stays),
  Next lint/build green; browser acceptance at 1280 and 390 px without body overflow.

## Idempotence and Recovery

All changes are additive UI wiring; re-running tests is safe. Reverting removes
the links/header component and restores the `SectionLinks` row.

## Artifacts and Notes

Primary files: `web/components/Nav.tsx`, `web/components/ui/DrillDownHeader.tsx`,
`web/components/dashboard/{SleepWidget,StatusRow,ActivitiesWidget}.tsx`,
`web/app/dashboard/page.tsx`, `web/app/{activities,sleep,hrv}/page.tsx`.
Focused acceptance test: `tests/smoke/test_ui_beta_v2_m1_drilldowns.py`.

## Interfaces and Dependencies

No API contract changes: the drill-downs reuse `/api/activities?days=30`,
`/api/sleep/summary`, `/api/hrv/summary`, and existing dashboard widgets.
Dependencies: parent #264; M1 is the first slice; no new routing/UI libraries.
