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
- The AI coaching hardening work is now largely complete; the next meaningful risks are less about page modularity and more about product behavior, especially how much adaptive planning and explainability still remain compared with the long-term reference target.
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

- [x] (2026-06-19 20:35+04:00) Completed the next Planning UX hardening v2 slice: execution checkpoints now derive a compact `execution_corrective_microcycle` from day-level reconciliation plus weekly review, persist it next to the existing execution summary, preview it before apply in the execution editor, and surface the same next-2-3-day action story on Planning, Dashboard, and AI Coaching. Smoke coverage was extended across planning explainability, checkpoint history, dashboard handoff, recommended AI entry prompts, and coach explainability before moving to final validation.
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
- [x] (2026-06-13 20:01+04:00) Completed the next Hardening Sprint slice: extracted prompt construction, tool-call resolution, and the core response-execution turn into `models/ai_coach_runtime.py`, kept `ui.pages.ai_coaching` as a compatibility wrapper around the new runtime, added focused smoke coverage for the execution boundary, and re-ran the full smoke suite (`73 passed`).
- [x] (2026-06-13 20:12+04:00) Completed the next Hardening Sprint slice: extracted markdown tool-result formatting and browser-side speech/streaming helpers into `ui/components/ai_coach_output.py`, kept `ui.pages.ai_coaching` as a compatibility wrapper for `app.py` and older tests, fixed the streaming helper so final text preserves sentence spacing, and re-ran the full smoke suite (`76 passed`).
- [x] (2026-06-13 23:11+04:00) Completed the next Planning V2 slice: the planner now applies recovery-aware day roles (`off / recovery / easy / quality / long`) inside the daily expansion step, exposes weekly structure metadata plus daily session focus rows on the planning page, preserves the existing export/sync contract, and re-ran the full smoke suite (`78 passed`).
- [x] (2026-06-13 23:27+04:00) Completed the next Planning V2 slice: added planner-owned `session_templates` metadata aligned to the existing daily tuple contract, surfaced phase/sport/session naming/duration on the planning page, upgraded ICS / Intervals.icu / FIT / TCX exports to consume the richer metadata when available, and re-ran the full smoke suite (`84 passed`).
- [x] (2026-06-13 23:40+04:00) Completed the next Hardening Sprint slice: added an isolated acceptance runtime with `./run_acceptance.sh`, auto-seeded demo data into a unique temporary SQLite database, disabled real Garmin login inside that runtime, surfaced acceptance-mode reset/status messaging in the UI shell, and re-ran the full smoke suite (`88 passed`).
- [x] (2026-06-14 03:35+04:00) Closed the isolated acceptance checkpoint: browser-verified a fresh `./run_acceptance.sh` session at `http://localhost:8510`, confirmed the unique temporary DB path and disabled Garmin login, exercised planning and AI coaching on the seeded dataset, fixed the narrow target-TSS slider step so the real `500..505` range stays interactive, and re-ran the full smoke suite (`89 passed`).
- [x] (2026-06-14 07:47+04:00) Completed the next Planning V2 slice: introduced `plan_adjustment` as a local replanning entity (`completed / skipped / reduced / unavailable`), limited replanning to the near-term horizon plus a short safe catch-up window, surfaced the checkpoint and replanning story on the planning page, browser-verified the new flow on a fresh acceptance runtime at `http://localhost:8510`, and re-ran the full smoke suite (`91 passed`).
- [x] (2026-06-14 08:01+04:00) Completed the next Planning V2 + Coach Explainability bridge slice: persisted compact planning checkpoints in SQLite, restored that context for dashboard and AI coaching beyond the immediate planning-page session, surfaced the latest checkpoint plus recent checkpoint history in the product UI, and re-ran focused smoke coverage (`8 passed`) plus the full smoke suite (`94 passed`).
- [x] (2026-06-14 16:02+04:00) Closed the real persisted-planning acceptance checkpoint: restarted the isolated `8510` runtime on the same temporary SQLite database, fixed acceptance boot so it preserves existing data and rehydrates demo-mode session flags instead of reseeding, browser-verified that the saved planning checkpoint still appears on both dashboard and AI coaching after restart, and re-ran the full smoke suite (`96 passed`).
- [x] (2026-06-14 16:44+04:00) Completed the next Planning V2 + Coach Explainability bridge slice: the dashboard now turns the persisted planning checkpoint into a real execution-feedback loop, locally rebuilds the near-term plan from the saved checkpoint even after the planning page is gone, stores the updated checkpoint back to SQLite, browser-verified the reduced-load replan flow on the isolated acceptance runtime at `http://localhost:8510`, and re-ran the full smoke suite (`98 passed`).
- [x] (2026-06-14 17:08+04:00) Completed the next Planning V2 + Coach Explainability bridge slice: execution checkpoints are now first-class coaching signals, the shared explainability helper carries their impact into dashboard `Почему сегодня такой фокус`, `Следующий шаг`, and AI-coach handoff/entry copy, the acceptance browser flow on a fresh isolated runtime at `http://localhost:8511` proved the same reduced-load checkpoint changes both dashboard and AI-coach guidance, and the full smoke suite now passes at `102 passed`.
- [x] (2026-06-14 17:28+04:00) Implemented the next Coach Explainability runtime slice: dashboard and AI-entry handoffs now carry a one-shot `operational_brief` response contract, the AI runtime turns the first post-handoff answer into a deterministic `Сегодня / Ближайшие 2-3 дня / Не делать / Почему` brief while preserving normal free-form chat afterward, added smoke coverage for both the dashboard-handoff click path and the modern-chat one-shot contract consumption path, and the full smoke suite now passes at `106 passed`.
- [x] (2026-06-14 21:59+04:00) Closed the real acceptance checkpoint for that runtime slice on the live `http://localhost:8511` acceptance app: clicking `😴 Открыть план восстановления` on the dashboard and then `😴 Спросить про восстановление` in AI coaching produced a first assistant reply with `🎯 Operational Brief` plus the required `Сегодня / Ближайшие 2-3 дня / Не делать / Почему` sections, while a follow-up user message (`Объясни подробнее, почему ты сделал такой вывод.`) returned an ordinary free-form assistant answer without repeating the structured wrapper.
- [x] (2026-06-14 22:32+04:00) Completed the next Planning V2 slice: added an in-place near-term editor for the next 7-10 plan days, wired manual edits into `daily_plan`, `session_templates`, weekly summaries, explainability notes, and persisted planning checkpoints, added focused smoke coverage for both manual day edits and unchanged-sport rescaling behavior, and re-ran the full smoke suite (`110 passed`).
- [x] (2026-06-14 22:58+04:00) Completed the next Planning V2 + Coach Explainability bridge slice: extracted a shared persisted `near_term_edit` summary, surfaced that manual-edit signal in dashboard checkpoint/history UI, AI coaching entry/explainability, and planning export/sync messaging, re-ran focused smoke coverage (`21 passed`) plus the full smoke suite (`112 passed`), and browser-verified on a fresh isolated acceptance runtime at `http://localhost:8513` that a cold-reloaded saved checkpoint visibly carries `Ручная правка` into both dashboard and AI coaching.
- [x] (2026-06-16 23:38+04:00) Completed the Planning UX hardening slice around the near-term editor: replaced the submit-only form flow with a live draft that shows `Черновик правок`, explicit `Было → Станет` diffs, reset/apply controls, and clearer saved-vs-draft messaging, fixed `off`-day duration so zero-load days now stay at `0` minutes, and made `ui.pages` imports lazy so planning helper tests no longer pull the whole page shell during collection. Focused validation passed on system Python for `test_planning_near_term`, `test_planning_page_explainability`, `test_training_planner_adaptive`, `test_planning_checkpoint_history`, `test_dashboard_ai_handoff`, `test_ai_coaching_recommended_prompt`, `test_coach_explainability`, and `test_ui_page_exports` (`51 passed` total). A full `tests/smoke` run and a fresh acceptance runtime were both blocked by separate pre-existing environment issues in `services/__init__.py` and `ai_trainer_env` runtime checks rather than by the planning UX code itself.
- [x] (2026-06-17 19:40+04:00) Closed the workspace-move hardening loop and the next Planning UX slice together: `python3 -m pytest tests/smoke -q` is green again at `124 passed`, `./run_acceptance.sh` starts cleanly again from the moved workspace by launching Streamlit through `python -m streamlit`, the near-term editor now previews touched weeks plus the future persisted `Ручная правка` label before apply, the weekly manual-edit note now counts only truly changed days, and the Streamlit width-compat layer no longer forces deprecated `use_container_width` on modern runtimes. Acceptance startup, `HTTP 200`, and `/_stcore/health -> ok` all passed on a fresh isolated `http://localhost:8510` runtime without the earlier width warnings.
- [x] (2026-06-17 20:01+04:00) Completed the next Planning V2 + Explainability slice on top of that editor: manual near-term edits now carry an explicit post-edit strategy (`Оставить как есть` / `Наверстать аккуратно` / `Беречь восстановление`), the planning model can safely redistribute part of the resulting `Δ TSS` across the next 1-2 weeks instead of stopping at the edited days, persisted checkpoints now retain both the manual-edit delta and the chosen follow-up behavior, and dashboard/AI explainability now describe not only that the horizon was edited but what happened to the following weeks afterward. Validation passed on focused planning/coaching smoke coverage (`39 passed`), the full smoke suite (`127 passed`), and a fresh isolated acceptance boot on `http://localhost:8510` with `HTTP 200` plus `/_stcore/health -> ok`.
- [x] (2026-06-17 23:59+04:00) Completed the next Planning UX hardening slice: manual near-term edits now receive a shared safety assessment (`low / medium / high`) based on added or removed load, quality/rest-day structure, follow-up strategy, and current fatigue state; the planning draft preview shows that assessment before apply; persisted checkpoints retain the same signal; and dashboard plus AI coaching now carry the same risk/guardrail language instead of only mentioning raw `Δ TSS`. Validation passed on focused planning/coaching smoke coverage (`43 passed` across the targeted files), the full smoke suite (`131 passed`), and a fresh isolated acceptance boot on `http://localhost:8510` with `HTTP 200` on `/` plus `/_stcore/health -> ok`.
- [x] (2026-06-18 23:59+04:00) Completed the next Planning UX hardening slice: risky near-term drafts now offer a one-click safer alternative that can switch the follow-up strategy (`keep -> protect_recovery` or `keep -> catch_up`) and minimally rewrite the touched days to reduce overload or underload risk instead of merely warning about it. The planning editor now shows the proposed safer outcome before apply, and one click rewrites the live draft in session state. Validation passed on focused planning-page/model smoke coverage (`22 passed` across `test_planning_near_term` and `test_planning_page_explainability`), the full smoke suite (`133 passed`), and a fresh isolated acceptance boot on `http://localhost:8510` with `HTTP 200` on `/` plus `/_stcore/health -> ok`.
- [x] (2026-06-19 18:48+04:00) Completed the next Planning UX hardening slice: near-term manual edits are now reversible through a real rollback path instead of only draft-level caution. Planning checkpoints now persist enough plan detail to restore the exact previous version, the latest manual-edit checkpoint stores the precise rollback target checkpoint id instead of relying on history order, the planning page shows a weekly before/after preview for that rollback, and one click restores the prior version and saves it back as the new current checkpoint. Validation passed on focused checkpoint/planning smoke coverage (`47 passed` across rollback, near-term, and explainability tests), the full smoke suite (`135 passed`), and a fresh isolated acceptance boot on `http://localhost:8510` with `HTTP 200` on `/` plus `/_stcore/health -> ok`.
- [x] (2026-06-19 19:25+04:00) Completed the next Planning V2 + Explainability slice: planning checkpoints are now explicit saved plan versions with provenance (`initial_plan / manual_edit / execution_feedback / restore_version`) instead of just raw summaries. The planning page now shows recent version history with week-level compare + restore for any recent checkpoint, dashboard and AI coaching expose the active version lineage, and execution-feedback summaries no longer misfire after an ordinary manual edit or restored version merely because the inherited `plan_adjustment` label stayed the same. Validation passed on focused smoke coverage across checkpoint, planning, dashboard, and coaching boundaries (`39 passed` across the targeted files), the full smoke suite (`138 passed`), and a fresh isolated acceptance boot on `http://localhost:8510` with `HTTP 200` on `/` plus `/_stcore/health -> ok`.
- [x] (2026-06-19 20:20+04:00) Completed the next Planning V2 + Explainability slice: execution feedback is now day-level instead of only week-level. Planning and Dashboard both render the same shared execution-reconciliation editor, the model now turns per-day outcomes into a concrete near-term fact summary (`planned vs actual TSS`, changed-day counts, inferred checkpoint type, and completion share), local replanning uses that summary without mixing actuals into `daily_plan`, and dashboard plus AI coaching now surface the same fact window after the checkpoint is saved. Validation passed on focused smoke coverage across planning execution, checkpoint history, dashboard handoff, planning explainability, coach explainability, recommended prompt, and page exports (`47 passed` across the targeted files), the full smoke suite (`141 passed`), and a fresh isolated acceptance boot on `http://localhost:8512` with `HTTP 200` on `/` plus `/_stcore/health -> ok` after skipping occupied legacy ports `8510/8511`.
- [x] (2026-06-19 21:15+04:00) Completed the next Planning V2 + Explainability slice: execution feedback now derives a compact weekly review on top of the new day-level facts instead of stopping at raw `planned vs actual` totals. Planning and Dashboard surface that weekly review with explicit deviations plus a selected response strategy, the planning model persists the same `execution_weekly_review` and `catch_up_strategy_override` through rebuild/checkpoint/history flows, AI coaching prompt context now carries the same weekly review into explainability and handoff copy, and the shared execution editor no longer crashes on stale `number_input` state when a row's allowed TSS collapses to zero. Validation passed on focused smoke coverage (`34 passed` across planning execution, checkpoint history, dashboard handoff, coach explainability, and recommended prompt), the full smoke suite (`145 passed`), and a fresh isolated acceptance boot on `http://localhost:8520` with `HTTP 200` on `/` plus `/_stcore/health -> ok` after skipping already occupied local ports `8510` and `8512`.
- [ ] Planning V2 — adaptive planning driven by load, availability, and interruptions.
- [ ] Coach Explainability — clearer reasoning and daily guidance on top of live metrics.

