"""Immutable inputs and retained artifacts for one planning build protocol."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from typing import Any, Mapping

PROTOCOL_VERSION = 1
STORAGE_SCHEMA_VERSION = 1
CANONICAL_VERSION = 1
PLANNING_BUILD_RULE_VERSION = "planning-build-v1"


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    # Numpy scalars from the existing pandas SQL view must keep their values,
    # not become strings. Missing frame values are normalized before this call.
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Unsupported planning snapshot type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Versioned, finite, exact JSON; never apply display rounding to evidence."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"), default=_json_value)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def dependency_components(sources_json: str) -> dict[str, str]:
    sources = json.loads(sources_json)
    frame = sources["activities"]
    identity = frame["columns"].index("activity_id")
    frame["data"] = sorted(frame["data"], key=lambda row: canonical_json(row[identity]))
    return {key: fingerprint(value) for key, value in sources.items()}


def utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("planning preview timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


class PlanningBuildPreviewError(ValueError):
    """Safe protocol outcome; HTTP adapters translate it without exposing inputs."""

    def __init__(self, code: str, detail: str, *, status: int = 409, retryable: bool = False):
        super().__init__(detail)
        self.code = code
        self.status = status
        self.retryable = retryable
        self.context: dict[str, Any] = {}


@dataclass(frozen=True)
class BuildParameters:
    """JSON owns nested values; callers receive copies, never shared mutable lists.

    Raw inputs are validated/resolved by the shared planner once while capturing
    dependencies. A resolved instance contains the canonical public form keys.
    """

    payload_json: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> BuildParameters:
        return cls(canonical_json(dict(value)))

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self.payload_json)


@dataclass(frozen=True)
class BuildInputSnapshot:
    parameters: BuildParameters
    sources_json: str
    context_json: str
    revision_time: str
    checkpoint_source: str = "initial_plan"

    def sources(self) -> dict[str, Any]:
        return json.loads(self.sources_json)

    def context(self) -> dict[str, Any]:
        return json.loads(self.context_json)

    @property
    def dependency_digest(self) -> str:
        # Calculation preserves SQL ordering. Fingerprinting a set-like activity
        # read view uses stable identities so equal rows do not depend on ties.
        return fingerprint({"canonical_version": CANONICAL_VERSION,
                            "parameters": self.parameters.as_dict(),
                            "sources": dependency_components(self.sources_json), "context": self.context(),
                            "checkpoint_source": self.checkpoint_source})


@dataclass(frozen=True)
class PreparedPlanBuild:
    """Fully serialized result; confirmation must insert these bytes, not rebuild."""

    snapshot: BuildInputSnapshot
    checkpoint_json: str
    response_json: str
    settings_write_json: str = "{}"
