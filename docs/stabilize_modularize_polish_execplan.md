# Stabilize, Modularize, and Polish the Core AI Trainer Flow

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

The product idea is already clear: AI Trainer combines Garmin data ingestion, recovery analysis, sleep analysis, training planning, and AI coaching in one Streamlit application. What is missing is operational discipline. A new contributor can launch the app today, but the current repository makes that experience fragile: credentials are rendered in the UI, startup depends on repairing installed packages, tests are hard to trust, and the main application file is too large to evolve safely.

After this plan is complete, a contributor should be able to create a clean virtual environment, install the documented dependencies, start the application, and exercise the main user journey without hidden repair steps or developer-only knowledge. A user should be able to open the app, either connect Garmin or deliberately choose a demo path, load data, land on a coherent dashboard, and get to the AI coach with obvious next actions. The observable proof is simple: the app starts from a clean environment, the first screen is safe and clear, the default smoke test command passes, and the main user flow can be followed without guessing.

## Progress

- [x] (2026-06-06 11:05+03:00) Audited the current repository structure, startup flow, test setup, and runtime hygiene.
- [x] (2026-06-06 11:05+03:00) Launched the application and inspected the landing page and network activity through a live browser automation session.
- [x] (2026-06-06 11:05+03:00) Wrote a three-iteration roadmap covering stabilization, modularization, and core-flow polish.
- [x] (2026-06-06 11:10+03:00) Expanded the roadmap with explicit developer-driven execution rules appropriate to the repository stage.
- [x] (2026-06-06 12:11+03:00) Iteration 1 completed: removed Garmin credential prefill from the UI, added an explicit `doctor_env.py` workflow, introduced `requirements-dev.txt`, `pytest.ini`, smoke tests, and verified the landing page plus contributor-safe smoke command.
- [ ] Iteration 2 — Modularize page rendering and UI boundaries around `app.py`.
- [ ] Iteration 3 — Polish the core user flow from entry to insight and AI recommendation.

## Surprises & Discoveries

- Observation: Garmin credentials are rendered back into the UI on the landing screen.
  Evidence: `app.py` passes `Settings.GARMIN_EMAIL` and `Settings.GARMIN_PASSWORD` as default values in `show_garmin_connection()`, and the live browser snapshot showed populated email and password fields before any interaction.

- Observation: Application startup currently mutates installed packages inside `site-packages`.
  Evidence: `run.sh` executes `scripts/repair_streamlit_proto.py`, and that script writes into `streamlit/proto/__init__.py` and recreates missing `sniffio` runtime files.

- Observation: The documented default test command is not reliable in the current virtual environment.
  Evidence: `python -m pytest tests/` fails because `site-packages/pytest` imports as a namespace package, and the `pytest` directory contains no importable module files beyond `__pycache__`.

- Observation: The first page load emits Streamlit telemetry to an external webhook endpoint.
  Evidence: A live browser session captured POST requests to `https://webhooks.fivetran.com/...` with a `viewReport` payload referencing the local Streamlit app.

- Observation: The repository already contains useful architectural seams that should be strengthened rather than replaced.
  Evidence: `services/garmin.py`, `services/data_cache.py`, `state/manager.py`, and `ui/navigation.py` already separate some orchestration concerns from the monolithic `app.py`.

- Observation: The current virtual environment is damaged beyond a single-package fix because multiple packages are missing source files or `dist-info` metadata.
  Evidence: `python -m pytest` initially failed, `doctor_env.py repair --dev` restored compiled module files for several packages, and a final `pip install --ignore-installed ...` was needed to get a working pytest entrypoint for verification.

## Decision Log

- Decision: Use three iterations named `Stabilize`, `Modularize`, and `Polish Core Flow` instead of a single large refactor.
  Rationale: The current problems span security, runtime reproducibility, architecture, and product UX. Solving them in one undifferentiated change would hide regressions and make acceptance ambiguous.
  Date/Author: 2026-06-06 / Codex

- Decision: Keep Streamlit as the product shell for this roadmap.
  Rationale: The application already launches and expresses the intended product. The current pain comes from repository hygiene, runtime drift, and an oversized `app.py`, not from a confirmed framework dead end.
  Date/Author: 2026-06-06 / Codex

