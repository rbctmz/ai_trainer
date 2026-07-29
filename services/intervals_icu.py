"""Intervals.icu helpers for planned-workout sync."""
from __future__ import annotations

import base64
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Mapping, Sequence
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from config.settings import Settings
from models.plan_events import normalize_intervals_event

DEFAULT_USER_AGENT = "AI-Trainer/1.0 (+https://github.com/rbctmz/ai_trainer)"
MAX_RECONCILIATION_WINDOW_DAYS = 90
WELLNESS_FIELDS = (
    "id",
    "updated",
    "restingHR",
    "hrv",
    "hrvSDNN",
    "sleepSecs",
    "sleepScore",
    "sleepQuality",
)
MIN_RUNNING_THRESHOLD_PACE_SECONDS_PER_KM = 120.0
MAX_RUNNING_THRESHOLD_PACE_SECONDS_PER_KM = 900.0


class IntervalsICUError(RuntimeError):
    """Base Intervals.icu integration error."""


class IntervalsICUConfigurationError(IntervalsICUError):
    """Raised when the integration is not configured."""


def _normalize_base_url(base_url: str) -> str:
    return (base_url or "https://intervals.icu").rstrip("/")


def _basic_auth_header(api_key: str) -> str:
    token = base64.b64encode(f"API_KEY:{api_key}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def dominant_sport(parts: Mapping[str, float]) -> str:
    """Return the dominant sport key for a planned day."""
    sport_priority = ("bike", "run", "swim")
    return max(sport_priority, key=lambda sport: float(parts.get(sport, 0.0) or 0.0))


def build_planned_workout_description(
    goal_type: str,
    distance: str,
    total_tss: float,
    parts: Mapping[str, float],
    session_template: Mapping[str, Any] | None = None,
) -> str:
    """Build a compact event description for planned Intervals.icu workouts."""
    if session_template and session_template.get("description"):
        return str(session_template["description"])
    return (
        "План из AI Trainer\n"
        f"Цель: {goal_type} / {distance}\n"
        f"Total TSS: {round(total_tss, 1)}\n"
        f"Run: {round(float(parts.get('run', 0.0) or 0.0), 1)}\n"
        f"Bike: {round(float(parts.get('bike', 0.0) or 0.0), 1)}\n"
        f"Swim: {round(float(parts.get('swim', 0.0) or 0.0), 1)}"
    )


def build_planned_event_payload(
    dt: datetime,
    total_tss: float,
    parts: Mapping[str, float],
    goal_type: str,
    distance: str,
    session_template: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Convert one daily plan entry into an Intervals.icu event payload."""
    if float(total_tss or 0.0) <= 0:
        raise ValueError("Нельзя отправить в Intervals.icu день без тренировочной нагрузки.")

    sport = str(session_template.get("sport") or dominant_sport(parts)) if session_template else dominant_sport(parts)
    sport_type = {
        "bike": "Ride",
        "run": "Run",
        "swim": "Swim",
    }.get(sport, "Workout")
    start_dt = dt.replace(hour=7, minute=0, second=0, microsecond=0)
    return {
        "start_date_local": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "category": "WORKOUT",
        "name": str(session_template.get("export_name")) if session_template and session_template.get("export_name") else f"{goal_type} {distance} — {dt.strftime('%Y-%m-%d')}",
        "description": build_planned_workout_description(goal_type, distance, total_tss, parts, session_template=session_template),
        "type": sport_type,
        "icu_training_load": int(round(float(total_tss))),
    }


def build_planned_events(
    days: Sequence[tuple[datetime, float, Dict[str, float]]],
    goal_type: str,
    distance: str,
    minimum_tss: float = 1.0,
    session_templates: Sequence[Mapping[str, Any]] | None = None,
) -> List[Dict[str, Any]]:
    """Convert a slice of the daily plan into Intervals.icu event payloads."""
    events: List[Dict[str, Any]] = []
    for idx, (dt, total_tss, parts) in enumerate(days):
        if float(total_tss or 0.0) < minimum_tss:
            continue
        session_template = session_templates[idx] if session_templates and idx < len(session_templates) else None
        events.append(
            build_planned_event_payload(
                dt,
                total_tss,
                parts,
                goal_type,
                distance,
                session_template=session_template,
            )
        )
    return events


@dataclass(frozen=True)
class IntervalsICUClient:
    """Small personal-use Intervals.icu client based on API-key basic auth."""

    api_key: str
    athlete_id: str = "0"
    base_url: str = "https://intervals.icu"
    timeout_seconds: int = 15

    def is_configured(self) -> bool:
        return bool((self.api_key or "").strip())

    def connection_info(self) -> Dict[str, Any]:
        return {
            "configured": self.is_configured(),
            "athlete_id": str(self.athlete_id or "0"),
            "base_url": _normalize_base_url(self.base_url),
        }

    def list_calendars(self) -> Any:
        return self._request_json("GET", f"/api/v1/athlete/{self.athlete_id}/calendars")

    def get_athlete_profile(self) -> Any:
        return self._request_json("GET", f"/api/v1/athlete/{self.athlete_id}")

    def list_race_events(self, oldest: date, newest: date) -> List[Dict[str, Any]]:
        """Read and normalize A/B/C events inside a bounded date window."""
        if newest < oldest:
            raise ValueError("newest must not be before oldest")
        if (newest - oldest).days > 365:
            raise ValueError("Intervals.icu event discovery is limited to 365 days")
        payload = self._request_json(
            "GET",
            f"/api/v1/athlete/{self.athlete_id}/events",
            params={"oldest": oldest.isoformat(), "newest": newest.isoformat()},
        )
        rows = payload if isinstance(payload, list) else []
        return [event for row in rows if isinstance(row, Mapping) if (event := normalize_intervals_event(row))]

    @staticmethod
    def _validate_reconciliation_window(oldest: date, newest: date) -> None:
        if newest < oldest:
            raise ValueError("newest must not be before oldest")
        if (newest - oldest).days > MAX_RECONCILIATION_WINDOW_DAYS:
            raise ValueError(
                f"Intervals.icu reconciliation is limited to {MAX_RECONCILIATION_WINDOW_DAYS} days"
            )

    def list_activities(self, oldest: date, newest: date) -> List[Dict[str, Any]]:
        """Read only the provider fields required to join local completed activities.

        Fail-closed (M1 §11 step 3 refinement 3 + review P1.2): a non-list payload,
        a non-mapping element, or an element with an INVALID ``id`` RAISES rather
        than being silently coerced to ``[]`` / dropped. Silently dropping would
        let a malformed response become a "clean empty" chunk that advances the
        cursor past the lost data. The windowed-sync adapter catches the resulting
        ``IntervalsICUError`` and marks the chunk dirty (no cursor advance).

        ``id`` must be a non-bool scalar (``str`` or ``int``) whose ``str().strip()``
        is non-empty (review P1.2): a complex id like ``[1]`` used to pass, normalize
        to ``intervals_[1]`` and persist, advancing the cursor. ``bool`` is excluded
        explicitly because it is an ``int`` subclass.
        """
        self._validate_reconciliation_window(oldest, newest)
        payload = self._request_json(
            "GET",
            f"/api/v1/athlete/{self.athlete_id}/activities",
            params={"oldest": oldest.isoformat(), "newest": newest.isoformat()},
        )
        if not isinstance(payload, list):
            raise IntervalsICUError(
                "Intervals.icu activities: expected a list response, got "
                f"{type(payload).__name__}"
            )
        fields = (
            "id",
            "external_id",
            # `source` attributes external_id to a provider namespace (GARMIN_CONNECT,
            # STRAVA, …). Without it, an external_id cannot be assumed to be a Garmin
            # id (ADR-0008 п.2 fail-closed matching).
            "source",
            "paired_event_id",
            # start_date is UTC; start_date_local is the athlete's local wall clock.
            # Keep them distinct so ingest never records local time as UTC.
            "start_date",
            "start_date_local",
            "type",
            "name",
            "icu_training_load",
            "moving_time",
        )
        rows: List[Dict[str, Any]] = []
        for row in payload:
            if not isinstance(row, Mapping):
                raise IntervalsICUError(
                    "Intervals.icu activities: response contained a non-mapping entry "
                    "— refusing to advance past potentially lost data"
                )
            _validate_activity_id(row.get("id"))
            rows.append({field: row.get(field) for field in fields})
        return rows

    def list_wellness(self, oldest: date, newest: date) -> List[Dict[str, Any]]:
        """Read only recovery inputs used by the canonical M4 mapping.

        The provider's readiness and CTL/ATL fields are deliberately not
        requested.  Malformed rows fail closed so the wellness cursor cannot
        advance past data that was silently dropped.
        """
        self._validate_reconciliation_window(oldest, newest)
        payload = self._request_json(
            "GET",
            f"/api/v1/athlete/{self.athlete_id}/wellness",
            params={
                "oldest": oldest.isoformat(),
                "newest": newest.isoformat(),
                "fields": ",".join(WELLNESS_FIELDS),
            },
        )
        if not isinstance(payload, list):
            raise IntervalsICUError(
                "Intervals.icu wellness: expected a list response, got "
                f"{type(payload).__name__}"
            )
        rows: List[Dict[str, Any]] = []
        for row in payload:
            if not isinstance(row, Mapping):
                raise IntervalsICUError(
                    "Intervals.icu wellness: response contained a non-mapping entry"
                )
            raw_day = row.get("id")
            if (
                not isinstance(raw_day, str)
                or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_day)
            ):
                raise IntervalsICUError(
                    f"Intervals.icu wellness: invalid local date id {raw_day!r}"
                )
            try:
                date.fromisoformat(raw_day)
            except ValueError as exc:
                raise IntervalsICUError(
                    f"Intervals.icu wellness: invalid local date id {raw_day!r}"
                ) from exc
            # Preserve the provider row for observability/forward compatibility;
            # the pure normalizer below is the bounded canonical projection and
            # deliberately ignores provider readiness/CTL/ATL.
            rows.append(dict(row))
        return rows

    def list_workout_events(self, oldest: date, newest: date) -> List[Dict[str, Any]]:
        """Read bounded WORKOUT event identity evidence without writing the calendar."""
        self._validate_reconciliation_window(oldest, newest)
        payload = self._request_json(
            "GET",
            f"/api/v1/athlete/{self.athlete_id}/events",
            params={"oldest": oldest.isoformat(), "newest": newest.isoformat()},
        )
        fields = (
            "id",
            "external_id",
            "uid",
            "category",
            "start_date_local",
            "type",
            "name",
            "workout_doc",
            "moving_time",
        )
        return [
            {field: row.get(field) for field in fields}
            for row in (payload if isinstance(payload, list) else [])
            if isinstance(row, Mapping) and str(row.get("category") or "").upper() == "WORKOUT"
        ]

    def test_connection(self) -> Dict[str, Any]:
        calendars = self.list_calendars()
        return {
            "ok": True,
            "calendar_count": len(calendars) if isinstance(calendars, list) else None,
            "calendars": calendars,
        }

    def create_event(self, event_payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self._request_json(
            "POST",
            f"/api/v1/athlete/{self.athlete_id}/events",
            payload=dict(event_payload),
        )

    def create_events(self, event_payloads: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        created: List[Dict[str, Any]] = []
        for payload in event_payloads:
            created.append(self.create_event(payload))
        return created

    def upsert_events_by_external_id(
        self,
        event_payloads: Iterable[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Upsert events using the caller-owned Intervals.icu external_id."""
        payload = [dict(item) for item in event_payloads]
        if not payload:
            return []
        response = self._request_json(
            "POST",
            f"/api/v1/athlete/{self.athlete_id}/events/bulk",
            payload=payload,
            params={
                "upsert": "true",
                "upsertOnUid": "false",
                "updatePlanApplied": "true",
            },
        )
        return [dict(item) for item in response if isinstance(item, Mapping)] if isinstance(response, list) else []

    def delete_events(self, event_payloads: Iterable[Mapping[str, Any]]) -> int:
        payload = [
            {
                "id": item.get("id"),
                "external_id": item.get("external_id"),
            }
            for item in event_payloads
            if item.get("id") is not None
        ]
        if not payload:
            return 0
        response = self._request_json(
            "PUT",
            f"/api/v1/athlete/{self.athlete_id}/events/bulk-delete",
            payload=payload,
        )
        return int(response.get("eventsDeleted") or 0) if isinstance(response, Mapping) else 0

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        if not self.is_configured():
            raise IntervalsICUConfigurationError(
                "Intervals.icu не настроен. Укажите INTERVALS_ICU_API_KEY в .env."
            )

        headers = {
            "Accept": "application/json",
            "Authorization": _basic_auth_header(self.api_key),
            "User-Agent": DEFAULT_USER_AGENT,
        }
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")

        query_string = ""
        if params:
            query_string = f"?{urlparse.urlencode(params)}"

        request = urlrequest.Request(
            f"{_normalize_base_url(self.base_url)}{path}{query_string}",
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with urlrequest.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8").strip()
        except urlerror.HTTPError as exc:
            message = _decode_http_error(exc)
            raise IntervalsICUError(message) from exc
        except urlerror.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise IntervalsICUError(f"Не удалось подключиться к Intervals.icu: {reason}") from exc
        except TimeoutError as exc:
            raise IntervalsICUError(
                f"Не удалось подключиться к Intervals.icu: {exc}"
            ) from exc

        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise IntervalsICUError("Intervals.icu вернул ответ, который не удалось разобрать как JSON.") from exc


def _validate_activity_id(raw_id: Any) -> None:
    """Strict provider-activity id gate (review P1.2).

    ``id`` must be a NON-bool scalar (``str`` or ``int``) whose ``str().strip()``
    is non-empty. ``bool`` is rejected explicitly (it is an ``int`` subclass); a
    complex type (list/dict) or a None/empty/whitespace value is rejected too.
    Without this a payload like ``{"id": [1]}`` passed ``is not None``, normalized
    to ``intervals_[1]`` and persisted, advancing the cursor past garbage data.
    """
    if isinstance(raw_id, bool) or not isinstance(raw_id, (str, int)):
        raise IntervalsICUError(
            f"Intervals.icu activities: id must be a scalar str/int, got {raw_id!r}"
        )
    if not str(raw_id).strip():
        raise IntervalsICUError("Intervals.icu activities: id must be non-empty")


def _decode_http_error(exc: urlerror.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8").strip()
    except Exception:
        raw = ""
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("error") or payload.get("detail")
            if message:
                return f"Intervals.icu вернул HTTP {exc.code}: {message}"
        return f"Intervals.icu вернул HTTP {exc.code}: {raw}"
    return f"Intervals.icu вернул HTTP {exc.code}."


def get_client() -> IntervalsICUClient:
    """Return a client configured from application settings."""
    return IntervalsICUClient(
        api_key=Settings.INTERVALS_ICU_API_KEY or "",
        athlete_id=str(Settings.INTERVALS_ICU_ATHLETE_ID or "0"),
        base_url=Settings.INTERVALS_ICU_BASE_URL or "https://intervals.icu",
    )


def is_configured() -> bool:
    return get_client().is_configured()


def connection_info() -> Dict[str, Any]:
    return get_client().connection_info()


def test_connection() -> Dict[str, Any]:
    return get_client().test_connection()


def push_planned_events(event_payloads: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return get_client().create_events(event_payloads)


def list_race_events(oldest: date, newest: date) -> List[Dict[str, Any]]:
    """Return read-only normalized race events from the configured account."""
    return get_client().list_race_events(oldest, newest)


def _cycling_sport_settings(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    """Pick the cycling entry from sportSettings by capability, not by index —
    Intervals.icu does not document index 0 as a stable "this is cycling" slot."""
    for entry in raw.get("sportSettings") or []:
        if isinstance(entry, dict) and entry.get("eFTPSupported"):
            return entry
    return {}


def _running_sport_settings(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the one exact Run settings entry, or fail closed on ambiguity."""
    matches: list[Mapping[str, Any]] = []
    for entry in raw.get("sportSettings") or []:
        if not isinstance(entry, Mapping):
            continue
        types = entry.get("types")
        if isinstance(types, list) and "Run" in types:
            matches.append(entry)
    return matches[0] if len(matches) == 1 else {}


def _running_threshold_pace_seconds_per_km(value: Any) -> float | None:
    """Convert Intervals.icu metres/second to bounded seconds/kilometre."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    speed_metres_per_second = float(value)
    if not math.isfinite(speed_metres_per_second) or speed_metres_per_second <= 0:
        return None
    # Bound reciprocal floating-point noise before applying the inclusive
    # validation interval (e.g. 1000 / (1000 / 120) can be 119.9999999999).
    seconds_per_km = round(1000.0 / speed_metres_per_second, 6)
    if not (
        MIN_RUNNING_THRESHOLD_PACE_SECONDS_PER_KM
        <= seconds_per_km
        <= MAX_RUNNING_THRESHOLD_PACE_SECONDS_PER_KM
    ):
        return None
    return seconds_per_km


def normalize_athlete_profile(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Flatten Intervals profile signals into explicit local canonical units.

    Missing, reshaped, ambiguous, or malformed fields degrade to ``None``
    instead of raising.
    """
    if not isinstance(raw, dict):
        return {
            "ftp": None,
            "weight_kg": None,
            "lthr": None,
            "threshold_pace_seconds_per_km": None,
        }

    cycling = _cycling_sport_settings(raw)
    running = _running_sport_settings(raw)

    def _positive_number(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    return {
        "ftp": _positive_number(cycling.get("ftp")),
        "weight_kg": _positive_number(raw.get("icu_weight")),
        # Intervals.icu keeps a single lthr per athlete today (repeated across
        # every sportSettings entry rather than varying per sport), so reading
        # it from the cycling entry alongside ftp is equivalent to reading it
        # from any other entry.
        "lthr": _positive_number(cycling.get("lthr")),
        "threshold_pace_seconds_per_km": (
            _running_threshold_pace_seconds_per_km(
                running.get("threshold_pace")
            )
        ),
    }


def sync_athlete_profile(database: Any) -> Dict[str, Any]:
    """Fetch and persist Intervals FTP/weight/LTHR/running threshold pace.

    Never raises: a missing configuration or a failed request is reported back
    as ``{"synced": False, "reason": ...}`` so a caller can fold it into its
    warnings instead of aborting on an optional signal it does not depend on.
    """
    client = get_client()
    if not client.is_configured():
        return {"synced": False, "reason": "not_configured", "profile": None}

    try:
        raw_profile = client.get_athlete_profile()
    except IntervalsICUError as exc:
        return {"synced": False, "reason": str(exc), "profile": None}

    profile = normalize_athlete_profile(raw_profile)
    previous = database.get_athlete_profile()
    threshold_pace = profile.get("threshold_pace_seconds_per_km")
    if threshold_pace is not None:
        threshold_provenance = {
            "threshold_pace_source": "intervals_icu",
            # Database.save_athlete_profile stamps CURRENT_TIMESTAMP for a
            # newly observed pace when this is omitted.
            "threshold_pace_synced_at": None,
        }
    elif previous and previous.get("threshold_pace_seconds_per_km") is not None:
        profile["threshold_pace_seconds_per_km"] = previous.get(
            "threshold_pace_seconds_per_km"
        )
        threshold_provenance = {
            "threshold_pace_source": previous.get("threshold_pace_source"),
            "threshold_pace_synced_at": previous.get("threshold_pace_synced_at"),
        }
    else:
        threshold_provenance = {
            "threshold_pace_source": None,
            "threshold_pace_synced_at": None,
        }

    database.save_athlete_profile(
        {
            **profile,
            **threshold_provenance,
            "source": "intervals_icu",
        }
    )
    stored = database.get_athlete_profile()
    return {"synced": True, "reason": None, "profile": stored or profile}
