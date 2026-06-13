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
- The remaining large AI coaching boundary is now the tool-calling and response-execution engine in `ui/pages/ai_coaching.py`; the monthly progress-report core has been moved into `models/ai_coach_progress.py`, but the execution pipeline still needs the final decomposition wave.
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
- [x] (2026-06-13 00:20+04:00) Completed the next Planning V2 slice: the planner now interprets start-state load (`CTL/ATL/TSB`) as `fresh / balanced / fatigued / deep_fatigue`, softens risky early weeks when the athlete starts tired, and allows more catch-up after holiday/limited-availability scenarios when the athlete starts fresh.
- [x] (2026-06-13 00:20+04:00) Hardened the planning UI around degenerate target-TSS ranges by replacing the collapsed `500..500` slider case with a fixed-value control, then re-ran the smoke suite (`58 passed`).
- [x] (2026-06-13 00:46+04:00) Started the Coach Explainability slice by introducing a shared readiness/explainability helper and routing both dashboard next-step guidance and the AI coaching recommended first prompt through the same reasoning contract.
- [x] (2026-06-13 00:46+04:00) Added the first user-facing explainability surfaces for that slice: a `Почему сегодня такой фокус` briefing on the dashboard and a matching `Почему такой старт` block on the AI coaching page, then re-ran the smoke suite (`61 passed`).
- [x] (2026-06-13 01:09+04:00) Completed the next Coach Explainability slice: the shared helper now produces a richer daily briefing (`Сегодня / Ближайшие 2-3 дня / Следить за`) plus plan-aware prompt context, the dashboard now stores a concrete AI-coach handoff, and the AI coaching page renders that handoff as an actionable top-of-chat checkpoint.
- [x] (2026-06-13 11:51+04:00) Completed the next Hardening Sprint slice: extracted AI provider setup/status and first-run entry/handoff guidance out of `ui/pages/ai_coaching.py` into dedicated `ui/components/ai_coach_provider.py` and `ui/components/ai_coach_entry.py`, preserved the existing `ui.pages.ai_coaching` helper contract for smoke tests and callers, and re-ran the full smoke suite (`64 passed`).
- [x] (2026-06-13 19:38+04:00) Completed the next Hardening Sprint slice: extracted the remaining AI chat shell (state bootstrap, sidebar diagnostics, conversation surface, quick-question bar, and free-form input) into `ui/components/ai_coach_chat.py`, added focused smoke coverage for the new state bootstrap and quick-question contract, and re-ran the full smoke suite (`67 passed`).
- [x] (2026-06-13 19:54+04:00) Completed the next Hardening Sprint slice: extracted the monthly progress-report assembly and filtering logic into `models/ai_coach_progress.py`, kept `ui.pages.ai_coaching` as a compatibility wrapper for existing callers, added focused smoke coverage for the progress boundary, and re-ran the full smoke suite (`70 passed`).
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

- Observation: explicit `illness` and `injury` interruption scenarios already apply a strong first-week reduction, so layering a generic fatigue guard on top creates an unrealistic double penalty.
  Evidence: the first implementation of the load-aware slice pushed the existing illness test from week-one `60` TSS down to `50` TSS, which was technically consistent with the added start-load guard but product-wise too punitive. The fix was to skip the extra load-guard layer when an illness/injury interruption is already active.

- Observation: dashboard and AI coaching were both already using the same raw signals, but with different branching rules and different wording, which made the product feel less coherent than the underlying data actually was.
  Evidence: `ui/pages/dashboard.py` had its own `TSB/HRV` next-step logic, while `ui/pages/ai_coaching.py` separately chose a recommended first prompt from `TSB/readiness/recovery_state`. The new shared helper replaced that duplication and the smoke suite still passed afterward.

- Observation: the safest way to modularize `ui/pages/ai_coaching.py` was to preserve its old helper names as import-level re-exports instead of forcing every smoke test and caller to learn the new component paths immediately.
  Evidence: after extracting provider and entry/handoff code into `ui/components/*`, the existing smoke tests for demo flow, real-provider flow, recommended prompt selection, and dashboard handoff all continued to run unchanged and the full suite still passed at `64 passed`.

- Observation: the next safe extraction boundary was the chat shell, not the tool-calling engine.
  Evidence: moving state bootstrap, sidebar diagnostics, conversation rendering, quick prompts, and the free-form input bar into `ui/components/ai_coach_chat.py` reduced `ui/pages/ai_coaching.py` from `1818` lines to `1440` lines while the full smoke suite increased to `67 passed` after adding focused coverage for the new boundary.