## Surprises & Discoveries

- Observation: weekly review by itself was still too abstract to close the execution-feedback loop.
  Evidence: after the day-level reconciliation slice, the product could explain `140/180 TSS` and name the lost key or long session, but the next step still depended on the user inferring what the next 2-3 days should look like. Adding a derived `execution_corrective_microcycle` exposed the missing contract immediately in planning history, dashboard checkpoint cards, and the first AI-coach handoff prompt.

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

- Observation: the AI coaching execution pipeline can be moved into `models/` without sacrificing the current Streamlit UX states around generation, tool processing, and chat persistence.
  Evidence: `models/ai_coach_runtime.py` now owns prompt construction, conversation-history assembly, tool-call parsing, and final-response post-processing, while the page still controls placeholder copy and message persistence. `ui/pages/ai_coaching.py` dropped again to `1045` lines and the full smoke suite increased to `73 passed`.

- Observation: the last AI coaching page seam was not just extractable; it also exposed a small real UX defect in the legacy helper.
  Evidence: after moving markdown-formatting and browser-side helpers into `ui/components/ai_coach_output.py`, a focused smoke test showed that the old streaming implementation was dropping the space between streamed sentences because the split pattern discarded separators. Fixing that inside the new output module preserved the final text exactly while keeping the same cursor-style streaming behavior, and the full smoke suite increased to `76 passed`.

- Observation: the planner's existing per-sport day weights were good enough for export fidelity, but not good enough on their own to imply a believable training week.
  Evidence: before the new slice, the planner could already constrain and redistribute weekly TSS, yet it had no explicit concept of `recovery`, `quality`, or `long` days. Adding a recovery-aware role layer on top of the existing daily expansion preserved the daily export shape while finally letting the product explain why one day is easy and another is key.

- Observation: the next safe planning improvement after recovery-aware roles is a metadata layer, not a rewrite of the daily tuple contract.
  Evidence: the new `session_templates` list can carry `phase / sport / role / focus / duration / export_name / description` for every day while `daily_plan` still stays as `(datetime, total_tss, parts)`. After wiring the metadata into CSV/ICS/Intervals/FIT/TCX paths, the full smoke suite still passed at `84 passed`, which would have been much riskier with a broad planner/export contract change.

- Observation: local browser verification of this repository now has two separate operational gates: Streamlit port binding and onboarding state.
  Evidence: starting `./run.sh` inside the sandbox failed with `PermissionError: [Errno 1] Operation not permitted` when binding port `8501`, but the same command succeeded once run unsandboxed. After that, the browser verified the onboarding page on `http://localhost:8501/`; proceeding to demo-mode clickthrough would have replaced the local cache, so the safe verification stopped at app boot for this slice.

- Observation: acceptance verification needs a runtime boundary, not just a warning in the onboarding copy.
  Evidence: the old demo path already warned that it would replace the local cache, but that still made browser acceptance awkward because the warning was true. The new `./run_acceptance.sh` launcher instead points Streamlit at a unique temporary SQLite file, turns on acceptance flags, and lets the app auto-seed a deterministic demo dataset there. After the change, the smoke suite increased to `88 passed` while the main `ai_trainer.db` path stayed untouched.

- Observation: the in-app browser dev-log feed is noisy across local Streamlit restarts and cannot be treated as a strict per-run console transcript.
  Evidence: after restarting the acceptance app on `http://localhost:8510`, the browser log feed still showed earlier `8501` health-check noise and one pre-fix narrow-slider warning timestamped `2026-06-14T03:21:55.972Z`, even though the fresh acceptance session displayed a new temporary DB path and the real `500..505` TSS control moved from `500` to `501` during direct interaction.

- Observation: local replanning can be added as a short-horizon planner overlay without breaking the existing export and sync contract.
  Evidence: the new `plan_adjustment` slice only changes the near-term weekly TSS plan and explanation summary, while the same acceptance run still showed `📅 Экспорт в календарь (ICS)`, `📤 Intervals.icu`, and `🧩 Экспорт тренировки (FIT-CSV / FIT / TCX)` after building the replanned output.

- Observation: dashboard and AI coaching do not need the full exported daily plan payload to preserve planning context across sessions.
  Evidence: saving a compact checkpoint snapshot with goal metadata, weekly summary rows, and constraint summary was enough to restore plan-aware explainability, render a recent-checkpoint card on the dashboard, and keep AI coaching aligned with the latest replanning state after the user leaves the planning page.

- Observation: acceptance restart needs two separate persistence guarantees, not just a durable SQLite file.
  Evidence: the first real restart attempt exposed two independent failures: acceptance boot was reseeding and wiping the isolated DB on each new browser session, and once that was fixed the app still fell back to the welcome flow because `demo_mode` and related session flags were not rehydrated from the preserved isolated dataset. After fixing both boundaries, the same saved planning checkpoint remained visible on dashboard and AI coaching after a cold restart of `http://localhost:8510`.

