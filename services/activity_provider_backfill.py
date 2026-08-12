"""Read-only evidence for the offline activity provider-link repair (#429)."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import sqlite3
from typing import Any, Callable


def preview_provider_link_backfill(
    database_path: str | Path,
    classify: Callable[[Any], str],
) -> dict[str, Any]:
    """Profile unlinked canonicals without returning identifiers or payloads."""
    path = Path(database_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"database does not exist: {path}")

    uri = f"{path.as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        rows = conn.execute(
            """SELECT CAST(activity.activity_id AS TEXT)
               FROM activities AS activity
               WHERE NOT EXISTS (
                   SELECT 1
                   FROM activity_provider_links AS links
                   WHERE CAST(links.canonical_activity_id AS TEXT) =
                         CAST(activity.activity_id AS TEXT)
               )"""
        ).fetchall()
        claimant_rows = conn.execute(
            """SELECT CAST(external_id AS TEXT), COUNT(*)
               FROM activity_provider_links
               WHERE provider = 'intervals'
                 AND external_provider = 'garmin'
                 AND external_id IS NOT NULL
               GROUP BY CAST(external_id AS TEXT)"""
        ).fetchall()

    classifications = Counter(classify(row[0]) for row in rows)
    claimants = {str(coordinate): int(count) for coordinate, count in claimant_rows}
    outcomes = Counter({"matched": 0, "standalone": 0, "ambiguous": 0})
    for (activity_id,) in rows:
        if classify(activity_id) != "garmin":
            continue
        count = claimants.get(str(activity_id), 0)
        if count == 1:
            outcomes["matched"] += 1
        elif count == 0:
            outcomes["standalone"] += 1
        else:
            outcomes["ambiguous"] += 1

    return {
        "unlinked_total": len(rows),
        "classifications": {
            source: int(classifications[source]) for source in sorted(classifications)
        },
        "garmin_coordinates": {
            key: int(outcomes[key]) for key in ("matched", "standalone", "ambiguous")
        },
    }


__all__ = ["preview_provider_link_backfill"]
