"""Route-level контракт `signals.load.acwr` — issue #608.

`contract:extract` этот сдвиг не видит: вложенный сигнал типизирован общим
словарём, поэтому значения enum и состав полей экстрактор не перечисляет.
Между тем runtime DTO изменился по-настоящему — добавлены шесть полей и заменены
значения статуса. Контракт закрыт тестом уровня роутера, а не экстрактором.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from data.database import Database
from state import StateManager
from utils.athlete_time import athlete_local_date


pytestmark = pytest.mark.smoke


#: Публичная шкала (issue #608).
_EXPECTED_SCALE = {
    "below_baseline",
    "expected_band",
    "elevated",
    "strongly_elevated",
}

#: Поля, которых в DTO до слайса не было вовсе.
_NEW_FIELDS = {
    "acute_tau_days",
    "chronic_tau_days",
    "calculation_version",
    "semantics_version",
    "limitation",
    "intervention_eligible",
}

_FORBIDDEN_WORDS = (
    "риск",
    "травм",
    "опасн",
    "безопасн",
    "injury",
    "risk",
    "safe",
)

#: Версии зафиксированы точными значениями: смена словаря не должна двигать
#: версию математики, а смена формулы — версию интерпретации.
_CALCULATION_VERSION = "acwr-ewma-v1"
_SEMANTICS_VERSION = "descriptive-v2"


def _seed(db: Database, *, days: int = 90, tss: float = 50.0) -> Database:
    anchor = athlete_local_date()
    rows = []
    for offset in range(days):
        day = anchor - timedelta(days=days - 1 - offset)
        rows.append(
            {
                "activity_id": f"acwr-api-{offset}",
                "date": day.strftime("%Y-%m-%d"),
                "sport": "cycling",
                "duration_minutes": 60,
                "distance_km": 30.0,
                "tss": tss,
            }
        )
    db.save_activities(rows)
    return db


def test_dashboard_summary_acwr_contract(tmp_path) -> None:
    """DTO отдаёт новую шкалу, шесть новых полей и точные версии."""
    from api.routers.dashboard import dashboard_summary

    db = _seed(Database(str(tmp_path / "acwr-api.db")))
    payload = dashboard_summary(db=db, state=StateManager({}))

    acwr = payload["signals"]["load"]["acwr"]

    missing = _NEW_FIELDS - set(acwr)
    assert not missing, f"в DTO нет полей: {sorted(missing)}"
    assert acwr["status"] in _EXPECTED_SCALE, (
        f"status={acwr['status']!r} вне описательной шкалы"
    )
    assert acwr["acute_tau_days"] == 7
    assert acwr["chronic_tau_days"] == 42
    assert acwr["calculation_version"] == _CALCULATION_VERSION
    assert acwr["semantics_version"] == _SEMANTICS_VERSION
    assert acwr["intervention_eligible"] is False, (
        "ACWR не даёт права на предписывающее вмешательство"
    )
    assert acwr["limitation"].strip()

    lowered = acwr["label"].lower()
    for word in _FORBIDDEN_WORDS:
        assert word not in lowered, (
            f"подпись {acwr['label']!r} в DTO содержит {word!r}"
        )


def test_dashboard_summary_provider_status_uses_new_scale(tmp_path) -> None:
    """Провайдерский прежний словарь не выходит наружу через DTO."""
    from api.routers.dashboard import dashboard_summary

    db = _seed(Database(str(tmp_path / "acwr-provider.db")))
    # sync_training_status принимает словарь {дата: значения колонок}.
    db.sync_training_status(
        {
            athlete_local_date().strftime("%Y-%m-%d"): {
                "acwr_status": "high_risk",
            }
        }
    )

    payload = dashboard_summary(db=db, state=StateManager({}))
    acwr = payload["signals"]["load"]["acwr"]

    assert acwr["provider_status"] in _EXPECTED_SCALE, (
        f"provider_status={acwr['provider_status']!r}: прежний словарь ушёл в DTO"
    )
