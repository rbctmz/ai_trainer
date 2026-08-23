"""Гейт подтверждения перестановки зон/avgHR в вело-каскаде (#444 S3).

Чистые функции над теневыми парами: метрики кандидатов, терцильный bias и
вердикт гейта. Продуктовый каскад НЕ меняется — модуль только оценивает, а
сам flip станет отдельным срезом (S3′) с провенанс-эскортом после прохождения
гейта. Критерии зафиксированы в docs/bike_hr_tss_m0_execplan.md (M1, S3).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from services.bike_hr_tss_candidates import avg_hr_tss, hrss_tss, power_tss_target, zones_tss


HOLD_FRAC = 0.30
MIN_PAIRS_WITH_ZONES = 20
MIN_HOLDOUT = 6
MAX_ABS_FULL_BIAS = 5.0
MAX_ABS_HARD_BIAS = 5.0
DEPENDENT_ACTIVITY_MAX_GAP_MINUTES = 30.0


def _started_at_utc(pair: dict) -> datetime | None:
    value = str(pair.get("started_at_utc") or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _elapsed_minutes(pair: dict) -> float | None:
    for key in ("duration_minutes", "moving_minutes"):
        try:
            value = float(pair.get(key))
        except (TypeError, ValueError):
            continue
        if np.isfinite(value) and value > 0:
            return value
    return None


def group_dependent_bike_pairs(
    pairs: list[dict],
    *,
    max_gap_minutes: float = DEPENDENT_ACTIVITY_MAX_GAP_MINUTES,
) -> list[list[dict]]:
    """Group contiguous recordings from one ride into evaluation episodes.

    Product activities remain separate. This grouping is used only to keep
    dependent activity parts together in the #444 statistical split. A pair
    without a trustworthy start and duration is fail-closed as a singleton;
    sharing a calendar date alone is never enough to merge two activities.
    """
    gap = timedelta(minutes=max(0.0, float(max_gap_minutes)))

    def sort_key(pair: dict) -> tuple[str, datetime, str]:
        started_at = _started_at_utc(pair)
        return (
            str(pair.get("date") or ""),
            started_at or datetime.max.replace(tzinfo=timezone.utc),
            str(pair.get("activity_id") or ""),
        )

    episodes: list[list[dict]] = []
    current: list[dict] = []
    current_date = ""
    current_end: datetime | None = None

    def flush() -> None:
        nonlocal current, current_date, current_end
        if current:
            episodes.append(current)
        current = []
        current_date = ""
        current_end = None

    for pair in sorted(pairs, key=sort_key):
        started_at = _started_at_utc(pair)
        duration = _elapsed_minutes(pair)
        pair_date = str(pair.get("date") or "")
        if started_at is None or duration is None:
            flush()
            episodes.append([pair])
            continue

        ended_at = started_at + timedelta(minutes=duration)
        if (
            current
            and pair_date == current_date
            and current_end is not None
            and started_at <= current_end + gap
        ):
            current.append(pair)
            current_end = max(current_end, ended_at)
            continue

        flush()
        current = [pair]
        current_date = pair_date
        current_end = ended_at

    flush()
    return episodes


def build_episode_candidate_rows(pairs: list[dict]) -> list[dict]:
    """Aggregate additive TSS candidates for independent ride episodes."""
    rows: list[dict] = []
    candidates = {
        "target": power_tss_target,
        "hrss": hrss_tss,
        "zones": zones_tss,
        "avg_hr": avg_hr_tss,
    }
    for episode in group_dependent_bike_pairs(pairs):
        values: dict[str, float | None] = {}
        for name, candidate in candidates.items():
            component_values = [candidate(pair) for pair in episode]
            values[name] = (
                float(sum(component_values))
                if all(value is not None for value in component_values)
                else None
            )
        if values["target"] is None:
            continue
        rows.append(
            {
                "date": str(episode[0].get("date") or ""),
                "activity_ids": [str(pair.get("activity_id") or "") for pair in episode],
                **values,
            }
        )
    return rows


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """MAE / median AE / bias / RMSE (TSS-единицы)."""
    err = np.asarray(y_pred) - np.asarray(y_true)
    abs_err = np.abs(err)
    return {
        "n": int(len(y_true)),
        "mae": float(np.mean(abs_err)),
        "median_ae": float(np.median(abs_err)),
        "bias": float(np.mean(err)),
        "rmse": float(np.sqrt(np.mean(err ** 2))),
    }


def by_intensity(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Signed bias и MAE по терцилям целевого TSS (easy/moderate/hard)."""
    order = np.argsort(y_true)
    n = len(y_true)
    thirds = [(0, n // 3), (n // 3, 2 * n // 3), (2 * n // 3, n)]
    labels = ["easy", "moderate", "hard"]
    out = {}
    for label, (lo, hi) in zip(labels, thirds):
        if lo >= hi:
            continue
        idx = order[lo:hi]
        out[label] = metrics(y_true[idx], y_pred[idx])
    return out


def evaluate_reorder(pairs: list[dict]) -> dict:
    """Вердикт гейта перестановки зон/avgHR по независимым эпизодам."""
    candidate_rows = build_episode_candidate_rows(pairs)
    rows = [
        {**row, "avg": row["avg_hr"]}
        for row in candidate_rows
        if row["zones"] is not None and row["avg_hr"] is not None
    ]
    rows.sort(key=lambda r: (r["date"], r["activity_ids"]))
    n_pairs = sum(len(row["activity_ids"]) for row in rows)
    n = len(rows)
    if n == 0:
        return {
            "n_pairs": 0,
            "n_episodes": 0,
            "holdout_n": 0,
            "holdout_activity_n": 0,
            "full": None,
            "hard_tercile": None,
            "holdout": None,
            "checks": [
                {"id": "n_episodes", "label": f"независимых эпизодов с зонами ≥ {MIN_PAIRS_WITH_ZONES}",
                 "passed": False, "detail": "0/20"},
            ],
            "passed": False,
        }

    holdout_n = max(1, int(round(n * HOLD_FRAC)))
    holdout = rows[-holdout_n:]
    targets = np.array([r["target"] for r in rows])
    hard_idx = np.argsort(targets)[-(n // 3):] if n >= 3 else np.array([], dtype=int)
    hard = [rows[i] for i in hard_idx]

    def _pair_metrics(subset):
        return (
            metrics(
                np.array([r["target"] for r in subset]),
                np.array([r["zones"] for r in subset]),
            ),
            metrics(
                np.array([r["target"] for r in subset]),
                np.array([r["avg"] for r in subset]),
            ),
        )

    full_zones, full_avg = _pair_metrics(rows)
    hold_zones, hold_avg = _pair_metrics(holdout)
    hard_bias_zones = hard_bias_avg = None
    if hard:
        _hard_zones, _hard_avg = _pair_metrics(hard)
        hard_bias_zones = _hard_zones["bias"]
        hard_bias_avg = _hard_avg["bias"]

    def _fmt(value):
        return "—" if value is None else f"{value:+.1f}"

    checks = [
        {"id": "n_episodes", "label": f"независимых эпизодов с зонами ≥ {MIN_PAIRS_WITH_ZONES}",
         "passed": n >= MIN_PAIRS_WITH_ZONES, "detail": f"{n}/{MIN_PAIRS_WITH_ZONES}"},
        {"id": "holdout_n", "label": f"хрон. holdout ≥ {MIN_HOLDOUT} эпизодов",
         "passed": len(holdout) >= MIN_HOLDOUT, "detail": f"{len(holdout)}/{MIN_HOLDOUT}"},
        {"id": "full_mae", "label": "full-set: MAE(avgHR) ≤ MAE(зоны)",
         "passed": full_avg["mae"] <= full_zones["mae"],
         "detail": f"avg {full_avg['mae']:.1f} vs zones {full_zones['mae']:.1f}"},
        {"id": "full_bias", "label": "full-set: |bias(avgHR)| ≤ 5 TSS",
         "passed": abs(full_avg["bias"]) <= MAX_ABS_FULL_BIAS,
         "detail": f"bias {_fmt(full_avg['bias'])}"},
        {"id": "hard_bias", "label": "hard-терциль: |bias(avgHR)| ≤ 5 TSS",
         "passed": hard_bias_avg is None or abs(hard_bias_avg) <= MAX_ABS_HARD_BIAS,
         "detail": f"bias {_fmt(hard_bias_avg)} (зоны {_fmt(hard_bias_zones)})"},
        {"id": "holdout_mae", "label": "holdout: MAE(avgHR) ≤ MAE(зоны)",
         "passed": hold_avg["mae"] <= hold_zones["mae"],
         "detail": f"avg {hold_avg['mae']:.1f} vs zones {hold_zones['mae']:.1f}"},
        {"id": "holdout_bias", "label": "holdout: |bias(avgHR)| ≤ 5 TSS",
         "passed": abs(hold_avg["bias"]) <= MAX_ABS_FULL_BIAS,
         "detail": f"bias {_fmt(hold_avg['bias'])}"},
    ]

    return {
        "n_pairs": n_pairs,
        "n_episodes": n,
        "holdout_n": len(holdout),
        "holdout_activity_n": sum(len(row["activity_ids"]) for row in holdout),
        "full": {"zones": full_zones, "avg": full_avg},
        "hard_tercile": {
            "n": len(hard),
            "bias_zones": hard_bias_zones,
            "bias_avg": hard_bias_avg,
        },
        "holdout": {"zones": hold_zones, "avg": hold_avg},
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
    }