- Observation: the compact planning checkpoint is now rich enough not only to explain the last plan, but also to regenerate a safe short-horizon replan from outside the planning page.
  Evidence: after restoring only goal metadata, weekly summary rows, constraint summary, `start_week`, and planner mix/weight metadata from SQLite, the dashboard acceptance run on `http://localhost:8510` accepted `Нагрузка урезана` at `60%`, saved a new checkpoint, reduced total load from `1197` to `1157` TSS, and rendered the new delta summary without relying on the original in-memory planning-page state.

- Observation: execution feedback needs to remain visible even when readiness stays in a recovery-first state; otherwise the product technically remembers the checkpoint but still reads as if only readiness mattered.
  Evidence: on a fresh isolated acceptance dataset at `http://localhost:8511`, the athlete still started in a `Фокус на восстановлении` state after a reduced-load checkpoint. The correct product behavior was not to suppress recovery, but to inject checkpoint-aware guardrails directly into `Сегодня / Ближайшие 2-3 дня / Следить за` on both dashboard and AI coaching. After the change, the live UI explicitly added `Считайте облегчённую неделю новой верхней границей...`, `После урезанной недели возвращайте нагрузку только ступенчато...`, and `Не компенсируйте урезанный объём резким ростом интенсивности.`

- Observation: prompt-only shaping is not a strong enough contract for the first post-dashboard coaching answer because provider behavior and mock responses can still drift away from the intended operational format.
  Evidence: the current acceptance/runtime stack uses both real providers and a deterministic mock provider, and the mock provider intentionally returns ordinary free-form text. The stable solution was therefore to carry a compact response contract through the handoff and enforce the visible `Operational Brief` structure inside the runtime wrapper, not to rely on provider compliance alone.

- Observation: acceptance browser verification on an already running local Streamlit tab is not a reliable proof that the current planning code is loaded, because both `run.sh` and `run_acceptance.sh` disable file watching.
  Evidence: the existing `http://localhost:8511` acceptance tab still built plans without the new `✍️ Редактировать ближайшие 7-10 дней` section after the code was already green in tests, while a fresh isolated instance on `http://localhost:8512` immediately rendered the new near-term editor and accepted a manual edit.

- Observation: browser automation against the inline near-term editor is materially less stable than downstream checkpoint verification, even on a fresh isolated runtime.
  Evidence: on `http://localhost:8513`, the browser could build the plan and expose the editor plus editable day rows, but repeated attempts to mutate the TSS inputs failed because the Streamlit widgets alternated between stale/invisible Playwright targets and clipboard-backed typing constraints. Seeding the isolated SQLite checkpoint with the same saved `near_term_edit` signal and reloading the app immediately proved the user-visible persistence surfaces on dashboard and AI coaching instead.

- Observation: `ui.pages` package import was still much heavier than the planning helper tests needed because package import eagerly pulled unrelated pages and, through them, heavyweight services.
  Evidence: `python3 -X importtime -c "import ui.pages.planning"` showed import time jumping through `ui.pages.activities` and then into `services.acceptance_mode` before ever reaching planning helpers; replacing `ui/pages/__init__.py` with lazy render-function wrappers made `import ui.pages.planning` return immediately again.

- Observation: the current full-smoke and acceptance-launch blockers are no longer inside the planning page itself, but in shared environment/import boundaries outside this slice.
  Evidence: `python3 -m pytest tests/smoke -q` hung during collection at `tests/smoke/test_acceptance_mode_service.py` while importing `from services import acceptance_mode`, and interrupting the run showed the traceback stopping in `services/__init__.py`. Separately, `ACCEPTANCE_PORT=8514 ./run_acceptance.sh` stalled inside `scripts/doctor_env.py` while probing `import streamlit` through `ai_trainer_env`, matching the earlier `pluggy`/venv drift symptoms.

- Observation: the near-term editor had a subtle zero-load inconsistency before this slice: a day turned into `off` could still preview and persist a non-zero duration.
  Evidence: the new draft summary test first failed with `assert 30 == 0` for an `off` day, which traced back to `_estimate_session_duration_minutes(...)` returning a floor duration even when `total_tss <= 0`. Returning `0` for zero-load days fixed both the draft preview and persisted session-template metadata.

- Observation: after the workspace move, the acceptance launcher failure was not in `streamlit` importability, but in the virtualenv wrapper script itself.
  Evidence: `./run_acceptance.sh` passed `doctor_env.py check --runtime` and `import streamlit`, but then crashed with `ai_trainer_env/bin/streamlit: .../Documents/GitHub/ai_trainer/.../python3: bad interpreter`. Switching launchers to `python -m streamlit` fixed startup without depending on a rewritten shebang.

- Observation: the first weekly draft-preview test exposed that manual-edit week notes were overstating the number of edited days.
  Evidence: a draft that changed only one row still produced `ручная правка: 7 дн., Δ +15 TSS` because `apply_near_term_day_edits(...)` incremented `edited_days` for every row in the horizon, not only changed rows. Moving the counter update inside the `changed` branch made both the preview and persisted checkpoint truthful.

- Observation: the initial width-compat layer solved old Streamlit support but reintroduced warnings on modern Streamlit by backporting too aggressively.
  Evidence: acceptance boot on Streamlit `1.57.0` emitted repeated `Please replace use_container_width with width` warnings even after the planning page itself switched to `width="stretch"`. The root cause was `utils/streamlit_compat.py` always translating `width='stretch'` into `use_container_width=True`; making that translation conditional on the target function lacking a native `width` parameter removed the warnings while keeping backward compatibility tests green.

- Observation: a manual near-term edit that changes the first 7-10 days is not product-complete unless the next 1-2 weeks have an explicit policy too.
  Evidence: before this slice, the editor could truthfully mutate the near horizon and persist that fact, but the weekly story ended there: the rest of the plan stayed silent about whether the removed load was intentionally dropped, partly returned, or compensated by a lighter follow-up block. Adding an explicit post-edit strategy exposed that missing contract immediately in the preview, checkpoint summary, and AI prompt context.

- Observation: week-level redistribution after a manual edit must update `daily_plan`, `session_templates`, and `weekly_summary` together or explainability drifts away from the exportable plan.
  Evidence: the first implementation of future-week redistribution updated `daily_plan` and `weekly_tss_plan` but left the cached `weekly_summary` totals stale for those weeks. Recomputing the touched weeks from the scaled daily rows fixed the mismatch and kept comparison tables, checkpoint storage, and exports aligned.

- Observation: raw `Δ TSS` is not enough to warn about a risky manual edit, because the same delta can be safe or dangerous depending on current fatigue and whether the edit removes rest or adds intensity.
  Evidence: the new smoke coverage distinguishes a low-risk recovery cut (`catch_up` after removing load) from a high-risk overload (`keep` plus added quality/load on top of `Накопленная усталость`) even though both cases are just manual edits to the same 7-day window.

- Observation: once the editor can classify a draft as risky, a warning-only UI is not enough; the next trust gap is whether the product can suggest a safer rewrite without forcing the user to reverse-engineer it manually.
  Evidence: the new `build_safer_near_term_draft(...)` helper can turn a `high` overload draft into a lower-risk variant by switching the post-edit strategy and restoring or softening specific days, while the new smoke coverage proves that the helper returns `None` for already low-risk drafts instead of rewriting them gratuitously.

- Observation: rollback for the latest manual edit cannot safely depend on `planning_checkpoint_history[1]`, because after one rollback that ordering naturally turns into a redo candidate rather than the true parent version.
  Evidence: the new slice had to introduce an explicit `near_term_edit_rollback_target_checkpoint_id` plus direct database lookup by id; otherwise a restored checkpoint would immediately point back to the just-undone edit simply because it was now the second-most-recent row.

- Observation: legacy compact checkpoints need a restore path that respects the saved `weekly_tss_plan`, not a fresh pass through planning constraints.
  Evidence: the first fallback implementation used `rebuild_goal_plan_with_adjustment(...)` and changed a saved `[180, 220, 240]` weekly plan into `[145, 230, 230]`, which is acceptable for execution replanning but wrong for version rollback. Reconstructing daily/session details directly from the stored weekly plan fixed that mismatch.

- Observation: acceptance boot can still show a transient `streamlit-runtime` timeout during the first runtime probe without indicating a product regression.
  Evidence: on `2026-06-19`, the first acceptance health check timed out after `15s`, `doctor_env.py` immediately retried and confirmed `streamlit-runtime: 1.57.0`, and the same run then booted `http://localhost:8510` successfully with `HTTP 200` on `/` plus `ok` on `/_stcore/health`.

- Observation: once checkpoints can represent manual edits, restores, and execution replans, `plan_adjustment_label` is no longer a safe proxy for "the latest execution checkpoint".
  Evidence: both a restored version and a manual near-term edit can legitimately inherit the same persisted `plan_adjustment` payload from the plan they were based on. The correct fix was to persist explicit checkpoint provenance and gate execution-feedback summaries on that lineage instead of on labels or recency alone.

- Observation: the next trust gap after versioned checkpoints was not "which week status was chosen", but "what actually happened inside the near-term window".
  Evidence: the old `completed / skipped / reduced / unavailable` checkpoint model could only approximate reality through `missed_sessions` or one coarse `reduced_load_share`, which was enough for local replanning math but not enough to explain why a checkpoint existed or what exact short-term load delta it represented. Day-level reconciliation closes that gap without rewriting the whole planning engine.