- Observation: the progress-report boundary is safe to move into `models/` even though the final rendered markdown still belongs to the page layer.
  Evidence: extracting the report assembly, recovery/sleep summaries, and monthly-progress filtering into `models/ai_coach_progress.py` reduced `ui/pages/ai_coaching.py` again to `1168` lines, while preserving the old page-level helper names through thin wrappers and keeping the full smoke suite green at `70 passed`.

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

- Decision: interpret start-state load inside the planner model itself, not in the page layer.
  Rationale: the load-aware behavior belongs to the planning contract, not to Streamlit. Keeping the readiness classification and its rules in `models/training_planner.py` lets the same logic drive UI summaries, tests, and future non-UI integrations without duplicating thresholds.
  Date/Author: 2026-06-13 / Codex

- Decision: do not stack the generic start-fatigue guard on top of explicit `illness` or `injury` interruption blocks.
  Rationale: illness and injury already encode a severe near-term reduction pattern. Adding another first-week fatigue cut on top overstates caution and makes the plan harder to trust. Availability/holiday/limited scenarios still benefit from the separate start-load interpretation, but sickness/injury should use the dedicated interruption path alone.
  Date/Author: 2026-06-13 / Codex

- Decision: start Coach Explainability with a shared reasoning helper instead of directly rewriting prompts or UI copy in place.
  Rationale: the biggest current risk is divergence, not missing text. If dashboard and AI coaching continue to branch independently, any new wording polish will drift again. A shared helper creates one contract for `recovery / plan_week / form_today` and lets both surfaces explain the same signals consistently.
  Date/Author: 2026-06-13 / Codex

- Decision: modularize `ui/pages/ai_coaching.py` by extracting provider setup/status and entry/handoff guidance first, while keeping the old helper names importable from `ui.pages.ai_coaching`.
  Rationale: those two areas were the clearest UI-facing seams and the lowest-risk extraction targets. Preserving the old import contract let the repository keep its existing smoke tests and page callers while still shrinking the monolith and creating clearer reuse boundaries in `ui/components/*`.
  Date/Author: 2026-06-13 / Codex

- Decision: make the next extraction target the chat shell around `render_ai_chat_page(...)`, not the AI/tool-calling engine.
  Rationale: the shell owns page-local concerns such as Streamlit layout, sidebar diagnostics, message history presentation, and quick-question actions, which are easier to isolate than the lower-level response pipeline. That gives another meaningful size reduction and cleaner boundaries without risking the more complex tool execution path yet.
  Date/Author: 2026-06-13 / Codex

- Decision: move the monthly progress-report core into `models/ai_coach_progress.py`, but keep markdown presentation wiring and public helper compatibility in `ui.pages.ai_coaching`.
  Rationale: the progress report is mostly data interpretation and recommendation logic, which belongs with the coaching model layer rather than a Streamlit page. The page still owns the existing `format_tool_result(...)` presentation contract, so the safest extraction is a model-level core that accepts a formatter callback while preserving the old page imports for current callers and smoke tests.
  Date/Author: 2026-06-13 / Codex

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

The latest hardening slice confirms that `ui/pages/ai_coaching.py` can now be decomposed by responsibility rather than by file-size panic. Provider setup, entry/handoff, chat shell, and monthly progress reporting now each have a dedicated boundary, and the page has dropped to `1168` lines without breaking the legacy helper contract expected by `app.py` and the smoke suite. That is the right pattern for the final lap: the remaining tool-calling engine is now isolated as the last major seam instead of being tangled together with unrelated UI and reporting logic.

The next Planning V2 slice made the planner sensitive to the athlete's starting load state, not just the event target and calendar constraints. `apply_planning_constraints(...)` now receives live `CTL`, `ATL`, and `TSB`, classifies the starting state as `fresh`, `balanced`, `fatigued`, or `deep_fatigue`, and uses that state to soften the first weeks when the athlete is already carrying too much fatigue. In the opposite direction, the same state can make `catch up` slightly more permissive after holiday or limited-availability blocks when the athlete starts fresh instead of stale.

That slice also exposed an important boundary condition in the UI contract. When the realistic target weekly TSS collapsed to a single allowed value, Streamlit rejected the `slider(min=500, max=500)` call outright. The fix was to treat that as a fixed-value control instead of trying to force a degenerate slider. That keeps Planning V2 stable when availability caps the target harder than the nominal distance range.

The validation evidence is again strong enough to keep moving forward without reopening older work. The adaptive-planning smoke tests now cover deep-fatigue start states and fresh-start catch-up behavior, the planning-page explainability tests cover the collapsed target-TSS control, and the full smoke suite passes at `58 passed`.

