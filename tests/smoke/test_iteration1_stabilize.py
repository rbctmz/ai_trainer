from __future__ import annotations

import pandas as pd
import pytest

from ui.components import get_garmin_form_defaults
from utils.sleep_metrics import compute_sleep_regularity


pytestmark = pytest.mark.smoke


def test_garmin_form_defaults_never_prefill_credentials():
    defaults = get_garmin_form_defaults()

    assert defaults == {"email": "", "password": ""}


def test_sleep_regularity_smoke_metrics_are_computed():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-10-01", "2025-10-02", "2025-10-03"]),
            "bedtime": ["23:30", "23:45", "00:15"],
            "wakeup_time": ["07:00", "07:05", "07:10"],
        }
    )

    metrics = compute_sleep_regularity(df)

    assert metrics["count"] == 3
    assert metrics["bedtime"]["mean_text"] == "23:50"
    assert metrics["wakeup"]["mean_text"] == "07:05"