- Observation: actual execution facts should not overwrite the future-looking `daily_plan`; they need their own persisted summary.
  Evidence: turning `daily_plan` rows themselves into "actuals" would blur the boundary between planned exportable sessions and historical execution. The stable contract was to persist a normalized `execution_reconciliation` summary inside the checkpoint/constraint payload and let local replanning consume that evidence while keeping `daily_plan` as a plan.

- Observation: Streamlit widget state for day-level execution editing can outlive the current row contract and crash the page even when the underlying planning data is valid.
  Evidence: the live dashboard hit `StreamlitValueAboveMaxError: The value 41 is greater than the max_value 0` after a row's current planned TSS collapsed to zero while the persisted widget key still held an earlier positive value. The stable fix was not just clamping a raw number, but separating logical `actual_tss` state from the widget key and resolving outcome-aware display values (`as_planned -> planned`, `missed/unavailable -> 0`, `reduced -> clamped custom value`) before rendering the input.

## Decision Log

- Decision: persist the execution-driven next-step as `execution_corrective_microcycle` inside `constraint_summary.plan_adjustment` rather than as a separate planning mode or top-level checkpoint type.
  Rationale: the microcycle is not an independent source of truth; it is the concrete follow-up generated from the already persisted execution facts and weekly review. Keeping it adjacent to `execution_reconciliation` and `execution_weekly_review` preserves one execution-feedback contract that can be summarized, versioned, and re-explained consistently across Planning, Dashboard, and AI Coaching.
  Date/Author: 2026-06-19 / Codex

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

- Decision: checkpoint provenance must be explicit persisted metadata (`initial_plan / manual_edit / execution_feedback / restore_version`), not inferred from history position or inherited labels.
  Rationale: once a restored version can sit above its parent in recency order, and once ordinary manual edits can preserve earlier `plan_adjustment` data, UI and coaching surfaces need a durable source-of-truth for what this version actually is. Provenance also makes version history, compare/restore, and execution-feedback gating use the same contract instead of separate heuristics.
  Date/Author: 2026-06-19 / Codex

- Decision: model day-level execution facts as a separate normalized `execution_reconciliation` payload inside the checkpoint/plan-adjustment contract rather than by mutating planned daily rows into historical results.
  Rationale: the planning engine still needs a future-oriented `daily_plan` for exports, previews, and near-term editing. A separate persisted fact summary can drive local replanning, dashboard cards, and AI explainability without corrupting that boundary, and it keeps the new day-level UI compatible with the older weekly checkpoint math.
  Date/Author: 2026-06-19 / Codex

- Decision: derive the next execution-feedback UX layer as a compact `execution_weekly_review` plus an explicit selected response strategy on top of day-level reconciliation, instead of introducing a second parallel execution model.
  Rationale: the new day-level rows already describe what materially happened. The missing product behavior was not more raw data, but a compact user-facing interpretation: which key deviations matter this week, whether the week now looks compressed or partially lost, and whether the safer next reaction is `Беречь восстановление` or `Наверстать аккуратно`. Persisting that interpretation inside `plan_adjustment` keeps Dashboard, Planning, checkpoint history, and AI coaching on one shared contract while leaving `daily_plan` and the replanning math intact.
  Date/Author: 2026-06-19 / Codex

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

- Decision: compute manual-edit risk inside `models/planning_near_term.py` but normalize and present it only through `models/planning_summary.py`.
  Rationale: the heuristics depend on local planning mechanics such as edited-day deltas, removed rest days, follow-up redistribution, and current fatigue state, so the source of truth belongs next to the edit model. The user-facing badge, description, and guardrail still need one shared renderer for planning, checkpoints, dashboard, and AI coaching, so those strings should continue to flow through the shared summary layer.
  Date/Author: 2026-06-17 / Codex

- Decision: implement the safer alternative as a model helper that rewrites the live draft and selected follow-up strategy, not as a separate “safe apply” planner path.
  Rationale: the user is still editing one near-term draft, not choosing between two different planning systems. Returning a normalized safer draft from `models/planning_near_term.py` lets the Streamlit page show exactly what would change, apply it back into the existing session-state controls with one click, and keep the same preview/apply flow, tests, and persistence contract.
  Date/Author: 2026-06-18 / Codex

- Decision: make rollback target selection explicit at checkpoint-save time instead of inferring it later from recency ordering.
  Rationale: once rollback itself creates a new latest checkpoint, “latest minus one” stops meaning “version before the last manual edit.” Persisting `near_term_edit_rollback_target_checkpoint_id` on the manual-edit checkpoint keeps undo semantics stable across reloads and additional history entries.
  Date/Author: 2026-06-19 / Codex

- Decision: enrich persisted planning snapshots with `daily_plan`, `session_templates`, and near-term rollback metadata even though the top-level checkpoint summary remains compact.
  Rationale: dashboard and AI coaching still only need compact summaries, but reversible planning edits require full-fidelity restore data. Storing the richer detail inside `goal_plan_snapshot` preserves the lightweight user-facing summary while making rollback and exact version comparison possible.
  Date/Author: 2026-06-19 / Codex

- Decision: modularize `ui/pages/ai_coaching.py` by extracting provider setup/status and entry/handoff guidance first, while keeping the old helper names importable from `ui.pages.ai_coaching`.
  Rationale: those two areas were the clearest UI-facing seams and the lowest-risk extraction targets. Preserving the old import contract let the repository keep its existing smoke tests and page callers while still shrinking the monolith and creating clearer reuse boundaries in `ui/components/*`.
  Date/Author: 2026-06-13 / Codex

- Decision: make the next extraction target the chat shell around `render_ai_chat_page(...)`, not the AI/tool-calling engine.
  Rationale: the shell owns page-local concerns such as Streamlit layout, sidebar diagnostics, message history presentation, and quick-question actions, which are easier to isolate than the lower-level response pipeline. That gives another meaningful size reduction and cleaner boundaries without risking the more complex tool execution path yet.
  Date/Author: 2026-06-13 / Codex

- Decision: move the monthly progress-report core into `models/ai_coach_progress.py`, but keep markdown presentation wiring and public helper compatibility in `ui.pages.ai_coaching`.
  Rationale: the progress report is mostly data interpretation and recommendation logic, which belongs with the coaching model layer rather than a Streamlit page. The page still owns the existing `format_tool_result(...)` presentation contract, so the safest extraction is a model-level core that accepts a formatter callback while preserving the old page imports for current callers and smoke tests.
  Date/Author: 2026-06-13 / Codex

- Decision: extract the tool-calling and response-execution turn into `models/ai_coach_runtime.py`, but keep `process_modern_chat_message(...)` and `process_chat_message(...)` in the page layer as Streamlit adapters.
  Rationale: the runtime logic is provider- and tool-oriented, not UI-oriented, so it belongs in `models/`. The page still has to own placeholder states, `st.chat_message(...)`, reruns, and persistence side effects, so the safest split is a reusable runtime core with page-level wrappers instead of trying to eliminate the page handlers entirely in one step.
  Date/Author: 2026-06-13 / Codex

- Decision: move `format_tool_result(...)`, `simulate_streaming_response(...)`, and `speak_text(...)` into `ui/components/ai_coach_output.py`, not into `models/`.
  Rationale: those helpers are output-oriented rather than reasoning-oriented. They render markdown for people and emit browser-side JavaScript for Streamlit, so they belong with the UI layer even though the page should not own them directly. Keeping page-level wrappers preserves the old import contract while making `ui/pages/ai_coaching.py` a genuinely thin adapter.
  Date/Author: 2026-06-13 / Codex

- Decision: add recovery-aware week structure as a separate role layer on top of the current daily TSS expansion, instead of replacing the existing mix/weight planner with a brand-new scheduler.
  Rationale: the current planner already has valuable constraints, per-sport mix overrides, export integrations, and smoke coverage. Replacing it wholesale would be high-risk. A role layer (`off / recovery / easy / quality / long`) gives the product a much more believable weekly structure, preserves the daily tuple contract used by exports and `Intervals.icu`, and creates a clean stepping stone toward richer session planning later.
  Date/Author: 2026-06-13 / Codex

- Decision: implement the first session-template slice as planner-owned aligned metadata, and treat export/sync consumers as optional adopters of that metadata.
  Rationale: the product needed richer per-day semantics than `total_tss + sport parts`, but the current planner/export stack already had many consumers that assume the old tuple shape. A parallel metadata list is the lowest-risk way to add `phase`, `session role`, `focus`, `duration`, and human-readable naming now, while keeping every old integration path backward-compatible until a later, larger planning rewrite is justified.
  Date/Author: 2026-06-13 / Codex

- Decision: make acceptance mode a separate launcher and runtime contract instead of overloading the normal `run.sh` path.
  Rationale: the repository now has two distinct intents. Normal `./run.sh` should keep representing the user's real local app state, including `ai_trainer.db` and optional Garmin connections. Acceptance verification needs the opposite: a deterministic, disposable runtime on a dedicated port with demo data and no chance of touching the real account or database. A dedicated `./run_acceptance.sh` script plus app-side acceptance guards keeps those intents explicit and safer.
  Date/Author: 2026-06-13 / Codex

- Decision: treat the acceptance checkpoint as `smoke suite + functional browser proof`, not as `empty dev console`, in this local Codex environment.
  Rationale: the in-app browser retains stale log history across local restarts, so the reliable acceptance signal is a fresh isolated DB, visible runtime markers, successful planning/AI navigation, and direct widget interaction on the current session rather than zero historical console lines.
  Date/Author: 2026-06-14 / Codex

