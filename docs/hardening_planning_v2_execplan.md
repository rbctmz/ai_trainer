# Hardening, Planning V2, and Coach Explainability

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

The first three iterations did the right foundational work. The application now has a coherent onboarding path, a working dashboard, a real AI coaching flow, and a contributor-safe smoke suite. The next bottleneck is no longer "can the product be used at all?" It is "can the product be trusted, extended, and differentiated as a real coaching system?"

This phase therefore has three goals in order:

1. `Hardening Sprint`: remove operational fragility around Garmin authentication, environment drift, and release hygiene.
2. `Planning V2`: turn the current planning page from a useful calculator into an adaptive planning engine.
3. `Coach Explainability`: make the product explain why it recommends a given next step, not just render a chat answer.

The observable proof is different from the previous phase. Success now means the app still launches and tests cleanly, but also that the real Garmin path is quieter and more predictable, planning decisions are better grounded in constraints and recent load, and AI recommendations are easier to trust because the user can see the reasoning signals behind them.

## Current State

As of 2026-06-12, the repository is at a strong functional checkpoint:

- `app.py` is now a thin Streamlit shell rather than a product monolith.
- Product surfaces live under `ui/pages/*` and `ui/components/*`.
- Garmin sync orchestration lives in `services/sync.py`.
- Demo onboarding and real-provider auto-connect are working.
- DeepSeek support is wired and browser-verified.
- `ai_trainer_env/bin/python -m pytest tests/smoke -q` passes locally.

The current weak points are operational rather than conceptual:

- Garmin authentication still succeeds through `garminconnect` fallback, but the `garth` path is noisy and brittle.
- The worktree still contains unrelated local environment noise in `ai_trainer_env/*`.
- A few large feature modules, especially `ui/pages/ai_coaching.py`, are already becoming their own monoliths.
- The planning engine is useful, but still much closer to a TSS simulator than to a constraint-aware adaptive coach.

## Reference Signals

`IntervalCoach` is a useful product reference not because it should be copied feature-for-feature, but because its changelog shows what a mature coaching product keeps polishing:

- adaptive planning based on availability and interruptions,
- recovery-aware day-level adjustments,
- explicit handling of illness, injury, holiday, and limited availability,
- richer analytics such as rider profile and readiness interpretation,
- explainable behavior instead of opaque automation.

This repository should borrow those product patterns while staying faithful to the current architecture and scope.

## Progress

- [x] (2026-06-12 11:00+04:00) Re-audited the current repository after Iteration 3, including branch state, smoke-suite status, module sizes, and the remaining operational risks.
- [x] (2026-06-12 11:00+04:00) Reviewed `IntervalCoach` changelog themes as a product reference and mapped them into three concrete workstreams for AI Trainer.
- [x] (2026-06-12 13:50+04:00) Started Hardening Sprint by validating `matin/garth` against its upstream repository and docs, then hardening the local runtime so a broken or deprecated `garth` install no longer masquerades as a normal login failure.
- [x] (2026-06-12 14:05+04:00) Completed the first product-facing hardening slice: removed `garth` from the normal fresh-login path, kept it as a legacy diagnostic surface in Garmin connection info/UI, and expanded the smoke suite around the new auth contract.
- [x] (2026-06-12 14:10+04:00) Completed the first Planning V2 slice: added an `Intervals.icu` personal API-key adapter, wired planning-page sync controls for day/week event export, and covered the new boundary with smoke tests plus a real browser check.
- [x] (2026-06-12 14:41+04:00) Completed the first live-provider fix for that slice: added an explicit adapter `User-Agent`, re-ran smoke tests, and verified in the real UI that `Intervals.icu подключён. Найдено календарей: 1.`
- [x] (2026-06-12 14:42+04:00) Closed the real end-to-end acceptance loop: sent one planned workout day from the planning page, then confirmed through live API read-back that event `Триатлон Олимпийка — 2026-06-08` exists in `Intervals.icu` with `icu_training_load=14`.
- [x] (2026-06-12 23:33+04:00) Completed the next Planning V2 slice: the planner now accepts weekly hours, available training days, interruption type/duration, and catch-up vs protect-recovery strategy; smoke tests pass and the real planning page renders the new adaptive controls plus constraint summary.
- [x] (2026-06-12 23:58+04:00) Completed the Planning UX + Explainability slice: the planning page now presents a scenario preview before generation, a post-build reasoning section with scenario/planner cards, a before/after weekly comparison table, and split CSV exports for comparison, weekly detail, and daily detail.
- [x] (2026-06-12 23:59+04:00) Re-ran the smoke suite after the explainability refactor (`54 passed`) and browser-verified the updated planning flow on a separate local Streamlit instance at `http://localhost:8502` so the user's long-running `8501` session was not disturbed.
- [ ] Planning V2 — adaptive planning driven by load, availability, and interruptions.
- [ ] Coach Explainability — clearer reasoning and daily guidance on top of live metrics.

