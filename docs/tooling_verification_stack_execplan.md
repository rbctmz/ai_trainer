# Add an architecture map and a verification stack for agent-written code

**Change Class: Class A — Full.** The work adds a new verification boundary and new CI gates, which matches the automatic escalation trigger for "a new cross-module public contract or a new architectural boundary" in `docs/AI_Feature_Development_Workflow.md`.

This ExecPlan is a living document and must be maintained in accordance with `.agent/PLANS.md`. Its `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` sections must stay current while the work proceeds. The document is self-contained: a contributor who has only the current working tree and this file can deliver the whole change. Every term of art is defined in plain language below; nothing here assumes memory of an earlier plan or a conversation.

## Purpose / Big Picture

After this change, a maintainer of this repository can answer three questions without reading source code line by line. First, what are the parts of this system and which one owns which responsibility — visible as one interactive architecture map plus a generated `ARCHITECTURE.md` that a coding agent can load as context. Second, where is the code both complicated and untested — visible as a ranked report of a metric called CRAP, defined below. Third, do the tests actually detect wrong behavior — visible as a mutation score, also defined below.

The reason this matters is that reviewing code has become the slow part of this repository's development loop, while writing it has become fast. A green test run currently proves only that the tests passed; it does not prove that the tests would have failed if the code were wrong. A high-coverage module can still contain assertions that check nothing. A low-coverage module can be the one that breaks in production. Neither condition is visible anywhere in CI today, and the architecture of the system lives only in the heads of the people who built it. Coverage itself is not a gap — `docs/code_quality_measurements.md` already publishes an 81 % contributor-safe baseline — but it is a measurement that nothing enforces, and it says nothing about complexity: a module can be fully covered and still be the one nobody dares to change. This plan turns the existing measurement into a gate and adds the complexity term that coverage cannot express.

The user-visible proof arrives in three steps. After Milestone 1, `ARCHITECTURE.md` exists at the repository root and a generated diagram shows components whose nodes link back to source files. After Milestone 2, running `python scripts/quality/crap_report.py --top 20` prints a ranked table of modules, and CI fails a pull request that makes a module's CRAP score worse than the committed baseline. After Milestone 3, running `python -m mutmut run` reports how many deliberate small bugs the test suite caught, and CI fails a pull request whose touched modules let through a larger share of those bugs than the baseline allowed.

## Progress

- [x] (2026-09-19 11:04Z) Read `.agent/PLANS.md`, `docs/AI_Feature_Development_Workflow.md`, `.github/ISSUE_TEMPLATE/agent_task.yml`, `.github/workflows/ci.yml`, `pytest.ini`, `requirements-dev.txt`, `web/package.json`, and `docs/README.md` to establish the current state.
- [x] (2026-09-19 11:04Z) Classified the change as Class A because it introduces a new verification boundary and new CI gates.
- [x] (2026-09-19 11:04Z) Confirmed that `web/` has no JavaScript unit-test runner. Corrected on review: the claim first written here that no coverage measurement exists was false — `pytest-cov` is already a development dependency and `docs/code_quality_measurements.md` already carries an 81 % contributor-safe baseline. What is absent is complexity and mutation measurement. See `Surprises & Discoveries`.
- [x] (2026-09-19 11:04Z) Wrote this initial revision of the ExecPlan.
- [x] (2026-09-19 11:12Z) Measured the smoke baseline on commit `5420754` (= `origin/main` at `7fc940f` plus a docs-only commit) with a fresh virtual environment built from `requirements-dev.txt`: `1 failed, 2626 passed, 32 skipped in 291.65s`. The failing test is `tests/smoke/test_dsh_pilot_preflight_timeout.py::test_leading_zero_limit_cannot_smuggle_past_the_ceiling`; it passes when run alone. See `Surprises & Discoveries`.
- [x] (2026-09-19 11:52Z) Re-measured after moving the working copy to `~/ai_trainer` and clearing stale bytecode: `2627 passed, 32 skipped in 275.34s`, exit status zero, no failure. The reproducible baseline is therefore `2627 passed, 32 skipped`, and the single earlier failure is recorded as an unreproduced flake rather than a known failure.
- [x] (2026-09-20 07:57Z) Merged `main` (at `93e6f58`) into this branch, which is the step the review of this plan required before any further edit; the branch head is now the merge commit `f5c9132`. Because the review also produced thirteen inline findings, all of priority P2 from the first review round on `f14bd5d`, this revision addresses every one of them: the coverage claims are corrected against the measurements already committed in `docs/code_quality_measurements.md`, `data/` is brought into both metric scopes, the new-module and regression rules are stated, the baseline environment is pinned, the provider variable and the MCP registration path are named, the generated-file revision marker is made reproducible, `backups/` joins the exclusion list, module complexity is defined, and the fail-before evidence is required to be a real failing assertion.
- [ ] Re-measure the smoke and contributor-safe counts on the merged head before committing any Milestone 2 baseline. The counts recorded above were taken on `5420754`, which is no longer an ancestor of this branch, so they describe that commit and not this tree. A flaky or stale baseline makes both ratchets unusable.
- [ ] Resolve or explicitly accept the order-dependent smoke failures recorded in `Surprises & Discoveries`. Reproduction recipe so far: `python -m pytest tests/smoke/test_dsh_pilot_preflight_timeout.py tests/smoke/test_evidence_discipline_docs.py -q` fails on a two-file subset while the whole file passes alone. **(blocking for Milestone 2; the polluting file is not yet identified)**
- [ ] Milestone 1: install CodeBoarding, generate the architecture map, commit `ARCHITECTURE.md`, register the MCP server for agents.
- [ ] Milestone 2: add `radon` to the development requirements (`pytest-cov` is already there), implement the CRAP report over the scope already documented in `docs/code_quality_measurements.md`, re-measure and commit the baseline in the pinned environment, add smoke tests for the metric.
- [ ] Milestone 3: add mutation testing, commit the mutation baseline, add the changed-module gate, wire both gates into CI, record the gates in the workflow docs.
- [ ] Update `docs/README.md` to list this ExecPlan, and update `docs/engineering_process_metrics.md` with the two new tracked measures.

## Surprises & Discoveries