- Decision: implement replanning as a `plan_adjustment` entity that only mutates the near-term horizon plus a short safe catch-up window, not as a full-plan regeneration trigger.
  Rationale: the product gap is around truthful response to missed or constrained execution, not around recomputing every distant week from scratch. A short-horizon overlay is safer, easier to explain, and preserves the repository's current export/sync contracts while still making planning meaningfully more adaptive.
  Date/Author: 2026-06-14 / Codex

- Decision: persist planning context as compact checkpoint snapshots, not as full exported plan payloads.
  Rationale: dashboard and AI coaching only need the goal shape, recent weekly story, and applied constraint summary in order to explain the latest plan or replanning outcome. Storing that compact checkpoint in SQLite keeps the persistence boundary small, avoids coupling the database to every export-oriented daily artifact, and is still rich enough to rebuild plan-aware handoff context on later page visits.
  Date/Author: 2026-06-14 / Codex

- Decision: enforce the first post-handoff coaching reply as a one-shot runtime response contract, not as a permanent chat mode or a prompt-only best effort.
  Rationale: the user-facing requirement is narrow and operational: the first answer after a dashboard or recommended-entry handoff should reliably return `Сегодня / Ближайшие 2-3 дня / Не делать / Почему`. Making that contract one-shot keeps the chat flexible after the initial action, while enforcing it in the runtime wrapper keeps the behavior deterministic across real and mock providers.
  Date/Author: 2026-06-14 / Codex

- Decision: acceptance auto-demo must seed only empty isolated databases, and must restore demo-mode session state when an isolated dataset already exists.
  Rationale: the acceptance launcher is meant to provide a safe disposable environment, but the persisted-planning acceptance checkpoint specifically requires cold-restart continuity on the same temporary DB. Reseeding on every new browser session destroys the very artifact being verified, while preserving the DB without restoring session-only demo flags drops the app back into the welcome screen. The correct contract is therefore `seed if empty, otherwise rehydrate`.
  Date/Author: 2026-06-14 / Codex

- Decision: rebuild dashboard execution-feedback replans from persisted checkpoint context instead of requiring a live planning-page session.
  Rationale: execution feedback belongs to the daily operational loop on the dashboard, not only to the page where the original plan was created. Reconstructing the near-term plan from the compact checkpoint plus planner metadata keeps the flow durable across restarts and lets both dashboard and AI coaching continue from the latest saved checkpoint.
  Date/Author: 2026-06-14 / Codex

- Decision: let execution feedback augment recovery guidance as well as power a dedicated execution-review focus.
  Rationale: a real athlete can be both fatigued and coming off a meaningful execution checkpoint at the same time. If recovery remains the top-level focus, the checkpoint still has to change the visible guardrails; otherwise the product falls back to sounding readiness-only again. The shared helper now treats actionable checkpoints as either a primary `execution_review` focus when readiness is otherwise calm, or as mandatory guardrail text inside the recovery/form guidance when readiness is already red.
  Date/Author: 2026-06-14 / Codex

- Decision: implement near-term planning edits as a 7-10 day overlay on top of the existing `daily_plan + session_templates` contract instead of introducing a separate calendar editor or forcing a full plan rebuild.
  Rationale: the product gap is local plan truthfulness, not yet a full scheduling system. Updating the first 7-10 days in place keeps the existing exports, explainability tables, and persisted checkpoint flow intact while still letting the user correct the next week based on real life.
  Date/Author: 2026-06-14 / Codex

- Decision: close the persisted manual-edit acceptance slice by seeding a near-term-edited checkpoint into the isolated acceptance database and cold-reloading the app, instead of brute-forcing the inline Streamlit editor through flaky browser automation.
  Rationale: the behavior under test for this slice is that a saved manual near-term edit becomes a first-class persisted coaching signal across dashboard and AI coaching. The editor mechanics themselves were already covered by smoke tests and a prior real manual edit on `http://localhost:8512`; the remaining acceptance gap was persistence and downstream propagation, which the DB-seeded cold-reload path proves deterministically.
  Date/Author: 2026-06-14 / Codex

- Decision: rework the near-term editor around a persistent live draft with explicit reset/apply controls instead of keeping the original `form`-only submit flow.
  Rationale: the old form hid all pending changes until submit time, gave no compact diff preview, and made the product harder to reason about during both manual use and browser verification. A live draft keeps the same planning contract but makes the UI honest about what is currently saved, what is only a draft, and what exact day-level changes are about to be applied.
  Date/Author: 2026-06-16 / Codex

- Decision: make `ui.pages` exports lazy at the package boundary instead of requiring every test that touches one page helper to import all page modules up front.
  Rationale: planning helper tests only need `ui.pages.planning`, but the eager `ui.pages.__init__` path still pulled unrelated pages and their heavy service imports into collection. Lazy wrappers preserve the public import surface used by `app.py` and the smoke suite while keeping page-local helper imports cheap and predictable.
  Date/Author: 2026-06-16 / Codex

- Decision: launch Streamlit through `python -m streamlit` in both `run.sh` and `run_acceptance.sh` instead of trusting the checked-in `ai_trainer_env/bin/streamlit` wrapper.
  Rationale: after the workspace move, the Python interpreter inside the virtualenv still worked and `import streamlit` still passed, but the wrapper script carried a stale absolute shebang from the old checkout path. Module-based launch keeps both virtualenv and system-runtime flows working without depending on wrapper regeneration.
  Date/Author: 2026-06-17 / Codex

- Decision: extend the near-term draft UX with week-level preview and the future persisted `near_term_edit` label before apply.
  Rationale: the live draft already showed day-level diffs, but it still made the user infer how those edits would change weekly totals and what checkpoint signal the rest of the product would see afterward. Showing the touched weeks and projected persisted label before apply makes the editor more trustworthy without changing the underlying planning model.
  Date/Author: 2026-06-17 / Codex

- Decision: make the Streamlit width-compat layer signature-aware so it only backports `width='stretch'` when the runtime truly lacks native `width` support.
  Rationale: unconditional translation to `use_container_width=True` kept older versions working but polluted modern acceptance runs with deprecation warnings. Signature-aware patching preserves old-runtime compatibility while letting new Streamlit builds use the native `width` API directly.
  Date/Author: 2026-06-17 / Codex

- Decision: treat the aftermath of a manual near-term edit as a first-class planning strategy, not as an implicit side effect of the edited days alone.
  Rationale: once the user manually changes the near horizon, the next meaningful question is no longer only “what changed today?” but also “what should happen to the next 1-2 weeks because of that change?” Encoding `keep / catch_up / protect_recovery` directly into `near_term_edit` keeps the behavior explicit, persistable, and explainable across dashboard and AI coaching.
  Date/Author: 2026-06-17 / Codex

- Decision: implement post-edit redistribution as local week-level scaling inside `models/planning_near_term.py` instead of forcing a full plan rebuild through `apply_planning_constraints(...)`.
  Rationale: the user is editing an already accepted local plan, not asking to regenerate the whole cycle from scratch. Scaling only the next 1-2 weeks preserves the existing daily/session-template contract, keeps the change small and deterministic, and lets exports plus checkpoint summaries continue to describe one coherent plan artifact.
  Date/Author: 2026-06-17 / Codex

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

Planning V2 is accepted when weekly planning reacts to time constraints and interruptions instead of only ramp logic and static target ranges, and when near-term manual edits remain coherent after persistence and reload.

Coach Explainability is accepted when the dashboard and AI coaching can surface the main reasoning signals behind a recommendation, including recent execution or manual near-term plan changes, without requiring the user to reverse-engineer them from charts or a long-form chat answer.

## Outcomes & Retrospective

This section starts empty on purpose. The previous plan ended with a working product flow. This plan begins at the moment where the product needs to become a durable system rather than a successful sequence of flows.

The latest slice closes the next abstraction gap in execution feedback. The product no longer stops at a persisted fact window plus a weekly headline; it now turns that evidence into an explicit corrective microcycle for the next 2-3 days, including one concrete action, the next-window expectation, and one guardrail that survive local replanning, checkpoint persistence, dashboard summary cards, planning version history, and AI-coach prompt context. That makes the handoff from “what happened” to “what do I do next” materially more coach-like.

This was also the right level of scope for the next planning improvement. A separate planning mode would have fractured the checkpoint story and forced every downstream surface to decide whether to trust weekly review, day-level reconciliation, or a parallel follow-up entity. Keeping the microcycle inside the existing execution checkpoint contract means every surface now reads the same lineage: fact window, weekly review, then short corrective window.

The latest slice closes the next execution-feedback trust gap. The product no longer stops at "140 of 180 TSS happened"; it now turns day-level facts into a compact weekly review with a headline, concrete deviations such as a lost key or long session, and an explicit follow-up response strategy that survives rebuild, checkpoint persistence, dashboard cards, planning history, and AI coaching context. That makes the execution-feedback loop feel more like coaching and less like a bookkeeping delta.

This slice also tightened a real runtime seam, not just the UX copy. The shared execution editor had a latent Streamlit-state failure where an old widget value could survive after the allowed max dropped to zero and crash the page. Moving to outcome-aware actual-TSS resolution plus separate logical/widget keys keeps the editor stable while preserving the user-visible day-level workflow, and the new smoke coverage plus full `145 passed` run make that regression much harder to reintroduce silently.

