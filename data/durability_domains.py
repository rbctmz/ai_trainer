"""Domains whose preservation the durability track must prove (#622/#623/#624).

Single source of truth shared by the automatic snapshot manifest, the backup
health report and the #624 migration verification. Keeping it here — dependency
free, no pandas import — lets the snapshot service and the migration CLI agree on
what "the data survived" means instead of drifting apart.

A table absent from a given checkout's schema is simply reported as absent; this
tuple is the union, not a requirement that every install has every table.
"""

from __future__ import annotations

__all__ = ["KEY_DOMAINS", "PROVIDER_DOMAINS", "LOCAL_DOMAINS"]

#: Provider-owned history: replaceable by a fresh sync, but still worth proving.
PROVIDER_DOMAINS: tuple[str, ...] = (
    "activities",
    "activity_provider_links",
)

#: Locally born data. A provider sync cannot reconstruct any of it — the exact
#: gap that made the 2026-09-20 incident unrecoverable.
LOCAL_DOMAINS: tuple[str, ...] = (
    "planning_checkpoints",
    "coach_decisions",
    "plan_actual_matches",
    "session_feedback",
    "readiness_snapshots",
)

#: Everything a snapshot manifest reports and a migration verifies.
KEY_DOMAINS: tuple[str, ...] = PROVIDER_DOMAINS + LOCAL_DOMAINS