- Decision: Prefer extraction and boundary cleanup over rewrite.
  Rationale: The repository already has working building blocks in `state/`, `services/`, and `ui/`. Reorganizing around those seams is lower risk than rebuilding the product architecture from scratch.
  Date/Author: 2026-06-06 / Codex

- Decision: Treat developer tooling and product-facing flows as separate concerns.
  Rationale: The current default UI exposes development helpers and demo mechanics in the same surface as production actions. The roadmap should make the main user journey clearer without blocking internal debugging tools.
  Date/Author: 2026-06-06 / Codex

- Decision: Use developer-driven practices selectively rather than mechanically.
  Rationale: SpecDD, BDD, TDD, contract-first module boundaries, and self-review fit the current repository and will improve execution quality. A heavy rewrite process or full architecture ceremony would slow the project without solving the immediate product and runtime risks.
  Date/Author: 2026-06-06 / Codex

- Decision: Replace silent startup-time runtime mutation with explicit environment diagnostics and repair commands.
  Rationale: The old startup path normalized package mutation inside `site-packages` as part of every run. The safer contract is to check runtime health during startup, fail loudly when the environment is damaged, and provide a separate one-time repair command.
  Date/Author: 2026-06-06 / Codex

- Decision: Introduce a dedicated smoke test path instead of claiming that the full `tests/` tree is contributor-safe.
  Rationale: The repository contains a mix of pure checks, diagnostics, and live integration tests. A dedicated `tests/smoke/` path and pytest markers are a more honest stabilization step than pretending the existing flat suite is uniformly safe.
  Date/Author: 2026-06-06 / Codex

## Outcomes & Retrospective

The outcome of this planning milestone is not code movement; it is a precise execution sequence. The repository already proves that the product concept is viable, but it also proves that the next bottleneck is execution quality rather than ideation. This roadmap therefore does not propose a new product direction. It proposes a disciplined path to make the existing product safe to run, easier to change, and easier to trust.

The main lesson from the initial audit is that the strongest short-term gains do not come from new analytics features. They come from removing unsafe defaults, restoring trust in the environment, and shrinking the mental load of `app.py`. The work should begin there.

After completing Iteration 1, that hypothesis held. The landing page no longer exposes stored Garmin secrets, the startup script now checks runtime health instead of patching packages silently, and the repository has a documented smoke path that was actually run successfully. The remaining lesson is that the current virtual environment is significantly more damaged than it first appeared, so future work should prefer verifying behavior from a clean environment whenever possible instead of assuming the checked-in `ai_trainer_env` is representative.

## Context and Orientation

The Streamlit entry point is `app.py`. It currently owns page configuration, theme setup, Garmin connection UI, page navigation, data synchronization, page rendering, and many page-specific helper functions. It is the composition root of the application, but it is also the largest concentration of implementation detail. The file currently contains functions such as `show_dashboard()`, `show_activities()`, `show_hrv_analysis()`, `show_sleep_analysis()`, `show_planning()`, `show_ai_coaching()`, `show_sync_logs()`, and `show_data_management()`.

The Garmin integration lives primarily in `data/garmin_client.py` and `data/garth_client.py`. These files talk to external APIs and currently mix transport logic, fallback behavior, debug printing, and some Streamlit error rendering. `data/database.py` provides the local SQLite cache used by the app.

The typed state wrapper is `state/manager.py`. It is one of the best existing abstractions in the repository because it centralizes lazy session-state construction for `Database`, `GarminClient`, `ChatManager`, `UniversalAICoach`, and `AITools`. `services/garmin.py` already provides a thin service layer over Garmin authentication and profile access. `services/data_cache.py` already provides cached database reads for activities, HRV, sleep, and daily health data. `ui/navigation.py` already owns page selection widgets.

The tests live in `tests/`, but they are currently flat and mixed. Unit-style checks, integration scenarios, live Garmin calls, real Ollama checks, and debug-oriented scripts all share the same namespace. In this document, a "smoke test" means a quick automated check that should pass in a normal contributor setup without real external credentials. A "live test" means a test that depends on real external systems such as Garmin, Ollama, or live API keys.

The "core flow" in this plan means the shortest high-value path through the product: open the app, choose either real Garmin onboarding or a clearly labeled demo mode, load data, read the dashboard and recovery context, then open AI coaching and receive an actionable next step.