## Surprises & Discoveries

- Observation: the current `garth` installation in the local virtual environment is structurally damaged.
  Evidence: importing `garth` returns a namespace package with no `__file__`, no `__version__`, and no `login` attribute, while `site-packages/garth` contains only subdirectories and `__pycache__` files. This matches the earlier report that the checked-in virtual environment is damaged beyond a normal dependency state.

- Observation: even a healthy `garth` install is no longer a valid fresh-login strategy according to the upstream project itself.
  Evidence: the upstream repository is explicitly marked deprecated, states that Garmin changed the auth flow, and says that new logins no longer work. The preserved docs still show `garth.login(...)` as the historical API, but the front page and getting-started guide now describe it as a reference-only surface for existing saved sessions.

- Observation: `Intervals.icu` is a realistic next integration target for Planning V2 because it already exposes workout, calendar-event, and activity endpoints that line up with the current planning and export surfaces.
  Evidence: the public API guide describes API-key access for personal use, athlete-id `0` shortcuts, calendar event CRUD, workout CRUD, downloadable planned workout formats, and activity detail endpoints with interval data. Those fit naturally with the current planning page and future explainability/export work.

- Observation: the product is now modular at the shell level, but some page modules are already large enough to need a second wave of internal decomposition.
  Evidence: `ui/pages/ai_coaching.py` is above 2200 lines, `ui/pages/dashboard.py` is near 1000 lines, and `ui/pages/planning.py` is above 600 lines.

- Observation: the next differentiator is more likely to come from adaptive planning and explainability than from adding yet another AI provider.
  Evidence: the provider layer already supports OpenAI, Anthropic, Gemini, Ollama, DeepSeek, and Mock AI. By contrast, planning still lacks first-class concepts such as illness, holiday, or constrained availability, and the changelog patterns in IntervalCoach emphasize those areas.

- Observation: the repository does not currently declare a dedicated HTTP client dependency for general-purpose outbound integrations.
  Evidence: `requirements.txt` lists Streamlit, pandas, AI SDKs, and Garmin-specific packages, but neither `requests` nor `httpx` is declared as an app-level dependency. The first `Intervals.icu` slice should therefore prefer the Python standard library for HTTP transport instead of adding a new dependency just for one small adapter.

- Observation: the new planning sync section is resilient even before the user adds Intervals credentials.
  Evidence: browser verification on `http://localhost:8501` after generating a goal plan shows a visible `📤 Intervals.icu` section and, without an API key in `.env`, an explanatory non-blocking message instead of an exception or broken layout.

- Observation: `Intervals.icu` accepts the same API-key request via `curl`, but rejects the default Python `urllib` fingerprint with a Cloudflare-style `403`.
  Evidence: `curl -u API_KEY:*** https://intervals.icu/api/v1/athlete/0/calendars` returned `HTTP/2 200`, while the same endpoint via `urllib.request.urlopen(...)` returned `HTTP Error 403: Forbidden` until a normal `User-Agent` header was added. The adapter therefore needs an explicit `User-Agent`, not different auth logic.

- Observation: the first real provider-side event created by the planning page preserved the expected shape of the AI Trainer payload.
  Evidence: a live read-back from `GET /api/v1/athlete/0/events?oldest=2026-06-08&newest=2026-06-08` returned event id `115757268` with name `Триатлон Олимпийка — 2026-06-08`, `type=\"Ride\"`, `start_date_local=\"2026-06-08T07:00:00\"`, `icu_training_load=14`, and the exported description block from AI Trainer.

- Observation: availability-aware planning can be added without rewriting the existing Banister forecast or export surfaces.
  Evidence: the planner model now constrains weekly TSS, redistributes load onto selected days, and annotates weekly adjustments before the existing daily expansion, forecast chart, CSV export, ICS export, and `Intervals.icu` sync all continue to work against the adjusted plan shape.