- **Observed**: coverage is already measured in this repository, and this plan's original claim that it is not was wrong. `requirements-dev.txt` carries `pytest-cov>=5,<7` (and `mypy>=1.11,<2.0`), and `docs/code_quality_measurements.md` — snapshot 2026-09-17, issue #587 — records a contributor-safe baseline of 27488 statements with 81 % covered over `api/`, `models/`, `services/`, `data/`, and `utils/`. That document also names the blind zones: `utils/modern_ui.py` at 0 %, `data/garth_client.py` at 14 %, `models/ai_data_context.py` at 15 %, `data/garmin_client.py` at 48 %, `models/ai_tools.py` at 53 %. What is genuinely absent from the repository is cyclomatic complexity (no `radon` dependency anywhere) and mutation testing (no runner, no baseline, no gate). The source is `requirements-dev.txt` and `docs/code_quality_measurements.md`.
- **Inferred**: because coverage already has a documented baseline, Milestone 2 must not re-derive one from scratch and must not install `pytest-cov` as if it were new. It adds `radon` and mutation testing, and it reuses the established coverage scope so that the CRAP number and the documented 81 % describe the same selection. Choosing a different scope would silently produce a second, incomparable coverage definition.
- **Verified by**: reading `requirements-dev.txt` (row `pytest-cov>=5,<7`) and the coverage table in `docs/code_quality_measurements.md` at the merged tree. Confirmed.

