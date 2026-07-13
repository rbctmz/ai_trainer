"""Intervals.icu helpers for planned-workout sync."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Mapping, Sequence
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from config.settings import Settings
from models.plan_events import normalize_intervals_event

DEFAULT_USER_AGENT = "AI-Trainer/1.0 (+https://github.com/rbctmz/ai_trainer)"


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

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
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

        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise IntervalsICUError("Intervals.icu вернул ответ, который не удалось разобрать как JSON.") from exc


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


def normalize_athlete_profile(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Flatten an Intervals.icu athlete-profile response into the fields this
    app's TSS math needs. Degrades every field to None instead of raising when
    the response is missing, reshaped, or partially populated."""
    if not isinstance(raw, dict):
        return {"ftp": None, "weight_kg": None, "lthr": None}

    cycling = _cycling_sport_settings(raw)

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
    }


def sync_athlete_profile(database: Any) -> Dict[str, Any]:
    """Fetch the athlete's current FTP/weight/LTHR from Intervals.icu and
    persist it locally. Never raises: a missing configuration or a failed
    request is reported back as {"synced": False, "reason": ...} so a caller
    (e.g. the main Garmin sync flow) can fold it into its warnings instead of
    aborting on an optional signal it does not depend on."""
    client = get_client()
    if not client.is_configured():
        return {"synced": False, "reason": "not_configured", "profile": None}

    try:
        raw_profile = client.get_athlete_profile()
    except IntervalsICUError as exc:
        return {"synced": False, "reason": str(exc), "profile": None}

    profile = normalize_athlete_profile(raw_profile)
    database.save_athlete_profile({**profile, "source": "intervals_icu"})
    return {"synced": True, "reason": None, "profile": profile}