## Developer-Driven Execution Style

This roadmap should use developer-driven discipline, but only where it fits the current maturity of the project. The right level for this repository is `SpecDD`, `BDD`, `TDD`, contract-first boundaries, and mandatory self-review. The wrong level for this repository is heavyweight process theater or a large architectural rewrite in the name of purity.

For this project, `SpecDD` means that each iteration starts by updating this ExecPlan before code moves. If scope changes, the `Progress`, `Decision Log`, and `Outcomes & Retrospective` sections must be updated first so the repository always contains the current truth. `BDD` means that the user-visible scenarios are written from the outside in, especially for the core flow. The important scenarios are not abstract domain stories; they are concrete product behaviors such as "user opens the app and does not see stored secrets" or "user loads demo data and lands on the dashboard with a visible next step."

`TDD` is appropriate for the stabilization and boundary work. It should be used to protect the contributor-safe smoke path, the Garmin connection UI rules, the page-dispatch boundaries, and any extracted logic that can be exercised without a live browser. It is not necessary to force a test-first ritual for every visual wording change. Contract-first design is appropriate at the boundaries between `app.py`, `ui/pages/*`, `ui/components/*`, `services/*`, and `data/*`. That means establishing stable function signatures and error-handling expectations before moving large amounts of code.

Mandatory self-review is part of every iteration. Each iteration should end by checking correctness, regression risk, runtime behavior, and whether the solution made the code easier to understand. Minimal complexity is an explicit guardrail. This plan should not introduce a new frontend framework, a new service layer hierarchy, an event bus, or full domain-driven architecture terminology. The project is not at the stage where those abstractions would pay for themselves.

## Plan of Work

### Iteration 1 — Stabilize

The goal of the first iteration is to make the repository safe to run and truthful to develop against. This iteration should fix anything that blocks a contributor from trusting the startup flow, the default test path, or the handling of secrets. The measurable result is that a clean environment can launch the app without hidden repair side effects, the landing screen does not echo stored credentials, and the repository documents a default automated test path that actually runs.

The first code changes should begin in `app.py`, `run.sh`, `README.md`, and the runtime repair script. Remove the UI behavior that pre-fills Garmin credentials from settings. Retain convenience for development only if it can be done without rendering secrets to the browser. The preferred outcome is that credentials come from user input or Streamlit session state only, and never appear pre-populated from `.env`.

The next stabilization task is to stop treating runtime package mutation as a normal startup step. The preferred end state is to simplify `run.sh` so it launches the app without rewriting files inside `site-packages`. If full removal of the repair script is not yet feasible, move the repair logic into a one-time maintenance command such as `scripts/doctor_env.py` and make `run.sh` fail loudly when the environment is broken instead of silently patching it on every start. The same iteration should repair the development dependency path by introducing an explicit development install manifest such as `requirements-dev.txt` or another committed equivalent that includes `pytest` directly, rather than relying on accidental transitive installation.

The final stabilization task is to make the test surface honest. Add `pytest.ini` with explicit markers such as `live`, `debug`, and `smoke`. Mark real-network and debug-oriented tests in place instead of moving everything at once. Update the README so the default command runs only the contributor-safe suite. The repository should stop implying that all tests are equal.

This iteration should be executed with strict developer-driven discipline. Before code changes begin, record the stabilization acceptance scenarios in this ExecPlan using plain-language `Given / When / Then` behavior descriptions. Then add or update automated tests for the safe startup path, the Garmin credential rendering rule, and the contributor-safe pytest path before changing implementation details.

### Iteration 2 — Modularize

The goal of the second iteration is to stop `app.py` from being the default destination for every product change. This is not a rewrite. It is an extraction pass that keeps behavior stable while moving page logic into dedicated modules and moving UI plumbing out of the data layer. The measurable result is that `app.py` becomes a readable orchestration file rather than a page implementation dump.

Create a new package under `ui/` for page renderers. A concrete and stable layout is `ui/pages/dashboard.py`, `ui/pages/activities.py`, `ui/pages/hrv.py`, `ui/pages/sleep.py`, `ui/pages/planning.py`, `ui/pages/ai_coaching.py`, `ui/pages/sync_logs.py`, `ui/pages/data_management.py`, and `ui/pages/welcome.py`. Move the bodies of the existing `show_*` functions into these modules one page at a time. Each page module should expose a single renderer function with the signature `def render(state: StateManager) -> None`.