- Observation: a small set of explicit user inputs gives a meaningfully more adaptive plan without demanding a full calendar UI.
  Evidence: the real planning page now renders weekly available hours, available weekdays, interruption type, interruption duration, and `Беречь восстановление` vs `Наверстать аккуратно`; after building a plan, the UI shows a human-readable summary of which constraints were applied.

- Observation: `run.sh` intentionally disables Streamlit file watching, so browser verification against an already running app can silently show stale UI even when the repository code is newer.
  Evidence: the original `8501` session continued to show the old heading `Ограничения и interruptions` and the old expander copy until a fresh Streamlit process was started, while the current working tree only contained `🧭 Сценарий и ограничения` and `⚙️ Продвинутые настройки распределения`.

## Decision Log

- Decision: treat the next phase as a new ExecPlan instead of extending the previous three-iteration roadmap indefinitely.
  Rationale: the earlier plan is complete and should remain a closed record of the stabilization/modularization/core-flow work. The next work has a different objective and therefore deserves its own acceptance criteria.
  Date/Author: 2026-06-12 / Codex

- Decision: start the new phase with Garmin auth and environment hardening, not with planning features.
  Rationale: the product flow is now good enough that operational fragility is the main thing undermining trust. The clearest current example is the broken `garth` runtime, which creates noisy and misleading auth attempts even though the fallback path works.
  Date/Author: 2026-06-12 / Codex

- Decision: treat `garth` as an optional legacy acceleration path, not as the default fresh-auth mechanism.
  Rationale: upstream `matin/garth` now states that Garmin's auth changes broke new logins. Continuing to try `garth.login(email, password)` on every fresh login attempt adds noise and delay while providing no supported success path. The hardening target is therefore graceful detection plus clean fallback, not heroic retries.
  Date/Author: 2026-06-12 / Codex

- Decision: keep `Intervals.icu` in scope as a planning/export integration candidate, not as a replacement for Garmin ingestion.
  Rationale: Garmin remains the primary source for personal activity, readiness, and recovery signals in this product. `Intervals.icu` is more interesting as a second-system integration for planned workouts, calendar sync, and richer workout/export semantics.
  Date/Author: 2026-06-12 / Codex

- Decision: use `IntervalCoach` as a product-pattern reference, not as a roadmap to copy.
  Rationale: the right lesson is not "implement every feature they shipped." The useful lesson is where a mature coaching product keeps investing: adaptive planning, explicit interruption handling, better daily guidance, and more truthful explanations.
  Date/Author: 2026-06-12 / Codex

- Decision: start Planning V2 with a single-user `Intervals.icu` API-key adapter that creates calendar events from the existing daily plan.
  Rationale: the current product is a local single-athlete Streamlit app, not a multi-user SaaS. The simplest valuable slice is therefore personal API-key sync for planned workouts, which reuses the existing daily planner and export semantics without introducing OAuth or multi-tenant state.
  Date/Author: 2026-06-12 / Codex

- Decision: make the next Planning V2 slice availability-aware through weekly hours, selected training days, and near-term interruption inputs instead of attempting a full calendar scheduler.
  Rationale: that input set is small enough to implement safely in the current Streamlit page, but rich enough to produce materially different plans. It also aligns directly with the product patterns seen in `IntervalCoach`: limited availability, missed time, and careful catch-up decisions.
  Date/Author: 2026-06-12 / Codex

- Decision: verify the explainability slice on a second local Streamlit instance instead of restarting the user's existing `8501` process.
  Rationale: `run.sh` starts Streamlit with `--server.fileWatcherType none`, which made the already running instance stale. Launching a temporary `8502` server from the current worktree provided clean acceptance evidence without interrupting the user's live session.
  Date/Author: 2026-06-12 / Codex

## Plan of Work

### Hardening Sprint

The goal of the sprint is to make the current product quieter, more predictable, and easier to release. The highest-priority items are:

- make `garth` capability detection explicit and fail soft when the package is broken,
- keep Garmin auth fallback behavior working without misleading error noise,
- separate genuine runtime requirements from optional accelerators,
- clean up release hygiene around smoke tests, docs, and environment expectations.

The measurable result is that the real Garmin path still works, but the app no longer behaves as if a broken `garth` install were a normal auth failure.

### Planning V2

The goal is to evolve the current planning screen into a constraint-aware planning engine. Key additions should include:

- availability-aware weekly targets,
- illness / injury / holiday / limited-availability inputs,
- catch-up versus protect-recovery decisions after missed sessions,
- clearer explanation of why a weekly target was chosen.

