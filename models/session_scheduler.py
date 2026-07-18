"""Deterministic weekly slot scheduler (Issue #205, Milestone 3b).

Places one week's sport budget into a bounded number of daily occasions BEFORE
materialization: weekly sport budget → roles and available slots →
``allocated_parts`` per day → ``sessions[]`` → ``weekly_summary``. The
historical per-day smeared parts are no longer materialized; the scheduler may
remove the daily smear as long as each week's per-discipline budget is
conserved exactly.

Contract for a normal 10-hour week (confirmed by the athlete): 7-10 training
occasions; at most two occasions per day; at most two two-a-day days; no day
with three independent sessions; at least one full rest day; two to four
sessions per discipline; a brick is one occasion with two deliverable leaves;
bike plus run in one occasion only as an explicit brick; the preferred
two-a-day pair is swim plus bike-or-run; at most one hard session per day;
never inflate hours through a hidden floor — an oversized budget is explicitly
reduced (``status="reduced"``) or refused (``status="infeasible"``).
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

SCHEDULER_RULE_VERSION = "session-scheduler-v1"

_SPORTS = ("bike", "run", "swim")
# The hard-role set is shared policy: RecoveryTransfer's collision/spacing
# guards (Issue #209) must agree with the scheduler's own one-hard-per-day and
# spacing rules, so both read this one definition.
HARD_SESSION_ROLES = frozenset({"long", "quality"})
_HARD_ROLES = HARD_SESSION_ROLES

# Named feasibility policy: the honest ceiling for one calendar day's training
# load. Basis: an amateur long ride of roughly 3.5-4 hours at endurance
# intensity accumulates about 180-240 TSS; a day asked to hold more than that
# is not one athlete's training day but an accounting overflow. When the weekly
# budget exceeds days × this ceiling, the scheduler explicitly reduces the
# budget (status="reduced") instead of silently smearing load. The long-slot
# role weights independently cap any single occasion at well under half of the
# week (long ≈ 45% of ITS OWN discipline's budget, not of the week).
MAX_DAY_TSS_POLICY = 220.0
# Companion duration ceiling (Issue #209): TSS alone does not bound a day —
# a low-intensity day can carry acceptable TSS yet unacceptable hours. The
# same ~4-hour amateur reasoning as above, expressed in persisted minutes
# (independent sessions sum their duration_minutes; a composite brick counts
# the parent duration with the transition included).
MAX_DAY_DURATION_MINUTES = 240
_ROLE_WEIGHTS = {"long": 3.0, "quality": 2.2, "easy": 1.4, "recovery": 1.0}
_ROLE_RANK = {"long": 0, "quality": 1, "easy": 2, "recovery": 3}


def _is_triathlon(goal_type: str) -> bool:
    lowered = str(goal_type or "").lower()
    return "триатлон" in lowered or "tri" in lowered


def _sport_frequency(budget: float, share: float) -> int:
    if budget <= 0:
        return 0
    if budget < 25.0:
        return 1
    return 3 if share >= 0.30 else 2


SCHEDULER_TIME_QUANTUM_MINUTES = 5


def schedule_week_slots(
    *,
    week_budget: Mapping[str, float],
    phase: str,
    goal_type: str = "Триатлон",
    load_state: str = "balanced",
    available_day_indices: Sequence[int] | None = None,
    pinned_off_days: Sequence[int] = (),
    available_weekly_hours: float | None = None,
    day_preferences: Mapping[str, Sequence[float]] | None = None,
    template_rotation: Sequence[str] | None = None,
) -> Dict[str, Any]:
    """Return the deterministic slot plan for one week.

    Output: ``allocated_parts`` (7 dicts), ``day_roles``/``day_focuses`` (7),
    ``occasions`` (7 lists of ``{sport, role, parts, is_brick}``), ``status``
    (``scheduled``/``reduced``/``infeasible``), ``notes``, ``rule_version``.
    """
    notes: List[str] = []
    budget = {sport: round(float(week_budget.get(sport, 0.0) or 0.0), 1) for sport in _SPORTS}
    pinned = {int(day) for day in pinned_off_days}
    days = sorted(
        {int(day) for day in (available_day_indices if available_day_indices is not None else range(7))}
        - pinned
    )
    days = [day for day in days if 0 <= day <= 6]
    phase_key = str(phase or "Base").strip().lower()
    total_budget = round(sum(budget.values()), 1)

    empty = {
        "rule_version": SCHEDULER_RULE_VERSION,
        "status": "scheduled",
        "notes": notes,
        "allocated_parts": [{"run": 0.0, "bike": 0.0, "swim": 0.0} for _ in range(7)],
        "day_roles": ["off"] * 7,
        "day_focuses": ["Отдых"] * 7,
        "occasions": [[] for _ in range(7)],
        "template_rotation": list(template_rotation or []),
    }
    if total_budget <= 0 or not days:
        if total_budget > 0 and not days:
            empty["status"] = "infeasible"
            notes.append("Нет доступных дней для недельного бюджета — план недели не размещён.")
        return empty

    # 1. Guarantee at least one full rest day when the athlete offered 6+ days.
    if len(days) >= 6:
        rest_day = 3 if 3 in days else days[len(days) // 2]
        days = [day for day in days if day != rest_day]

    # Honest capacity check: reduce the budget explicitly instead of smearing.
    status = "scheduled"
    capacity_tss = round(len(days) * MAX_DAY_TSS_POLICY, 1)
    if total_budget > capacity_tss:
        scale = capacity_tss / total_budget
        budget = {sport: round(value * scale, 1) for sport, value in budget.items()}
        status = "reduced"
        notes.append(
            f"Недельный бюджет {total_budget} TSS не помещается в {len(days)} дн. "
            f"(потолок {capacity_tss} TSS) — бюджет явно снижен до {round(sum(budget.values()), 1)} TSS."
        )

    # 2. Frequency per discipline for the phase.
    total = sum(budget.values()) or 1.0
    frequency = {
        sport: min(_sport_frequency(budget[sport], budget[sport] / total), 4, len(days) + 1)
        for sport in _SPORTS
    }

    # 4 (prepared here): a brick merges the bike long slot with one run slot.
    brick_allowed = (
        _is_triathlon(goal_type)
        and phase_key in {"build", "peak"}
        and str(load_state or "").lower() != "deep_fatigue"
        and frequency["bike"] >= 1
        and frequency["run"] >= 1
    )

    # Build the occasion list in a fixed priority order. The long slot belongs
    # to the discipline carrying the largest budget (bike in a triathlon, the
    # sport itself in a single-sport goal).
    long_sport = max(
        (s for s in _SPORTS if budget[s] > 0),
        key=lambda s: (budget[s], -_SPORTS.index(s)),
        default="bike",
    )

    def _sport_roles(sport: str, count: int) -> List[str]:
        if count <= 0:
            return []
        if sport == "swim":
            return ["easy"] + ["recovery"] * (count - 1)
        if sport == long_sport:
            return ["long", "quality", "easy", "easy"][:count]
        return ["quality", "easy", "easy", "easy"][:count]

    occasions: List[Dict[str, Any]] = []
    for sport in _SPORTS:
        for role in _sport_roles(sport, frequency[sport]):
            occasions.append({"sport": sport, "role": role, "is_brick": False})

    # A fatigued athlete's CURRENT week must contain an explicit recovery
    # occasion. Only an unpinned easy slot may be demoted — race, rest,
    # activation, long, quality, and protected slots are never touched, the
    # demotion changes neither the sport budget nor the slot count, and the
    # caller bounds `load_state` to the seven-day readiness window (future
    # weeks arrive as "balanced"), per the Issue #201/#202 precedent.
    if str(load_state or "").lower() in {"fatigued", "deep_fatigue"} and not any(
        o["role"] == "recovery" for o in occasions
    ):
        for occasion in reversed(occasions):
            if occasion["role"] == "easy" and not occasion["is_brick"]:
                occasion["role"] = "recovery"
                break

    if brick_allowed:
        long_bike = next((o for o in occasions if o["sport"] == "bike" and o["role"] == "long"), None)
        run_easies = [o for o in occasions if o["sport"] == "run" and o["role"] == "easy"]
        donor_run = run_easies[-1] if run_easies else None
        if long_bike is not None and donor_run is not None:
            occasions.remove(donor_run)
            long_bike["is_brick"] = True
            long_bike["brick_run_share"] = True

    # Capacity in occasions: each day ≤2, at most two two-a-day days.
    max_occasions = len(days) + 2

    def _sport_slot_count(sport: str) -> int:
        return sum(
            1
            for o in occasions
            if o["sport"] == sport or (o["is_brick"] and sport in {"bike", "run"})
        )

    while len(occasions) > max_occasions:
        # Drop the least important occasion (last easy/recovery of the sport
        # with the most slots) and note the merge — never create a new crumb
        # and never drop a discipline's last slot (its budget must land).
        droppable = [
            o
            for o in reversed(occasions)
            if o["role"] in {"easy", "recovery"}
            and not o["is_brick"]
            and _sport_slot_count(o["sport"]) >= 2
        ]
        if not droppable:
            break
        victim = droppable[0]
        occasions.remove(victim)
        status = status if status == "reduced" else "reduced"
        notes.append(
            f"Слот {victim['sport']}/{victim['role']} не поместился в {len(days)} дн. — "
            "его нагрузка объединена с другой сессией той же дисциплины."
        )
    if len(occasions) > 2 * len(days):
        status = "infeasible"
        notes.append("Даже минимальное число сессий не помещается в доступные дни.")
        occasions = occasions[: 2 * len(days)]

    # 3+4. Deterministic placement: long/brick first, then qualities with
    # spacing, then easies/recoveries; two-a-day pairs must include swim.
    day_occasions: Dict[int, List[Dict[str, Any]]] = {day: [] for day in days}

    def _day_has_hard(day: int) -> bool:
        return any(o["role"] in _HARD_ROLES for o in day_occasions[day])

    def _day_sports(day: int) -> set:
        found = set()
        for o in day_occasions[day]:
            found.add(o["sport"])
            if o["is_brick"]:
                found.add("run")
        return found

    def _can_pair(day: int, occasion: Mapping[str, Any]) -> bool:
        existing = day_occasions[day]
        if len(existing) != 1:
            return False
        if existing[0]["is_brick"] or occasion["is_brick"]:
            return False
        sports = _day_sports(day) | {occasion["sport"]}
        if "swim" not in sports:
            return False
        if occasion["sport"] in _day_sports(day):
            return False
        if occasion["role"] in _HARD_ROLES and _day_has_hard(day):
            return False
        two_a_days = sum(1 for d in days if len(day_occasions[d]) >= 2)
        return two_a_days < 2

    def _hard_distance(day: int) -> int:
        hard_days = [d for d in days if _day_has_hard(d)]
        if not hard_days:
            return 7
        return min(abs(day - d) for d in hard_days)

    # Issue #205 M3b.1: legacy `weights_overrides` become slot day PREFERENCES.
    # A sport's preference vector steers where its slots land (the long ride
    # follows the athlete's heaviest preferred day); zero/absent preferences
    # reproduce the default deterministic placement exactly.
    preferences = {
        sport: [float(v or 0.0) for v in vector]
        for sport, vector in (day_preferences or {}).items()
        if sport in _SPORTS and vector and any(float(v or 0.0) > 0 for v in vector)
    }

    def _pref(sport: str, day: int) -> float:
        vector = preferences.get(sport) or []
        return vector[day] if day < len(vector) else 0.0

    ordered = sorted(
        occasions,
        key=lambda o: (0 if o["is_brick"] or o["role"] == "long" else _ROLE_RANK[o["role"]] + 1,
                       o["sport"]),
    )
    default_long = 5 if 5 in days else days[-1]
    preferred_long = max(
        days,
        key=lambda d: (_pref(long_sport, d), 1 if d == default_long else 0, d),
    )
    for occasion in ordered:
        occasion_sport = "bike" if occasion["is_brick"] else occasion["sport"]
        target: int | None = None
        if occasion["is_brick"] or occasion["role"] == "long":
            target = preferred_long if not day_occasions[preferred_long] else None
        if target is None:
            free_days = [d for d in days if not day_occasions[d]]
            if occasion["role"] in _HARD_ROLES:
                if free_days:
                    target = max(
                        free_days,
                        key=lambda d: (_pref(occasion_sport, d), _hard_distance(d), -d),
                    )
            elif free_days:
                target = max(free_days, key=lambda d: (_pref(occasion_sport, d), -d))
        if target is None:
            pairable = [d for d in days if _can_pair(d, occasion)]
            if pairable:
                target = max(pairable, key=lambda d: (_pref(occasion_sport, d), -d))
        if target is None:
            # Rule 6: merge into an existing occasion of the same discipline.
            same_sport = [
                (d, o)
                for d in days
                for o in day_occasions[d]
                if o["sport"] == occasion["sport"] or (o["is_brick"] and occasion["sport"] in {"bike", "run"})
            ]
            if same_sport:
                notes.append(
                    f"Слот {occasion['sport']}/{occasion['role']} объединён с сессией той же дисциплины."
                )
                occasion["merged"] = True
                continue
            status = "infeasible" if status != "reduced" else status
            notes.append(f"Слот {occasion['sport']}/{occasion['role']} разместить не удалось.")
            occasion["merged"] = True
            continue
        day_occasions[target].append(occasion)

    placed = [o for o in occasions if not o.get("merged")]

    # 5+6. Distribute each sport's budget across its own occasions only; the
    # rounding remainder joins the largest occasion of that discipline.
    def _sport_occasions(sport: str) -> List[Dict[str, Any]]:
        out = []
        for o in placed:
            if o["sport"] == sport or (o["is_brick"] and sport == "run"):
                out.append(o)
        return out

    for occasion in placed:
        occasion["parts"] = {s: 0.0 for s in _SPORTS}

    for sport in _SPORTS:
        slots = _sport_occasions(sport)
        if not slots or budget[sport] <= 0:
            continue
        weights = []
        for o in slots:
            if o["is_brick"] and sport == "run":
                weights.append(1.2)  # the brick run leg is a purposeful short leg
            else:
                weights.append(_ROLE_WEIGHTS[o["role"]])
        weight_sum = sum(weights)
        shares = [round(budget[sport] * w / weight_sum, 1) for w in weights]
        remainder = round(budget[sport] - sum(shares), 1)
        if abs(remainder) >= 0.1:
            largest = max(range(len(slots)), key=lambda i: shares[i])
            shares[largest] = round(shares[largest] + remainder, 1)
        for o, share in zip(slots, shares):
            o["parts"][sport] = round(o["parts"][sport] + share, 1)

    # 7. Weekly hours must not exceed availability except one scheduler time
    # quantum (5 minutes). The canonical duration contract: the check
    # MATERIALIZES each occasion through the workout catalog — the same path
    # the plan will execute — so achievable load is never cut by a steeper
    # surrogate estimator. Capacity is a ceiling, not an obligation to fill.
    # A real trim is explicit: recorded note AND status="reduced".
    plan_rotation_out: List[str] = list(template_rotation or [])
    if available_weekly_hours and float(available_weekly_hours) > 0:
        # Canonical WEEK projection: measure exactly the way the builder will
        # persist the week — occasions aggregated into calendar days (the same
        # parts that reach daily_plan), one `_split_day_sessions` call per day
        # with the day's hardest role, and ONE shared recent_template_keys
        # rotation across the whole week. Lazy import; never re-enters expand.
        def _week_minutes() -> tuple:
            """(minutes, rotation_out) — the plan-level rotation contract: the
            week is projected starting from the rotation state accumulated by
            the previous weeks, exactly as the builder will see it."""
            from models.training_planner import _split_day_sessions

            rotation: List[str] = list(template_rotation or [])
            total_minutes = 0
            for day in days:
                entries = sorted(day_occasions[day], key=lambda o: _ROLE_RANK[o["role"]])
                if not entries:
                    continue
                parts = {"run": 0.0, "bike": 0.0, "swim": 0.0}
                for o in entries:
                    for sport in _SPORTS:
                        parts[sport] = round(parts[sport] + float(o["parts"][sport] or 0.0), 1)
                total = round(sum(parts.values()), 1)
                if total <= 0:
                    continue
                sessions, _allocated, _meta = _split_day_sessions(
                    parts=parts,
                    total=total,
                    is_brick=any(o["is_brick"] for o in entries),
                    phase=phase,
                    session_role=entries[0]["role"],
                    day_focus="—",
                    goal_type=goal_type,
                    distance="",
                    zone_snapshot={},
                    load_state=load_state,
                    recent_template_keys=rotation,
                )
                total_minutes += sum(int(session.get("duration_minutes") or 0) for session in sessions)
            return total_minutes, rotation

        limit_minutes = int(round(float(available_weekly_hours) * 60)) + SCHEDULER_TIME_QUANTUM_MINUTES
        original_total = round(sum(sum(o["parts"].values()) for o in placed), 1)
        trimmed = False
        rotation_out: List[str] = list(template_rotation or [])
        for _outer in range(len(placed) + 1):
            estimated, rotation_out = _week_minutes()
            for _ in range(6):
                if estimated <= limit_minutes:
                    break
                scale = max(0.5, (limit_minutes - SCHEDULER_TIME_QUANTUM_MINUTES) / estimated)
                for o in placed:
                    for sport in _SPORTS:
                        if o["parts"][sport] > 0:
                            o["parts"][sport] = round(o["parts"][sport] * scale, 1)
                trimmed = True
                estimated, rotation_out = _week_minutes()
            if estimated <= limit_minutes:
                break
            # Duration floors dominate: TSS scaling cannot shrink the week
            # further, so drop the least loaded soft occasion explicitly and
            # merge its remaining budget into the same discipline if possible.
            victims = sorted(
                (o for o in placed if o["role"] in {"easy", "recovery"} and not o["is_brick"]),
                key=lambda o: sum(o["parts"].values()),
            ) or sorted(
                (o for o in placed if not o["is_brick"] and o["role"] != "long"),
                key=lambda o: sum(o["parts"].values()),
            )
            if not victims:
                status = "infeasible"
                notes.append(
                    f"Даже минимальные длительности сессий не помещаются в {available_weekly_hours} ч."
                )
                break
            victim = victims[0]
            placed.remove(victim)
            for day in days:
                if victim in day_occasions[day]:
                    day_occasions[day].remove(victim)
            same_sport = [
                o
                for o in placed
                if o["sport"] == victim["sport"] or (o["is_brick"] and victim["sport"] in {"bike", "run"})
            ]
            if same_sport:
                receiver = max(same_sport, key=lambda o: o["parts"].get(victim["sport"], 0.0))
                receiver["parts"][victim["sport"]] = round(
                    receiver["parts"].get(victim["sport"], 0.0) + victim["parts"].get(victim["sport"], 0.0), 1
                )
                notes.append(
                    f"Слот {victim['sport']}/{victim['role']} снят ради лимита часов; "
                    "его нагрузка объединена с сессией той же дисциплины."
                )
            else:
                notes.append(
                    f"Слот {victim['sport']}/{victim['role']} снят ради лимита часов; "
                    "его остаток бюджета явно отброшен."
                )
            trimmed = True
        if trimmed:
            trimmed_total = round(sum(sum(o["parts"].values()) for o in placed), 1)
            status = "reduced" if status == "scheduled" else status
            notes.append(
                f"Недельный бюджет {original_total} TSS не помещается в "
                f"{available_weekly_hours} ч по материализованным длительностям — "
                f"бюджет явно снижен до {trimmed_total} TSS."
            )
        plan_rotation_out = list(rotation_out)

    # Assemble the 7-day outputs.
    from models.training_planner import _build_day_focus_label  # lazy: avoid import cycle

    allocated_parts = [{"run": 0.0, "bike": 0.0, "swim": 0.0} for _ in range(7)]
    day_roles = ["off"] * 7
    day_focuses = ["Отдых"] * 7
    occasions_out: List[List[Dict[str, Any]]] = [[] for _ in range(7)]
    for day in days:
        entries = sorted(day_occasions[day], key=lambda o: _ROLE_RANK[o["role"]])
        if not entries:
            continue
        for o in entries:
            for sport in _SPORTS:
                allocated_parts[day][sport] = round(allocated_parts[day][sport] + o["parts"][sport], 1)
            occasions_out[day].append(
                {
                    "sport": "brick" if o["is_brick"] else o["sport"],
                    "role": o["role"],
                    "parts": {s: v for s, v in o["parts"].items() if v > 0},
                    "is_brick": bool(o["is_brick"]),
                }
            )
        primary = entries[0]
        day_roles[day] = primary["role"]
        primary_sport = "brick" if primary["is_brick"] else primary["sport"]
        day_focuses[day] = _build_day_focus_label(primary["role"], primary_sport)

    return {
        "rule_version": SCHEDULER_RULE_VERSION,
        "status": status,
        "notes": notes,
        "allocated_parts": allocated_parts,
        "day_roles": day_roles,
        "day_focuses": day_focuses,
        "occasions": occasions_out,
        "template_rotation": plan_rotation_out,
    }


__all__ = [
    "HARD_SESSION_ROLES",
    "MAX_DAY_DURATION_MINUTES",
    "MAX_DAY_TSS_POLICY",
    "SCHEDULER_RULE_VERSION",
    "schedule_week_slots",
]
