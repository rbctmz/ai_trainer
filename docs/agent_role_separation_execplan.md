# Establish task-scoped roles for coding agents

This ExecPlan is a living document. The sections `Progress`, `Surprises &
Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept current
while Issue #522 is implemented. Maintain this file according to
`.agent/PLANS.md` from the repository root.

## Purpose / Big Picture

After this change, Codex, Claude Code, OpenCode, and future tools start from one
repository constitution that assigns authority by task role rather than model
brand. A UI specialist can improve a component without silently changing domain
contracts; a domain implementer can change shared logic without restyling the
interface; an independent reviewer can report findings without editing the
branch. A contributor can verify the contract by reading the first section of
`AGENTS.md`, confirming that `CLAUDE.md` imports it, and running the focused
documentation smoke test.

## Progress

- [x] (2026-09-05 14:14 MSK) Created branch
  `codex/issue-522-agent-role-separation` from current `main`, preserving only
  the pre-existing untracked `backups/` directory outside scope.
- [x] (2026-09-05 14:17 MSK) Inspected Issue #522, `AGENTS.md`, `CLAUDE.md`, the
  development workflow, ADR/ASR guidance, and the OpenCode pilot evidence.
- [x] (2026-09-05 14:17 MSK) Searched the working tree, all Git refs/history,
  Spotlight, common local directories, GitHub code search, and a possible wiki
  repository for the referenced raw article; no copy was found.
- [x] (2026-09-05 14:17 MSK) Chose task-scoped roles and separated the missing
  UI showcase into a follow-up rather than pretending it already exists.
- [x] (2026-09-05 14:17 MSK) Added the canonical role contract, thin Claude
  import, OpenCode alignment, ASR trace, and focused documentation test.
- [x] (2026-09-05 14:24 MSK) Ran focused validation (3 passed), Ruff,
  `git diff --check`, and the contributor-safe smoke suite (2257 passed, 1
  environment skip). Restored the explicit `Evidence Discipline` references in
  the thin Claude adapter after the first full run exposed that existing
  entry-point contract.
- [x] (2026-09-05 14:31 MSK) Ran one read-only OpenCode review with
  `deepseek/deepseek-v4-pro`; fixed its one blocking P2 and dispositioned all
  three nonblocking suggestions below. Preflight and postflight hashes matched,
  so the reviewer made no repository changes.
- [x] (2026-09-05 14:34 MSK) Updated Issue #522 to the verified task-scoped
  contract and created non-duplicate follow-up #548 for the isolated UI
  component showcase. No commit, push, or PR was created.
- [ ] (2026-09-05 14:35 MSK) User explicitly authorized commit, push, and PR
  publication; publish the verified branch and record the resulting PR.

## Surprises & Discoveries

- **Observed**: Issue #522 names
  `raw/articles/2026-08-30-llm-under-hood-codex-claude-ui.md`, but the path does
  not exist in the working tree, ignored files, any local or remote-tracking Git
  history, GitHub code search, Spotlight, Desktop, Downloads, Trash, or a GitHub
  wiki repository.
  **Inferred**: the article was probably an untracked local note or lived in a
  different knowledge workspace. The cheapest falsifier was an exact filename
  and source-link search across the repository and common local roots.
  **Verified by**: those searches returned no matching file. The plan therefore
  treats the Telegram post as historical inspiration, not a normative build
  dependency, and does not fabricate its content.
- **Observed**: the former `CLAUDE.md` repeated project overview, architecture,
  commands, integration rules, and coding guidance already present in
  `AGENTS.md`.
  **Inferred**: parallel copies can drift and give different agents conflicting
  instructions. The cheapest falsifier was to compare headings and commands in
  both files.
  **Verified by**: direct reads showed the duplication; the new `CLAUDE.md`
  imports `@AGENTS.md` and retains only Claude-specific behavior.
- **Observed**: the current OpenCode `plan` agent denies its edit tool but still
  permits shell commands.
  **Inferred**: Plan mode reduces accidental edits but is not an operating-system
  read-only boundary. The cheapest falsifier was `opencode agent list`.
  **Verified by**: the permission listing showed `edit: deny` alongside allowed
  shell execution; the runbook now distinguishes prevention from postflight
  detection.
- **Observed**: the first full smoke run failed because `CLAUDE.md` no longer
  contained the literal evidence-discipline pointers required by
  `test_evidence_discipline_docs.py`.
  **Inferred**: importing `AGENTS.md` is sufficient for Claude at runtime but
  does not satisfy the repository's independently testable entry-point
  invariant. The cheapest falsifier was the failing focused assertion itself.
  **Verified by**: adding a two-line pointer to `Evidence Discipline`,
  `.agent/PLANS.md`, and `docs/AI_Feature_Development_Workflow.md` made the full
  suite pass with 2257 tests and one environment skip.

## Decision Log

- Decision: Assign roles by requested scope, not permanently by Codex, Claude,
  or OpenCode identity.
  Rationale: vendor-locked roles fail as soon as another model is introduced and
  wrongly turn a routing preference into authority. Tool defaults remain hints,
  while explicit handoffs control boundary changes.
  Date/Author: 2026-09-05 / Codex with user approval.
- Decision: Keep `AGENTS.md` canonical and make `CLAUDE.md` import it with
  `@AGENTS.md`.
  Rationale: Claude Code loads `CLAUDE.md`, not `AGENTS.md`; the official
  [Claude Code memory documentation](https://code.claude.com/docs/en/memory)
  documents `@path/to/import` syntax and specifically recommends importing
  `AGENTS.md`. A short adapter avoids duplicate architecture and workflow
  instructions.
  Date/Author: 2026-09-05 / Codex.
- Decision: Make Independent Reviewer read-only by default and keep final
  authority with the supervisor and human.
  Rationale: the OpenCode pilot produced useful evidence but also an incorrect
  count and hypothetical suggestions; external output needs independent
  reproduction before it can affect the branch.
  Date/Author: 2026-09-05 / Codex.
- Decision: Defer the isolated UI component showcase to a separate issue.
  Rationale: no current showcase surface was found, and building one changes the
  web product/tooling boundary. It must have its own acceptance criteria and web
  validation instead of hiding inside a documentation refactor.
  Date/Author: 2026-09-05 / Codex.

## Outcomes & Retrospective

The local implementation now has one early-loaded role contract, a Claude
adapter, an external-reviewer runbook, an ASR trace, and a focused regression
test. Focused and full smoke validation are green. The independent review's one
blocking P2 was fixed by narrowing the ASR-SEC-1 statement to the external
reviewer role, matching the canonical contract. Issue #522 now reflects the
implemented scope and links to UI-showcase follow-up #548. Publication was
explicitly authorized after local completion and is now in progress.

## Context and Orientation

`AGENTS.md` is the repository-wide instruction file used by Codex and compatible
agents. `CLAUDE.md` is the project instruction entry point for Claude Code.
`docs/AI_Feature_Development_Workflow.md` defines change classes, evidence
discipline, review severity, and the two-round review budget.
`docs/opencode_external_reviewer_runbook.md` defines how OpenCode can act as a
read-only second reviewer. `docs/architecture/asr_catalog.md` is the living
quality-attribute catalog. Issue #522 originally proposed permanent vendor roles
and bundled an isolated UI preview; this plan replaces the former with explicit
task roles and defers the latter as a separate deliverable.

A role is a bounded set of responsibilities and permissions for one task. A
handoff is a recorded boundary where one role stops and names the input another
role needs. A routing hint is a default assignment convenience, not permission
to expand scope. Independent Reviewer means the agent may inspect and report but
may not mutate project or external state.

## Plan of Work

Place `Agent Role Separation` immediately after the title in `AGENTS.md` so an
agent reads it before repository details. Define Spec / Architecture Owner,
Domain / API Implementer, UI / Design Specialist, Independent Reviewer, and
Supervisor / Integrator. State cross-boundary handoff rules and make model-name
defaults non-authoritative.

Replace duplicated project material in `CLAUDE.md` with an `@AGENTS.md` import
and a short Claude-specific section. The adapter must tell Claude not to infer UI
authority merely from its identity and must stop UI work before changing specs,
ADRs, API schemas, or domain logic.

Connect the role contract to the main development workflow and the OpenCode
runbook. Add an ASR catalog entry covering ASR-MOD-2, because UI/domain
separation protects server-owned semantics, and ASR-SEC-1, because reviewer
boundaries exclude secrets and personal data. Reuse ADR-0005 for reproducible
handoffs; no new product architecture ADR is required.

Add `tests/smoke/test_agent_role_separation_docs.py`. It must prove that the role
contract precedes project structure, all roles exist, Claude imports the
canonical file without its former overview copy, and OpenCode uses the same
Independent Reviewer role and review budget.

After validation and review, update Issue #522 so its purpose and acceptance
criteria match the implemented task-role contract. Create a separate issue for
the UI showcase; do not implement that product/tooling surface on this branch.

## Concrete Steps

Run commands from `/Users/gregkisel/Developer/ai_trainer`.

First run the focused contract:

    ai_trainer_env/bin/python -m pytest -q tests/smoke/test_agent_role_separation_docs.py

Expect three passing tests. Then run repository formatting and the contributor-
safe smoke suite:

    ai_trainer_env/bin/python -m ruff check tests/smoke/test_agent_role_separation_docs.py
    git diff --check
    ai_trainer_env/bin/python -m pytest tests/smoke -q

No web source or API contract changes are planned, so Next lint/build and
contract extraction are not required. If the final diff touches `web/`, `api/`,
or `web/lib/types.ts`, this decision becomes invalid and the corresponding
repository gates must run.

Inspect the final diff and verify that `git status --short --branch` contains
only the intended instruction, documentation, and test files plus the
pre-existing `backups/` entry. Run one independent review round against the
exact branch diff and record each finding disposition before publishing.

## Validation and Acceptance

Acceptance is met when the focused test reports three passes; the smoke suite
and Ruff are green; `AGENTS.md` presents all five roles before project details;
`CLAUDE.md` contains a literal active `@AGENTS.md` import and no duplicated
Project Overview or Current Architecture section; OpenCode is bound to
Independent Reviewer; and no UI, API, database, or personal-data file changed.

The original acceptance claim that instructions make an agent incapable of
crossing scope is intentionally narrowed: Markdown instructions guide behavior
but are not a hard security boundary. Observable acceptance is that every entry
point loads the same rules, a static contract prevents silent drift, and the
workflow requires a handoff before cross-boundary edits.

## Idempotence and Recovery

All repository changes are text and a read-only smoke test; rerunning validation
does not alter product state. If the Claude import causes a tool-specific issue,
restore the prior `CLAUDE.md` from Git history, not from `backups/`, while
keeping the canonical role contract in `AGENTS.md`. If an external reviewer
modifies files, stop it, compare against the recorded preflight status, and
restore only its proven changes without touching unrelated user work.

GitHub issue edits are external writes. Prepare the final body from the verified
local contract, update Issue #522 once, and create at most one non-duplicate UI
showcase follow-up. Retry only after read-only lookup confirms the first write
did not succeed.

## Artifacts and Notes

The 2026-09-05 OpenCode pilot established the initial reviewer workflow:
`deepseek/deepseek-v4-pro` returned a completed report, the focused Issue #531
regression passed, no repository changes remained, and supervisory review
caught an incorrect count in the generated report. This evidence motivates the
Independent Reviewer and Supervisor separation; model availability remains a
dated snapshot in `docs/opencode_external_reviewer_runbook.md`.

The missing raw article is not recreated. The durable source of truth is the
implemented repository contract and its test.

Independent review dispositions (2026-09-05):

- `fixed-in working tree`: the blocking P2 at
  `docs/architecture/asr_catalog.md` no longer attributes the external-analysis
  data exclusion to the UI role.
- `addressed-in working tree`: the nonblocking import-support concern now has an
  official Claude Code documentation citation in the Decision Log.
- `disputed`: the nonblocking `.gitignore` suggestion would hide the visible
  pre-existing `backups/` safety signal and changes an out-of-scope user-owned
  path; the directory remains untouched and untracked.
- `disputed`: the nonblocking test-expansion suggestion asks the static guard to
  detect arbitrary future paraphrases. The current test intentionally pins the
  active import and the two headings actually removed from the duplicated
  file; broader semantic duplication remains a review concern, not a stable
  string invariant.

## Interfaces and Dependencies

No runtime API, TypeScript DTO, database schema, environment variable, or user-
visible product interface changes. The instruction interfaces are the five role
names and handoff rule in `AGENTS.md`, the `@AGENTS.md` import consumed by Claude
Code, and the Independent Reviewer reference consumed by the OpenCode runbook.
The only executable dependency is Python standard-library `pathlib` under the
existing pytest environment.

Revision note (2026-09-05): created this plan after Issue #522 triage, expanded
the design from vendor-locked assignments to task-scoped roles, incorporated the
OpenCode pilot, and separated the absent UI showcase from the documentation
contract. Updated after validation and independent review to record the smoke
results, correct the reviewer-only ASR-SEC-1 boundary, cite Claude import
support, and disposition every review comment.

Revision note (2026-09-05): synchronized the final scope to Issue #522 and
created follow-up #548 after a duplicate search returned no matches. Kept
commit, push, and PR publication outside this local implementation step.