The measurable result is that the planning page no longer behaves like a pure TSS slider plus projection chart.

### Coach Explainability

The goal is to make AI coaching feel grounded and consistent. The likely slices are:

- a daily briefing card,
- explicit "why this recommendation" output linked to TSB / HRV / sleep / readiness,
- recent plan-adjustment history and a clearer handoff between sync, dashboard, and coach.

The measurable result is that the product can answer not only "what should I do?" but also "why are you telling me this today?"

## Validation and Acceptance

The Hardening Sprint is accepted when the Garmin auth path behaves predictably in a damaged or reduced environment, the smoke suite remains green, and the docs describe the real contributor path instead of an idealized one.

Planning V2 is accepted when weekly planning reacts to time constraints and interruptions instead of only ramp logic and static target ranges.

Coach Explainability is accepted when the dashboard and AI coaching can surface the main reasoning signals behind a recommendation without requiring the user to reverse-engineer them from charts or a long-form chat answer.

## Outcomes & Retrospective

This section starts empty on purpose. The previous plan ended with a working product flow. This plan begins at the moment where the product needs to become a durable system rather than a successful sequence of flows.

The first hardening slice immediately justified the new plan. The upstream `garth` project itself now says that new logins are broken and the library is deprecated, while the local virtual environment adds an extra layer of corruption on top by shipping a namespace package with missing public API exports. The right response was not to add more retries, but to make AI Trainer stop treating `garth` fresh login as a normal path and to fail soft into `garminconnect` instead.

The next hardening slice turned that into a real product contract. Fresh Garmin authentication now belongs solely to `garminconnect`, while `garth` remains available only as legacy diagnostics and optional runtime context. That is a more honest user-facing model and a better base for future integrations such as `Intervals.icu`, which fits the planning/export side of the product better than the primary ingestion path.

The first Planning V2 slice is now real, not hypothetical. The planning page can export its generated daily plan to `Intervals.icu` through a dedicated service adapter, the environment contract is documented in `.env.example`, and the UI behaves sensibly even when the integration is not configured yet. That is the correct shape for this phase: additive, testable, and useful before the larger adaptive-planning work begins.

The first live user verification also revealed a useful production detail: `Intervals.icu` is not rejecting the API key or the endpoint shape, but it does reject the default `urllib` client signature. That bug belongs in the adapter boundary, not in the planning UI. Fixing it there keeps the integration predictable for both connection checks and future event creation.

The real acceptance loop is now closed for this slice. The app can discover the configured `Intervals.icu` account, validate the connection from the planning page, send at least one planned workout event, and confirm that event through provider-side read-back. That is enough evidence to treat the integration as production-shaped rather than prototype-shaped.

The next Planning V2 slice changed the planner from a pure target-and-ramp calculator into a constrained planner. It still uses the same Banister forecasting and export surfaces, but now the user can express how much training time actually exists, which weekdays are usable, whether the next block is affected by illness, holiday, or limited availability, and whether missed load should be protected or partially caught up. That is the first real step toward adaptive planning rather than static load projection.

Revision note (2026-06-12 23:33+04:00): recorded the availability-and-interruption slice after verifying the new controls and constraint summary in the real planning UI and re-running the smoke suite (`52 passed`).

The explainability slice turned that adaptive logic into something a user can actually read. Before this change, the planning page could generate a better adaptive plan, but the output still behaved like a flat chart plus raw weekly rows. Now the page frames the scenario before generation, then explains the outcome after generation through a headline, compact metrics, a scenario card, a planner-decision card, and a before/after weekly table. The planner is still the same engine underneath, but the user no longer has to reverse-engineer why the numbers changed.

The acceptance evidence for that slice is strong enough to treat it as complete. The smoke suite now passes at `54 passed`, and a fresh Streamlit instance launched from the current worktree on `http://localhost:8502` shows the updated `🧭 Сценарий и ограничения` pre-plan section and, after pressing `🧭 Построить план до старта`, the new `🧠 Почему план такой` and `↔️ До / После По Неделям` sections. That closes the loop for this sprint: the planning UI is now aligned with the adaptive engine already added in the previous slice.

Revision note (2026-06-12 23:59+04:00): recorded the Planning UX + Explainability slice after browser-verifying the new planning page on a temporary `8502` Streamlit instance and re-running the smoke suite (`54 passed`).
