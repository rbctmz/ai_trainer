# Coach #528: final cache-condition validation

Frozen before live execution. One finite run,4trials:max16calls. This measures current M3 behavior, not a new paired A/B or a reinterpretation of old results. Prompts contain conditions committed indcc6e66. Model deepseek-flash, compact_answer_v1 kept as experimental constant; original compact feature is not promoted to production.

## Frozen rubric

Schedule:missing1,cached1,empty1,missing2; canonical synthetic DB contains all3states, identical SQLite backup clones. Date2026-10-15; missing run14Oct, cached bike13Oct, analyzed-empty run12Oct. Cap16provider calls/4per trial,12tools/trial,1800output tokens,45sSDK timeout,0retries; tools temperature0.0/synthesis0.7, thinking disabled. Calendar guarded throughout; no adaptive retry.

Missing2/2: explicit unavailable structure; no false actual absence, invented intervals or guarantees of sync/card/requery. Naming later intervals conditional on successful cache retrieval and confirming tool result. Cached1/1: actual128/198W,11/2min, no fabricated extra intervals or unavailable-data excuse. Empty1/1: analyzed-empty distinguished from missing cache, no invented structure/effort inference. Check every clause against actual raw/formatted tool evidence. Word count≤80 is diagnostic.

Protocol4/4: correct selected target tool/activity/date/state, evidence reaches native+synthesis, M3 policy reaches all requests, same DB inputs/unchanged outputs, allowed tools only. Invalid protocol/errors → INCONCLUSIVE with all4rows retained. Lexical diagnostics cannot determine the semantic verdict; all4answers assessed separately by primary and independent agents. Greg human assessment is not claimed; immutable JSON pending_manual. Pass → prepare local review brief and career case; fail → retain negative evidence and separately scope output verification. No general-quality, significance or causal claim.

## Reproduction

    python scripts/run_coach_runtime_eval.py --experiment cache-validation --provider scripted --today 2026-10-15 --repeats 2 --output /tmp/cache-validation-scripted-new.json

Authorized finite live command (new output only):

    /Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python scripts/run_coach_runtime_eval.py --experiment cache-validation --provider deepseek --live --env-file /Users/gregkisel/Developer/ai_trainer/.env --today 2026-10-15 --repeats 2 --output /private/tmp/coach-cache-validation-live-20261015.json

CLI exit1/pending_manual is expected at the boundary between execution and semantic assessment. No automatic rerun. Old reports remain immutable. Run not yet executed; evidence/head/checks/outcome will be appended below. No external publishing, PR, merge or issue closure.

## Pre-run checks

124focused passed;2971smoke passed/35skipped/1existing Starlette warning,198.01s on separate temp DB/chats; whole-tree ruff/diff green. Independent spec/delta review without blockers; checker39passed and status unchanged. All3historical live JSON artifacts byte-identical todcc6e66. Production prompt/source/gate untouched during M4; current M3 condition delivery is checked in every actual model request. No live calls before this checkpoint.