The latest slice turns planning checkpoints from "whatever was saved last" into explicit plan versions with lineage. Each saved checkpoint now records whether it came from the initial build, a manual near-term edit, an execution-feedback replan, or a restore of a prior version; the planning page can compare the active plan against several recent versions and restore any of them; and dashboard plus AI coaching now surface that provenance directly instead of relying on raw checkpoint labels alone.

That change also fixed a subtle trust bug. Before explicit provenance, a manual edit or restored version could still carry an inherited `plan_adjustment` payload and therefore look like a fresh execution checkpoint to downstream explainability surfaces. Gating execution-feedback summaries on the checkpoint's real source keeps the coaching story honest: execution feedback remains an operational signal, while manual edits and restored versions stay version-history events.

The new execution-reconciliation slice makes that operational signal far more concrete. Instead of saving only a coarse week-level status, the product can now capture what happened day by day in the near-term window, compress that into a persisted `planned vs actual` fact summary, and use that summary consistently in local replanning, checkpoint cards, and AI coaching context. This materially improves trust because the product can now explain not only that a checkpoint exists, but what real short-term load delta created it.

Equally important, this was implemented without breaking the planning contract itself. `daily_plan` remains a forward-looking plan used for exports and editing, while historical reality is stored as a separate normalized `execution_reconciliation` summary inside the checkpoint payload. That keeps planning semantics clean while still letting the adaptive engine react to real execution.

The first hardening slice immediately justified the new plan. The upstream `garth` project itself now says that new logins are broken and the library is deprecated, while the local virtual environment adds an extra layer of corruption on top by shipping a namespace package with missing public API exports. The right response was not to add more retries, but to make AI Trainer stop treating `garth` fresh login as a normal path and to fail soft into `garminconnect` instead.

The next hardening slice turned that into a real product contract. Fresh Garmin authentication now belongs solely to `garminconnect`, while `garth` remains available only as legacy diagnostics and optional runtime context. That is a more honest user-facing model and a better base for future integrations such as `Intervals.icu`, which fits the planning/export side of the product better than the primary ingestion path.

The first Planning V2 slice is now real, not hypothetical. The planning page can export its generated daily plan to `Intervals.icu` through a dedicated service adapter, the environment contract is documented in `.env.example`, and the UI behaves sensibly even when the integration is not configured yet. That is the correct shape for this phase: additive, testable, and useful before the larger adaptive-planning work begins.

The first live user verification also revealed a useful production detail: `Intervals.icu` is not rejecting the API key or the endpoint shape, but it does reject the default `urllib` client signature. That bug belongs in the adapter boundary, not in the planning UI. Fixing it there keeps the integration predictable for both connection checks and future event creation.

The next Planning V2 slice keeps that same additive pattern. The planner still emits the old aligned daily tuples for forecast and load simulation, but now also emits explicit session metadata that explains what each day is meant to be. That immediately improves the planning page table and makes exports less generic: a `quality` bike day can now carry a meaningful name, a better Intervals.icu description, and a different FIT/TCX step structure from a `recovery` run.

This slice also clarified the safe boundary for real browser verification in this repository. Booting the app from the current worktree is now verified again, but a full demo-mode clickthrough would mutate the local cache and therefore should be treated as an explicit acceptance step, not as a silent background check. For day-to-day coding, the full smoke suite plus a boot-level browser sanity check is the right default checkpoint unless the user wants to spend a fresh demo or real-provider session on product acceptance.

The new acceptance-mode slice turns that boundary into an actual contributor tool. Instead of tiptoeing around the normal demo-mode button, a contributor can now run `./run_acceptance.sh`, which launches the app on a dedicated port against a unique temporary SQLite database, auto-loads the deterministic demo dataset, disables real Garmin login, and provides an explicit UI reset path for reseeding the dataset mid-session. That is a much better base for future browser-based acceptance checks on planning features because the runtime itself is now safe by construction.

The real acceptance loop is now closed for this slice. The app can discover the configured `Intervals.icu` account, validate the connection from the planning page, send at least one planned workout event, and confirm that event through provider-side read-back. That is enough evidence to treat the integration as production-shaped rather than prototype-shaped.

The isolated acceptance runtime is now also proven as a contributor checkpoint, not just as an implementation detail. A fresh `8510` session showed a new temporary SQLite path in the UI, disabled the real Garmin login path, rendered both the planning and AI coaching pages against seeded data, and exposed the existing export/sync surfaces after building a plan. Restarting that runtime and interacting with the narrow `500..505` target-TSS control then confirmed the last planning regression fix directly in the real browser: the value advanced from `500` to `501`, which would have been impossible with the old hardcoded `step=25`.

The remaining nuance is verification hygiene rather than product behavior. The Codex in-app browser's dev-log feed kept stale entries from earlier local sessions, including old port-`8501` noise and a pre-fix slider warning, so a strict "console must be empty" rule would misclassify a healthy acceptance run. The correct hardening standard for this repository is therefore a green smoke suite plus functional browser proof on a fresh isolated runtime, not raw log emptiness.

The next Planning V2 slice finally gives the planner a truthful answer to "what if this week didn't happen the way we planned?" Instead of forcing the user to rebuild the whole cycle or silently accept stale numbers, the planning page now accepts a local execution checkpoint (`выполнено / пропущено / урезано / ограничено`), mutates only the near-term horizon, and optionally returns a small safe amount of load inside a short local window when the user selects `Наверстать аккуратно`. That keeps the adaptation grounded in the next 7-14 days instead of smearing it across the whole season.

This slice is valuable not only because it changes numbers, but because it changes trust. The planning page now explains the local replanning story in the same place where it already explains availability and interruption logic: the scenario card includes the checkpoint, the planner-decision card includes local return load when it exists, and the weekly comparison stays aligned with exportable plan data. In the fresh acceptance verification on `http://localhost:8510`, the app rendered the new `♻️ Локальная перепланировка` controls, accepted a reduced-week checkpoint, built the plan successfully, showed the new `🧠 Почему план такой` headline for local replanning, and still exposed the full ICS / Intervals.icu / FIT export surface afterward.

The follow-up slice makes that replanning durable instead of page-local. The app now writes a compact planning checkpoint to SQLite whenever the user builds or rebuilds a plan, reloads the latest checkpoint and short history into state, shows that recent checkpoint story on the dashboard, and gives AI coaching the same persisted context even when the planning page is no longer the active session surface.

That persistence boundary is intentionally narrow. Instead of storing the full export-oriented daily plan payload, AI Trainer now persists only the goal metadata, weekly summary rows, and constraint summary needed to explain what changed most recently. That keeps the database contract simpler while still letting the dashboard and AI coach talk coherently about the latest plan adjustment, interruption state, and target load envelope. Focused smoke coverage passes for checkpoint round-tripping and handoff behavior, and the full smoke suite now passes at `94 passed`.

The final acceptance pass turned that design into a real contributor checkpoint instead of a plausible one. Running the isolated app on `http://localhost:8510`, then restarting it against the exact same temporary SQLite file, exposed two product-level issues that normal unit coverage would not have caught cleanly: acceptance bootstrap was reseeding the DB on restart, and preserved isolated datasets were not restoring the session flags required to stay in demo-mode product flow. Fixing those two boundaries was necessary before persistence could be claimed honestly.

The acceptance evidence is now concrete and current. The isolated DB contains a saved planning checkpoint row for `Триатлон / Олимпийка`; after a cold restart on that same DB, the dashboard again shows `🗂️ Последний planning checkpoint` with the saved timestamp and load summary, and the AI coaching page shows the same checkpoint block plus the plan-aware explainability handoff. With the acceptance bootstrap contract corrected and the full smoke suite now green at `96 passed`, persisted planning checkpoints are proven as a real end-to-end product behavior rather than a page-local implementation detail.

The next Planning V2 slice closes that persistence loop into an operational one. The dashboard no longer just displays the saved checkpoint; it now lets the user record what actually happened (`выполнено / пропущено / урезано / ограничено`), rebuild the short-horizon plan from the persisted checkpoint context, and save the updated result back to SQLite without returning to the planning page. That is an important product shift: planning context is no longer just explainable after the fact, it is actionable from the daily execution surface.

The real browser proof for that slice is concrete. On the isolated acceptance runtime at `http://localhost:8510`, the dashboard rendered `🗂️ Последний planning checkpoint` plus `♻️ Факт выполнения`, accepted a reduced-load execution checkpoint at `60%`, saved a new checkpoint timestamp, changed the summary from `Нет · Сумма 1197 TSS` to `Нагрузка урезана · Сумма 1157 TSS`, and showed the success delta (`-40`) in place. With focused checkpoint/execution smoke coverage added and the full smoke suite now green at `98 passed`, the execution-feedback loop is proven as a real end-to-end workflow rather than a page-local control.

The next bridge slice makes that workflow visible inside coaching, not only inside planning or checkpoint cards. Actionable execution checkpoints are now part of the shared explainability contract itself. When readiness is otherwise stable, they can become the top-level focus (`Разберите execution checkpoint и ближайший план`). When readiness is already red, they still inject concrete guardrails into the recovery briefing so the product does not revert to sounding like a pure readiness engine.

The live acceptance proof for that change is more nuanced and therefore more valuable. On a fresh isolated runtime at `http://localhost:8511`, the athlete still started in a recovery-first state after a reduced-load checkpoint, so the correct behavior was not to replace the recovery focus with something artificial. Instead, after building a plan and applying `Нагрузка урезана` at `60%`, the dashboard changed `Сегодня`, `Ближайшие 2-3 дня`, and `Следить за` to mention the reduced week explicitly, including `Локальный replan уже изменил объём на -40 TSS.` Opening AI coaching from that next step carried the same checkpoint-aware guardrails into `Переход с дашборда` and `Почему такой старт`. With the full smoke suite now green at `102 passed`, execution feedback is proven as a first-class coaching signal rather than only a planning artifact.

