# Independent consolidated review: #674

Reviewer: Sol, read-only Independent Reviewer after Luna's explicit stop-edit handoff. Scope: entire product/test diff on base034bf88; Class B issue acceptance and non-goals only. No native GitHub review/acceptance/merge performed.

## Finding G1 — blocking P2

Observed: saved checkpoint carries canonical daily row zero load, explicit off/zero-duration/empty sessions template, but template.total_tss=20.0. The optional template field survives ordinary build/save/restore. Candidate returns session=null.

Inferred: empty-day guard never checks optional template.total_tss and silently turns contradictory positive load into confirmed rest. Falsifier: actual save/restore/Today probe requiring non-null card when that positive field exists.

Verified by: test_independent_boundary.py, independent-boundary-red.log: 1 failed. This violates issue #674 acceptance5 and non-goal preserving contradictory/incomplete evidence. Absent optional total_tss must remain supported because the normal generator omits that field.

Disposition: handed to Luna for a scoped delta: check optional template.total_tss if present, add exact regression; no other blocker found in consolidated full diff.

## Existing test environment boundary

Independent focused run:88passed/1failed. Failure is the SQLite guard deliberately blocking an older Coach test's tempfile.mktemp path in the system default temporary directory; source assertion was not evaluated. Will rerun in verified tracked-source temporary export. Live database untouched.

## Report fixture boundary

The original investigation's evaluated zero-row control used shared helper's default sport_label=бег against canonical off/отдых template. Candidate preserves this contradiction. Final acceptance uses consistent off metadata, plus mismatch control. Current upcoming_plan_sessions skips tss<=0, so ordinary production defect uses template fallback; evaluated branch is defensive compatibility coverage.

## Scoped delta verification

G1 correction checks optional template.total_tss only when present. Exact independently reproduced boundary now passes inside the 91-test focused acceptance run (90 tracked focused tests plus one independent probe); both original empty-day regressions and neighboring Today/Coach/daily-story tests pass. No new blocker in scoped delta. All-repository Ruff and git diff --check pass. Eight actual API adapter scenarios and48 Next/Chromium states pass. No second full-code review performed. Disposition: G1 fixed-in 49d8f6116550e38f3daa2cde19063364a1389e76; independently verified, zero open blocking findings.