- **Observed**: the recorded smoke baseline (`2627 passed, 32 skipped`) was measured on commit `5420754`, and `git merge-base --is-ancestor 5420754 b283b62` exits 1, so that measurement and the commit it names sit on a history that is no longer an ancestor of this branch. The branch was then merged with `main` at `93e6f58` (this PR's own merge commit), which brought in work that was not present when the baseline was taken. The source is the ancestry check and the merge commit now at the head of this branch.
- **Inferred**: a pass count is only a baseline for the tree it was measured on. The number recorded earlier remains valid as a description of `5420754`, but it cannot be committed as the baseline for the merged tree, and neither the CRAP baseline nor the mutation baseline may be generated before the smoke count is re-measured on the merged head.
- **Verified by**: the ancestry check exits 1 and the merge commit is present at the branch head. Confirmed; the re-measurement itself is NOT YET run and is the first item of Milestone 2.

- **Observed**: `web/package.json` declares scripts `dev`, `build`, `start`, `lint`, `contract:inventory`, and `contract:extract`, and its `devDependencies` list contains no `jest`, `vitest`, or other unit-test runner. The source is `web/package.json`.
- **Inferred**: the Next.js front end cannot be mutation-tested or covered in this plan without first introducing a unit-test runner, which is a separate change with its own review. The cheapest falsifying check is to grep the tracked tree for a test runner import (`grep -rn "vitest\|jest" web/`) and confirm no match.
- **Verified by**: NOT YET. Confirm during Milestone 3 before writing any TypeScript tooling; if a runner does exist, the non-goal recorded below must be revised.

- **Observed**: `docs/technical_debt_register.md` has a snapshot date of 2026-08-16 and lists exactly one open item, `TD-006` (P2, structure, "large modules concentrate churn"). The source is that file.
- **Inferred**: the missing verification layer is not currently tracked as debt, so this plan introduces new measurement rather than closing a register entry. Consequence: no `TD-XXX` identifier is created or consumed by this work, and the register should not be edited except to link this plan if a reviewer asks.
- **Verified by**: reading the register's `Сводка` table directly; confirmed one open row.

- **Observed**: the measured smoke baseline is `1 failed, 2626 passed, 32 skipped in 291.65s`. The single failure is `tests/smoke/test_dsh_pilot_preflight_timeout.py::test_leading_zero_limit_cannot_smuggle_past_the_ceiling`. Running that test alone with the same interpreter and the same environment reports `1 passed in 0.52s`. Both results come from captured command output on commit `5420754`, in a fresh virtual environment built from `requirements-dev.txt`.
- **Inferred**: the failure depends on test execution order or on state left by another test in the suite, rather than on the assertions in the test itself. The cheapest falsifying check is to run the same file on its own (`python -m pytest tests/smoke/test_dsh_pilot_preflight_timeout.py -q`) and then the smoke directory in reverse order; if the file passes in isolation and fails in the suite, the order hypothesis stands, and if it passes in the suite when the suite is split in half, the culprit is in the other half.
- **Verified by**: the isolated run was executed and passed, so the "the test itself is broken" hypothesis is rejected. The order hypothesis is NOT YET tested, and whether the suite also fails this way in CI on `main` is NOT YET checked. Do not report this as a pre-existing `main` failure until that check runs. The new CRAP and mutation gates from Milestones 2 and 3 both run the same suite, so resolving this must precede Milestone 2's baseline commitment; otherwise a flaky baseline makes both ratchets unusable.

- **Observed**: the same commit was measured twice more after the working copy moved from `/tmp/ai_trainer` to `~/ai_trainer`, with the same interpreter and dependency set: `2627 passed, 32 skipped in 282.53s` and then `2627 passed, 32 skipped in 275.34s`, both with a zero exit status, the second one written to a log file whose tail is quoted in `Concrete Steps`. The previously failing test passed in both runs. Source: captured command output.
- **Inferred**: `test_leading_zero_limit_cannot_smuggle_past_the_ceiling` is flaky rather than deterministically broken, and the flake did not reproduce on two consecutive clean runs. The cheapest falsifying check is a repeat loop over the file inside a full-suite context (run the smoke suite N times and count how often the test fails); a single-file repeat will not exercise the ordering that the hypothesis blames.
- **Verified by**: three suite-level runs exist, with one failure and two passes. The first run was the only one made against a tree carrying bytecode compiled at a different absolute path, which is recorded below as a separate observation and is a candidate confounder. The flake is NOT YET reproduced deliberately, so its rate is unknown. Consequence for Milestone 2: the coverage baseline must be committed from a run whose result is reproducible, and this observation must be extended with a repeat count before that happens.

- **Observed**: running a two-file subset on the moved tree — `python -m pytest tests/smoke/test_dsh_pilot_preflight_timeout.py tests/smoke/test_evidence_discipline_docs.py -q` — produced `1 failed, 44 passed in 19.52s`, and the failure was `test_limit_outside_1_300_fails_before_paid_run[-5]`, a different test in the same file than the one that failed first. Running that test alone gave `6 passed in 0.44s`, and running the whole file alone gave `39 passed in 19.49s`. Source: captured command output on commit `f368904`.
- **Inferred**: `tests/smoke/test_dsh_pilot_preflight_timeout.py` contains order- or state-dependent tests, and the affected test depends on which other files the session runs alongside it, since the file passes entirely on its own. The cheapest falsifying check is a bisect over subsets: run the file paired with one other directory at a time and, when a pairing fails, halve that partner until one file remains.
- **Verified by**: the isolated single test and the isolated whole file both passed, so the two-file failure is caused by the combination rather than by the test's own assertions. The exact polluting file is NOT YET identified. Consequence: `tests/smoke/test_dsh_pilot_preflight_timeout.py` is a candidate for per-test isolation or an order-insensitive rewrite, and this must be resolved or explicitly accepted before Milestone 2 commits a coverage baseline, because mutation testing re-runs subsets of this suite many times and a flaky partner makes survivor counts irreproducible.

- **Observed**: the first smoke run on the moved tree reported failure locations as `../../../tmp/ai_trainer/tests/smoke/...` even though the command ran from `/home/greg/ai_trainer`. Every `__pycache__` directory in the copied tree contained the literal string `/tmp/ai_trainer`, because `__pycache__` bytecode records the absolute source path it was compiled from and the tree was copied with `rsync -a`. Source: `grep -rl "/tmp/ai_trainer" tests/__pycache__` and a byte-level search of one `.pyc`.
- **Inferred**: the stale bytecode changes only how pytest reports paths, not which tests run or what they assert, because the source files were verified byte-identical between the two locations with `diff -r` before the copy was accepted. The cheapest falsifying check is to delete every `__pycache__` and `.pytest_cache` directory, re-run, and confirm that the reported paths are local and the pass count is unchanged.
- **Verified by**: after deleting the caches, the smoke suite reported `2627 passed, 32 skipped in 275.34s` with `grep -c "/tmp/ai_trainer"` on the captured log returning zero. The hypothesis that the paths were cosmetic is supported. Practical lesson for any future move of this tree: clear `__pycache__` and `.pytest_cache` immediately after copying, before trusting any reported path.

## Decision Log

- Decision: build the verification stack on CodeBoarding for the architecture map rather than on a diagramming-only tool.
  Rationale: CodeBoarding derives its components from a control-flow and dependency analysis of the real tree and exposes the result both as a generated Markdown document and through a Model Context Protocol server. A Model Context Protocol server, abbreviated MCP, is a small local process that offers tools and documents to a coding agent over a standard protocol; registering one lets the agent read the architecture instead of re-deriving it from source on every turn. A tool that only draws a picture would not reduce the agent's context cost, which is half the point of the milestone.
  Date/Author: 2026-09-19 / Hermes Agent

- Decision: generate the architecture analysis with a locally hosted model reached through the repository's existing `OLLAMA_HOST` and `OLLAMA_MODEL` settings on the first runs, falling back to a hosted provider already configured in `.env` only if the local result is unusable. Revised on review: the first version of this plan named `OLLAMA_BASE_URL`, which does not exist in this repository.
  Rationale: `AGENTS.md` warns that `logs/` may contain personal training metrics. Sending repository source to a third-party provider is a data-handling decision that belongs to the maintainer, not to a tooling commit. Running the generator locally keeps the decision reversible. No new secret is introduced by this plan; it reuses provider configuration that already exists. The wrapper must read the provider configuration the way the rest of the repository does rather than inventing a variable name: `OLLAMA_HOST` (default `http://localhost:11434`) and `OLLAMA_MODEL` are defined in `config/settings.py` and documented in `.env.example`, and no variable called `OLLAMA_BASE_URL` is defined anywhere in the tracked tree. A wrapper that required `OLLAMA_BASE_URL` would either reject a correctly configured checkout or silently reach a default endpoint that the repository never configured, so the `--provider ollama` path must build its endpoint from `OLLAMA_HOST` and its model from `OLLAMA_MODEL`, and must exit with the documented code 3 when `OLLAMA_HOST` is unset.
  Date/Author: 2026-09-19, revised 2026-09-20 / Hermes Agent

- Decision: implement CRAP as a committed script over `pytest-cov` data plus `radon`, rather than adopting a commercial quality dashboard.
  Rationale: the inputs are two small, well-known libraries; the arithmetic is one formula; and a committed script stays runnable offline and in CI without a service account. A dashboard would add a dependency and a data-egress question for a number that a hundred lines of Python can produce.
  Date/Author: 2026-09-19 / Hermes Agent

- Decision: enforce both new metrics as a ratchet on touched modules, not as an absolute threshold on the whole repository.
  Rationale: this repository already carries modules that would fail an absolute bar. A whole-repository gate would block every unrelated pull request until a large cleanup landed, which is the failure mode that makes teams disable a gate. Requiring only that a touched module does not get worse keeps the gate honest and immediately useful.
  Date/Author: 2026-09-19 / Hermes Agent

- Decision: measure coverage on the contributor-safe test selection (`-m "not live and not debug and not e2e"`) over the same five packages that `docs/code_quality_measurements.md` already measures — `api/`, `models/`, `services/`, `data/`, and `utils/` — and state in the report that the number is a lower bound. Revised on review: the first version of this plan listed `config/` and omitted `data/`, which both contradicted the committed measurement and left the provider clients outside every gate.
  Rationale: the live, debug, and end-to-end selections need credentials, network, or a browser, so they are not part of the path a reviewer runs. Using the same selection as CI keeps the developer's number and the gate's number identical, which is what makes a ratchet enforceable. The package list is not a free choice: `docs/code_quality_measurements.md` already publishes an 81 % baseline over these five packages, and a different list would silently define a second coverage number that no committed document describes, so a reviewer comparing the two would see a disagreement that is really a scope difference. `data/` must be included because it holds the provider clients and is product code by the repository's own definition in `AGENTS.md`, and because it carries the largest uncovered modules in the committed measurement: `data/garth_client.py` at 14 % and `data/garmin_client.py` at 48 %. Leaving it out would mean that a pull request changing ingestion behaviour receives neither CRAP nor mutation protection while both jobs still report green. `config/` is excluded for the reason the committed document already records: `config.settings` is imported by the root `tests/conftest.py` before measurement starts, so the package never appears in `--cov` output and listing it would suggest a coverage number that cannot exist.
  Date/Author: 2026-09-19, revised 2026-09-20 / Hermes Agent

- Decision: choose `mutmut` as the Python mutation runner, with `cosmic-ray` as the fallback if `mutmut`'s test-runner integration proves too restrictive.
  Rationale: `mutmut` runs any test command that reports success through an exit code, supports incremental runs that remember earlier results, and exposes a CI exit flag. The published comparison of Python mutation tools rates `cosmic-ray` highest on community activity but notes `mutmut`'s simpler integration, and this plan values the smaller wiring surface first.
  Date/Author: 2026-09-19 / Hermes Agent

- Decision: do not refactor any module because of a score produced by this work.
  Rationale: the plan's deliverable is measurement. Mixing refactoring into it would make the diff unreviewable and would let a scoring bug masquerade as a code improvement. Findings become their own issues, filed with the score as evidence.
  Date/Author: 2026-09-19 / Hermes Agent

- Decision: a module absent from the committed baseline is not permanently exempt from either gate. It must either already satisfy the absolute threshold, or the change that introduces it must carry a reviewed baseline entry for it. Revised on review: the first version treated any unbaselined module as new and allowed it to pass.
  Rationale: absence from the baseline is re-evaluated on every run, so under the first rule a complex, untested module could be introduced, pass both gates, and then continue to bypass the ratchet indefinitely — every later edit to it would also be "new" — while both jobs reported green. The two acceptable outcomes keep the exemption visible at the moment it is created without adding ceremony to ordinary work: a module whose CRAP is at or below the threshold of 30 needs nothing, because it is not what the metric is looking for, and a module above it must appear in the diff as an explicit baseline entry that a reviewer can accept or reject. The same rule governs the mutation gate, for the same reason.
  Date/Author: 2026-09-20 / Hermes Agent

- Decision: the CRAP regression comparison takes an explicit set of changed paths, and the command exposes it. Revised on review: the first version's `regressions()` received every current score and the front end had no way to narrow it.
  Rationale: the stated guarantee is that a pull request touching nothing relevant passes, but a function that receives every module can only compare the whole repository, so a documentation or test-only pull request would fail whenever coverage shifted in a module it never touched — the failure mode that teaches people to disable a gate. The function therefore takes a `changed` set and the front end takes `--changed PATH` (repeatable) and `--changed-from-git REV`; with no set given the command still prints the repository-wide table but does not fail the gate, and CI always passes the pull request's changed files. A gate whose scope is not the diff is a gate nobody can satisfy locally.
  Date/Author: 2026-09-20 / Hermes Agent

- Decision: the mutation gate compares the surviving share of mutants rather than the absolute number of survivors. Revised on review: the first version failed a module when its survivor count rose above the baseline.
  Rationale: the outcome this milestone claims is that a pull request which lets through a larger share of deliberate bugs fails, and a survivor count cannot express a share. Comparing counts passes a module that moves from 10 survivors out of 100 mutants to 9 out of 20, where the survival rate worsens from 10 % to 45 %, and it fails a module that moves from 20 out of 200 to 21 out of 210, where the rate is unchanged. The baseline therefore stores the total mutant count alongside the survivor count, and the gate compares `survivors / total` for each touched module against the baseline rate, with the tolerance expressed in percentage points. When the total mutant count changes, the rate remains the comparison, and the gate prints both totals so a reviewer can see which number moved.
  Date/Author: 2026-09-20 / Hermes Agent

- Decision: both baselines are generated in an environment equivalent to the one CI uses, and the environment is recorded inside the baseline file. Added on review.
  Rationale: `docs/code_quality_measurements.md` already records that this repository's test counts depend on the environment: a clean checkout produces 38 skips where a warmed workspace produces 13, because the absence of `web/node_modules` skips 22 contract tests and the absence of a local `ai_trainer.db` skips 3 more. A baseline generated in a warmed workspace therefore measures a different selection than the clean CI job that will compare against it, and can report higher coverage or kill a different set of mutants, so an unchanged tree would fail. The baseline file consequently carries a metadata block naming the Python version, the exact command, and the skip count observed when it was written, together with the module map; a run whose skip count differs from the recorded one is reported as not comparable rather than as a regression.
  Date/Author: 2026-09-20 / Hermes Agent

- Decision: module complexity is the arithmetic sum of the cyclomatic complexities `radon` reports for that module's blocks. Added on review: the first version defined complexity per function and then used it per module without saying how the two relate.
  Rationale: without a stated aggregation, two conforming implementations can assign different scores to the same module — sum, maximum, and average all satisfy the earlier wording — so the threshold and the committed baseline would not be portable between them. `radon` reports one entry per function, per method, per class-level block, and per module-level block, and it reports a nested function as its own entry rather than folding it into its parent, so the module figure is the sum over all reported entries with each block counted exactly once and no parent's aggregate added on top. The sum is the aggregation that matches the formula in use, which multiplies a single complexity figure by an uncovered share, and it is the only one that cannot decrease when a branch is added. A hand-computed test over a module containing two functions, a method, and a nested function pins the definition.
  Date/Author: 2026-09-20 / Hermes Agent

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

Add `scripts/quality/generate_architecture_map.py` as the single entry point. It must accept `--repo-root` and `--provider` flags, read the provider configuration from the environment exactly as the rest of the repository does (`.env` via `config/settings.py` conventions), refuse to run when the provider environment variable is unset rather than silently falling back, and write its output to `.codeboarding/`. Because `AGENTS.md` states that `logs/` may contain personal training metrics and that `ai_trainer.db` is a local cache, the wrapper must pass an explicit exclusion list covering `logs/`, `ai_trainer.db`, `archived/`, `backups/`, `spikes/`, `debug/`, `examples/`, `research/`, and `output/`; those directories are already declared as out of scope in `AGENTS.md`. The first version of this plan omitted `backups/` from that list, and it belongs there for the same reason as the rest: it holds stale copies of the tree, so leaving it in scope would let the generator report duplicate components that correspond to no live file and, when the documented hosted-provider fallback is used, would send the contents of those copies to that provider. The exclusion list must be asserted in a test rather than trusted, because a silently dropped entry produces a plausible-looking map rather than an error.

Commit the generated `ARCHITECTURE.md` at the repository root and the `.codeboarding/` component documents. Commit the generated artifacts rather than gitignoring them, because their value is that an agent reads them without running a generator first. Add a header comment to `ARCHITECTURE.md` stating that the file is generated, naming the command that regenerates it, and naming the source revision it describes, so a stale copy is detectable.

The revision marker must name the revision of the *source*, not the commit that contains the file. The first version of this plan asked for "the commit at which it was produced", which cannot be satisfied together with the idempotence requirement stated in *Idempotence and Recovery*: the artifact cannot contain the hash of the commit that adds it, because writing that hash changes the commit, and a marker holding the pre-artifact `HEAD` changes on every regeneration, so a clean checkout would produce a diff even when no source changed. The marker is therefore defined as the hash of the most recent commit that touched the analysed source and the tooling — the output of `git log -1 --format=%H -- api models services data utils config scripts` — which is stable across commits that only regenerate the artifact, and which a reader can resolve to a real commit to see what the map describes. The header also names the generator version and the command with its arguments, because those change the output shape, and the *Idempotence and Recovery* check is run after the artifact is committed, so it proves the marker rather than assuming it.

Wire the generator into the agent workflow in two places. First, register the CodeBoarding MCP server in a tracked configuration file at the repository root: `.mcp.json`, holding a single top-level `mcpServers` object whose one entry names the server, the command that starts it, and its arguments. Naming that file and its shape is the point — the first version of this plan said "the repository's agent configuration" without naming a file or a format, and the tracked tree contains no MCP configuration at all, so an implementer could satisfy every acceptance check in this milestone while the agent-facing capability existed only in an uncommitted personal configuration on one machine, or did not exist. The file must be committed, because a capability that only works on the machine where it was installed by hand is not part of the repository. The exact command and arguments are taken from the installed version's own documentation, as the paragraph above requires, and recorded in the `Decision Log`; the plan deliberately does not guess them. Second, add one line to `AGENTS.md` under Architecture Context pointing at `ARCHITECTURE.md` as the first thing to read before significant planning work. Add the same pointer to `docs/README.md`.

The proof of this milestone is behavioral: after running the documented command on a clean checkout, `ARCHITECTURE.md` exists, the diagram renders, and a node click navigates to a real source path. It is not proven by the command exiting zero, and it is not proven by the two files existing either — the agent-facing half of the milestone is the registered server, so the acceptance also includes one MCP query, issued on a clean checkout from the committed `.mcp.json`, whose response names at least one component of this repository. That transcript belongs in `Artifacts and Notes` alongside the generator output, because a milestone that claims an agent can read the architecture without having asked the server a single question has verified only that a file was written.

### Milestone 2 — CRAP metric and the untested-complexity report

At the end of this milestone a maintainer can rank modules by risk and see whether a pull request made any module worse. The first step is not a new measurement but a re-measurement: the smoke and contributor-safe counts recorded earlier in this plan were taken on `5420754`, which is no longer an ancestor of this branch, so they must be re-run on the merged head and written back here before anything is committed as a baseline. The same run repeats the coverage command already documented in `docs/code_quality_measurements.md` and confirms whether the published 81 % still describes this tree; if it does not, the difference is recorded here as a fact about the merged tree rather than silently absorbed into a new number. Both runs happen in the environment pinned below, and the skip count observed is written down with the result, because a count is only comparable to another count from the same environment.

Add `radon` to `requirements-dev.txt` as a bounded range in the style already used there; `pytest-cov` is already present at `pytest-cov>=5,<7` and must not be added a second time. Implement `scripts/quality/crap_metric.py` with pure functions and no file I/O in the scoring path, and `scripts/quality/crap_report.py` as the command-line front end. Score at module granularity, not function granularity, for the first iteration: module granularity matches the paths a reviewer already thinks in and keeps the baseline file small enough to review in a diff. Record in the `Decision Log` that function-level scoring is deferred, and why.

The module figure must be defined, not assumed. `radon` reports complexity per block, and a module contains several blocks, so `module_scores()` computes a module's complexity as the arithmetic sum of the complexities of every block `radon` reports for that file — each function, each method, each class body, and the module-level block — with each block counted once and no parent's aggregate added on top, because `radon` reports a nested function as its own entry rather than folding it into its parent. The decision and its reasoning are recorded in the `Decision Log`. The alternative aggregations are not equivalent: taking the maximum would let a module grow many moderately complex functions while its score stood still, and taking the average would improve the score by adding a trivial function, which is the opposite of what the metric is for. The coverage side of the join comes from the five packages already measured in `docs/code_quality_measurements.md` — `api/`, `models/`, `services/`, `data/`, and `utils/` — for the reason recorded there and repeated in the `Decision Log`: `data/` holds the provider clients and carries the largest uncovered modules, and `config/` cannot appear in `--cov` output at all because the root `tests/conftest.py` imports it before measurement starts.

The report prints a ranked table with the columns path, statements, complexity, coverage fraction, and CRAP score, and supports a JSON output mode so CI and a human read the same numbers. It writes and reads a committed baseline at `.quality/crap_baseline.json`, which carries a metadata block naming the Python version, the exact generating command, and the skip count observed when it was written, together with the map from module path to score. The metadata exists because a coverage or mutation number is only comparable to another number from the same environment: `docs/code_quality_measurements.md` already records that this repository's selection differs by 25 tests between a clean checkout and a warmed workspace, so a baseline taken in one and compared in the other would fail an unchanged tree. A run whose skip count differs from the recorded one is reported as not comparable rather than as a regression. Regression comparison uses a tolerance, configured in `.quality/crap.json` alongside the absolute threshold of 30, so that a module resting exactly on the threshold does not flip the gate on a rounding difference.

Regression comparison is scoped to the pull request's own diff. `regressions()` takes the set of changed module paths and compares only those, and `crap_report.py` exposes `--changed PATH` (repeatable) and `--changed-from-git REV` to build that set; when no set is supplied the command prints the repository-wide table and exits successfully rather than failing the gate, and the continuous-integration job always passes the changed files it derived from the pull request. The first version of this plan promised that unrelated pull requests pass while handing the comparison function every module in the repository, which meant a documentation-only change could fail because coverage had shifted in a module it never touched.

A module present in the report but absent from the baseline has exactly two acceptable outcomes, and permanent exemption is not one of them. If its CRAP score is at or below the threshold of 30 it passes, because such a module is not what the metric is looking for. If its score is above the threshold, the change that introduces the module must carry a reviewed baseline entry for it in the same commit, so the exemption appears in the diff at the moment it is created. This replaces the earlier rule under which any unbaselined module passed: with that rule a complex, untested module could be added, pass both gates, and remain outside the ratchet indefinitely, because absence from the baseline is re-evaluated on every run and would keep excusing it. The baseline is refreshed by an explicit command named in the script's `--help` output, and refreshing it is a reviewed change rather than a maintenance chore.

Add `tests/smoke/test_crap_metric.py` covering the formula at its boundaries — full coverage reducing the score to complexity, zero coverage maximizing it, and a known hand-computed case — plus the coverage-map loader, the regression comparison including the tolerance boundary and its restriction to the supplied changed set, and the two-outcome rule for a module absent from the baseline. The aggregation needs its own case, because it is the part of this milestone that a second implementation is most likely to get differently: the test builds a small module containing two top-level functions, one method inside a class, and a nested function, states the expected complexity of each block, and asserts that the module figure is their sum. That expected value is written by hand from the source text in the test rather than read from `radon`, so the test pins the definition instead of recording whatever the library returns.

The tests must fail before the implementation exists, and the failure must be a real one. The first version of this plan offered `ERROR: file or directory not found: tests/smoke/test_crap_metric.py` as the fail-before transcript, which proves only that pytest was asked for a file that did not exist; it would count as a valid RED step even if the eventual implementation were a stub that happened to satisfy nothing. The file is therefore created first, containing the assertions against the specified interface, and the transcript recorded in `Artifacts and Notes` is the failing assertion or the failed import that pytest reports when the module it imports is genuinely absent — not a missing-path error.

Document the metric in `docs/engineering_process_metrics.md`, which already exists and is the named place for tracked post-merge outcomes, and add a pointer from `docs/README.md`.

### Milestone 3 — Mutation testing and the continuous-integration ratchet

At the end of this milestone the test suite has a measurable ability to fail. Add `mutmut` to `requirements-quality.txt`, configure it in the project's `pyproject.toml` to mutate only `api/`, `models/`, `services/`, `data/`, and `utils/`, and to run the contributor-safe pytest selection as its test command. The mutated set is the coverage set, deliberately and with one exception: `data/` is included because it holds the provider clients and carries the two least-covered modules in the committed measurement (`data/garth_client.py` at 14 %, `data/garmin_client.py` at 48 %), so leaving it out would let a pull request change ingestion behaviour with neither metric protecting it while both jobs reported green; and `config/` is omitted because it cannot be covered (the root `tests/conftest.py` imports it before measurement starts) and because mutating a package whose coverage is structurally absent produces survivors that no test could ever kill. A mutation scope narrower than the coverage scope is a gate with a documented hole, so the two lists are asserted equal by a test.

Produce the mutation baseline once, outside CI, and commit it as `.quality/mutation_baseline.json` mapping module path to survivor count and total mutant count. This run is expected to be slow; measure the wall-clock duration and record it in `Artifacts and Notes` so the next contributor is not surprised, and record in the `Decision Log` that full-repository mutation runs stay out of CI for that reason.

Implement `scripts/quality/mutation_gate.py`. Given a list of changed Python paths and a baseline, it runs mutation only over those paths, then fails when a touched module's survival rate — its surviving mutants divided by its total mutants — rises above the baseline rate for that module by more than the configured tolerance, expressed in percentage points. The comparison is a rate and not a count, and the reason is recorded in the `Decision Log`: a module that moves from 10 survivors out of 100 mutants to 9 out of 20 has improved its survivor count while worsening its survival rate from 10 % to 45 %, so a count-based gate would pass exactly the regression this milestone exists to catch, and it would fail a module that moved from 20 out of 200 to 21 out of 210 with an unchanged rate. Both totals are printed with the verdict, so a reviewer can see whether the rate moved because the numerator or the denominator did. The baseline is therefore read as a mapping from module path to a survivor count and a total mutant count, and a baseline entry that carries only a count is rejected as malformed rather than silently compared.

A touched module absent from the baseline follows the same two-outcome rule as Milestone 2. It passes when its survival rate is at or below the mutation rate the gate would accept for a baselined module, and otherwise the change that introduces it must carry a reviewed baseline entry for it. Treating an unbaselined module as new and merely reporting it, as the first version of this plan did, would leave a newly added module outside the ratchet for as long as it existed, since its absence is re-evaluated on every run. A touched module whose environment does not match the baseline's recorded one — a different skip count, and therefore a different test selection — is reported as not comparable rather than as a regression.

Add `.github/workflows/quality-metrics.yml` with two jobs. The `crap` job runs on every pull request and every push to `main`, reusing the dependency installation pattern already in `.github/workflows/ci.yml`, and passes the pull request's changed files to `--changed`. The `mutation` job runs when Python files under the mutated paths changed *or* when anything under `tests/` changed, and carries an explicit `timeout-minutes`. The test-tree trigger is the part the first version of this plan got wrong: it scoped the job to the mutated product paths alone, while the acceptance asks the job to catch a pull request that weakens assertions. A change that only edits `tests/` touches no mutated path, so the job would be skipped at exactly the moment its verdict mattered most, and a suite that had been hollowed out would keep reporting green. Because mutation is expensive, the job does not re-mutate the whole tree when only tests changed: it maps the changed test files to the modules they exercise — by the module-name convention already visible in `tests/`, and by the `--cov` report when the mapping is ambiguous — and mutates that set, falling back to a conservative broader run when the mapping cannot be resolved. A pull request that changes shared fixtures rather than test files is treated as a test change, because a fixture edit can weaken assertions in every test that uses it. Both jobs must be added to whatever list of required checks the branch protection uses; if that list cannot be discovered from the repository, the plan requires the contributor to state in the `Outcomes & Retrospective` section that the gate is advisory until a maintainer adds it, rather than claiming enforcement that does not exist.

Finally, record the two gates where the process is defined: add them to the review section of `docs/AI_Feature_Development_Workflow.md` and to the development-commands block of `AGENTS.md`, and add the two measures to `docs/engineering_process_metrics.md`.

Non-goals for this milestone: TypeScript or Next.js mutation testing, whole-repository mutation runs in CI, any refactoring of modules that score badly, and any change to the product's runtime dependencies.

## Concrete Steps

All commands run from the repository root unless stated otherwise. A virtual environment is expected at `ai_trainer_env` per `AGENTS.md`; activate it first with `source ai_trainer_env/bin/activate`.

Baseline measurement, before any change:

    python -m pytest tests/smoke -q
    python -m pytest -m "not live and not debug and not e2e" tests/ -q

On commit `5420754` the first command was run three times. The first run, made while the tree still lived at `/tmp/ai_trainer`, produced:

    1 failed, 2626 passed, 32 skipped, 3 warnings in 291.65s (0:04:51)

The failure was `tests/smoke/test_dsh_pilot_preflight_timeout.py::test_leading_zero_limit_cannot_smuggle_past_the_ceiling`, which passes when run in isolation. The second and third runs, made after the tree moved to `~/ai_trainer` and the stale bytecode was cleared, produced:

    2627 passed, 32 skipped, 3 warnings in 275.34s (0:04:35)

with exit status zero. Treat `2627 passed, 32 skipped` as the baseline to hold and treat the earlier single failure as an unreproduced flake whose rate is unknown. The wider contributor-safe selection has not been run yet: it covers a much larger set and its count must be recorded here before Milestone 2 commits a coverage baseline, because the CRAP report scores exactly that selection. The issue's `### Smoke baseline` section carries the same numbers; do not replace them with an estimate.

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
      --cov=api --cov=models --cov=services --cov=data --cov=utils \
      --cov-report=term-missing --cov-report=json:.quality/coverage.json -q

Expected: a coverage table followed by the test summary, with a skip count that matches the one recorded in the baseline metadata. A run whose skip count differs is not comparable to a committed baseline and must be repeated in the environment described in `docs/code_quality_measurements.md` rather than written down as a new number. `.quality/coverage.json` must exist and must be gitignored — it is a per-run artifact, not a committed file. Record the coverage total for the five measured packages here next to the published 81 %, so a difference between the two is stated rather than assumed.

    python scripts/quality/crap_report.py --top 20

Expected: a ranked table with a header row naming path, statements, complexity, coverage, and CRAP, followed by twenty rows in descending score order.

    python scripts/quality/crap_report.py --write-baseline

Expected: writes `.quality/crap_baseline.json` and prints the number of modules recorded.

    python -m pytest tests/smoke/test_crap_metric.py -q

Expected: all tests pass. Before the implementation exists, this command must fail because `tests/smoke/test_crap_metric.py` exists and its assertions cannot be satisfied — an `ImportError` for the modules it imports, or a failed assertion — and that transcript belongs in `Artifacts and Notes` as the fail-before evidence. A `file or directory not found` error is not acceptable evidence here: it records that a path was absent, not that a behaviour was missing, and it would satisfy the requirement even against a stub implementation.

Milestone 3:

    python -m mutmut run
    python -m mutmut results

Expected: a progress line per mutant and a final summary reporting killed, survived, and total counts. Record the wall-clock duration. If the run exceeds the time the contributor is willing to spend, do not reduce the mutated paths silently — record the reduced scope and the reason in the `Decision Log`.

    python scripts/quality/mutation_gate.py --write-baseline

Expected: writes `.quality/mutation_baseline.json` and prints the number of modules recorded.

Then open a pull request that edits one covered module in a way that weakens its tests without failing them, and confirm the `crap` and `mutation` jobs fail. That pull request is evidence and must be closed, not merged.

## Validation and Acceptance

Milestone 1 is accepted when, on a clean checkout, running the documented generator command produces `ARCHITECTURE.md` whose component names correspond to real top-level modules, and opening the generated diagram and clicking a component navigates to an existing path in the tree. The check is that a person who has never read `api/` can name the responsibility of each of the five top-level Python packages using only the map; a reviewer records the attempt in the `Outcomes & Retrospective` section, including any module the map failed to explain.

Milestone 2 is accepted when `python scripts/quality/crap_report.py --top 20` prints a ranked table on the unmodified tree, when `python -m pytest tests/smoke/test_crap_metric.py -q` passes, and when the same command failed on a real assertion or import before the implementation existed. It is further accepted when, on a pull request that lowers one module's coverage without lowering its complexity, the `crap` job reports a regression against the baseline and fails; when a pull request that touches nothing relevant passes even if coverage elsewhere moved; when a pull request that adds a module scoring above the threshold without a baseline entry fails; and when the same pull request with a reviewed baseline entry in the same commit passes. Given a module at CRAP 12 on the baseline, when a commit pushes it to CRAP 31, then the gate fails and names the module; given a module whose score moves by less than the configured tolerance, when the same gate runs, then it passes; and given a run whose skip count differs from the baseline's recorded one, when the gate runs, then it reports the run as not comparable rather than as a regression.

Milestone 3 is accepted when `python -m mutmut run` completes and reports a mutation score on the unmodified tree, when `.quality/mutation_baseline.json` is committed carrying both the survivor count and the total mutant count for every module, and when a pull request that weakens assertions in a covered module fails the `mutation` job — including a pull request that touches only files under `tests/`, which must trigger the job rather than skip it — while a pull request that leaves every touched module's survival rate at or below its baseline rate passes. A module whose survivor count falls while its survival rate rises must fail: that case is the reason the gate compares rates, and it belongs in the acceptance because it is the only phrasing that distinguishes the two implementations. The acceptance is phrased as behavior because the point of the milestone is a gate that fires on the right input, not a script that exists.

The repository-wide acceptance for all three milestones together: `python -m ruff check .` is green, the contributor-safe pytest selection passes at the recorded baseline count, the web contract artifacts are still fresh per the `web-contract` job, and every new file is additive — no existing product module, test, or runtime dependency is modified by this plan.

## Idempotence and Recovery

Every step is additive and safe to repeat. The generator is safe to re-run: it rewrites its own output directory and `ARCHITECTURE.md`, and re-running it twice in a row must produce no diff, which is itself worth checking and recording. The coverage command writes only to `.quality/coverage.json`, which is gitignored, and a partially written coverage file is overwritten on the next run. Baseline files are plain JSON and are regenerated by the two documented `--write-baseline` commands; an unwanted baseline change is recovered with `git checkout -- .quality/`, which is why baselines belong in the tree and not in a cache directory.

No step in this plan touches `ai_trainer.db`, no step performs a schema migration, and no step calls a live provider with write access. The only external call is the architecture generator's model call, which sends source text and receives a description; if it fails halfway, re-run it, and if a provider is rate-limited, switch the `--provider` flag rather than editing configuration. If a baseline must be rebuilt because the metric definition changed, that is a deliberate act: change the metric in a commit that also updates the baseline and states in the commit message which modules moved and why, so the diff is reviewable rather than a wholesale replacement.

## Artifacts and Notes

The fail-before transcript for Milestone 2 is to be recorded here once `tests/smoke/test_crap_metric.py` exists and has been run before its implementation. The first version of this plan carried

    $ python -m pytest tests/smoke/test_crap_metric.py -q
    ERROR: file or directory not found: tests/smoke/test_crap_metric.py

as that transcript, and it is withdrawn: it records that the path did not exist, which is not the same claim as the behaviour being absent, and it would have satisfied the requirement even if the implementation that followed were an empty stub. The transcript that belongs here names a failing assertion or a failed import and quotes the assertion it failed.

The pass-after transcript is to be added here once the implementation lands, along with the `--top 20` table, the MCP query transcript from Milestone 1, the mutmut summary with its both-totals verdict, and the measured wall-clock duration of the mutation baseline run. Keep these to the lines that prove the claim.

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
        """Walk api/, models/, services/, data/, utils/; a module's complexity is the sum of radon's per-block complexities for that file; join with coverage."""

    def regressions(
        current: list[ModuleScore],
        baseline: dict[str, float],
        tolerance: float,
        changed: set[str] | None = None,
    ) -> list[ModuleScore]:
        """Return scores that exceed their baseline entry by more than tolerance, considering only the paths in `changed` when it is supplied. A module absent from the baseline is never returned here; the caller decides its fate by the threshold rule."""

`scripts/quality/crap_report.py` — command-line front end. Flags: `--top N`, `--json`, `--write-baseline`, `--fail-on-regression`, `--changed PATH` (repeatable), `--changed-from-git REV`, `--repo-root PATH`, `--coverage PATH`. Exit codes: `0` on success, `1` on a regression when `--fail-on-regression` is set, `2` on a missing coverage file, a malformed baseline, or a baseline whose recorded environment does not match the run.

`scripts/quality/mutation_gate.py` — command-line front end. Flags: `--write-baseline`, `--changed PATH` (repeatable), `--changed-from-git REV`, `--tolerance N`. Exit codes as above.

`scripts/quality/generate_architecture_map.py` — command-line front end. Flags: `--repo-root PATH`, `--provider NAME`, `--out PATH`. Exit code `3` when the provider environment variable is unset.

`.quality/crap.json` — `{"threshold": 30, "tolerance": 1.0}`. `.quality/crap_baseline.json` — a committed baseline with an `environment` object naming the Python version, the exact command, and the observed skip count, plus a `modules` object mapping module path to its CRAP score. `.quality/mutation_baseline.json` — a committed baseline with the same `environment` object and a `modules` object mapping module path to `{"survivors": N, "total": M}`, because the gate compares the ratio and cannot reconstruct it from a survivor count alone. `.quality/coverage.json` — a gitignored per-run artifact. A reader comparing a committed baseline against a fresh run compares the `environment` blocks first, so an incomparable run is identified before any score is.

`.mcp.json` — tracked Model Context Protocol client configuration at the repository root, holding one `mcpServers` entry for the architecture server. Committed rather than left to a personal configuration, so that any checkout of this repository — including a fresh continuous-integration environment — can query the architecture map.

`tests/smoke/test_crap_metric.py` — smoke tests for the metric, the coverage-map loader, and regression comparison.

`.github/workflows/quality-metrics.yml` — the `crap` and `mutation` jobs.

Modified files: `requirements-dev.txt` (add `radon` only — `pytest-cov>=5,<7` and `mypy>=1.11,<2.0` are already listed there, and re-adding `pytest-cov` would duplicate an existing bounded range), `AGENTS.md` (architecture pointer and the two new commands), `docs/README.md` (list this ExecPlan and the new pointer), `docs/engineering_process_metrics.md` (the two new measures), `docs/AI_Feature_Development_Workflow.md` (record the two gates in the review policy), `docs/code_quality_measurements.md` (state that the coverage number now feeds a gate and that the scope is unchanged), `.gitignore` (add `.quality/coverage.json`), `pyproject.toml` (add the mutation configuration section).

External dependencies and why each is chosen: `pytest-cov` for coverage because it is the pytest integration of `coverage.py`, already the de facto standard and requiring no new infrastructure. `radon` for cyclomatic complexity because it reports per-function complexity for Python without executing the code. `mutmut` for mutation testing because it accepts any test command that reports success through an exit code, supports incremental runs, and exposes a continuous-integration exit flag; `cosmic-ray` is the named alternative. `codeboarding` for the architecture map because it derives components from static analysis of the real tree and serves the result to a coding agent over MCP.

---

*Note (2026-09-20 07:57Z): fifth revision, authored by Hermes Agent. Reason: the branch was merged with `main` at `93e6f58` as the review required, and the first review round on `f14bd5d` returned thirteen inline findings, all priority P2, every one of which is addressed here. The claims about coverage were corrected against `docs/code_quality_measurements.md`, which already publishes an 81 % baseline and already lists `pytest-cov` as a dependency; `data/` was added to both metric scopes and `config/` removed, because the provider clients are product code and carry the largest uncovered modules while `config.settings` is imported before measurement starts. The rules for a module absent from the baseline, for the scope of a regression comparison, and for the mutation comparison were restated — the last of these now compares survival rates rather than survivor counts. Baseline generation was pinned to a continuous-integration-equivalent environment and the environment recorded inside each baseline file; the provider variable was corrected from the non-existent `OLLAMA_BASE_URL` to `OLLAMA_HOST` and `OLLAMA_MODEL`, which are what `config/settings.py` and `.env.example` define; the generated-file revision marker was redefined so that it can be satisfied together with the idempotence requirement; the MCP server registration was given a named tracked file and a clean-checkout smoke query in the milestone acceptance; `backups/` was added to the generator's exclusion list; module complexity was defined as the sum of `radon`'s per-block figures with a hand-computed test to pin it; and the fail-before transcript, which had recorded a missing file rather than a failing assertion, was withdrawn. No milestone was added or removed and no acceptance was weakened.*

*Note (2026-09-19 12:05Z): fourth revision, authored by Hermes Agent. Reason: a two-file subset run reproduced an order-dependent failure in `tests/smoke/test_dsh_pilot_preflight_timeout.py` on a test different from the one that failed first, while the file passes entirely on its own. `Surprises & Discoveries` and the Milestone 2 blocking item were updated with the reproduction recipe and with the consequence for mutation testing, which re-runs subsets and would inherit the flake as irreproducible survivor counts. No design decision changed.*

*Note (2026-09-19 11:52Z): third revision, authored by Hermes Agent. Reason: the working copy moved from `/tmp/ai_trainer` to `~/ai_trainer` and the smoke suite was re-measured twice, both times green at `2627 passed, 32 skipped`. The `Progress`, `Surprises & Discoveries`, and `Concrete Steps` sections were updated to promote the reproducible count to the baseline, to downgrade the earlier single failure to an unreproduced flake with an unknown rate, and to record that copied `__pycache__` bytecode carries the old absolute source path. No design decision changed.*

*Note (2026-09-19 11:12Z): second revision, authored by Hermes Agent. Reason: the smoke baseline was measured on commit `5420754` in a fresh virtual environment built from `requirements-dev.txt`. The measurement returned one failure that passes in isolation, so the `Progress`, `Surprises & Discoveries`, and `Concrete Steps` sections were updated to record the numbers, to state the order-dependence hypothesis with its unresolved check, and to add a Milestone 2 blocking item for resolving it. No design decision changed; the `Decision Log` is unchanged because no decision depended on the baseline.*

*Note (2026-09-19 11:04Z): initial revision, authored by Hermes Agent. Reason: the repository has no committed plan for introducing verification metrics; this document creates one so the change class, the milestones, and the acceptance conditions are recorded before any code is written. No revision has yet been made in response to implementation discoveries.*
