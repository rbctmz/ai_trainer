# Add an architecture map and a verification stack for agent-written code

**Change Class: Class A — Full.** The work adds a new verification boundary and new CI gates, which matches the automatic escalation trigger for "a new cross-module public contract or a new architectural boundary" in `docs/AI_Feature_Development_Workflow.md`.

This ExecPlan is a living document and must be maintained in accordance with `.agent/PLANS.md`. Its `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` sections must stay current while the work proceeds. The document is self-contained: a contributor who has only the current working tree and this file can deliver the whole change. Every term of art is defined in plain language below; nothing here assumes memory of an earlier plan or a conversation.

## Purpose / Big Picture

After this change, a maintainer of this repository can answer three questions without reading source code line by line. First, what are the parts of this system and which one owns which responsibility — visible as one interactive architecture map plus a generated `ARCHITECTURE.md` that a coding agent can load as context. Second, where is the code both complicated and untested — visible as a ranked report of a metric called CRAP, defined below. Third, do the tests actually detect wrong behavior — visible as a mutation score, also defined below.

The reason this matters is that reviewing code has become the slow part of this repository's development loop, while writing it has become fast. A green test run currently proves only that the tests passed; it does not prove that the tests would have failed if the code were wrong. A high-coverage module can still contain assertions that check nothing. A low-coverage module can be the one that breaks in production. Neither condition is visible anywhere in CI today, and the architecture of the system lives only in the heads of the people who built it.

The user-visible proof arrives in three steps. After Milestone 1, `ARCHITECTURE.md` exists at the repository root and a generated diagram shows components whose nodes link back to source files. After Milestone 2, running `python scripts/quality/crap_report.py --top 20` prints a ranked table of modules, and CI fails a pull request that makes a module's CRAP score worse than the committed baseline. After Milestone 3, running `python -m mutmut run` reports how many deliberate small bugs the test suite caught, and CI fails a pull request whose touched modules let through a larger share of those bugs than the baseline allowed.

## Progress

- [x] (2026-09-19 11:04Z) Read `.agent/PLANS.md`, `docs/AI_Feature_Development_Workflow.md`, `.github/ISSUE_TEMPLATE/agent_task.yml`, `.github/workflows/ci.yml`, `pytest.ini`, `requirements-dev.txt`, `web/package.json`, and `docs/README.md` to establish the current state.
- [x] (2026-09-19 11:04Z) Classified the change as Class A because it introduces a new verification boundary and new CI gates.
- [x] (2026-09-19 11:04Z) Confirmed the absence of any coverage or complexity measurement on the current tree, and confirmed that `web/` has no JavaScript unit-test runner.
- [x] (2026-09-19 11:04Z) Wrote this initial revision of the ExecPlan.
- [ ] Measure the smoke baseline in a working environment (`python -m pytest tests/smoke -q`) and record the exact pass/fail counts here. The checkout used to author this plan contained no virtual environment (`ls -d ai_trainer_env .venv venv` found none), so no baseline was measured. **(remaining: this measurement; nothing else in Milestone 1 depends on it)**
- [ ] Milestone 1: install CodeBoarding, generate the architecture map, commit `ARCHITECTURE.md`, register the MCP server for agents.
- [ ] Milestone 2: add `pytest-cov` and `radon`, implement the CRAP report, commit the baseline, add smoke tests for the metric.
- [ ] Milestone 3: add mutation testing, commit the mutation baseline, add the changed-module gate, wire both gates into CI, record the gates in the workflow docs.
- [ ] Update `docs/README.md` to list this ExecPlan, and update `docs/engineering_process_metrics.md` with the two new tracked measures.

## Surprises & Discoveries

- **Observed**: nothing in this repository measures test coverage or code complexity today. `requirements-dev.txt` lists only `-r requirements.txt`, `pytest`, `playwright`, and `ruff`; `pytest.ini` sets `addopts = -ra` with no coverage flag; and no `pyproject.toml` `[tool.coverage]` section, `.coveragerc`, or `setup.cfg` exists. The source is the files themselves.
- **Inferred**: a green contributor-safe run therefore cannot distinguish a module whose tests exercise its behavior from a module whose tests merely import it. The cheapest falsifying check is to install `pytest-cov` and run the contributor-safe selection once with `--cov-report=term-missing`, then look for modules that have tests naming them yet execute zero statements.
- **Verified by**: NOT YET. This check is the first step of Milestone 2 and its result must be recorded here.

