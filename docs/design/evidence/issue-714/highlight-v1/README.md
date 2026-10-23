# S4 owner-requested highlight revision

23October2026, #714 / draft#715. Explicit Integrator→UI/Design handoff is
recorded in #714 after owner requested visible differences on replacement.
This is presentation within approved C2 facts, not a new domain comparison.
API/TS/schema/domain/spec and save lifecycle are unchanged.

Known differing displayed summary values receive an accent background plus
visible text «Изменено». Row headers retain accessible names and describe the
marker via aria-describedby. Equal values are unmarked. A missing/unsupported
value yields «Нет данных для сравнения», never a claimed change or zero.
For dated prescriptions the highlight consumes server-provided added/removed/
changed states; browser does not recompute calendar/content classifications,
lineage, whole-period deltas, publication eligibility or scientific verdicts.

Observed UI RED: the existing real8→4week edit had no difference marker despite
visible different end/total. New assertions failed1test/1existing warning12.23s.
Final full S4 UI contour23passed/1existing warning38.55s: checks differing and
unchanged summary rows across390/900/1280 light/dark, partial unknown values,
legacy/historical receipts and existing confirmation semantics.33existing
mobile/polish/contract checks passed1.77s; Ruff/diff and web lint/production build/
contract freshness pass. No new whole contributor claim for this UI-only slice.

Actual temporary-data new/edit/replacement/cancel/post-commit-response-loss and
same-identity replay captures pass, plus320px no document overflow. No unhandled
JS errors; provider discovery503 and deliberately aborted response are classified.
All data synthetic, no live athlete/provider writes. Older comparison/revision1
owner images are unchanged. Initial new clipped capture hid the action footer
after taller summary; capture helper now uses element screenshot for full summary
and actions. This was evidence capture repair, not product/save behavior.

New owner response on the earlier paired edit correctly identified changed end
and total. Replacement response identified differing rows/requested highlighting;
it did not answer old-cycle/history consequences. That criterion remains pending.
Exact responses are kept out of this public evidence. Native review1/2 remains
historical9d41e2b, final scoped2/2 reserved for stable feedback; previous local C3
READY applies toc324c9e, not this new delta. No additional local full review loop.
No acceptance label, ready transition or merge.

Reproduce from task worktree, primary venv bin on PATH, PYTHONPATH=.:

    python -m pytest -m e2e tests/e2e/test_planning_confirmation_s4_ui.py -q -p no:cacheprovider --tb=short
    python docs/design/evidence/issue-714/highlight-v1/capture.py
    npm --prefix web run lint
    npm --prefix web run build
    npm --prefix web run contract:extract -- --check

After these images are shown to the owner, preserve them as fixed feedback
artifacts. Subsequent capture revisions need a new directory; avoid rerunning
this helper into shown files.
