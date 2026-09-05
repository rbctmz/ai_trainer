# CLAUDE.md

@AGENTS.md

## Claude Code-specific guidance

`AGENTS.md` is the canonical repository constitution and is imported above.
Do not duplicate its architecture, commands, workflow, or review rules here.
Its **Evidence Discipline** section remains mandatory: follow `.agent/PLANS.md`
and `docs/AI_Feature_Development_Workflow.md` for causal claims and validation.

- Do not infer authority from being Claude Code. Use the role assigned by the
  task and the narrowest scope that can complete it.
- When assigned the UI / Design Specialist role, work in `web/` against the
  existing API and TypeScript contracts. You may inspect specs, ADRs, Python,
  and contract tests for context, but do not modify them as part of the UI slice.
- If a UI change requires a contract, domain, or acceptance-criteria change,
  stop at a clean handoff and name the exact change required from the Spec /
  Architecture Owner or Domain / API Implementer.
- Do not use `--dangerously-skip-permissions`. Use Plan Mode when the requested
  role or cross-boundary scope is unclear.
- In the `@claude` GitHub Action, keep one milestone per mention and preserve the
  pushed RED/GREEN boundary described in `AGENTS.md`.

Use `/memory` when diagnosing instruction loading: Claude Code should report
this file and the imported `AGENTS.md` before repository work begins.
