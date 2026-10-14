# Local review brief: Coach #528 experiment and bounded fixes

Prepared2026-10-15. Branch codex/issue-528-runtime-experiment, worktree coach-runtime-eval. Implementation checkpoint02687ef; subsequent checkpoint contains evidence/design docs only. Merge base and GitHub main both verified23fd7d6ce19a93c6d07b885daf8cf298d0afa909 via read-only ls-remote. No push, GitHub PR, remote CI, human review or merge performed.

## Problem / resulting behavior

For a completed activity without cached intervals, the tool promised that synchronization/card opening would supply them. Actual fetching can fail or return no data. The incorrect message was passed intact to model context; live Coach repeated it. Source correction80649bc removes the guarantee. Shared instructiondcc6e66 explicitly separates provider availability, successful local-cache retrieval and confirming tool result, preserving unavailable/structured/analyzed-empty semantics.

Final current-version observation: both missing-cache answers now preserve uncertainty without the observed sync/card/requery promise, and cached actual interval numbers remain correct. The analyzed-empty control still adds an unsupported promise that a future check will confirm a hypothesis. Thus this bundle demonstrates target improvement and residual risk, not complete model reliability or completed broad product acceptance.

## Review boundaries

- Production changes: one not_fetched tool message in models/ai_tools.py and one shared cognitive instruction in models/ai_coach_runtime.py. No API/TS/DB/UI/sync/provider mutation change. No deterministic new output validator.
- Experimental additions: existing shared runtime runner + explicit live CLI, versioned synthetic registries/fixtures, read-only tool allowlist, global/per-trial caps, redacted immutable traces and separate semantic assessment. Historical negative baseline/compact/source findings retained; compact contract remains experimental, not a product feature.
- Final M4: one run4trials/12of16calls,0errors, identity/state/evidence/policy exposure4/4, identical canonical DB inputs/unchanged outputs4/4. Automatic4/4 is diagnostic; [semantic assessment](assessment.md) does not accept all4answers as fully supported.
- Validation before run:124focused passed,2971smoke passed/35skipped/1existing warning; whole-tree ruff/diff green. Independent spec and implementation checks without blockers, checker39tests passed. Skips are TypeScript dependency/opt-in fixture/historical pilot/process/socket checks; no web/API changes. This is shared-runtime acceptance on synthetic data, not API/SSE, live athlete or clinical acceptance.

## Remaining gate / disposition

Observed content finding: empty answer «это подтвердит проверка карточки» guarantees confirmation of a hypothesis that the tool does not verify. Next proposed slice is [evidence-backed answer verification](../../issue_528_answer_verification_followup.md), ownerGreg for acceptance/prioritization. No additional prompt edit, model run, implementation or external issue in this completed experiment. Clean semantic acceptance and merge readiness are not claimed. Code/protocol may be reviewed read-only independently of accepting wider model behavior.

## Career-use evidence boundary

A supported engineering narrative is: instrumented real model→tool selection→cached evidence→answer→state checks; found a false source guarantee, preserved negative experiments, implemented a source correction and explicit conditions, then found a residual assertion through control-case semantic review despite automated4/4. [Trace](live-validation.json), [measured report](README.md) and [assessment](assessment.md) support that narrative.

Do not claim production deployment, general hallucination elimination, clinical coaching validation, statistically established improvement, model training or success of the full issue. The current engineering case is evidence-first diagnosis and honest bounded validation with a documented next verification design.
