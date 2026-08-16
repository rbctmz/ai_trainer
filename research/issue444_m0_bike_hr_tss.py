"""M0 report generator for issue #444 (personal bike TSS from HR, no power).

Reproducible, read-only analysis over the local SQLite cache.  It does NOT
change any product TSS: it only recomputes, compares and prints.

Scope (M0):
  * inventory of bike power/HR availability (local aggregates + provenance);
  * date-accurate FTP resolution (the athlete profile changed FTP mid-history);
  * target = Power TSS from normalized power + date-accurate FTP;
  * four candidates compared on a chronological (walk-forward) holdout:
      1. HRSS (Karvonen-style hrTSS)  hours * ((avgHR-RHR)/(LTHR-RHR))^2 * 100
      2. fixed HR-zone weights       sum(minutes_z * weight_z)  [current code]
      3. current avg-HR formula      hours * (avgHR/LTHR)^2 * 100 [current code]
      4. personal model              NNLS zone-minutes -> Power TSS

Run:
    python research/issue444_m0_bike_hr_tss.py [--db ai_trainer.db]
"""
from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import numpy as np
from scipy.optimize import nnls

# Current bike cascade constants (data/data_processor.py).
BIKE_HR_ZONE_WEIGHTS = (0.2, 0.35, 0.65, 0.95, 1.3)
LTHR = 163.0  # from athlete_profile (constant across the synced history)
BIKE_SPORTS = ("cycling", "indoor_cycling")
ZONE_COLS = ("z1", "z2", "z3", "z4", "z5")


@dataclass
class BikeActivity:
    activity_id: str
    date: date
    sport: str
    duration_min: float
    moving_min: Optional[float]
    avg_hr: Optional[float]
    max_hr: Optional[float]
    avg_power: Optional[float]
    normalized_power: Optional[float]
    zones_min: tuple[Optional[float], ...]
    stored_tss: Optional[float]
    stored_method: Optional[str]
    stored_ftp: Optional[float]
    garmin_load: Optional[float]


