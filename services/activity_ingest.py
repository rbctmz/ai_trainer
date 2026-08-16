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
from services.bike_hr_pairs import record_bike_hr_pair

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
    # Canonical id to use when this activity does NOT join a cross-provider anchor
    # (no external match, or a fail-closed 'ambiguous' outcome). Keeps a contested
    # activity on its own canonical instead of hijacking a shared one.
    standalone_canonical_id: str = ""

    def link(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "provider_activity_id": self.provider_activity_id,
            "external_provider": self.external_provider,
            "external_id": self.external_id,
            "provider_tss": self.provider_tss,
            "standalone_canonical_id": self.standalone_canonical_id or self.canonical_activity_id,
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


def _meters_to_km(value: Any) -> float | None:
    """Intervals.icu отдаёт дистанцию в метрах -> км (#417)."""
    metres = _to_float(value)
    if metres is None or metres < 0:
        return None
    return round(metres / 1000.0, 2)


def _seconds_to_minutes(value: Any) -> float | None:
    seconds = _to_float(value)
    if seconds is None or seconds <= 0:
        return None
    return round(seconds / 60.0, 3)


def _nonnegative_int(value: Any) -> int | None:
    number = _to_float(value)
    if number is None or number < 0:
        return None
    return int(round(number))


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
        standalone_canonical_id=activity_id,
    )


# Only these exact Intervals.icu `source` tokens mean "came from Garmin". An exact
# whitelist (not a substring test) is deliberate: "NOT_GARMIN" contains "garmin" but
# must NOT be attributed to Garmin.
_GARMIN_SOURCE_TOKENS = {"garmin", "garmin_connect", "garminconnect"}


def _intervals_source_namespace(raw_source: Any) -> str | None:
    """Map Intervals.icu ``source`` to a cross-provider namespace (ADR-0008 п.2).

    Fail closed: ``external_id`` is attributed to the ``garmin`` namespace ONLY when
    ``source`` is an exact known-Garmin token. Every other value — a different
    provider, an unrecognised token, or nothing — yields ``None`` (no cross-provider
    coordinate; the activity stays standalone) rather than being trusted as a
    Garmin id.
    """
    text = str(raw_source or "").strip().lower()
    if text in _GARMIN_SOURCE_TOKENS:
        return GARMIN_NAMESPACE
    return None


def _normalize_intervals(row: dict[str, Any]) -> ProviderActivity:
    intervals_id = str(row.get("id") or "").strip()
    if not intervals_id:
        raise ValueError("normalize_provider_activity(intervals): id is required")

    standalone_canonical_id = f"intervals_{intervals_id}"

    # Fail-closed cross-provider identity (blocker #1): only attribute external_id
    # to Garmin when Intervals' own `source` says the activity came from Garmin.
    raw_external = row.get("external_id")
    external_id = str(raw_external).strip() if raw_external not in (None, "") else None
    source_namespace = _intervals_source_namespace(row.get("source"))
    if external_id and source_namespace:
        external_provider = source_namespace
    else:
        external_provider, external_id = None, None

    # Only a Garmin-attributed external id anchors on the shared canonical (= the
    # Garmin activity id Garmin itself would use). Everything else stays standalone.
    if external_provider == GARMIN_NAMESPACE:
        canonical_activity_id = external_id
    else:
        canonical_activity_id = standalone_canonical_id

    provider_tss = _to_float(row.get("icu_training_load"))
    raw_type = str(row.get("type") or "").strip()
    sport = _INTERVALS_SPORT.get(raw_type.lower(), raw_type.lower() or None)
    start_local = str(row.get("start_date_local") or "")
    date = start_local[:10] if start_local else None
    # Record UTC only from the real UTC field (blocker #5): never store local wall
    # clock in a *_utc column.
    start_utc = str(row.get("start_date") or "").strip() or None
    moving_duration_minutes = _seconds_to_minutes(row.get("moving_time"))
    # Intervals exposes elapsed and moving durations separately. Older/minimal
    # payloads may omit elapsed_time, so retain the established moving-time fallback.
    duration_minutes = (
        _seconds_to_minutes(row.get("elapsed_time")) or moving_duration_minutes
    )

    # Local-first TSS (blocker #6): honour a locally-resolved tss/tss_method if the
    # caller (the M1 Intervals adapter runs the local cascade with FTP/LTHR) already
    # computed one; only fall back to the provider load when no local result exists,
    # and then mark it EXPLICITLY (ADR-0008 п.3). Bare reconciliation rows carry no
    # power/HR streams, so they take the fallback — but the cascade is not bypassed
    # when a local value is present.
    local_tss = _to_float(row.get("tss"))
    local_method = row.get("tss_method")
    if local_tss is not None and local_method:
        canonical_tss, canonical_method = local_tss, str(local_method)
    elif provider_tss is not None:
        canonical_tss, canonical_method = provider_tss, "intervals_icu_provider_fallback"
    else:
        canonical_tss, canonical_method = None, None

    canonical = {
        "activity_id": canonical_activity_id,
        "date": date,
        "started_at_utc": start_utc,
        "sport": sport,
        "duration_minutes": duration_minutes,
        "moving_duration_minutes": moving_duration_minutes,
        # #417: Intervals.icu отдаёт дистанцию в метрах — маппим в км.
        "distance_km": _meters_to_km(row.get("distance")),
        "avg_hr": _to_float(row.get("average_heartrate")),
        "max_hr": _to_float(row.get("max_heartrate")),
        "avg_power": _to_float(row.get("icu_average_watts")),
        "elevation_gain": _to_float(row.get("total_elevation_gain")),
        "calories": _nonnegative_int(row.get("calories")),
        "activity_name": row.get("name"),
        "description": row.get("description"),
        "source_tss": provider_tss,
        "tss": canonical_tss,
        "tss_method": canonical_method,
    }

    return ProviderActivity(
        provider="intervals",
        provider_activity_id=intervals_id,
        canonical_activity_id=canonical_activity_id,
        external_provider=external_provider,
        external_id=external_id,
        provider_tss=provider_tss,
        canonical=canonical,
        standalone_canonical_id=standalone_canonical_id,
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
    result = db.write_provider_activity(candidate.canonical, candidate.link(), primary_source=primary)
    # #444 S1: shadow bike power+HR pairs are derived data — best-effort. A pair
    # failure must never fail or roll back the canonical ingest; a missing pair
    # self-heals on the next sync of the same activity (idempotent upsert).
    try:
        record_bike_hr_pair(db, candidate.canonical)
    except Exception:
        pass
    return result


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


def backfill_provider_links(
    db: Any,
    *,
    primary_source: str | None = None,
) -> dict[str, int]:
    """ADR-0008 п.7: offline, idempotent backfill of provider-links for existing
    canonical activities, classified by :func:`classify_activity_id`.

    Reconciliation is part of the same transaction: a historical Garmin row may
    already have a standalone Intervals claimant that is outside today's incremental
    sync window. Leaving the merge until another provider fetch would preserve a
    duplicate indefinitely.
    """
    resolved_primary = str(
        primary_source or Settings.PRIMARY_ACTIVITY_SOURCE
    ).strip().lower()
    if resolved_primary not in {"garmin", "intervals"}:
        raise ValueError("primary_source must be 'garmin' or 'intervals'")
    return db.backfill_activity_provider_links(
        classify_activity_id,
        primary_source=resolved_primary,
    )


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
