# Deliver accepted activity protection and separate runtime evaluation

Date2026-10-16. User authorized two PRs after bounded M7 acceptance. Supervisor/Integrator owns packaging; Domain/API code is copied from accepted2fa5b19 without behavior changes. Original product scope Class A, accepted through M5/M7 specs and independent checks; this delivery split is Class B packaging, no new product acceptance/architecture. Related#528 is the broader behavioral-eval issue and is not closed by this product patch. Greg owns merge.

## Purpose and boundaries

Coach should preserve uncertainty when interval data is unavailable, distinguish analyzer-empty from actual absence, and avoid unsupported future promises. Existing shared Python validation receives allowlisted activity facts, checks the named assurances, reuses at-most-one correction and delivers factual fallback after failure. Explicit denial of a guarantee is preserved. This is bounded protection, not general factuality certification. Existing API/legacy consumers share it; no UI/schema/sync/migration/new live calls.

The accepted feature lived with47files/~18kadded lines of experimental history. Product PR contains only4production modules, existing prompt/tool regressions, the narrative regression module,9extracted synthetic cases and one small database fixture. Test data retains exact original raw/formatted tools and relevant answer fields; reports/provenance hashes identify source captures. Two eval-dependent marker/native integration cases stay in companion PR; product tests never import the new eval runner/registry or read docs/reports.

## Progress

- [x] Pinned main23fd7d6, original accepted2fa5b19; original history stays recoverable. Publish permissionsADMIN verified, no duplicate PRs.
- [x] Four product modules copied byte-identically;9saved regression rows extracted field-for-field. Small fixture replaces eval-registry dependency for legacy delivery test.
- [x] Product263focused passed; isolated smoke2989passed/35skipped/1existing Starlette warning,177.02s; whole-tree ruff/diff green. Independent packaging review263passed, no blockers, source/data equality verified. Code prepared for commit/push/PR against main.
- [x] Merge product9616287 into original experiment branch as7af3dfb preserving all historical commits/artifacts; companion PR#682 targets product branch and excludes product changes.
- [x] Both PRs#681/#682 attached; original-head contributor CI, contract, Web E2E and Gitleaks green. No automatic merge/live experiment.
- [x] Native review of9616287: four reproduced P2 findings; exact RED19failed/9passed. Scoped helper repair and rulesv5;291focused passed.
- [x] Independent read-only delta check:291passed, scoped ruff/diff green, unchanged git status, no reproduced blockers. Broad numeric comparison explicitly disputed as outside frozen scope.
- [x] Broad smoke3018passed/33skipped/1environment failure in189.80s: run_web child shell could not find python. With project venv on PATH, the complete failing module passed3/3 in0.37s; no product test failure remains. Whole-tree ruff/diff green. Repair ready for publication; commit/head, companion integration, thread replies and CI are recorded in the live PR descriptions to avoid another docs-only head change.
- [ ] Owner accepts native review of the final head and merges in dependency order; no agent acceptance/merge claimed.

## Frozen acceptance and validation

Existing M7 five conditions unchanged:4saved unsafe answers blocked; explicit denial preserved with0correction; affirmative/neighbor/double-negative guarantees blocked; structured facts/empty/unknown identity/date scoping preserved; existing correction/fallback/API/legacy/call caps retained. Delivery initially used rulesv4/evidencev3; the native-review repair below advances rulesv5 without changing evidence or metadata shape. Name/status attribution and unknown paraphrases remain known separate limits; M6partial3/4 is never regraded.

In product worktree run project Python with pytest -p no:cacheprovider on test_coach_activity_narrative_gate.py, test_coach_narrative_evidence_gate.py, test_ai_coach_runtime.py, test_coach_activity_structure_tool.py, test_activity_intervals.py. Run isolated tests/smoke with temporary DATABASE_PATH/CHATS_DIR and whole-tree ruff --no-cache. CI runs contributor-safe tests, contract and web E2E. No web sources changed, no local web build required. Independent review is bounded to extraction/packaging regressions and scope; no reopening accepted phrase coverage. One consolidated round, scoped repair only for reproduced blockers.

## Companion and rollback

Original codex/issue-528-runtime-experiment remains the evidence branch. Merge accepted product commit into it without rebasing/squashing old pinned commits. On the only anticipated conflict (narrative test imports), select independent product fixtures; original test_ai_coach_runtime integration cases remain. Companion base is product branch, then retarget main after product merge. Full sanitized reports remain byte-identical; historical hashes describe their original code, not repackaged test paths. No score/rubric rewrite or extra provider call. Revert packaging commits if needed, original2fa5b19 remains reachable.