def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def load_bike_activities(conn: sqlite3.Connection) -> list[BikeActivity]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT activity_id, date, sport, duration_minutes, moving_duration_minutes,
               avg_hr, max_hr, avg_power, normalized_power,
               hr_time_in_zone_1_seconds z1, hr_time_in_zone_2_seconds z2,
               hr_time_in_zone_3_seconds z3, hr_time_in_zone_4_seconds z4,
               hr_time_in_zone_5_seconds z5,
               tss, tss_method, tss_ftp_used, garmin_training_load
        FROM activities
        WHERE sport IN (?, ?)
        ORDER BY date, activity_id
        """,
        BIKE_SPORTS,
    ).fetchall()
    out = []
    for r in rows:
        zones = []
        for c in ZONE_COLS:
            v = _f(r[c])
            zones.append(None if v is None else round(v / 60.0, 3))
        out.append(
            BikeActivity(
                activity_id=r["activity_id"],
                date=datetime.strptime(r["date"], "%Y-%m-%d").date(),
                sport=r["sport"],
                duration_min=_f(r["duration_minutes"]),
                moving_min=_f(r["moving_duration_minutes"]),
                avg_hr=_f(r["avg_hr"]),
                max_hr=_f(r["max_hr"]),
                avg_power=_f(r["avg_power"]),
                normalized_power=_f(r["normalized_power"]),
                zones_min=tuple(zones),
                stored_tss=_f(r["tss"]),
                stored_method=r["tss_method"],
                stored_ftp=_f(r["tss_ftp_used"]),
                garmin_load=_f(r["garmin_training_load"]),
            )
        )
    return out


def load_ftp_history(conn: sqlite3.Connection) -> list[tuple[date, float]]:
    """Return [(synced_date, ftp), ...] sorted ascending, deduped by change."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT synced_at, ftp FROM athlete_profile ORDER BY synced_at"
    ).fetchall()
    history: list[tuple[date, float]] = []
    for r in rows:
        ftp = _f(r["ftp"])
        if ftp is None:
            continue
        try:
            d = datetime.strptime(r["synced_at"][:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        if history and history[-1][1] == ftp:
            continue
        history.append((d, ftp))
    return history


def ftp_at(history: list[tuple[date, float]], d: date) -> tuple[Optional[float], bool]:
    """Return (ftp, verified). verified=False when d predates the first sync."""
    verified = False
    ftp: Optional[float] = None
    for sync_d, value in history:
        if sync_d <= d:
            ftp = value
            verified = True
        else:
            break
    if ftp is None and history:
        ftp = history[0][1]  # earliest known, unverified for this date
    return ftp, verified


def load_rhr_by_date(conn: sqlite3.Connection) -> dict[date, float]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT date, resting_hr FROM daily_health WHERE resting_hr IS NOT NULL"
    ).fetchall()
    out: dict[date, float] = {}
    for r in rows:
        try:
            d = datetime.strptime(r["date"][:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        hr = _f(r["resting_hr"])
        if hr is not None and hr > 0:
            out[d] = hr
    return out


def rhr_for(rhr_map: dict[date, float], d: date, window_days: int = 7) -> Optional[float]:
    best = None
    for off in range(window_days + 1):
        cand = d.fromordinal(d.toordinal() - off)
        if cand in rhr_map:
            best = rhr_map[cand]
            break
    return best


def moving_duration(a: BikeActivity) -> Optional[float]:
    return a.moving_min if a.moving_min and a.moving_min > 0 else a.duration_min


def power_tss_target(a: BikeActivity, ftp: Optional[float]) -> Optional[float]:
    """Target Power TSS = hours * (NP/FTP)^2 * 100 (NP -> avg_power fallback)."""
    dur = moving_duration(a)
    power = a.normalized_power if a.normalized_power and a.normalized_power > 0 else a.avg_power
    if not dur or dur <= 0 or not power or power <= 0 or not ftp or ftp <= 0:
        return None
    return (dur / 60.0) * (power / ftp) ** 2 * 100.0


def hrss_karvonen(a: BikeActivity, rhr: Optional[float], lthr: float) -> Optional[float]:
    """Candidate 1: Karvonen-style hrTSS (needs RHR)."""
    dur = moving_duration(a)
    if not dur or dur <= 0 or not a.avg_hr or a.avg_hr <= 0:
        return None
    if rhr is None or rhr <= 0 or lthr <= 0 or (lthr - rhr) <= 0:
        return None
    if a.avg_hr <= rhr:
        return None
    if_num = (a.avg_hr - rhr) / (lthr - rhr)
    return (dur / 60.0) * (if_num ** 2) * 100.0


def hr_avg_formula(a: BikeActivity, lthr: float) -> Optional[float]:
    """Candidate 3: current avg-HR formula hours*(avgHR/LTHR)^2*100."""
    dur = moving_duration(a)
    if not dur or dur <= 0 or not a.avg_hr or a.avg_hr <= 0 or not lthr or lthr <= 0:
        return None
    return (dur / 60.0) * (a.avg_hr / lthr) ** 2 * 100.0


def hr_zone_formula(a: BikeActivity, weights) -> Optional[float]:
    """Candidate 2: fixed HR-zone weights (current code).

    Mirrors data_processor._zone_weighted_tss: NULL/<=0 zones are skipped
    per zone, and the candidate is computable when at least one zone has data.
    """
    total = 0.0
    has_zone_data = False
    for z, w in zip(a.zones_min, weights):
        if z is None or z <= 0:
            continue
        has_zone_data = True
        total += z * w
    return float(total) if has_zone_data else None


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    err = y_pred - y_true
    abs_err = np.abs(err)
    return {
        "n": int(len(y_true)),
        "mae": float(np.mean(abs_err)),
        "median_ae": float(np.median(abs_err)),
        "bias": float(np.mean(err)),
        "rmse": float(np.sqrt(np.mean(err ** 2))),
    }


def by_intensity(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Signed bias and MAE split by target-TSS tercile (easy/moderate/hard)."""
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="ai_trainer.db")
    ap.add_argument("--holdout-frac", type=float, default=0.30)
    args = ap.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    activities = load_bike_activities(conn)
    ftp_hist = load_ftp_history(conn)
    rhr_map = load_rhr_by_date(conn)
    conn.close()

    print("=" * 78)
    print("M0 — bike TSS from HR (issue #444): data inventory + 4-candidate compare")
    print("=" * 78)
    print(f"\nBike activities: {len(activities)}")
    print(f"FTP history (date -> ftp): {ftp_hist}")
    print(f"RHR samples in daily_health: {len(rhr_map)}")

    # Build quality pairs: power AND HR present (target computable).
    pairs = []
    for a in activities:
        ftp, verified = ftp_at(ftp_hist, a.date)
        target = power_tss_target(a, ftp)
        has_hr = a.avg_hr is not None and a.avg_hr > 0
        if target is not None and has_hr:
            pairs.append((a, ftp, verified, target))

    print(f"\nQuality pairs (power + HR, target computable): {len(pairs)}")
    print(f"  with HR zones (zones candidate computable): "
          f"{sum(1 for a, *_ in pairs if hr_zone_formula(a, BIKE_HR_ZONE_WEIGHTS) is not None)}")
    print(f"  with RHR (HRSS computable): "
          f"{sum(1 for a, *_ in pairs if rhr_for(rhr_map, a.date) is not None)}")
    print(f"  with unverified FTP (predate first sync): "
          f"{sum(1 for *_, v, _ in pairs if not v)}")

    print("\nTraining pairs (chronological):")
    print(f"  {'date':<11}{'sport':<15}{'dur':>6}{'avgHR':>7}{'NP':>6}{'ftp':>6}"
          f"{'target':>8}{'stored':>8}{'stored_ftp':>12}{'garmin':>8}")
    for a, ftp, verified, target in sorted(pairs, key=lambda p: p[0].date):
        print(f"  {a.date.isoformat():<11}{a.sport:<15}{moving_duration(a):>6.1f}"
              f"{a.avg_hr:>7.0f}{a.normalized_power or a.avg_power:>6.0f}{ftp:>6.0f}"
              f"{target:>8.1f}{a.stored_tss:>8.1f}{a.stored_ftp or 0:>12.0f}"
              f"{a.garmin_load or 0:>8.1f}{' (!ftp)' if not verified else ''}")

    # Candidate table: for each pair compute the four estimates.
    rows = []
    for a, ftp, _v, target in pairs:
        rhr = rhr_for(rhr_map, a.date)
        rows.append(
            {
                "target": target,
                "hrss": hrss_karvonen(a, rhr, LTHR),
                "zones": hr_zone_formula(a, BIKE_HR_ZONE_WEIGHTS),
                "avg_hr": hr_avg_formula(a, LTHR),
                "zones_min": a.zones_min,
                "date": a.date,
                "ftp": ftp,
            }
        )
    rows.sort(key=lambda r: r["date"])

    names = {"hrss": "1.HRSS(Karvonen)", "zones": "2.zones(fixed)", "avg_hr": "3.avgHR(current)"}

    print("\n" + "-" * 78)
    print("FULL-SET error vs Power TSS target (TSS units)")
    print("-" * 78)
    for key, label in names.items():
        sub = [r for r in rows if r[key] is not None]
        if not sub:
            print(f"  {label:<20} n=0 (insufficient inputs)")
            continue
        m = metrics(np.array([r["target"] for r in sub]), np.array([r[key] for r in sub]))
        print(f"  {label:<20} n={m['n']:<3} MAE={m['mae']:6.1f} medAE={m['median_ae']:6.1f} "
              f"bias={m['bias']:+6.1f} RMSE={m['rmse']:6.1f}")

    # Chronological (walk-forward) split.
    holdout_n = max(1, int(round(len(rows) * args.holdout_frac)))
    train = rows[:-holdout_n]
    hold = rows[-holdout_n:]
    print(f"\nChronological split: train={len(train)} (earlier) / holdout={len(hold)} (later)")

    # Personal model: NNLS on zone-minutes -> target, fit on train, predict holdout.
    def fit_personal(rows_sub):
        X = []
        y = []
        for r in rows_sub:
            if all(z is not None for z in r["zones_min"]) and r["target"] is not None:
                X.append([z or 0.0 for z in r["zones_min"]])
                y.append(r["target"])
        if len(y) < 3:
            return None
        X = np.array(X)
        y = np.array(y)
        coef, _ = nnls(X, y)
        return coef

    coef = fit_personal(train)
    personal_ok = coef is not None
    if personal_ok:
        mono = bool(np.all(np.diff(coef) >= -1e-9))
        print(f"\nPersonal model (NNLS) coefficients z1..z5: "
              f"{[round(c, 3) for c in coef]}")
        print(f"  monotonic non-decreasing: {mono}")
        print("  NOTE: nnls enforces non-negativity but NOT monotonicity; "
              "monotonicity is reported as a check.")

    def predict_personal(r):
        if coef is None or any(z is None for z in r["zones_min"]):
            return None
        return float(sum((z or 0.0) * c for z, c in zip(r["zones_min"], coef)))

    print("\n" + "-" * 78)
    print(f"HOLDOUT error (chronologically later rides, n={len(hold)})")
    print("-" * 78)
    for key, label in names.items():
        preds = [r[key] for r in hold if r[key] is not None]
        truths = [r["target"] for r in hold if r[key] is not None]
        if len(truths) < 2:
            print(f"  {label:<20} n={len(truths)} (insufficient)")
            continue
        m = metrics(np.array(truths), np.array(preds))
        print(f"  {label:<20} n={m['n']:<3} MAE={m['mae']:6.1f} medAE={m['median_ae']:6.1f} "
              f"bias={m['bias']:+6.1f} RMSE={m['rmse']:6.1f}")
    if personal_ok:
        scored = [(r, predict_personal(r)) for r in hold]
        truths = [r["target"] for r, p in scored if p is not None]
        preds = [p for _r, p in scored if p is not None]
        if len(truths) >= 2:
            m = metrics(np.array(truths), np.array(preds))
            print(f"  {'4.personal(NNLS)':<20} n={m['n']:<3} MAE={m['mae']:6.1f} "
                  f"medAE={m['median_ae']:6.1f} bias={m['bias']:+6.1f} RMSE={m['rmse']:6.1f}")
        else:
            print(f"  {'4.personal(NNLS)':<20} n={len(truths)} (insufficient holdout with zones)")

    # Intensity-bucket bias for the two current code candidates (context).
    print("\n" + "-" * 78)
    print("Signed bias by target-TSS tercile (full set, current-code candidates)")
    print("-" * 78)
    for key, label in [("zones", "2.zones(fixed)"), ("avg_hr", "3.avgHR(current)")]:
        sub = [r for r in rows if r[key] is not None]
        if not sub:
            continue
        yt = np.array([r["target"] for r in sub])
        yp = np.array([r[key] for r in sub])
        buckets = by_intensity(yt, yp)
        print(f"  {label}:")
        for bname, bm in buckets.items():
            print(f"    {bname:<9} n={bm['n']:<3} MAE={bm['mae']:6.1f} bias={bm['bias']:+6.1f}")

    print("\n" + "=" * 78)
    print("Interpretation notes (see docs/bike_hr_tss_m0_execplan.md)")
    print("=" * 78)


if __name__ == "__main__":
    main()
