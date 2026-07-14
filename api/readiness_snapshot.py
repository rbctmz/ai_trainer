"""Backward-compatible API import for the shared readiness service."""

from services.readiness_snapshot import (  # noqa: F401
    FACTOR_LABELS,
    PRIMARY_INPUTS,
    READINESS_SNAPSHOT_RULE_VERSION,
    build_readiness_snapshot,
)

__all__ = [
    "FACTOR_LABELS",
    "PRIMARY_INPUTS",
    "READINESS_SNAPSHOT_RULE_VERSION",
    "build_readiness_snapshot",
]
