"""Provider-neutral sync contracts shared across sync adapters and the job manager.

Both the Garmin adapter (``services.sync``) and the Intervals adapter
(``services.intervals_sync``), plus ``api/sync_jobs.SyncJobManager``, use ONE
progress-callback contract. It lives here — not in either adapter — so neither
provider owns the shared type and adding a third source does not require importing
a sibling provider's module (review P1.1 / slice-spec §5 source-aware wiring).

This module deliberately depends on nothing else in the project: it is a leaf so
the contract can be imported by every sync surface without pulling in a provider's
transitive graph.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class SyncProgressUpdate:
    """A UI-agnostic progress event emitted during a sync run.

    The job manager's ``on_progress(update: SyncProgressUpdate)`` takes a SINGLE
    argument and reads ``update.percent``/``message``/``step_text``/``stats_message``;
    every provider adapter must emit this object (not a positional tuple) so it
    drops into the existing sync-job runner unchanged.
    """

    percent: int
    message: str
    step_text: str | None = None
    stats_message: str | None = None


# The callback shape every adapter accepts. Re-exported by each adapter so callers
# do not need to know it originates here.
SyncProgressCallback = Callable[[SyncProgressUpdate], None]


__all__ = ["SyncProgressCallback", "SyncProgressUpdate"]