- **Observed**: `web/package.json` declares scripts `dev`, `build`, `start`, `lint`, `contract:inventory`, and `contract:extract`, and its `devDependencies` list contains no `jest`, `vitest`, or other unit-test runner. The source is `web/package.json`.
- **Inferred**: the Next.js front end cannot be mutation-tested or covered in this plan without first introducing a unit-test runner, which is a separate change with its own review. The cheapest falsifying check is to grep the tracked tree for a test runner import (`grep -rn "vitest\|jest" web/`) and confirm no match.
- **Verified by**: NOT YET. Confirm during Milestone 3 before writing any TypeScript tooling; if a runner does exist, the non-goal recorded below must be revised.

- **Observed**: `docs/technical_debt_register.md` has a snapshot date of 2026-08-16 and lists exactly one open item, `TD-006` (P2, structure, "large modules concentrate churn"). The source is that file.
- **Inferred**: the missing verification layer is not currently tracked as debt, so this plan introduces new measurement rather than closing a register entry. Consequence: no `TD-XXX` identifier is created or consumed by this work, and the register should not be edited except to link this plan if a reviewer asks.
- **Verified by**: reading the register's `Сводка` table directly; confirmed one open row.

## Decision Log

- Decision: build the verification stack on CodeBoarding for the architecture map rather than on a diagramming-only tool.
  Rationale: CodeBoarding derives its components from a control-flow and dependency analysis of the real tree and exposes the result both as a generated Markdown document and through a Model Context Protocol server. A Model Context Protocol server, abbreviated MCP, is a small local process that offers tools and documents to a coding agent over a standard protocol; registering one lets the agent read the architecture instead of re-deriving it from source on every turn. A tool that only draws a picture would not reduce the agent's context cost, which is half the point of the milestone.
  Date/Author: 2026-09-19 / Hermes Agent

- Decision: generate the architecture analysis with a locally hosted model through `OLLAMA_BASE_URL` on the first runs, falling back to a hosted provider already configured in `.env` only if the local result is unusable.
  Rationale: `AGENTS.md` warns that `logs/` may contain personal training metrics. Sending repository source to a third-party provider is a data-handling decision that belongs to the maintainer, not to a tooling commit. Running the generator locally keeps the decision reversible. No new secret is introduced by this plan; it reuses provider configuration that already exists.
  Date/Author: 2026-09-19 / Hermes Agent

- Decision: implement CRAP as a committed script over `pytest-cov` data plus `radon`, rather than adopting a commercial quality dashboard.
  Rationale: the inputs are two small, well-known libraries; the arithmetic is one formula; and a committed script stays runnable offline and in CI without a service account. A dashboard would add a dependency and a data-egress question for a number that a hundred lines of Python can produce.
  Date/Author: 2026-09-19 / Hermes Agent

- Decision: enforce both new metrics as a ratchet on touched modules, not as an absolute threshold on the whole repository.
  Rationale: this repository already carries modules that would fail an absolute bar. A whole-repository gate would block every unrelated pull request until a large cleanup landed, which is the failure mode that makes teams disable a gate. Requiring only that a touched module does not get worse keeps the gate honest and immediately useful.
  Date/Author: 2026-09-19 / Hermes Agent

- Decision: measure coverage on the contributor-safe test selection (`-m "not live and not debug and not e2e"`), and state in the report that the number is a lower bound.
  Rationale: the live, debug, and end-to-end selections need credentials, network, or a browser, so they are not part of the path a reviewer runs. Using the same selection as CI keeps the developer's number and the gate's number identical, which is what makes a ratchet enforceable.
  Date/Author: 2026-09-19 / Hermes Agent

