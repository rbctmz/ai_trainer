"""M1 dev-отчёт по теневым вело-парам power+HR (#444 S1/S2/S3).

Читает таблицу bike_hr_quality_pairs (только производные признаки, сырой
ряд не хранится — политика #390) и сравнивает кандидатов с целевым Power TSS
на дата-точном FTP. Формулы — services/bike_hr_tss_candidates.py,
статистика и гейт перестановки зон/avgHR — services/bike_hr_tss_eval.py.

Запуск:
    python research/issue444_m1_quality_pairs_report.py [--db ai_trainer.db]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from services.bike_hr_tss_candidates import (  # noqa: E402
    avg_hr_tss,
    hrss_tss,
    power_tss_target,
    zones_tss,
)
from services.bike_hr_tss_eval import by_intensity, evaluate_reorder, metrics  # noqa: E402


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
        target = power_tss_target(pair)
        if target is None:
            continue
        rows_out.append(
            {
                "pair": pair,
                "target": target,
                "hrss": hrss_tss(pair),
                "zones": zones_tss(pair),
                "avg_hr": avg_hr_tss(pair),
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

    print("\n" + "-" * 78)
    print("REORDER CHECK: зоны vs avgHR — статус гейта (#444 S3)")
    print("-" * 78)
    verdict = evaluate_reorder(pairs)
    for check in verdict["checks"]:
        mark = "✓" if check["passed"] else "✗"
        print(f"  [{mark}] {check['label']:<44} {check['detail']}")
    if verdict["passed"]:
        status = "ПРОЙДЕН — можно планировать S3′ (flip с провенанс-эскортом)"
    else:
        status = "НЕ пройден — продуктовый TSS остаётся без изменений, копим пары"
    print(f"\n  Гейт: {status}")
    hard = verdict.get("hard_tercile") or {}
    hard_bias_avg = hard.get("bias_avg")
    hard_bias_zones = hard.get("bias_zones")
    if hard_bias_avg is not None:
        print(
            f"  hard-терциль: bias(avgHR)={hard_bias_avg:+.1f}, "
            f"bias(зоны)={hard_bias_zones:+.1f} (n={hard.get('n')})"
        )


if __name__ == "__main__":
    main()