## Evidence and outcome

Observed: accepted test module read large reports and imported an eval-only fixture. Inferred: literal extraction plus one minimal SQLite fixture permits standalone product delivery. Cheap falsifier: compare extracted rows/models byte-for-byte with original, then execute all product regressions without eval files installed. Verified by: initial and independent equality checks passed,263focused and2989smoke passed without new eval files installed.35skips are22TypeScript dependency,10opt-in fixture regeneration,2pilot/process prerequisites,1socket limitation; no web change. ASR-REL-2,REL-1/3 read-only,ADR-0001 shared Python; no ASR status/contract change. Real PR URLs and current-head CI are reported in the PR descriptions/task response; scope acceptedness and CI/human merge remain distinct.

## Native-review repair milestone

On2026-10-16 the first native full-diff review of PR#681 at9616287 reported four P2s. Class B scoped correctness repair, Domain Implementer; user requested addressing review feedback. No evidence extraction, architecture, API, UI, prompts, persisted schema or model calls change. PR#682 has no submitted native review yet. Existing M7 acceptance and all captured reports remain historical results; these repairs do not regrade them or begin another experiment.

The observable contract for this delta is bounded to the reproduced forms. A possible delay followed by a comma cannot excuse an unconditional promise that intervals will appear. A hypothetical successful cache condition must name returned intervals, a nonempty structure, or explicit structured status; returning an error/unavailable/empty result is insufficient. Named analyzer-empty verbs require empty evidence. Named affirmative counts, actual-structure multipliers and interval-duration statements require structured evidence for the scoped date/activity. A correctly scoped structured statement, analyzed-empty observation, conditional premise, local uncertainty or explicit denial remains allowed. Comparing every numeric assertion with interval arithmetic, general paraphrase recognition and name/status attribution are outside this accepted protection; the fourth finding's broad numeric-comparison request is explicitly disputed on scope, while its three concrete unsupported-state examples are fixed.

Run the five focused modules listed above, then isolated tests/smoke and whole-tree ruff. One independent read-only delta check against9616287 verifies the four reproductions, safe controls and unchanged delivery tests; it must not start another full algorithm audit. Commit and push only after reproduced blockers are fixed, write fixed-in dispositions in all four threads, merge product into companion without altering reports, and verify exact-head CI separately from owner acceptance. No additional full review request or paid run is part of this milestone. Revert this single repair commit to restore rulesv4 if needed; no migration/reset is involved.

## Surprises & Discoveries

Observed:28new parametrized native-review cases returned19failed/9passed before the repair, including all four reported families; prior263focused cases passed. Inferred: exemptions were broader than their propositions and named absence/positive forms lacked state checks. Cheap falsifier: run the same public validator through unavailable/empty/structured and correct activity/date controls. Verified by: after the helper-only repair, all291focused cases pass, including all previous safe-denial and API/fallback regressions. Independent delta checker reproduced291passed and no scoped blockers with unchanged git status. Broad smoke3018passed/33skipped/1environment failure; the failing preflight module passed3/3 with correct venv PATH. Two previously socket/process-limited cases ran under the escalated local check, so skips decreased from35to33; TypeScript/opt-in prerequisites remain. The failure was outside the changed helper and its output explicitly reported python not found; the environment-only rerun falsified a product regression in that case.

## Decision Log

Decision2026-10-16: accept reproduced state/assurance violations as blocking P2s within existing invariants; repair named forms and preserve the bounded scope. Do not introduce a generic numeric fact checker to satisfy the broader wording of finding4. Increment rule version to v5 so new verdicts are distinguishable from historical v4; evidence staysv3. One delta verification follows the first native review; green CI and human merge acceptance remain separate.

## Outcomes & Retrospective

Packaging completed with two attached PRs; native review exposed four bounded correctness gaps despite earlier saved-answer acceptance. Repair focused tests, independent delta check, broad smoke plus isolated environment retry and ruff/diff are complete. Exact published heads, companion integration, thread dispositions and CI belong in the live PR descriptions. Human acceptance and merge remain pending. This is delivery review work, not a new live-model iteration.

Revision2026-10-16: record completed delivery and native review, its reproduced RED/GREEN evidence, explicit scope disposition and finite repair validation.