- Decision: choose `mutmut` as the Python mutation runner, with `cosmic-ray` as the fallback if `mutmut`'s test-runner integration proves too restrictive.
  Rationale: `mutmut` runs any test command that reports success through an exit code, supports incremental runs that remember earlier results, and exposes a CI exit flag. The published comparison of Python mutation tools rates `cosmic-ray` highest on community activity but notes `mutmut`'s simpler integration, and this plan values the smaller wiring surface first.
  Date/Author: 2026-09-19 / Hermes Agent

- Decision: do not refactor any module because of a score produced by this work.
  Rationale: the plan's deliverable is measurement. Mixing refactoring into it would make the diff unreviewable and would let a scoring bug masquerade as a code improvement. Findings become their own issues, filed with the score as evidence.
  Date/Author: 2026-09-19 / Hermes Agent

## Outcomes & Retrospective

Not yet written. This section is required at the end of each milestone and at completion. At the end of Milestone 1 it must state whether a fresh contributor could name each top-level module's responsibility from the map alone. At the end of Milestone 2 it must state whether the CRAP ranking surfaced anything that the churn data in `TD-006` did not already point at. At completion it must state what remains, including the deferred TypeScript coverage work and any module deliberately left out of the mutation baseline.

## Context and Orientation

This repository is AI Trainer, a self-hosted training coach. Its Python code lives under `api/` (FastAPI HTTP contracts), `models/` (domain logic and coach runtime), `services/` (ingestion and orchestration), `utils/` and `config/` (shared helpers and settings), and `data/` (provider clients). The Next.js user interface lives under `web/`. Tests live under `tests/`, with a contributor-safe smoke subset under `tests/smoke/` and browser tests under `tests/e2e/`. As of this plan the tree holds 127 Python files across `api/`, `models/`, `services/`, `utils/`, and `config/`, and 257 files matching `tests/test_*.py`.

The commands that matter are defined in `AGENTS.md`. Lint is `python -m ruff check .`. The contributor-safe test pass is `python -m pytest -m "not live and not debug and not e2e" tests/`. The smoke subset is `python -m pytest tests/smoke -q`. Marker definitions live in `pytest.ini`. Continuous integration is defined in `.github/workflows/ci.yml`, which currently runs three jobs: `contributor-safe-tests` (ruff plus the contributor-safe pytest selection), `web-contract` (contract artifact freshness and contract tests), and `web-e2e` (Playwright).

Process documents that constrain this work: `.agent/PLANS.md` defines the ExecPlan format and the Evidence Discipline form used in the `Surprises & Discoveries` section above. `docs/AI_Feature_Development_Workflow.md` defines Change Classes A, B, and C and the review policy. `docs/README.md` is the documentation navigation source of truth, and new documents must be added to it. `docs/technical_debt_register.md` is the single register of confirmed technical debt. `.github/ISSUE_TEMPLATE/agent_task.yml` defines the structured issue form, which is why the issue accompanying this plan carries `### ExecPlan`, `### Acceptance criteria`, and `### Smoke baseline` sections — the issue-parsing automation in `.github/scripts/` depends on those exact headings.

Three terms are used throughout and are defined here so this document stands alone.

*Cyclomatic complexity* is the number of independent paths through a function, computed by counting decision points. A function with no branches has complexity 1; each `if`, loop, `and`, or `or` adds one. `radon` computes this for Python.

*Coverage* is the fraction of a module's executable statements that ran during a test session. `pytest-cov` produces it.

*Mutation testing* is a way to measure whether tests can fail. The tool makes many small, deliberate changes to the code — for example replacing a `<` with a `<=`, or deleting a line — each change being one *mutant*. It then runs the tests against each mutant. If the tests fail, the mutant was *killed*, meaning the suite detected that change. If the tests still pass, the mutant *survived*, meaning the suite cannot tell correct code from that specific wrong version. The mutation score is the killed share of all mutants. A survivor is a concrete, named hole in the suite.

*CRAP* combines the first two. For a module `m` with complexity `comp(m)` and coverage fraction `cov(m)`, the score is:

    crap(m) = comp(m)^2 * (1 - cov(m))^3 + comp(m)