At the same time, extract the Garmin connection widget from `app.py` into a reusable UI component such as `ui/components/garmin_connection.py`. `app.py` should continue to own page configuration, theme bootstrap, the authenticated versus unauthenticated gate, page selection, and top-level dispatch. It should not continue to own the full implementation of every page.

This iteration should also clean the boundary between UI and integration code. `data/garmin_client.py` and `data/garth_client.py` should no longer call Streamlit rendering functions directly. They should return values or structured errors, and the page layer should decide how to render failures. This change is essential for testing because it allows the integration layer to be exercised without a browser context.

This iteration should be contract-first. Before moving page bodies, define the stable renderer signatures and boundary rules that each new module must satisfy. Extraction should proceed one page at a time, with tests and a short self-review after each page move rather than one giant cutover.

### Iteration 3 — Polish Core Flow

The goal of the third iteration is to make the product feel coherent to a first-time user. The measurable result is that a user can move from entry to insight without being exposed to internal debugging concepts or being forced to infer what to do next. This is where the product becomes easier to trust, not merely easier to maintain.

The entry screen and post-login empty-state dashboard should be redesigned around the core flow. The product should explicitly present two paths: real Garmin onboarding and a clearly marked demo path. The demo path must be visibly synthetic and must never look like synced personal data. After successful sync or demo load, the dashboard should explain what happened, what the main metrics mean at a glance, and what the best next action is. The best next action should include a direct path into AI coaching with starter prompts that reflect actual available context such as readiness, sleep, HRV, or recent load.

This iteration should also remove or hide developer-only controls from the default user surface. The current development expander and direct test-data affordances should either move behind a debug flag or into a separate admin/development page that is not presented as part of the normal user journey. A product user should not encounter ambiguous controls such as test data loading without deliberate intent.

Finally, add a repeatable manual smoke walkthrough for the core flow. This does not require adopting a heavy browser-testing framework inside the repository. A written walkthrough in the plan and a small automated smoke subset are enough, as long as they make regressions obvious.

This iteration should be driven by BDD-style product scenarios rather than internal implementation detail. Write the core flow scenarios first, polish the UI against those scenarios, and keep every visible change tied to an observable user outcome.

## Concrete Steps

All commands below assume the working directory is the repository root:

    cd /Users/gregkisel/Documents/GitHub/ai_trainer

For Iteration 1, begin by validating the current environment honestly before changing code:

    source ai_trainer_env/bin/activate
    python -c "import pytest, streamlit, sniffio; print('imports ok')"
    python -m pytest -m "not live and not debug" tests/
    ./run.sh

The expected post-iteration behavior is that the import command succeeds, the test command runs a contributor-safe suite, and `./run.sh` starts the app without mutating installed packages or displaying stored Garmin secrets on the first screen.

If the current virtual environment is already corrupted, do not keep patching it in place. Move it aside so it remains available for inspection and create a fresh one:

    mv ai_trainer_env ai_trainer_env.broken.$(date +%Y%m%d%H%M%S)
    python -m venv ai_trainer_env
    source ai_trainer_env/bin/activate
    pip install -r requirements-dev.txt

The expected post-iteration behavior is that a clean environment becomes the normal path, not a special recovery path.

For Iteration 2, work page by page and keep the app runnable after each extraction:

    source ai_trainer_env/bin/activate
    python -m pytest -m "not live and not debug" tests/
    ./run.sh

After moving each page, start the app and click through the corresponding navigation item in a local browser. The expected post-iteration behavior is that `app.py` still runs the application, but page implementations live under `ui/pages/` and UI failures are rendered outside the data clients.

For Iteration 3, validate the product flow manually in a local browser after every visible change:

    source ai_trainer_env/bin/activate
    ./run.sh

Open `http://localhost:8501`, verify that the Garmin path and demo path are clearly distinguished, load one of them, land on the dashboard, and navigate into AI coaching. The expected post-iteration behavior is that the user never needs development knowledge to complete the basic journey.

## Validation and Acceptance

Iteration 1 is accepted when a new contributor can follow the committed setup instructions, install dependencies from the committed manifests, and run the documented default test command successfully. The landing screen must show empty credential fields by default. Startup must no longer depend on silently editing files inside `site-packages` during every run. Live tests must be opt-in rather than part of the implied default path.

