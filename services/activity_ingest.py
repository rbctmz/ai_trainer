"""Common activity ingest (ADR-0008 / #269, M0).

A single, deterministic funnel `provider data → canonical activity + provider-link`
for BOTH sources (Garmin, Intervals). Pure normalization is split from the atomic
DB write, and — critically — the sync cursor is advanced ONLY after a whole batch
succeeds (``ingest_provider_batch``), never inside a per-activity transaction: else
a failure on the N-th activity, after the first already advanced the cursor, would
strand the data behind the cursor (ADR-0008 п.5/п.8).

This is the ExecPlan's "common ingest" contract point (`to_canonical_activity`);
``to_canonical_activity`` is kept as an alias of ``normalize_provider_activity``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from config.settings import Settings

# Cross-provider identity namespace. Intervals stores the *source* activity id in
# ``external_id``; in the Garmin+Intervals beta that source is Garmin, so both a
# Garmin activity and the Intervals copy that references it resolve to the SAME
# coordinate ("garmin", garmin_id) — and therefore the SAME canonical activity —
# regardless of arrival order. The namespace is mandatory (ADR-0008 п.2): a bare
# ``external_id`` is not globally unique on its own.
GARMIN_NAMESPACE = "garmin"

# Intervals.icu activity ``type`` → our canonical sport. Unknown types pass through
# lowercased rather than being dropped.
_INTERVALS_SPORT = {
    "ride": "cycling",
    "virtualride": "cycling",
    "gravelride": "cycling",
    "mountainbikeride": "cycling",
    "ebikeride": "cycling",
    "run": "running",
    "virtualrun": "running",
    "trailrun": "running",
    "swim": "swimming",
    "openwaterswim": "swimming",
    "weighttraining": "gym",
    "workout": "gym",
}


@dataclass(frozen=True)
class ProviderActivity:
    """Normalized candidate: canonical activity fields + provider-link fields.

    ``canonical`` holds the ``activities`` column values (incl. ``activity_id`` =
    ``canonical_activity_id`` and ``tss``/``source_tss``/``tss_method``). The
    link-shaped view is exposed via :meth:`link`. DB-free by construction.
    """

    provider: str
    provider_activity_id: str
    canonical_activity_id: str
    external_provider: str | None
    external_id: str | None
    provider_tss: float | None
    canonical: dict[str, Any]

    def link(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "provider_activity_id": self.provider_activity_id,
            "external_provider": self.external_provider,
            "external_id": self.external_id,
            "provider_tss": self.provider_tss,
        }


@dataclass
class BatchResult:
    """Outcome of :func:`ingest_provider_batch`."""

    ingested: list[dict[str, Any]] = field(default_factory=list)
    cursor_advanced: bool = False


def classify_activity_id(activity_id: Any) -> str:
    """ADR-0008 п.7: offline classification of an EXISTING ``activity_id`` by shape.

    ``demo_activity_*`` → ``demo``; an all-digit Garmin id → ``garmin``; anything
    else → ``legacy_unknown`` (never pretend legacy/test data is Garmin).
    """
    text = str(activity_id or "").strip()
    if text.startswith("demo_activity_"):
        return "demo"
    if text.isdigit():
        return "garmin"
    return "legacy_unknown"


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_garmin(row: dict[str, Any]) -> ProviderActivity:
    activity_id = str(row.get("activity_id") or "").strip()
    if not activity_id:
        raise ValueError("normalize_provider_activity(garmin): activity_id is required")

    # A Garmin row is already canonical-shaped (post ActivityProcessor). Pass its
    # fields through and pin activity_id; the DB write reads only known columns.
    canonical = dict(row)
    canonical["activity_id"] = activity_id
    source_tss = _to_float(row.get("source_tss"))

    # Garmin self-anchors in the "garmin" namespace so the Intervals copy that
    # references this activity resolves to the same canonical.
    return ProviderActivity(
        provider="garmin",
        provider_activity_id=activity_id,
        canonical_activity_id=activity_id,
        external_provider=GARMIN_NAMESPACE,
        external_id=activity_id,
        provider_tss=source_tss,
        canonical=canonical,
    )


def _normalize_intervals(row: dict[str, Any]) -> ProviderActivity:
    intervals_id = str(row.get("id") or "").strip()
    if not intervals_id:
        raise ValueError("normalize_provider_activity(intervals): id is required")

    raw_external = row.get("external_id")
    external_id = str(raw_external).strip() if raw_external not in (None, "") else None
    external_provider = GARMIN_NAMESPACE if external_id else None
    # Garmin-sourced Intervals activity → same canonical id as Garmin would use;
    # a genuinely Intervals-only activity gets its own namespaced canonical id.
    canonical_activity_id = external_id if external_id else f"intervals_{intervals_id}"

    provider_tss = _to_float(row.get("icu_training_load"))
    raw_type = str(row.get("type") or "").strip()
    sport = _INTERVALS_SPORT.get(raw_type.lower(), raw_type.lower() or None)
    start_local = str(row.get("start_date_local") or "")
    date = start_local[:10] if start_local else None
    moving_time = _to_float(row.get("moving_time"))
    duration_minutes = round(moving_time / 60.0, 3) if moving_time else None

    canonical = {
        "activity_id": canonical_activity_id,
        "date": date,
        "started_at_utc": start_local or None,
        "sport": sport,
        "duration_minutes": duration_minutes,
        "activity_name": row.get("name"),
        # Intervals reconciliation fields carry no power/HR streams, so a local TSS
        # cannot be recomputed here → the provider load is used as the canonical
        # TSS, EXPLICITLY marked as a provider fallback (ADR-0008 п.3). This is
        # only ever written to the canonical row when Intervals is authoritative.
        "source_tss": provider_tss,
        "tss": provider_tss,
        "tss_method": "intervals_icu_provider_fallback" if provider_tss is not None else None,
    }

    return ProviderActivity(
        provider="intervals",
        provider_activity_id=intervals_id,
        canonical_activity_id=canonical_activity_id,
        external_provider=external_provider,
        external_id=external_id,
        provider_tss=provider_tss,
        canonical=canonical,
    )


def normalize_provider_activity(provider_row: dict[str, Any], source: str) -> ProviderActivity:
    """Pure ``provider data → candidate`` transform (the common-ingest contract).

    No DB access. ``source`` is ``"garmin"`` or ``"intervals"``; an unknown source
    fails fast rather than guessing.
    """
    normalized_source = str(source or "").strip().lower()
    if normalized_source == "garmin":
        return _normalize_garmin(provider_row)
    if normalized_source == "intervals":
        return _normalize_intervals(provider_row)
    raise ValueError(f"normalize_provider_activity: unknown source {source!r}")


# ExecPlan continuity: the plan names this contract point ``to_canonical_activity``.
to_canonical_activity = normalize_provider_activity


def _resolve_primary(primary_source: str | None) -> str:
    return primary_source or Settings.PRIMARY_ACTIVITY_SOURCE


def ingest_provider_activity(
    db: Any,
    candidate: ProviderActivity,
    *,
    primary_source: str | None = None,
) -> dict[str, Any]:
    """Atomically persist ONE candidate: canonical + provider-link + ``source_tss``
    projection in a single transaction (ADR-0008 п.5). Never advances a cursor.

    Returns the DB write result. The public path guarantees no link is ever left
    without its canonical (they share the transaction), even though raw SQL admits
    such an orphan.
    """
    primary = _resolve_primary(primary_source)
    return db.write_provider_activity(candidate.canonical, candidate.link(), primary_source=primary)


def ingest_provider_batch(
    db: Any,
    candidates: list[ProviderActivity],
    *,
    advance_cursor: Callable[[], None] | None = None,
    primary_source: str | None = None,
) -> BatchResult:
    """Ingest every candidate (each its own atomic transaction), THEN advance the
    cursor exactly once — and only if the WHOLE batch succeeded (ADR-0008 п.8).

    A failure mid-batch propagates BEFORE ``advance_cursor`` runs, so the cursor
    stays put; already-ingested activities remain committed and a retry is
    idempotent (``UNIQUE(provider, provider_activity_id)`` + upsert → no duplicates).
    The cursor is never advanced inside a per-activity transaction — that is the
    whole point of keeping cursor advance here rather than in
    :func:`ingest_provider_activity`.
    """
    result = BatchResult()
    for candidate in candidates:
        # Module-global call so a failure-injection test can patch it.
        result.ingested.append(
            ingest_provider_activity(db, candidate, primary_source=primary_source)
        )
    if advance_cursor is not None:
        advance_cursor()
        result.cursor_advanced = True
    return result


def backfill_provider_links(db: Any) -> dict[str, int]:
    """ADR-0008 п.7: offline, idempotent backfill of provider-links for existing
    canonical activities, classified by :func:`classify_activity_id`.
    """
    return db.backfill_activity_provider_links(classify_activity_id)


__all__ = [
    "GARMIN_NAMESPACE",
    "BatchResult",
    "ProviderActivity",
    "backfill_provider_links",
    "classify_activity_id",
    "ingest_provider_activity",
    "ingest_provider_batch",
    "normalize_provider_activity",
    "to_canonical_activity",
]