The shape of that formula carries the meaning. When `cov(m)` is 1, the second term vanishes and the score equals the complexity, so a fully covered module can never score worse than its own complexity. When coverage falls, the cubic factor grows quickly and multiplies the squared complexity, so complexity and missing coverage punish each other. A score of 30 is the original advisability threshold published with the metric: above it, a module is considered risky enough to warrant attention. This plan names the number here so the implementation does not have to guess it, and records no other magic constants.

## Plan of Work

The work has three milestones. Each leaves the tree in a working, shippable state. Each is independently verifiable.

### Milestone 1 — Architecture map and agent-facing context

At the end of this milestone the repository contains a generated architecture document and a reproducible command that regenerates it. A contributor can open the generated diagram, click a component, and land in the source file that implements it. A coding agent can read the architecture through MCP without being handed the source of every module.

Install CodeBoarding as a development tool rather than a runtime dependency, so the product's `requirements.txt` is untouched. Pin an exact version in the new `requirements-quality.txt`, not a range, because this tool's configuration surface is young and a range would make the regenerated diagram change shape without a commit explaining why. Before writing the wrapper script, read the installed version's own documentation for its configuration file name and supported providers — do not take the filename from this plan, and record the actual name in the `Decision Log` once confirmed.

Add `scripts/quality/generate_architecture_map.py` as the single entry point. It must accept `--repo-root` and `--provider` flags, read the provider configuration from the environment exactly as the rest of the repository does (`.env` via `config/settings.py` conventions), refuse to run when the provider environment variable is unset rather than silently falling back, and write its output to `.codeboarding/`. Because `AGENTS.md` states that `logs/` may contain personal training metrics and that `ai_trainer.db` is a local cache, the wrapper must pass an explicit exclusion list covering `logs/`, `ai_trainer.db`, `archived/`, `spikes/`, `debug/`, `examples/`, `research/`, and `output/`; those directories are already declared as out of scope in `AGENTS.md`.

Commit the generated `ARCHITECTURE.md` at the repository root and the `.codeboarding/` component documents. Commit the generated artifacts rather than gitignoring them, because their value is that an agent reads them without running a generator first. Add a header comment to `ARCHITECTURE.md` stating that the file is generated, naming the command that regenerates it, and naming the commit at which it was produced, so a stale copy is detectable.

Wire the generator into the agent workflow in two places. Register the CodeBoarding MCP server in the repository's agent configuration so an agent can query the map, and add one line to `AGENTS.md` under Architecture Context pointing at `ARCHITECTURE.md` as the first thing to read before significant planning work. Add the same pointer to `docs/README.md`.

The proof of this milestone is behavioral: after running the documented command on a clean checkout, `ARCHITECTURE.md` exists, the diagram renders, and a node click navigates to a real source path. It is not proven by the command exiting zero.

### Milestone 2 — CRAP metric and the untested-complexity report

At the end of this milestone a maintainer can rank modules by risk and see whether a pull request made any module worse. The first step is the falsifying check recorded in `Surprises & Discoveries`: install `pytest-cov`, run the contributor-safe selection with `--cov-report=term-missing`, and record in this plan whether any tested module executes zero statements. If that check finds nothing, the CRAP work is still justified by the complexity term, but the claim in this plan's `Purpose` section must be softened to match the evidence.

Add `pytest-cov` and `radon` to `requirements-dev.txt` as bounded ranges in the style already used there. Implement `scripts/quality/crap_metric.py` with pure functions and no file I/O in the scoring path, and `scripts/quality/crap_report.py` as the command-line front end. Score at module granularity, not function granularity, for the first iteration: module granularity matches the paths a reviewer already thinks in and keeps the baseline file small enough to review in a diff. Record in the `Decision Log` that function-level scoring is deferred, and why.

The report prints a ranked table with the columns path, statements, complexity, coverage fraction, and CRAP score, and supports a JSON output mode so CI and a human read the same numbers. It writes and reads a committed baseline at `.quality/crap_baseline.json`, which maps module path to score. Regression comparison uses a tolerance, configured in `.quality/crap.json` alongside the absolute threshold of 30, so that a module resting exactly on the threshold does not flip the gate on a rounding difference. A module that exists in the report but not in the baseline is treated as new and is allowed to pass, because requiring a baseline entry for a new file would make every new module a gate failure; the baseline is refreshed by an explicit command named in the script's `--help` output.

