"""Finite A-G contract classifier for historical coach narrative claims.

This module classifies only already-detected, asserted trend/comparison
candidates. It is deliberately not a general Russian-language parser: neutral
coaching text never enters this boundary.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


PAIRWISE_SESSION = "A"
COMPOUND_SESSION = "B"
LONGITUDINAL_TREND = "C"
HISTORICAL_WITH_FUTURE = "D"
LONGITUDINAL_PERIOD = "E"
COMPLETED_NEXT = "F"
PLANNED_FUTURE = "G"
UNSUPPORTED = "unsupported"

_PAIRWISE = re.compile(
    r"(?:по\s+сравнению\s+с|сравнен\w*\s+с|(?:лучше|хуже)\s+прошл\w*|"
    r"чем\s+прошл\w*)",
    re.IGNORECASE,
)
_PAIRWISE_PREVIOUS_SESSION = re.compile(
    r"(?:(?:по\s+сравнению\s+с|сравнен\w*\s+с)\s+"
    r"(?:прошл|предыдущ|предшествующ)\w*"
    r"(?=\s*(?:(?:трениров|сесси)\w*|улучш\w*|ухудш\w*|"
    r"снижа\w*|сниз\w*|раст\w*|вырос\w*|стабил\w*|"
    r"(?:был|стал|получ|оказ|выш)\w*|[.,;:—–]|$))|"
    r"(?:лучше|хуже|чем)\s+(?:прошл|предыдущ|предшествующ)\w*)",
    re.IGNORECASE,
)
_PERIOD_OBJECT = re.compile(
    r"(?:прошл|предыдущ|предшествующ)\w*\s+"
    r"(?:недел\w*|месяц\w*|период\w*|год\w*|микроцикл\w*)",
    re.IGNORECASE,
)
_SESSION_OBJECT = re.compile(r"(?:трениров\w*|сесси\w*)", re.IGNORECASE)
_COMPLETED_NEXT = re.compile(
    r"следующ\w*\s+(?:трениров\w*|сесси\w*).{0,40}"
    r"(?:был(?:а|о|и)?|получил\w*|оказал\w*|выш(?:ел|ла|ло|ли))\b",
    re.IGNORECASE,
)
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

_PACE = re.compile(r"(?:темп\w*|скорост\w*)", re.IGNORECASE)
_NON_TRAINING_PACE_COMPOUND = re.compile(
    r"(?:темп\w*|скорост\w*)\s+"
    r"(?:восстанов\w*|адаптаци\w*|заживлен\w*|реакци\w*)",
    re.IGNORECASE,
)
_POWER = re.compile(r"мощност\w*", re.IGNORECASE)
_HEART_RATE = re.compile(
    r"(?:пульс\w*|чсс\b|сердечн\w+\s+ритм\w*)",
    re.IGNORECASE,
)
_TSS = re.compile(r"(?:\btss\b|нагрузк\w*)", re.IGNORECASE)
_HRV = re.compile(r"(?:\bhrv\b|\bвср\b)", re.IGNORECASE)
_FITNESS = re.compile(r"(?:форм\w*|фитнес\w*)", re.IGNORECASE)
_GENERIC = re.compile(r"(?:показател\w*|\bтренд\w*)", re.IGNORECASE)


@dataclass(frozen=True)
class TrendClaimContract:
    """One classified historical claim and its exact evidence requirements."""

    form: str
    domains: frozenset[str]
    claimed_direction: str | None
    target_date: str | None = None
    claimed_sport: str | None = None
    supported: bool = True

    @property
    def is_session_claim(self) -> bool:
        return bool(self.domains) and all(
            domain == "session" or domain.startswith("session_")
            for domain in self.domains
        )

    def expected_direction(self, domain: str) -> str | None:
        direction = self.claimed_direction
        if direction != "decreasing":
            return direction
        if domain in {"session_pace", "session_hr"}:
            return "improving"
        return "declining"


def classify_historical_trend_claim(
    scope: str,
    trend_word: str,
) -> TrendClaimContract:
    """Map one asserted historical candidate to the immutable A-F matrix."""
    lowered = str(scope or "").lower()
    direction = _direction(trend_word)
    target_date_match = _ISO_DATE.search(lowered)
    target_date = target_date_match.group() if target_date_match else None
    claimed_sport = _claimed_sport(lowered)
    metric_domains = _metric_domains(lowered, session=True)
    has_pairwise = bool(_PAIRWISE.search(lowered))
    has_previous_session = bool(_PAIRWISE_PREVIOUS_SESSION.search(lowered))

    if _COMPLETED_NEXT.search(lowered) and has_previous_session:
        return TrendClaimContract(
            form=COMPLETED_NEXT,
            domains=frozenset({"session"}),
            claimed_direction=None,
            target_date=target_date,
            claimed_sport=claimed_sport,
        )

    if has_pairwise and not _PERIOD_OBJECT.search(lowered):
        if has_previous_session and _SESSION_OBJECT.search(lowered) and metric_domains:
            return TrendClaimContract(
                form=(COMPOUND_SESSION if len(metric_domains) > 1 else PAIRWISE_SESSION),
                domains=frozenset(metric_domains),
                claimed_direction=direction,
                target_date=target_date,
                claimed_sport=claimed_sport,
            )
        return _unsupported(target_date)

    if _PERIOD_OBJECT.search(lowered):
        domains = _metric_domains(lowered, session=False)
        return (
            TrendClaimContract(
                form=LONGITUDINAL_PERIOD,
                domains=frozenset(domains),
                claimed_direction=direction,
                target_date=target_date,
                claimed_sport=claimed_sport,
            )
            if domains
            else _unsupported(target_date)
        )

    domains = _metric_domains(lowered, session=False)
    if domains:
        return TrendClaimContract(
            form=LONGITUDINAL_TREND,
            domains=frozenset(domains),
            claimed_direction=direction,
            target_date=target_date,
            claimed_sport=claimed_sport,
        )
    return _unsupported(target_date)


def _metric_domains(text: str, *, session: bool) -> set[str]:
    prefix = "session_" if session else "trend_"
    domains: set[str] = set()
    if _PACE.search(text) and not _NON_TRAINING_PACE_COMPOUND.search(text):
        domains.add(f"{prefix}pace")
    if _POWER.search(text):
        domains.add(f"{prefix}power")
    if _HEART_RATE.search(text):
        domains.add(f"{prefix}hr")
    if not session and _TSS.search(text):
        domains.add("load")
    if not session and _HRV.search(text):
        domains.add("hrv")
    if not session and _FITNESS.search(text):
        domains.add("fitness")
    if not session and not domains and _GENERIC.search(text):
        # A naked generic trend is supported only when no unknown subject is
        # attached to it. The finite contract does not let generic aggregate
        # evidence prove arbitrary wellbeing or performance nouns.
        remainder = _GENERIC.sub("", text)
        remainder = re.sub(
            r"(?:улучш\w*|ухудш\w*|раст[её]т|вырос\w*|снижа\w*|"
            r"сниз\w*|стабил\w*|[:;,—–.\s])",
            "",
            remainder,
        )
        if not re.search(r"[а-яёa-z]", remainder, re.IGNORECASE):
            domains.add("generic")
    return domains


def _claimed_sport(text: str) -> str | None:
    if re.search(r"\b(?:swim\w*|плав\w*)", text, re.IGNORECASE):
        return "swim"
    if re.search(r"\b(?:bike\w*|cycling\w*|вело\w*)", text, re.IGNORECASE):
        return "bike"
    if re.search(r"\b(?:run\w*|running\w*|бег\w*)", text, re.IGNORECASE):
        return "run"
    return None


def _direction(text: str) -> str | None:
    lowered = str(text or "").lower()
    if re.search(r"(?:улучш\w*|лучше|раст[её]т|вырос\w*)", lowered):
        return "improving"
    if re.search(r"(?:ухудш\w*|хуже)", lowered):
        return "declining"
    if re.search(r"(?:снижа\w*|сниз\w*)", lowered):
        return "decreasing"
    if re.search(r"стабил\w*", lowered):
        return "stable"
    return None


def _unsupported(target_date: str | None) -> TrendClaimContract:
    return TrendClaimContract(
        form=UNSUPPORTED,
        domains=frozenset({"unsupported_trend"}),
        claimed_direction=None,
        target_date=target_date,
        supported=False,
    )


__all__ = [
    "COMPLETED_NEXT",
    "COMPOUND_SESSION",
    "HISTORICAL_WITH_FUTURE",
    "LONGITUDINAL_PERIOD",
    "LONGITUDINAL_TREND",
    "PAIRWISE_SESSION",
    "PLANNED_FUTURE",
    "TrendClaimContract",
    "UNSUPPORTED",
    "classify_historical_trend_claim",
]