Iteration 2 is accepted when `app.py` is reduced to orchestration responsibilities: page config, theme bootstrap, authentication gate, navigation, and page dispatch. The implementations of dashboard, activities, HRV, sleep, planning, AI coaching, sync logs, data management, and welcome screens must live outside `app.py` in dedicated modules. `data/garmin_client.py` and `data/garth_client.py` must no longer render Streamlit UI messages directly.

Iteration 3 is accepted when the first-run user journey is coherent. A user must be able to distinguish between real Garmin onboarding and demo onboarding without reading code or documentation. After data is available, the dashboard must explain the next best step and provide an obvious path to AI coaching. Developer-only controls must be hidden or separated from the default user flow.

The full roadmap is accepted when all three iterations are complete and the following behavior can be observed from a clean setup: the app installs cleanly, starts cleanly, protects secrets on the first screen, exposes a truthful automated smoke path, keeps page logic outside `app.py`, and guides the user from entry to insight without developer affordances leaking into the main experience.

## Idempotence and Recovery

This roadmap should be executed additively wherever possible. During modularization, extract a page into a new module and delegate to it from `app.py` before deleting the old body. This keeps the application runnable after each step. During stabilization, prefer creating new committed environment manifests and bootstrap helpers over mutating existing installed packages.

If the virtual environment proves corrupted, move it aside instead of deleting it immediately so the broken state remains inspectable. If a page extraction introduces regressions, temporarily keep a compatibility wrapper in `app.py` that calls the new module. If a live test is flaky, mark it explicitly and remove it from the default pass before attempting deeper fixes.

The repository should remain usable after every milestone. No milestone in this plan requires a flag day rewrite.

## Artifacts and Notes

The initial audit produced four concrete pieces of evidence that should remain true until fixed:

    - The landing page rendered Garmin email and password values directly from settings.
    - `run.sh` called a repair script that rewrote runtime packages before launch.
    - `python -m pytest tests/` was not trustworthy in the current environment.
    - The first page load emitted Streamlit telemetry to an external webhook endpoint.

These observations are not side notes. They are the justification for the ordering of this roadmap. If future work changes any of them, update both `Surprises & Discoveries` and `Decision Log` immediately.

## Interfaces and Dependencies

The existing `StateManager` in `state/manager.py` remains the preferred entry point for session-bound dependencies. New page modules should accept `StateManager` and render UI only. The stable renderer signature for extracted page modules is:

    def render(state: StateManager) -> None:

At the end of Iteration 2, the repository should contain these render modules:

    ui/pages/dashboard.py
    ui/pages/activities.py
    ui/pages/hrv.py
    ui/pages/sleep.py
    ui/pages/planning.py
    ui/pages/ai_coaching.py
    ui/pages/sync_logs.py
    ui/pages/data_management.py
    ui/pages/welcome.py

The Garmin connection widget should move into a dedicated UI component with a stable function signature:

    def render_garmin_connection(state: StateManager) -> None:

`services/garmin.py` should remain the boundary that page code uses for authentication, connection status, and profile access. `services/data_cache.py` should remain the boundary that page code uses for cached read access. `data/garmin_client.py` and `data/garth_client.py` should not import or call Streamlit rendering helpers in the target state.

The development dependency story should become explicit. A committed development manifest such as `requirements-dev.txt` should include the runtime requirements plus `pytest`. `pytest.ini` should define at least the markers `live`, `debug`, and `smoke`. The default documented command should target the safe suite, for example:

    python -m pytest -m "not live and not debug" tests/

The AI surface should continue to rely on existing modules rather than new abstractions. `models/ai_coach_universal.py`, `models/chat_manager.py`, and `models/ai_tools.py` are the preferred units to preserve while page extraction proceeds.

Revision Note (2026-06-06 / Codex): Created the initial three-iteration ExecPlan after auditing the repository, launching the app, and reviewing the landing flow and runtime behavior in a live browser session.

Revision Note (2026-06-06 / Codex): Expanded the plan with explicit developer-driven execution guidance so future work uses SpecDD, BDD, TDD, contract-first boundaries, self-review, and minimal-complexity guardrails appropriate to this repository.