Add `tests/smoke/test_crap_metric.py` covering the formula at its boundaries — full coverage reducing the score to complexity, zero coverage maximizing it, and a known hand-computed case — plus the coverage-map loader and the regression comparison, including the tolerance boundary. These tests must fail before the implementation and pass after, and the plan's `Artifacts and Notes` section must show that transcript.

Document the metric in `docs/engineering_process_metrics.md`, which already exists and is the named place for tracked post-merge outcomes, and add a pointer from `docs/README.md`.

### Milestone 3 — Mutation testing and the continuous-integration ratchet

At the end of this milestone the test suite has a measurable ability to fail. Add `mutmut` to `requirements-quality.txt`, configure it in the project's `pyproject.toml` to mutate only `api/`, `models/`, `services/`, `utils/`, and `config/`, and to run the contributor-safe pytest selection as its test command.

Produce the mutation baseline once, outside CI, and commit it as `.quality/mutation_baseline.json` mapping module path to survivor count and total mutant count. This run is expected to be slow; measure the wall-clock duration and record it in `Artifacts and Notes` so the next contributor is not surprised, and record in the `Decision Log` that full-repository mutation runs stay out of CI for that reason.

Implement `scripts/quality/mutation_gate.py`. Given a list of changed Python paths and a baseline, it runs mutation only over those paths, then fails when a touched module's survivor count rises above its baseline plus tolerance. Handle the case where a touched module is absent from the baseline by treating it as new and reporting, not failing — the same rule Milestone 2 uses, for the same reason.

Add `.github/workflows/quality-metrics.yml` with two jobs. The `crap` job runs on every pull request and every push to `main`, reusing the dependency installation pattern already in `.github/workflows/ci.yml`. The `mutation` job runs only when Python files under the mutated paths changed, derives that list from the pull request's changed files, and carries an explicit `timeout-minutes`. Both jobs must be added to whatever list of required checks the branch protection uses; if that list cannot be discovered from the repository, the plan requires the contributor to state in the `Outcomes & Retrospective` section that the gate is advisory until a maintainer adds it, rather than claiming enforcement that does not exist.

Finally, record the two gates where the process is defined: add them to the review section of `docs/AI_Feature_Development_Workflow.md` and to the development-commands block of `AGENTS.md`, and add the two measures to `docs/engineering_process_metrics.md`.

Non-goals for this milestone: TypeScript or Next.js mutation testing, whole-repository mutation runs in CI, any refactoring of modules that score badly, and any change to the product's runtime dependencies.

## Concrete Steps

All commands run from the repository root unless stated otherwise. A virtual environment is expected at `ai_trainer_env` per `AGENTS.md`; activate it first with `source ai_trainer_env/bin/activate`.

Baseline measurement, before any change:

    python -m pytest tests/smoke -q
    python -m pytest -m "not live and not debug and not e2e" tests/ -q

Record both counts. The issue's `### Smoke baseline` section must contain these numbers, not an estimate.

Milestone 1:

    python -m pip install -r requirements-quality.txt
    python scripts/quality/generate_architecture_map.py --repo-root . --provider ollama
    git status --short

Expected: a new `.codeboarding/` directory and a modified or new `ARCHITECTURE.md`. Nothing under `api/`, `models/`, `services/`, or `web/` may appear in that output; if anything does, the generator wrote outside its output directory and the run must be treated as a failure.

    python -m ruff check .

Expected: `All checks passed!`. The generated documents must be excluded from linting or must already be Markdown, which ruff ignores.

    python -m pytest tests/smoke -q

Expected: the same counts recorded in the baseline step.

Milestone 2:

    python -m pip install -r requirements-dev.txt
    python -m pytest -m "not live and not debug and not e2e" tests/ \
      --cov=api --cov=models --cov=services --cov=utils --cov=config \
      --cov-report=term-missing --cov-report=json:.quality/coverage.json -q

Expected: a coverage table followed by the test summary. `.quality/coverage.json` must exist and must be gitignored — it is a per-run artifact, not a committed file. Record here whether any tested module shows zero executed statements, which settles the inference recorded in `Surprises & Discoveries`.

    python scripts/quality/crap_report.py --top 20

