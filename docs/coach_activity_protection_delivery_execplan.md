# Deliver accepted activity protection and separate runtime evaluation

Date2026-10-16. User authorized two PRs after bounded M7 acceptance. Supervisor/Integrator owns packaging; Domain/API code is copied from accepted2fa5b19 without behavior changes. Original product scope Class A, accepted through M5/M7 specs and independent checks; this delivery split is Class B packaging, no new product acceptance/architecture. Related#528 is the broader behavioral-eval issue and is not closed by this product patch. Greg owns merge.

## Purpose and boundaries

Coach should preserve uncertainty when interval data is unavailable, distinguish analyzer-empty from actual absence, and avoid unsupported future promises. Existing shared Python validation receives allowlisted activity facts, checks the named assurances, reuses at-most-one correction and delivers factual fallback after failure. Explicit denial of a guarantee is preserved. This is bounded protection, not general factuality certification. Existing API/legacy consumers share it; no UI/schema/sync/migration/new live calls.

The accepted feature lived with47files/~18kadded lines of experimental history. Product PR contains only4production modules, existing prompt/tool regressions, the narrative regression module,9extracted synthetic cases and one small database fixture. Test data retains exact original raw/formatted tools and relevant answer fields; reports/provenance hashes identify source captures. Two eval-dependent marker/native integration cases stay in companion PR; product tests never import the new eval runner/registry or read docs/reports.

## Progress

- [x] Pinned main23fd7d6, original accepted2fa5b19; original history stays recoverable. Publish permissionsADMIN verified, no duplicate PRs.
- [x] Four product modules copied byte-identically;9saved regression rows extracted field-for-field. Small fixture replaces eval-registry dependency for legacy delivery test.
- [x] Product263focused passed; isolated smoke2989passed/35skipped/1existing Starlette warning,177.02s; whole-tree ruff/diff green. Independent packaging review263passed, no blockers, source/data equality verified. Code prepared for commit/push/PR against main.
- [ ] Merge product branch into original experiment branch preserving all historical commits/artifacts; resolve only test fixture imports; companion PR against product branch so review excludes product changes.
- [ ] Verify companion tests/CI, attach both real PRs, report current-head CI and remaining human merge decision. No automatic merge/live experiment.

## Frozen acceptance and validation

Existing M7 five conditions unchanged:4saved unsafe answers blocked; explicit denial preserved with0correction; affirmative/neighbor/double-negative guarantees blocked; structured facts/empty/unknown identity/date scoping preserved; existing correction/fallback/API/legacy/call caps retained. Product tests cover public metadata shape (rulesv4/evidencev3) and delivery. Name/status attribution and unknown paraphrases remain known separate limits; M6partial3/4 is never regraded.

In product worktree run project Python with pytest -p no:cacheprovider on test_coach_activity_narrative_gate.py, test_coach_narrative_evidence_gate.py, test_ai_coach_runtime.py, test_coach_activity_structure_tool.py, test_activity_intervals.py. Run isolated tests/smoke with temporary DATABASE_PATH/CHATS_DIR and whole-tree ruff --no-cache. CI runs contributor-safe tests, contract and web E2E. No web sources changed, no local web build required. Independent review is bounded to extraction/packaging regressions and scope; no reopening accepted phrase coverage. One consolidated round, scoped repair only for reproduced blockers.

## Companion and rollback

Original codex/issue-528-runtime-experiment remains the evidence branch. Merge accepted product commit into it without rebasing/squashing old pinned commits. On the only anticipated conflict (narrative test imports), select independent product fixtures; original test_ai_coach_runtime integration cases remain. Companion base is product branch, then retarget main after product merge. Full sanitized reports remain byte-identical; historical hashes describe their original code, not repackaged test paths. No score/rubric rewrite or extra provider call. Revert packaging commits if needed, original2fa5b19 remains reachable.

## Evidence and outcome

Observed: accepted test module read large reports and imported an eval-only fixture. Inferred: literal extraction plus one minimal SQLite fixture permits standalone product delivery. Cheap falsifier: compare extracted rows/models byte-for-byte with original, then execute all product regressions without eval files installed. Verified by: initial and independent equality checks passed,263focused and2989smoke passed without new eval files installed.35skips are22TypeScript dependency,10opt-in fixture regeneration,2pilot/process prerequisites,1socket limitation; no web change. ASR-REL-2,REL-1/3 read-only,ADR-0001 shared Python; no ASR status/contract change. Real PR URLs and current-head CI are reported in the PR descriptions/task response; scope acceptedness and CI/human merge remain distinct.
