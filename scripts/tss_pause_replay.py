"""Offline threshold replay for #731 evidence; no DB, credentials or network.

Input is an explicitly supplied frozen activity-row JSON, never a product DB.
TSB uses canonical 90 dates; ACWR retains the dashboard's inclusive 91-date
read policy and production history/low-load guards. No threshold is adopted.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from models.load_metrics import compute_load_metrics
from models.signals_engine import acwr_metrics


def replay(rows: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    """Replay immutable daily anchors with production windows and no lookahead."""
    if end < start:
        raise ValueError("end precedes start")
    result = []
    anchor = start
    while anchor <= end:
        tsb_start = (anchor - timedelta(days=89)).isoformat()
        acwr_start = (anchor - timedelta(days=90)).isoformat()
        selected = [r for r in rows if acwr_start <= str(r['date']) <= anchor.isoformat()]
        metrics = compute_load_metrics(pd.DataFrame([
            r for r in selected if str(r['date']) >= tsb_start
        ]), anchor)
        acwr = acwr_metrics(pd.DataFrame(selected), as_of=anchor)
        tsb = metrics['tsb'] if metrics else None
        value = acwr['value']
        result.append({
            'date': anchor.isoformat(), 'ctl': metrics['ctl'] if metrics else None,
            'atl': metrics['atl'] if metrics else None, 'tsb': tsb,
            'acwr': value, 'acwr_history_days': acwr['history_days'],
            'acwr_reason': acwr['reason'],
            # Watch includes attention; exclusive categories are added separately.
            'tsb_watch_inclusive': tsb is not None and tsb < -5,
            'tsb_attention': tsb is not None and tsb < -10,
            'acwr_watch_inclusive': value is not None and value > 1.3,
            'acwr_attention': value is not None and value > 1.5,
        })
        anchor += timedelta(days=1)
    return result


def summarize(series: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts and explicit eligible denominators, retaining refusal reasons."""
    result: dict[str, Any] = {'evaluation_days': len(series), 'thresholds_provisional': True}
    for key in ('tsb', 'acwr'):
        eligible = [r for r in series if r[key] is not None]
        watch = sum(r[key + '_watch_inclusive'] for r in eligible)
        attention = sum(r[key + '_attention'] for r in eligible)
        result[key] = {
            'eligible_days': len(eligible), 'watch_including_attention': watch,
            'attention': attention, 'watch_only': watch - attention,
            'watch_percent': 100 * watch / len(eligible) if eligible else None,
            'attention_percent': 100 * attention / len(eligible) if eligible else None,
            'minimum': min((r[key] for r in eligible), default=None),
            'maximum': max((r[key] for r in eligible), default=None),
        }
    result['acwr_exclusions'] = dict(Counter(
        r['acwr_reason'] for r in series if r['acwr'] is None
    ))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--start', type=date.fromisoformat, required=True)
    parser.add_argument('--end', type=date.fromisoformat, required=True)
    args = parser.parse_args()
    series = replay(json.loads(args.input.read_text()), args.start, args.end)
    # Exclusive creation prevents accidental overwrite of an input or old record.
    with args.output.open('x') as stream:
        json.dump({'summary': summarize(series), 'daily': series}, stream, indent=2, allow_nan=False)


if __name__ == '__main__':
    main()