Expected: a ranked table with a header row naming path, statements, complexity, coverage, and CRAP, followed by twenty rows in descending score order.

    python scripts/quality/crap_report.py --write-baseline

Expected: writes `.quality/crap_baseline.json` and prints the number of modules recorded.

    python -m pytest tests/smoke/test_crap_metric.py -q

Expected: all tests pass. Before the implementation exists, this command must fail with a collection error naming the missing module; that transcript belongs in `Artifacts and Notes` as the fail-before evidence.

Milestone 3:

    python -m mutmut run
    python -m mutmut results

Expected: a progress line per mutant and a final summary reporting killed, survived, and total counts. Record the wall-clock duration. If the run exceeds the time the contributor is willing to spend, do not reduce the mutated paths silently — record the reduced scope and the reason in the `Decision Log`.

    python scripts/quality/mutation_gate.py --write-baseline

Expected: writes `.quality/mutation_baseline.json` and prints the number of modules recorded.

Then open a pull request that edits one covered module in a way that weakens its tests without failing them, and confirm the `crap` and `mutation` jobs fail. That pull request is evidence and must be closed, not merged.

## Validation and Acceptance

Milestone 1 is accepted when, on a clean checkout, running the documented generator command produces `ARCHITECTURE.md` whose component names correspond to real top-level modules, and opening the generated diagram and clicking a component navigates to an existing path in the tree. The check is that a person who has never read `api/` can name the responsibility of each of the five top-level Python packages using only the map; a reviewer records the attempt in the `Outcomes & Retrospective` section, including any module the map failed to explain.

Milestone 2 is accepted when `python scripts/quality/crap_report.py --top 20` prints a ranked table on the unmodified tree, when `python -m pytest tests/smoke/test_crap_metric.py -q` passes, and when the same command fails before the implementation exists. It is further accepted when, on a pull request that lowers one module's coverage without lowering its complexity, the `crap` job reports a regression against the baseline and fails; and when a pull request that touches nothing relevant passes. Given a module at CRAP 12 on the baseline, when a commit pushes it to CRAP 31, then the gate fails and names the module; given a module whose score moves by less than the configured tolerance, when the same gate runs, then it passes.

Milestone 3 is accepted when `python -m mutmut run` completes and reports a mutation score on the unmodified tree, when `.quality/mutation_baseline.json` is committed, and when a pull request that weakens assertions in a covered module fails the `mutation` job while a pull request that leaves every touched module at or below its baseline survivor count passes. The acceptance is phrased as behavior because the point of the milestone is a gate that fires on the right input, not a script that exists.

The repository-wide acceptance for all three milestones together: `python -m ruff check .` is green, the contributor-safe pytest selection passes at the recorded baseline count, the web contract artifacts are still fresh per the `web-contract` job, and every new file is additive — no existing product module, test, or runtime dependency is modified by this plan.

## Idempotence and Recovery

Every step is additive and safe to repeat. The generator is safe to re-run: it rewrites its own output directory and `ARCHITECTURE.md`, and re-running it twice in a row must produce no diff, which is itself worth checking and recording. The coverage command writes only to `.quality/coverage.json`, which is gitignored, and a partially written coverage file is overwritten on the next run. Baseline files are plain JSON and are regenerated by the two documented `--write-baseline` commands; an unwanted baseline change is recovered with `git checkout -- .quality/`, which is why baselines belong in the tree and not in a cache directory.

No step in this plan touches `ai_trainer.db`, no step performs a schema migration, and no step calls a live provider with write access. The only external call is the architecture generator's model call, which sends source text and receives a description; if it fails halfway, re-run it, and if a provider is rate-limited, switch the `--provider` flag rather than editing configuration. If a baseline must be rebuilt because the metric definition changed, that is a deliberate act: change the metric in a commit that also updates the baseline and states in the commit message which modules moved and why, so the diff is reviewable rather than a wholesale replacement.

## Artifacts and Notes

The fail-before transcript for Milestone 2, recorded on the unmodified tree:

    $ python -m pytest tests/smoke/test_crap_metric.py -q
    ERROR: file or directory not found: tests/smoke/test_crap_metric.py