Revision note (2026-06-13 00:20+04:00): recorded the load-aware planning slice and the fixed-value target-TSS control after re-running the full smoke suite (`58 passed`).

The first Coach Explainability slice is intentionally modest but strategically important. Instead of trying to make the AI sound better through prompt edits alone, it introduces a shared reasoning layer that turns the same signals — `TSB`, `CTL`, `ATL`, readiness, recovery state, and recent plan constraints — into one explainability summary. The dashboard now uses that summary to frame `Следующий шаг`, while AI coaching uses the same summary to decide what the recommended first question should be.

That immediately improves product coherence. A user who sees `Сначала разберите восстановление` on the dashboard will now encounter the same underlying logic when opening AI coaching, along with a short `Почему такой старт` block that lists the key signals behind the suggestion. This is not yet the full daily briefing vision, but it is the first moment where multiple surfaces in the product start speaking the same language about readiness.

The validation evidence is straightforward and sufficient for this slice. New smoke coverage now exercises the shared explainability helper directly, while the existing dashboard and AI-coaching smoke tests still pass on top of the refactor. The full smoke suite passes at `61 passed`.

Revision note (2026-06-13 00:46+04:00): recorded the first Coach Explainability slice after adding the shared readiness helper, wiring it into dashboard and AI coaching, and re-running the full smoke suite (`61 passed`).

The next Coach Explainability slice makes the shared reasoning contract meaningfully more product-like. Instead of stopping at `что спросить у AI`, the helper now also emits a concrete daily briefing with `Сегодня`, `Ближайшие 2-3 дня`, and `Следить за`, while weaving planning constraints back into both the visible explanation and the AI prompt itself. That closes an important gap: readiness guidance is no longer detached from the adaptive plan the user just built.

The dashboard-to-coach transition is now also a real handoff rather than a navigation hint. Pressing the primary AI action on the dashboard stores a specific recommended question, its reasoning, and the short operational briefing in session state; the AI coaching page then surfaces that package at the top of the chat so the user can either send it immediately or dismiss it. This makes `Следующий шаг` behave like an actual workflow continuation instead of a generic link.

The acceptance evidence is again clear enough to keep moving. New smoke coverage now validates the richer explainability payload, the dashboard handoff state, and the AI entry-point override, while the full smoke suite passes at `64 passed`.

Revision note (2026-06-13 01:09+04:00): recorded the richer daily-briefing and dashboard-to-AI handoff slice after re-running the full smoke suite (`64 passed`).

The next hardening slice attacked a different kind of risk: page-level sprawl. `ui/pages/ai_coaching.py` had grown into one large file responsible for provider selection, provider status, first-run recommendations, dashboard handoff UI, chat rendering, tool calling, and progress reporting. The refactor pulled the provider boundary into `ui/components/ai_coach_provider.py` and the first-run entry boundary into `ui/components/ai_coach_entry.py`, while keeping the existing helper names visible from `ui.pages.ai_coaching` so the rest of the repository did not need to change all at once.

That is not the end of modularization, but it is a meaningful hardening checkpoint. The page file is now materially smaller, the explainability handoff logic has a dedicated home, and the provider selection flow is isolated enough to change independently of the chat engine. Just as importantly, the smoke suite stayed green without forcing a simultaneous test rewrite, which means the extraction improved structure without destabilizing the product.

Revision note (2026-06-13 11:51+04:00): recorded the AI coaching modularization slice after extracting provider and entry/handoff helpers into `ui/components/*` and re-running the full smoke suite (`64 passed`).

The next hardening slice continued the same refactor one layer deeper by targeting the chat shell instead of the provider setup. The page-level responsibilities around state bootstrap, sidebar diagnostics, message rendering, first-run empty state, quick questions, and chat input now live in `ui/components/ai_coach_chat.py`, while `ui/pages/ai_coaching.py` mostly orchestrates page entry and the lower-level chat/tooling functions that still remain.

That is a useful structural checkpoint because it separates Streamlit page chrome from the response engine. The file is still large, but the remaining size is now concentrated more honestly in tool calling, prompt construction, and progress-report generation rather than in repetitive UI scaffolding. Focused smoke coverage for the new chat-shell state bootstrap also means this slice improved both maintainability and test visibility instead of just moving code around.

Revision note (2026-06-13 19:38+04:00): recorded the AI coaching chat-shell modularization slice after extracting the chat UI/state helpers into `ui/components/ai_coach_chat.py`, adding focused smoke coverage, and re-running the full smoke suite (`67 passed`).
