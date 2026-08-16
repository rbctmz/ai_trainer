"""M1 dev-отчёт по теневым вело-парам power+HR (#444 S1+S2).

Читает таблицу ``bike_hr_quality_pairs`` (только производные признаки, сырой
ряд не хранится — политика #390) и сравнивает фиксированные кандидаты с
целевым Power TSS на дата-точном FTP. Формулы кандидатов переиспользуются из
M0-скрипта ``issue444_m0_bike_hr_tss.py`` (единственный источник математики).

Запуск:
    python research/issue444_m1_quality_pairs_report.py [--db ai_trainer.db]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from issue444_m0_bike_hr_tss import (
    BIKE_HR_ZONE_WEIGHTS,
    BikeActivity,
    by_intensity,
    hr_avg_formula,
    hr_zone_formula,
    hrss_karvonen,
    metrics,
    power_tss_target,
)


def _to_activity(pair: dict) -> BikeActivity:
    """Адаптер строки bike_hr_quality_pairs к датаклассу M0-скрипта."""
    zones = [pair.get(f"hr_zone_minutes_z{zone}") for zone in range(1, 6)]
    return BikeActivity(
        activity_id=str(pair["activity_id"]),
        date=date.fromisoformat(pair["date"]),
        sport=pair.get("sport"),
        duration_min=pair["moving_minutes"],
        moving_min=pair["moving_minutes"],
        avg_hr=pair.get("avg_hr"),
        max_hr=None,
        avg_power=pair.get("avg_power"),
        normalized_power=pair.get("normalized_power"),
        zones_min=tuple(zones),
        stored_tss=None,
        stored_method=None,
        stored_ftp=None,
        garmin_load=None,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="ai_trainer.db")
    ap.add_argument("--holdout-frac", type=float, default=0.30)
    args = ap.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM bike_hr_quality_pairs ORDER BY date, activity_id"
    ).fetchall()
    conn.close()
    pairs = [dict(row) for row in rows]

    print("=" * 78)
    print("M1 — теневые вело-пары power+HR (#444 S1): сравнение кандидатов")
    print("=" * 78)
    print(f"\nВсего пар: {len(pairs)}")
    print(f"  с FTP на дату: {sum(1 for p in pairs if p['ftp_on_date'] is not None)}")
    print(f"  с HR-зонами: {sum(1 for p in pairs if p['zone_coverage_pct'] is not None)}")
    print(f"  с RHR: {sum(1 for p in pairs if p['rhr'] is not None)}")

    rows_out = []
    for pair in pairs:
        activity = _to_activity(pair)
        target = (
            power_tss_target(activity, pair["ftp_on_date"])
            if pair["ftp_on_date"]
            else None
        )
        if target is None:
            continue
        lthr = pair.get("lthr")
        rows_out.append(
            {
                "pair": pair,
                "activity": activity,
                "target": target,
                "hrss": hrss_karvonen(activity, pair.get("rhr"), lthr) if lthr else None,
                "zones": hr_zone_formula(activity, BIKE_HR_ZONE_WEIGHTS),
                "avg_hr": hr_avg_formula(activity, lthr) if lthr else None,
            }
        )
    rows_out.sort(key=lambda r: r["pair"]["date"])

    names = {"hrss": "1.HRSS(Karvonen)", "zones": "2.zones(fixed)", "avg_hr": "3.avgHR(current)"}

    print("\n" + "-" * 78)
    print("FULL-SET error vs Power TSS target (TSS units)")
    print("-" * 78)
    for key, label in names.items():
        subset = [r for r in rows_out if r[key] is not None]
        if not subset:
            print(f"  {label:<20} n=0 (insufficient inputs)")
            continue
        m = metrics(
            np.array([r["target"] for r in subset]),
            np.array([r[key] for r in subset]),
        )
        print(
            f"  {label:<20} n={m['n']:<3} MAE={m['mae']:6.1f} medAE={m['median_ae']:6.1f} "
            f"bias={m['bias']:+6.1f} RMSE={m['rmse']:6.1f}"
        )

    holdout_n = max(1, int(round(len(rows_out) * args.holdout_frac)))
    holdout = rows_out[-holdout_n:] if rows_out else []
    print(f"\nХронологический holdout: train={len(rows_out) - len(holdout)} / holdout={len(holdout)}")
    for key, label in names.items():
        subset = [r for r in holdout if r[key] is not None]
        if len(subset) < 2:
            print(f"  {label:<20} n={len(subset)} (insufficient)")
            continue
        m = metrics(
            np.array([r["target"] for r in subset]),
            np.array([r[key] for r in subset]),
        )
        print(
            f"  {label:<20} n={m['n']:<3} MAE={m['mae']:6.1f} medAE={m['median_ae']:6.1f} "
            f"bias={m['bias']:+6.1f} RMSE={m['rmse']:6.1f}"
        )

    print("\n" + "-" * 78)
    print("Signed bias by target-TSS tercile (full set)")
    print("-" * 78)
    for key, label in [("zones", "2.zones(fixed)"), ("avg_hr", "3.avgHR(current)")]:
        subset = [r for r in rows_out if r[key] is not None]
        if not subset:
            continue
        buckets = by_intensity(
            np.array([r["target"] for r in subset]),
            np.array([r[key] for r in subset]),
        )
        print(f"  {label}:")
        for bucket_name, bucket in buckets.items():
            print(
                f"    {bucket_name:<9} n={bucket['n']:<3} MAE={bucket['mae']:6.1f} "
                f"bias={bucket['bias']:+6.1f}"
            )


if __name__ == "__main__":
    main()
