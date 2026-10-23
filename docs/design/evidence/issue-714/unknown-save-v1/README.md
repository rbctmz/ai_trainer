# S4 final owner scenario: unknown save result

23October2026, #714 / draft#715, product source4dc9f37 / documentationc00dc50.
Observed during evidence QA: highlight-v1/owner-d used a summary-only screenshot
and omitted the wizard status/retry controls. It is not used as acceptance for
unknown-result handling. This new directory preserves all earlier shown owner
images and captures the actual wizard section with unknown status and retry.
No product, API, domain, save handler or acceptance criterion changed.

capture.py reuses the real temporary-data journey and captures only case D.
It explicitly verifies the status/retry controls are visible. Confirmation
commits then loses its response; retry uses the same identity and replays the
receipt. New/edit/replacement cancellation checks also execute in the shared
harness. All four journeys pass, no unhandled JS exceptions; disabled-provider
503 and deliberate response-loss ERR_FAILED remain classified. Ruff/diff pass.
The retained case-oracle.json is synthetic. No athlete cache/provider writes.

Owner follow-up on the frozen paired edit identified the changed end/total.
Replacement follow-up acknowledges the displayed replacement consequence after
a narrower question. This is clarified acknowledgement, not a blind first-use
study or a separately paraphrased history answer. The assistant restated the
closure/history consequence afterward. Exact private wording is not published.

This unknown-save image is now shown with one open status/next-action question;
answer pending. Preserve it. Current c00dc50 CI40004020426 succeeded; future
heads need their own CI status. Native1/2 historical9d41e2b; final scoped2/2
reserved until feedback stabilizes. No owner-wide acceptance, label or merge.

Reproduce with primary venv bin on PATH and PYTHONPATH=.:

    python docs/design/evidence/issue-714/unknown-save-v1/capture.py

Do not rerun into this shown directory; use a new version for future captures.
