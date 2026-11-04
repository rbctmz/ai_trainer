"""Anonymous controls for the #731 duration experiment, not a new TSS policy."""
import math
from datetime import date, timedelta

import pandas as pd
import pytest

from data.data_processor import ActivityProcessor
from models.acwr import acwr_signal
from models.banister import BanisterModel
from models.load_metrics import compute_load_metrics
from scripts.tss_pause_replay import replay, summarize


def test_aggregate_zone_times_cannot_identify_active_zone_distribution():
    # Same 12-minute recording and six-minute moving duration, but movement can
    # be the six minutes in zone 1 OR the six minutes in zone 5. Both recordings
    # have the same stored aggregate fields: a duration ratio cannot recover it.
    aggregate = {'hr_time_in_zone_1_seconds': 360, 'hr_time_in_zone_5_seconds': 360,
                 'duration_minutes': 12, 'moving_duration_minutes': 6}
    weights = ActivityProcessor._RUN_HR_ZONE_TSS_WEIGHTS
    observed = ActivityProcessor._zone_weighted_tss(aggregate, weights)
    active_low = ActivityProcessor._zone_weighted_tss({'hr_time_in_zone_1_seconds': 360}, weights)
    active_high = ActivityProcessor._zone_weighted_tss({'hr_time_in_zone_5_seconds': 360}, weights)
    assert observed == pytest.approx(11.7)
    assert active_low == pytest.approx(2.7)
    assert active_high == pytest.approx(9)
    assert active_low != active_high
    assert ActivityProcessor._zone_weighted_tss(
        {**aggregate, 'moving_duration_minutes': 12}, weights
    ) == observed


def test_no_pause_run_control_has_no_aggregate_duration_discrepancy():
    row = {'duration_minutes': 20, 'moving_duration_minutes': 20,
           'hr_time_in_zone_3_seconds': 1200}
    assert ActivityProcessor._zone_weighted_tss(row, ActivityProcessor._RUN_HR_ZONE_TSS_WEIGHTS) == 20


def test_swim_duration_sensitivity_does_not_establish_the_correct_clock():
    # Same distance and CSS: doubling duration divides unrounded sTSS by four.
    short = ActivityProcessor._pace_tss(8, .4, 120)
    long = ActivityProcessor._pace_tss(16, .4, 120)
    assert short == 13.3 and long == 3.3
    assert short / long == pytest.approx(4, abs=.04)


def test_replay_matches_production_and_ignores_future_load():
    start = date(2026, 1, 1)
    rows = [{'date': str(start + timedelta(days=i)), 'tss': 25 + i % 3,
             'sport': 'running', 'activity_id': str(i)} for i in range(100)]
    anchor = start + timedelta(days=99)
    actual = replay(rows + [{'date': str(anchor + timedelta(days=1)), 'tss': 10000}], anchor, anchor)[0]
    expected = compute_load_metrics(pd.DataFrame(rows[-90:]), anchor)
    assert actual['ctl'] == expected['ctl'] and actual['tsb'] == expected['tsb']
    assert actual['acwr'] == acwr_signal([r['tss'] for r in rows[-91:]])['value']
    # Independent recurrence on the exact canonical 90-day series.
    ctl = atl = 0.0
    for r in rows[-90:]:
        ctl += (1 - math.exp(-1 / 42)) * (r['tss'] - ctl)
        atl += (1 - math.exp(-1 / 7)) * (r['tss'] - atl)
    assert actual['tsb'] == round(ctl - atl, 1)


def test_replay_counts_warmup_missingness_and_zero_filled_rest_days():
    rows = [{'date': '2026-01-01', 'tss': 50, 'sport': 'running'}]
    result = replay(rows, date(2026, 1, 1), date(2026, 1, 3))
    assert [r['acwr_history_days'] for r in result] == [1, 2, 3]
    assert all(r['acwr'] is None for r in result)
    assert summarize(result)['acwr']['eligible_days'] == 0
    model = BanisterModel().get_current_metrics([50, 0, 0], pd.date_range('2026-01-01', periods=3).tolist())
    assert result[-1]['ctl'] == round(model['ctl'], 1)


@pytest.mark.parametrize('tsb,acwr,watch,attention', [
    (-5, 1.3, False, False), (-10, 1.5, True, False), (-10.1, 1.51, True, True),
])
def test_threshold_equalities_and_inclusive_watch_denominators(monkeypatch, tsb, acwr, watch, attention):
    # Research uses strict < and >, unlike the current descriptive zone labels.
    monkeypatch.setattr('scripts.tss_pause_replay.compute_load_metrics', lambda *a: {'ctl': 20, 'atl': 25, 'tsb': tsb})
    monkeypatch.setattr('scripts.tss_pause_replay.acwr_metrics', lambda *a, **k: {'value': acwr, 'history_days': 90, 'reason': None})
    series = replay([], date(2026, 1, 1), date(2026, 1, 1))
    result = summarize(series)
    assert result['tsb']['watch_including_attention'] == int(watch)
    assert result['tsb']['watch_only'] == int(watch) - int(attention)
    assert result['acwr']['attention_percent'] == 100 * attention


def test_replay_preserves_proven_multisport_lineage():
    rows = [dict(date='2026-01-01', activity_id='envelope', provider_external_id='', sport='multi_sport', tss=180)]
    for sport in ('swim', 'bike', 'run'):
        rows.append(dict(date='2026-01-01', activity_id=sport, provider_external_id='envelope', sport=sport, tss=30))
    actual = replay(rows, date(2026, 1, 1), date(2026, 1, 1))[0]
    expected = compute_load_metrics(pd.DataFrame([{'date': '2026-01-01', 'tss': 90}]), date(2026, 1, 1))
    assert actual['ctl'] == expected['ctl'] and actual['tsb'] == expected['tsb']