The next Coach Explainability runtime slice turns that shared reasoning into a stricter operational contract for the moment that matters most: the first coaching reply after a guided handoff. Dashboard and recommended-entry prompts now carry a compact `operational_brief` contract through session state, the runtime appends a provider-facing suffix only for that one turn, and the final rendered answer is wrapped into a deterministic `Сегодня / Ближайшие 2-3 дня / Не делать / Почему` structure even when the underlying provider responds in ordinary prose. That gives the product a more trustworthy handoff without locking the rest of the chat into a rigid template; the smoke suite now passes at `106 passed`, including focused checks that the dashboard handoff click stores the contract and that the modern chat path consumes it exactly once.

The final live acceptance proof for that slice is now also explicit instead of inferred from tests and code paths. On the active `http://localhost:8511` acceptance runtime, the dashboard handoff still showed the preview contract, clicking through into AI coaching produced a first assistant message headed `🎯 Operational Brief` with the expected `Сегодня / Ближайшие 2-3 дня / Не делать / Почему` sections, and the very next follow-up question returned a normal free-form analysis message rather than reusing the structured wrapper. That closes the last behavioral gap in the objective: the contract is both deterministic on the first handoff turn and genuinely one-shot afterward.

The next Planning V2 slice makes the current plan editable at the point where users actually need control: the next week. Instead of forcing a full rebuild when reality shifts slightly, the planning page now exposes `✍️ Редактировать ближайшие 7-10 дней`, lets the user change day role, dominant sport, and TSS in place, then rewrites the near-term daily rows, session metadata, weekly totals, and checkpoint snapshot without disturbing the rest of the cycle.

The acceptance evidence for that slice is concrete and user-visible. The first browser pass on the existing `http://localhost:8511` tab correctly exposed a stale-runtime trap: because acceptance runs with `--server.fileWatcherType none`, the old tab still showed the previous planning build and did not contain the new editor. Launching a fresh isolated runtime on `http://localhost:8512` closed that gap. On the fresh instance, building a plan rendered the new near-term section, opening the editor exposed seven editable days, changing the first day's TSS from `11` to `0` produced the flash `Ближний горизонт обновлён: 7 дн., Δ -11 TSS.`, and the explainability block immediately added `Ручная правка ближнего горизонта: 7 дн. в ближайших 7 дн., Δ -11 TSS.` while total planned load dropped from `1591` to `1580` TSS. With focused smoke coverage green (`22 passed`) and the full smoke suite now green at `110 passed`, the product has a real near-term editing checkpoint instead of only a replanning abstraction.

The next Planning V2 slice changed the planner from a pure target-and-ramp calculator into a constrained planner. It still uses the same Banister forecasting and export surfaces, but now the user can express how much training time actually exists, which weekdays are usable, whether the next block is affected by illness, holiday, or limited availability, and whether missed load should be protected or partially caught up. That is the first real step toward adaptive planning rather than static load projection.

Revision note (2026-06-12 23:33+04:00): recorded the availability-and-interruption slice after verifying the new controls and constraint summary in the real planning UI and re-running the smoke suite (`52 passed`).

The explainability slice turned that adaptive logic into something a user can actually read. Before this change, the planning page could generate a better adaptive plan, but the output still behaved like a flat chart plus raw weekly rows. Now the page frames the scenario before generation, then explains the outcome after generation through a headline, compact metrics, a scenario card, a planner-decision card, and a before/after weekly table. The planner is still the same engine underneath, but the user no longer has to reverse-engineer why the numbers changed.

The latest Planning UX hardening slice closes a subtler trust gap inside that editor. A manual `Δ TSS` is not self-explanatory: `+40` can be reasonable on a fresh athlete but dangerous if it removes the only rest day on top of `Накопленная усталость`, while `-30` can be healthy recovery or an unintended collapse of the week's only quality stimulus. The product now computes that distinction once inside the near-term edit model, then reuses the same normalized badge, reasons, and guardrail in the planning draft preview, persisted checkpoint summary, dashboard, and AI coaching prompt context. The result is not just more UI copy; it is a shared safety contract that survives persistence and remains visible where the user actually decides whether to trust the edit.

The follow-up slice turns that safety contract into an actionable editor behavior. The product no longer stops at “this looks risky”; it can now propose a safer version of the same draft, show the lower-risk outcome before anything is saved, and rewrite the live draft with one click. That keeps the interaction local and concrete: the athlete still sees exactly which day was softened or restored, but no longer has to deduce the safer combination of day edits and post-edit strategy unaided.

The acceptance evidence for that slice is strong enough to treat it as complete. The smoke suite now passes at `54 passed`, and a fresh Streamlit instance launched from the current worktree on `http://localhost:8502` shows the updated `🧭 Сценарий и ограничения` pre-plan section and, after pressing `🧭 Построить план до старта`, the new `🧠 Почему план такой` and `↔️ До / После По Неделям` sections. That closes the loop for this sprint: the planning UI is now aligned with the adaptive engine already added in the previous slice.

Revision note (2026-06-19 21:15+04:00): recorded the execution-aware weekly-review slice after wiring `execution_weekly_review` plus response-strategy persistence through planning execution/checkpoints/coaching, fixing the stale `number_input` crash in the shared execution editor, re-running focused smoke coverage (`34 passed`) plus the full smoke suite (`145 passed`), and verifying a fresh isolated acceptance boot on `http://localhost:8520` with `HTTP 200` on `/` plus `/_stcore/health -> ok` after skipping occupied local ports `8510` and `8512`.

Revision note (2026-06-12 23:59+04:00): recorded the Planning UX + Explainability slice after browser-verifying the new planning page on a temporary `8502` Streamlit instance and re-running the smoke suite (`54 passed`).

The latest hardening slices confirm that `ui/pages/ai_coaching.py` can now be decomposed by responsibility rather than by file-size panic. Provider setup, entry/handoff, chat shell, monthly progress reporting, and now the execution runtime each have a dedicated boundary, and the page has dropped further to `1045` lines without breaking the legacy helper contract expected by `app.py` and the smoke suite. That is the right pattern for the final lap: the execution engine is no longer tangled together with unrelated Streamlit scaffolding, so the remaining page weight is increasingly honest and presentation-focused.

The new runtime split is especially important because it clarifies what the product actually considers reusable coaching logic. Prompt construction, conversation-history assembly, tool-call parsing, and final response post-processing now live in `models/ai_coach_runtime.py`, while the page retains only UI concerns such as placeholder copy, `st.chat_message(...)`, persistence, reruns, and optional speech playback. That gives the repository a much cleaner base for the next extraction wave around result formatting and any future non-UI AI-coach integrations.

The final AI coaching hardening slice finished that decomposition cleanly. Markdown tool formatting plus speech/streaming helpers now live in `ui/components/ai_coach_output.py`, `ui/pages/ai_coaching.py` is down to `356` lines, and the old import surface used by `app.py` and legacy tests still works unchanged. The focused smoke added for this boundary also surfaced a subtle pre-existing bug where streamed sentences were concatenated without a space; fixing it inside the new output module improved UX while the full smoke suite moved up to `76 passed`.

The next Planning V2 slice finally makes the weekly plan feel more like coaching and less like arithmetic. The planner still starts from the existing weekly TSS target, constraint handling, and per-sport expansion, but it now overlays explicit day roles such as `off`, `recovery`, `easy`, `quality`, and `long`, then rebalances the daily totals accordingly. That keeps the established export and simulation surfaces intact while making the weekly shape much more believable.

That slice also created a useful new explainability seam. The planning page can now show not just `сколько TSS` falls on each day, but what that day is supposed to be for: a recovery slot, a key quality session, or the week's long session. Focused smoke coverage caught a real product-level inconsistency during implementation: a running plan had accidentally placed the `long` label on a lighter day than a recovery slot because the old weekly weights and weekend preference disagreed. Fixing that inside the new role layer made the planner's structure more truthful instead of merely more verbose, and the full smoke suite moved up to `78 passed`.

The next Planning V2 slice made the planner sensitive to the athlete's starting load state, not just the event target and calendar constraints. `apply_planning_constraints(...)` now receives live `CTL`, `ATL`, and `TSB`, classifies the starting state as `fresh`, `balanced`, `fatigued`, or `deep_fatigue`, and uses that state to soften the first weeks when the athlete is already carrying too much fatigue. In the opposite direction, the same state can make `catch up` slightly more permissive after holiday or limited-availability blocks when the athlete starts fresh instead of stale.

That slice also exposed an important boundary condition in the UI contract. When the realistic target weekly TSS collapsed to a single allowed value, Streamlit rejected the `slider(min=500, max=500)` call outright. The fix was to treat that as a fixed-value control instead of trying to force a degenerate slider. That keeps Planning V2 stable when availability caps the target harder than the nominal distance range.

The validation evidence is again strong enough to keep moving forward without reopening older work. The adaptive-planning smoke tests now cover deep-fatigue start states and fresh-start catch-up behavior, the planning-page explainability tests cover the collapsed target-TSS control, and the full smoke suite passes at `58 passed`.

Revision note (2026-06-13 00:20+04:00): recorded the load-aware planning slice and the fixed-value target-TSS control after re-running the full smoke suite (`58 passed`).

