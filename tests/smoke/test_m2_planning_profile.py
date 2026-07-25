"""M2 гейты хранения профиля планирования (#271 §3, §6 M2-T1/T2/T3).

До M2 параметры планирования (режим/intent/цель/дистанция/часы/дни) жили ТОЛЬКО в
React-стейте `/planning`: каждый вход начинался с жёстких констант (10 часов, все 7 дней,
`event_goal` + выдуманная дата сегодня+56). Профиль делает эти входы явными и
персистентными — один источник правды для формы, коуча и M3-handoff.

  - M2-T1 : round-trip PUT→GET, идемпотентность, `updated_at` двигается.
  - M2-T2 : fail-closed валидация — мусор не сохраняется и не портит уже сохранённое.
  - M2-T3 : битый JSON под ключом читается как «профиля нет», а не как 500.
"""
from __future__ import annotations

import json

import pytest

from api import planning_profile
from data.database import Database


pytestmark = pytest.mark.smoke


VALID = {
    "planning_mode": "training_goal",
    "intent": "develop",
    "goal_type": "triathlon",
    "distance": "olympic",
    "available_hours": 8.5,
    "available_days": ["mon", "wed", "sat"],
    "horizon_weeks": 8,
}


def _db(tmp_path, name: str = "profile.db") -> Database:
    return Database(str(tmp_path / name))


# --- M2-T1: round-trip -------------------------------------------------------

def test_m2_t1_profile_round_trip(tmp_path):
    db = _db(tmp_path)

    assert planning_profile.load_profile(db) is None
    assert planning_profile.profile_status(db)["completed"] is False

    saved = planning_profile.save_profile(db, VALID)
    loaded = planning_profile.load_profile(db)

    assert loaded == saved
    for key, value in VALID.items():
        assert loaded[key] == value
    assert loaded["source"] == "onboarding"
    assert loaded["updated_at"]

    status = planning_profile.profile_status(db)
    assert status["completed"] is True
    assert status["profile"] == loaded


def test_m2_t1_repeat_save_is_idempotent_and_restamps(tmp_path):
    db = _db(tmp_path)

    first = planning_profile.save_profile(db, VALID)
    second = planning_profile.save_profile(db, VALID)

    assert {k: v for k, v in second.items() if k != "updated_at"} == {
        k: v for k, v in first.items() if k != "updated_at"
    }
    assert second["updated_at"] >= first["updated_at"]
    # Ровно один ключ, а не история — профиль это состояние, не журнал.
    assert db.get_user_setting(planning_profile.PLANNING_PROFILE_SETTING_KEY)


def test_m2_t1_days_are_normalized_and_deduped(tmp_path):
    db = _db(tmp_path)

    saved = planning_profile.save_profile(db, {**VALID, "available_days": ["SAT", "mon", "mon"]})

    assert saved["available_days"] == ["mon", "sat"], "дни канонизируются и сортируются"


def test_m2_t1_source_is_recorded(tmp_path):
    db = _db(tmp_path)

    saved = planning_profile.save_profile(db, {**VALID, "source": "planning_form"})

    assert saved["source"] == "planning_form"


# --- M2-T2: fail-closed валидация -------------------------------------------

@pytest.mark.parametrize(
    "patch",
    [
        {"planning_mode": "freestyle"},
        {"planning_mode": ""},
        {"intent": "recover"},
        {"goal_type": "curling"},
        {"distance": "marathon_of_life"},
        {"available_hours": 0},
        {"available_hours": -3},
        {"available_hours": "восемь"},
        {"available_hours": 999},
        {"available_days": []},
        {"available_days": ["monday"]},
        {"available_days": "mon,wed"},
        {"horizon_weeks": 0},
        {"horizon_weeks": 200},
        {"source": "somewhere_else"},
    ],
)
def test_m2_t2_invalid_payload_is_rejected(tmp_path, patch):
    db = _db(tmp_path)

    with pytest.raises(ValueError):
        planning_profile.save_profile(db, {**VALID, **patch})

    assert planning_profile.load_profile(db) is None, "отказ не должен ничего записывать"


def test_m2_t2_rejection_does_not_clobber_existing_profile(tmp_path):
    db = _db(tmp_path)
    good = planning_profile.save_profile(db, VALID)

    with pytest.raises(ValueError):
        planning_profile.save_profile(db, {**VALID, "intent": "recover"})

    assert planning_profile.load_profile(db) == good


def test_m2_t2_missing_required_field_is_rejected(tmp_path):
    db = _db(tmp_path)
    payload = dict(VALID)
    payload.pop("available_hours")

    with pytest.raises(ValueError):
        planning_profile.save_profile(db, payload)


def test_m2_t2_unknown_keys_are_dropped_not_stored(tmp_path):
    db = _db(tmp_path)

    saved = planning_profile.save_profile(db, {**VALID, "ftp": 250, "secret": "x"})

    assert "ftp" not in saved and "secret" not in saved


# --- M2-T3: устойчивость к битому состоянию ----------------------------------

@pytest.mark.parametrize("raw", ["{not json", "", "null", "[]", '"just-a-string"', "{}"])
def test_m2_t3_corrupt_setting_reads_as_absent(tmp_path, raw):
    db = _db(tmp_path)
    db.set_user_setting(planning_profile.PLANNING_PROFILE_SETTING_KEY, raw)

    assert planning_profile.load_profile(db) is None
    status = planning_profile.profile_status(db)
    assert status["completed"] is False and status["profile"] is None


def test_m2_t3_profile_saved_with_now_invalid_value_reads_as_absent(tmp_path):
    """Профиль, записанный старой версией с невалидным сейчас значением, не должен
    притворяться валидным — иначе форма предзаполнится мусором."""
    db = _db(tmp_path)
    db.set_user_setting(
        planning_profile.PLANNING_PROFILE_SETTING_KEY,
        json.dumps({**VALID, "planning_mode": "legacy_mode"}),
    )

    assert planning_profile.load_profile(db) is None


def test_m2_t3_corrupt_profile_can_be_overwritten(tmp_path):
    db = _db(tmp_path)
    db.set_user_setting(planning_profile.PLANNING_PROFILE_SETTING_KEY, "{not json")

    saved = planning_profile.save_profile(db, VALID)

    assert planning_profile.load_profile(db) == saved
