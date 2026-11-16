# #623 M3 — synthetic backup status evidence

Captured by `tests/e2e/test_backup_status_ui.py` in an isolated API/Next/Chromium
stack, with typed BackupStatus fixtures and no personal data/providers.

- `backup-390-light.png`: 390×900 viewport, light theme, degraded with prior copy.
- `backup-1280-dark.png`: 1280×900 viewport, dark theme, same semantic state.

Images crop the actual global status element, not the whole page. All dates and
copy identity are synthetic. UI shows local display time, never paths, snapshot
IDs or machine reason codes. Keyboard Enter activates retry; while pending the
action is disabled. A successful check shows ready; a failed check retains an
honest warning. Automated assertions cover disabled/unknown/ready/degraded,
missing prior copy, pending/success/failure and no business-command replay.

These fixtures verify display/interaction, not a live backup or user service
restart. Backend snapshot contents and fresh-process startup are verified by
`tests/smoke/test_snapshot_runtime.py` and `test_backup_api.py`. Final candidate
SHA, test counts and review handoff are recorded in the M3 PR/ExecPlan.
