# Planning S1 / M4 synthetic browser evidence

Captured on 2026-10-17 by `tests/e2e/test_planning_build_confirmation_ui.py`
using the repository's isolated FastAPI/Next/Chromium harness. Temporary demo
SQLite only; no athlete database, model call, or provider write. Coach SSE is a
synthetic transport fixture; approval/replay still uses the real bound API/store.

`planning-confirm-*` shows the existing step 4 at 390/light, 900/dark and
1280/light+dark. The test checks keyboard Shift+Tab/Tab focus on Cancel/Confirm and
page overflow. Images were visually inspected; this is not a WCAG certification.
`planning-uncertain-390.png` and `coach-uncertain.png` show the real commit followed
by a deliberately dropped response: reset/cancel/new action is locked, and Retry
uses the original identity. Unknown outcomes do not claim that application failed
or that the plan is still unsaved. The test retries and verifies a durable replay.

All 18 targeted browser scenarios pass in 21.91s on the final UI tree. They include
exact identity-only submit with no profile PUT, distance edit with a held late
preview, explicit stale return, ambiguous/corrupt/missing identity outcomes, 422
and busy retry ownership, historical replay, real bound Coach success/lost/stale,
and cancel with unchanged active checkpoint/settings. Full S1/native/rollout
acceptance remains M5; cycle/date carry-over, training math and step-4 redesign
are intentionally unchanged.
