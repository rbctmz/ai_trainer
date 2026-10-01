# Independent bounded CI metadata delta review

2026-10-01. Scope: proposed uncommitted Gitleaks false-positive metadata fix on `codex/daily-loop-consistency-20261001`, HEAD `73c363e57625f141ae77b51bd822acd583d12b74`, PR #675 as reported by integrator. Independent Reviewer, read-only. This is a bounded CI delta review, not another full product review, native approval or merge approval.

## Disposition

**No blocking finding in the proposed metadata delta.** The fix is restricted to 60 exact fingerprints for 30 previously scanned immutable export-manifest checksum rows, preserving the nine existing exceptions. Current false-positive interpretation is consistent with the checksum evidence. The actual scanner still detects the authorized runtime-only synthetic secret.

## Evidence

**Observed:** `.gitleaksignore` adds exactly 30 `73c363e...:path:generic-api-key:line` and 30 `path:generic-api-key:line` entries targeting only `docs/reports/2026-10-01-daily-story-consistency/evidence/candidate-export.json`. No path-wide, directory-wide, regex or rule-wide exception, scanner configuration change, workflow disable, or skip is introduced. Historical fingerprints bind to the known docs evidence commit; tree fingerprints bind to the same exact rows/rule. Existing nine entries are retained.

**Verified by:** the authorized focused test module checks the full exception set equals the old nine plus the exact 60, parses each row as a single JSON mapping, and requires a nonempty source path with a 64-character lowercase hexadecimal value. It retains checks for read-only permissions, pinned workflow actions/scanner version, current-tree scan followed by runtime synthetic probe, and failure handling when the probe scanner reports clean or broken. Approved command returned **7 passed in 0.84s**:

```text
/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python /private/tmp/ai-trainer-daily-fix-20261001/run.py pytest -m 'not live and not debug and not e2e' tests/smoke/test_secret_scanning_ci.py --basetemp=/private/tmp/ai-trainer-daily-fix-20261001/runtime/reviewer-secret-ci -q
```

**Inferred from exact exclusions; falsifier executed:** the delta does not disable detection elsewhere. The approved real local scanner probe returned exit0 only after scanner detection exit42, printing `Gitleaks detected the runtime-only synthetic secret.`:

```text
/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python /private/tmp/ai-trainer-daily-fix-20261001/run.py python scripts/verify_secret_scanner.py --scanner /private/tmp/ai-trainer-daily-fix-20261001/scanner/gitleaks
```

The scanner operates on an ephemeral synthetic token created at runtime, outside ignored manifest coordinates. No source token literal is added. This proves that the tested detection path remains active; it does not claim detection of every conceivable credential format.

**Observed saved scanner logs:** `evidence/scanner-history.log` reports **2 commits scanned**, no leaks; `scanner-tree.log` reports ~15.01 MB scanned, no leaks. Interpret the first as the PR/event commit range, not a newly executed full repository history scan. These two clean scans were executed by the integrator; reviewer did not repeat them. Scanner 8.30.1 download/published-checksum verification and all 30 source-file SHA256 recomputations are integrator-observed evidence recorded in `secret-scan-false-positives.json`, not independently repeated by this reviewer. Archived source, credentials and personal data remained outside reviewer reads.

**Verified by:** `git diff --exit-code 65881db --` for all eight acceptance product/contract/test files returned exit0. Product bytes remain unchanged from the accepted product commit. Initial/final tracked delta is only `.gitleaksignore`, `tests/smoke/test_secret_scanning_ci.py`, and the integrator's report append. Reviewer wrote only this temporary report, with no Git/source/docs/external changes.

## Nonblocking limitation

Current-tree fingerprints are location based. The added guard verifies checksum *shape*, not the immutable exact digest value or equality to source bytes. A future 64-hex credential substituted at one of those same locations would still satisfy the shape test and could be ignored. Current evidence does not show such a substitution; this is not a blocker for the verified immutable manifest false positives. Future edits of the manifest require revalidation; pinning exact manifest bytes or these exact row values would strengthen that guard if the manifest stops being treated as immutable.

PR/head CI, E2E, native owner-review gate and merge state were not queried or approved here. Earlier Python/contract results and pending owner review/E2E are integrator-reported snapshots, not current gate certification.

## Scoped follow-up: immutable manifest pin

**Disposition: nonblocking limitation above addressed in the current uncommitted delta.** Only the added `hashlib` import and whole-file digest assertion were checked; no new full review round. `test_gitleaks_exceptions_are_only_verified_non_secret_shapes` now requires the actual manifest bytes' SHA256 to equal `e5adbb7476e87d677184f9592d4e30df1eb5e9e3fb69a2f5a3e00db5821c8f99` before parsing allowed rows. Exact locations and shape checks remain. A changed same-line 64-hex value now changes the whole-file checksum and fails this assertion, rather than passing on shape alone. The guard protects the immutable evidence snapshot; deliberate edits to the test's pin would themselves be a reviewable policy change.

Independent approved focused rerun: **7 passed in 0.91s**:

```text
/Users/gregkisel/Developer/ai_trainer/ai_trainer_env/bin/python /private/tmp/ai-trainer-daily-fix-20261001/run.py pytest -m 'not live and not debug and not e2e' tests/smoke/test_secret_scanning_ci.py --basetemp=/private/tmp/ai-trainer-daily-fix-20261001/runtime/reviewer-secret-pinned -q
```

The passing test also verifies that the pinned checksum equals current manifest bytes. No temporary or source manifest mutation was needed. Reviewer remains read-only; tracked status retains exactly the integrator's three metadata/report changes. Previous scanner detection evidence remains applicable; scanner/ignore scope was not expanded by this follow-up. No blocker remains in this scoped metadata review. Commit disposition is pending the integrator's metadata commit SHA.