The first Coach Explainability slice is intentionally modest but strategically important. Instead of trying to make the AI sound better through prompt edits alone, it introduces a shared reasoning layer that turns the same signals — `TSB`, `CTL`, `ATL`, readiness, recovery state, and recent plan constraints — into one explainability summary. The dashboard now uses that summary to frame `Следующий шаг`, while AI coaching uses the same summary to decide what the recommended first question should be.

That immediately improves product coherence. A user who sees `Сначала разберите восстановление` on the dashboard will now encounter the same underlying logic when opening AI coaching, along with a short `Почему такой старт` block that lists the key signals behind the suggestion. This is not yet the full daily briefing vision, but it is the first moment where multiple surfaces in the product start speaking the same language about readiness.

The validation evidence is straightforward and sufficient for this slice. New smoke coverage now exercises the shared explainability helper directly, while the existing dashboard and AI-coaching smoke tests still pass on top of the refactor. The full smoke suite passes at `61 passed`.

Revision note (2026-06-13 00:46+04:00): recorded the first Coach Explainability slice after adding the shared readiness helper, wiring it into dashboard and AI coaching, and re-running the full smoke suite (`61 passed`).

Revision note (2026-06-14 03:35+04:00): recorded the final isolated acceptance checkpoint after real browser verification on `http://localhost:8510`, direct validation of the narrow target-TSS slider fix, and a full smoke re-run (`89 passed`).

Revision note (2026-06-14 07:47+04:00): recorded the local-replanning slice after adding the `plan_adjustment` horizon overlay, browser-verifying the new planning flow on a fresh acceptance runtime, and re-running the full smoke suite (`91 passed`).

Revision note (2026-06-14 08:01+04:00): recorded the persisted-checkpoint slice after adding compact planning checkpoint storage plus dashboard/AI handoff recovery, validating focused checkpoint smoke coverage (`8 passed`), and re-running the full smoke suite (`94 passed`).

Revision note (2026-06-14 16:02+04:00): recorded the final persisted-planning acceptance checkpoint after fixing acceptance restart reseeding plus demo-session rehydration, browser-verifying the same saved planning checkpoint on dashboard and AI coaching after a cold restart of `http://localhost:8510`, and re-running the full smoke suite (`96 passed`).

Revision note (2026-06-14 16:44+04:00): recorded the dashboard execution-feedback slice after browser-verifying the real reduced-load replan on the isolated acceptance runtime at `http://localhost:8510` and re-running the full smoke suite (`98 passed`).

Revision note (2026-06-14 17:08+04:00): recorded the execution-aware coaching slice after extending the shared explainability helper with persisted execution-feedback signals, browser-verifying the checkpoint-aware dashboard and AI-coach copy on a fresh isolated runtime at `http://localhost:8511`, and re-running the full smoke suite (`102 passed`).

Revision note (2026-06-14 22:32+04:00): recorded the near-term editing slice after adding the in-place 7-10 day editor, verifying the stale-runtime trap on the old `8511` tab, browser-verifying a real manual edit on a fresh isolated runtime at `http://localhost:8512`, and re-running focused smoke coverage (`22 passed`) plus the full smoke suite (`110 passed`).

The follow-up bridge slice makes those near-term edits durable outside the planning page itself. Instead of staying as an in-memory annotation on the current plan, the saved `near_term_edit` signal is now normalized once, stored inside the compact planning checkpoint, shown in the dashboard checkpoint card and history, repeated in the AI coaching checkpoint entry, and pulled into the shared explainability line that frames the current plan context.

The final acceptance proof for that slice is intentionally persistence-first. On a fresh isolated runtime at `http://localhost:8513`, a cold reload against the same temporary SQLite database showed `Ручная правка: 3 дн. / 7 дн. · Δ -15 TSS` inside `🗂️ Последний planning checkpoint` on the dashboard and repeated the same signal plus `ручную правку ближнего горизонта: 3 дн. в ближайших 7 дн., Δ -15 TSS.` inside AI coaching explainability. Inline browser automation against the editor widgets itself remained flaky, so the deterministic acceptance path was to seed the isolated checkpoint directly and verify the user-visible persisted surfaces after reload. With focused smoke coverage green at `21 passed` and the full smoke suite now green at `112 passed`, manual near-term edits are proven as a durable cross-surface coaching signal rather than a planning-page-only tweak.

Revision note (2026-06-14 22:58+04:00): recorded the manual near-term edit propagation slice after adding the shared persisted summary helper, re-running focused smoke coverage (`21 passed`) plus the full smoke suite (`112 passed`), and browser-verifying the saved signal on dashboard and AI coaching after a cold reload of the isolated `http://localhost:8513` runtime.

The next planning UX slice made the near-term editor easier to trust before the user commits anything. Instead of hiding changes inside a submit-only form, the page now maintains a live draft with a compact `Черновик правок` summary, explicit `Было → Станет` rows, and a visible distinction between the already saved checkpoint and the still-editable draft. That makes the editor more usable for a human and easier to reason about in automated verification, even though the underlying planning contract stays the same.

This slice also surfaced and fixed a real modeling inconsistency rather than only a UI weakness. Turning a day into `off` previously still produced a non-zero duration floor, so the UI could claim `Отдых` while the derived template still looked like a short session. The duration helper now returns `0` for zero-load days, which makes preview, persisted `session_templates`, and downstream exports all agree on what an actual rest day means.

The validation result is strong where this slice actually lives. On system Python, focused planning and coaching smoke coverage passed for the hardened draft boundary plus the persisted-planning explainability boundary (`24 passed` across planning helper/explainability tests and another `21 passed` across checkpoint/dashboard/AI-handoff tests), and `test_ui_page_exports` now passes with the lazy `ui.pages` package wrappers (`6 passed`). Two broader checkpoints remain blocked by separate repository-level environment issues: full smoke collection still stalls at eager `services` package import, and `./run_acceptance.sh` currently hangs inside `scripts/doctor_env.py` while probing the damaged `ai_trainer_env` runtime. Those are now clearly infrastructure follow-ups rather than planning-UX regressions.

Revision note (2026-06-16 23:38+04:00): recorded the planning UX hardening slice after replacing the near-term editor form with a live draft/reset/apply flow, fixing zero-load day durations, making `ui.pages` exports lazy for cheaper helper imports, and validating the slice through focused system-Python smoke coverage (`51 passed` total across the relevant planning/coaching/page-export tests). Full smoke and fresh acceptance boot remain blocked by pre-existing `services/__init__.py` and `ai_trainer_env` environment drift.

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

The workspace-move follow-up closed two classes of risk at once. Operationally, the repository is back to a reproducible local checkpoint: the full smoke suite now passes again on system Python, the acceptance launcher survives a moved checkout because it runs Streamlit through `python -m streamlit`, and the clean acceptance boot on `http://localhost:8510` proves the runtime path instead of only the tests. Product-wise, the next Planning UX slice is now more honest: the near-term editor previews touched weeks plus the future persisted `Ручная правка` label before apply, and the saved weekly note no longer exaggerates how many days were really edited.

That changes what the next contributor should focus on. The immediate blockers are no longer environment drift or draft-trustworthiness inside the near-term editor. The remaining Planning V2 work can move back up a level toward richer adaptive behavior and explanation rather than spending another cycle on basic launcher reliability or draft-state honesty.

Revision note (2026-06-17 19:40+04:00): recorded the workspace-move hardening closure plus the next Planning UX hardening slice after re-running the full smoke suite (`124 passed`), verifying acceptance startup/health on a fresh isolated `http://localhost:8510` runtime, adding week-level draft preview, fixing overstated manual-edit day counts, and making the width-compat layer quiet on modern Streamlit.

The next slice made that manual-edit story materially more coach-like. The product no longer stops at “the next 7-10 days were edited”; it now also stores and explains what happens next: keep the delta local, return part of it carefully, or protect recovery by softening the following weeks. That is a real shift from a truthful editor toward a truthful adaptive planner, because the user can now see both the local change and the chosen recovery/catch-up consequence before saving, after saving, and later from the dashboard or AI coaching entry point.

The validation evidence is strong enough to treat this as a completed planning behavior slice rather than just UI polish. Focused planning/coaching smoke coverage passed at `39 passed`, the full smoke suite increased again to `127 passed`, and a fresh acceptance boot on `http://localhost:8510` still returned `HTTP 200` plus `/_stcore/health -> ok`. The next meaningful Planning V2 work can therefore move further outward into richer adaptation inputs or recommendation quality instead of revisiting manual-edit persistence or local follow-up semantics.

The newest slice closes the remaining trust gap in that workflow: reversibility. A risky draft is now safer to try not only because the product can warn or soften it, but because the saved manual edit is no longer a one-way operation. The planning page can show exactly how the current checkpoint differs from the prior version, restore that prior version from persisted data instead of approximation, and save the restored version back as the new current state. That moves near-term editing closer to a real coaching workflow: the athlete can experiment locally, inspect consequences, and still back out cleanly without rebuilding the whole plan from scratch.

Revision note (2026-06-17 20:01+04:00): recorded the post-edit-strategy slice after adding persisted `keep / catch_up / protect_recovery` behavior for manual near-term edits, re-running focused smoke coverage (`39 passed`) plus the full smoke suite (`127 passed`), and verifying fresh acceptance startup/health on the isolated `http://localhost:8510` runtime.

Revision note (2026-06-19 20:35+04:00): recorded the execution-driven corrective-microcycle slice after deriving and persisting `execution_corrective_microcycle`, propagating it through Planning, Dashboard, and AI Coaching explainability surfaces, and extending smoke coverage across checkpoint, handoff, and prompt-generation boundaries before final validation.
