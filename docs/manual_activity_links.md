# Link an explicitly confirmed duplicate activity (#720)

Use this operator command when an original Blocks→Intervals recording and a
manual Garmin FIT import represent the same cycling session. It preserves the
original Intervals canonical identity and counts the pair once. It does not find
duplicates automatically or write to either provider.

## Preview

Use an existing database and the provider ids, not the local `intervals_` prefix:

    python scripts/link_activities.py --database /path/to/offline.db \
      --intervals-id i_original --garmin-id 123456

The default is a read-only transaction: it does not initialize/migrate the schema.
JSON reports `allowed`, `blockers`, `linked`, `token`, and the affected pair's
`before`/`after` totals. These are pair totals, not whole-calendar totals. Missing
identities and malformed schemas fail with exit code 2; refusal previews also
return 2. No provider request occurs.

Both payloads must exist. Only recognized cycling types with identical timezone-aware
UTC starts and finite positive durations within one second are supported. The
original Intervals identity must be standalone. Tags, notes or immutable JSON
history referring to a disappearing canonical block the operation; resolve those
in a separate scoped task. Derived interval, power-curve and bike-pair caches are
cleared for disappearing ids and can be refetched. The surviving original's
references and caches are retained.

## Apply to a stopped, backed-up database

Stop every writer first. `--confirm-stopped` records the operator's confirmation;
it does not stop the app. Before a live operation create a validated backup using
`docs/sqlite_backup_restore.md`. Never substitute a plain file copy for SQLite's
backup API when committed pages may be in WAL. First rehearse on a disposable copy.

After inspecting the preview, repeat the exact ids with the returned token:

    python scripts/link_activities.py --database /path/to/offline.db \
      --intervals-id i_original --garmin-id 123456 \
      --apply --expected-token TOKEN --confirm-stopped \
      --reason 'Owner confirmed both records came from the same FIT'

A concurrent/state change invalidates the token. Inspect again instead of forcing
it. The write transaction stores the decision and reprojects one canonical;
failures roll back together. Both source payloads remain preserved. Subsequent
sync honors the decision, even after restart or PRIMARY_ACTIVITY_SOURCE changes.
The original Intervals payload is authoritative for the manual group, so its
load/method can differ from Garmin's. Preview shows that choice. One returned
Garmin-origin Intervals copy can follow the same coordinate; additional claimants
abort their ingest visibly and do not advance the failed sync chunk's cursor.

## Undo and reset

Preview unlink with the same ids and `--unlink`. Apply it using its new token,
`--unlink --apply --expected-token TOKEN --confirm-stopped`. A reason is not
required for unlink. It restores ordinary source-coordinate grouping using current
preserved payloads, rather than old snapshots; after a returned Intervals copy,
PRIMARY_ACTIVITY_SOURCE determines the normally grouped Garmin side. Derived
caches are invalidated and may be refetched. Repeated link/unlink is safe with a
fresh preview token. Full reset removes all manual decisions in the existing
reset transaction. Old backups remain a separate operator recovery option.

This implementation has no UI or HTTP endpoint. Tests use synthetic ids and data;
never attach personal SQLite copies or operator output to a public PR.

Duration precision clarification (2026-10-24 review): the one-second allowance is represented as 0.017 minutes, matching the existing three-decimal minute normalization; a two-second source difference is refused.