The pass-after transcript is to be added here once the implementation lands, along with the `--top 20` table, the mutmut summary, and the measured wall-clock duration of the mutation baseline run. Keep these to the lines that prove the claim.

## Interfaces and Dependencies

New files created by this plan, at these exact paths:

`requirements-quality.txt` — pinned versions of the analysis tools. Separate from `requirements-dev.txt` so that ordinary contributors do not pay the install cost of the mutation runner. It starts with `-r requirements-dev.txt` so that a quality environment is a superset of a development one.

`scripts/quality/__init__.py` — empty, marks the package.

`scripts/quality/crap_metric.py` — pure metric arithmetic and parsing. Required names:

    @dataclass(frozen=True)
    class ModuleScore:
        path: str
        statements: int
        complexity: int
        coverage_fraction: float
        crap: float

    def crap_score(complexity: int, coverage_fraction: float) -> float:
        """Return comp^2 * (1 - cov)^3 + comp. complexity >= 1, 0.0 <= coverage_fraction <= 1.0."""

    def load_coverage_map(coverage_json: pathlib.Path) -> dict[str, float]:
        """Return module path -> executed fraction, from pytest-cov's JSON report."""

    def module_scores(repo_root: pathlib.Path, coverage: dict[str, float]) -> list[ModuleScore]:
        """Walk the five mutated packages, compute radon complexity, join with coverage."""

    def regressions(
        current: list[ModuleScore],
        baseline: dict[str, float],
        tolerance: float,
    ) -> list[ModuleScore]:
        """Return scores that exceed their baseline entry by more than tolerance. Modules absent from the baseline are not regressions."""

`scripts/quality/crap_report.py` — command-line front end. Flags: `--top N`, `--json`, `--write-baseline`, `--fail-on-regression`, `--repo-root PATH`, `--coverage PATH`. Exit codes: `0` on success, `1` on a regression when `--fail-on-regression` is set, `2` on a missing coverage file or malformed baseline.

`scripts/quality/mutation_gate.py` — command-line front end. Flags: `--write-baseline`, `--changed PATH` (repeatable), `--changed-from-git REV`, `--tolerance N`. Exit codes as above.

`scripts/quality/generate_architecture_map.py` — command-line front end. Flags: `--repo-root PATH`, `--provider NAME`, `--out PATH`. Exit code `3` when the provider environment variable is unset.

`.quality/crap.json` — `{"threshold": 30, "tolerance": 1.0}`. `.quality/crap_baseline.json` and `.quality/mutation_baseline.json` — committed baselines. `.quality/coverage.json` — gitignored per-run artifact.

`tests/smoke/test_crap_metric.py` — smoke tests for the metric, the coverage-map loader, and regression comparison.

`.github/workflows/quality-metrics.yml` — the `crap` and `mutation` jobs.

Modified files: `requirements-dev.txt` (add `pytest-cov`, `radon`), `AGENTS.md` (architecture pointer and the two new commands), `docs/README.md` (list this ExecPlan and the new pointer), `docs/engineering_process_metrics.md` (the two new measures), `docs/AI_Feature_Development_Workflow.md` (record the two gates in the review policy), `.gitignore` (add `.quality/coverage.json`), `pyproject.toml` (add the mutation configuration section).

External dependencies and why each is chosen: `pytest-cov` for coverage because it is the pytest integration of `coverage.py`, already the de facto standard and requiring no new infrastructure. `radon` for cyclomatic complexity because it reports per-function complexity for Python without executing the code. `mutmut` for mutation testing because it accepts any test command that reports success through an exit code, supports incremental runs, and exposes a continuous-integration exit flag; `cosmic-ray` is the named alternative. `codeboarding` for the architecture map because it derives components from static analysis of the real tree and serves the result to a coding agent over MCP.

---

*Note (2026-09-19 11:04Z): initial revision, authored by Hermes Agent. Reason: the repository has no committed plan for introducing verification metrics; this document creates one so the change class, the milestones, and the acceptance conditions are recorded before any code is written. No revision has yet been made in response to implementation discoveries.*
