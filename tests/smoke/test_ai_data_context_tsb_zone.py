"""Smoke coverage for AIDataContext's TSB-zone migration (issue #63).

_predict_form and _generate_load_recommendations used to have their own,
mutually-inconsistent 5-bucket TSB boundary sets (10/0/-15/-30 and
15/5/-10/-25). Both now derive from the canonical models.banister.tsb_zone()
(-20/-10/+10, 4 buckets), which retires one string value from each function
-- pinned below as explicit negative assertions, not just the new behavior.

_predict_form's output flows into the live AI coach prompt via
AIDataContext.format_context_for_ai (see models/ai_coach_runtime.py), so
these are not cosmetic labels.
"""
from __future__ import annotations

from models.ai_data_context import AIDataContext


def _predict_form(tsb: float) -> str:
    # _predict_form only reads banister_metrics['tsb']; database access is
    # never touched by this call, so a None db is safe here.
    return AIDataContext(None)._predict_form({"tsb": tsb})


def _load_recommendations(tsb: float, ctl: float = 50.0, atl: float = 30.0) -> list[str]:
    return AIDataContext(None)._generate_load_recommendations({"tsb": tsb, "ctl": ctl, "atl": atl})


def test_predict_form_matches_canonical_zone_boundaries():
    assert _predict_form(-20.1) == "overreaching"
    assert _predict_form(-10.1) == "building_fitness"
    assert _predict_form(-10.0) == "maintaining"
    assert _predict_form(10.0) == "peaked"


def test_predict_form_retires_good_form():
    # Previously 0 < tsb <= 10 returned 'good_form'; that bucket is folded
    # into 'maintaining' now that the canonical table has only 4 zones.
    assert _predict_form(5.0) == "maintaining"
    assert _predict_form(7.0) != "good_form"


def test_load_recommendations_first_line_matches_canonical_zone_boundaries():
    assert _load_recommendations(-30.0)[0] == "Высокая усталость. Рассмотрите восстановительную неделю"
    assert _load_recommendations(-10.1)[0] == "Период накопления усталости. Хорошо для базового периода"
    assert _load_recommendations(-10.0)[0] == "Нормальное состояние для продолжения планомерных тренировок"
    assert _load_recommendations(10.0)[0] == "Отличная форма! Подходящее время для соревнований или тестовых тренировок"


def test_load_recommendations_retires_five_to_fifteen_bucket():
    # Previously 5 < tsb <= 15 said "Хорошая форма. Можно планировать
    # интенсивные тренировки"; that sentence is retired -- the range now
    # shows the "Отличная форма..." sentence used for tsb >= 10.
    assert _load_recommendations(12.0)[0] == "Отличная форма! Подходящее время для соревнований или тестовых тренировок"
    assert "Хорошая форма. Можно планировать интенсивные тренировки" not in _load_recommendations(12.0)


def test_load_recommendations_atl_and_ctl_checks_unaffected_by_tsb_zone():
    # These two checks are independent of the TSB branch and must keep
    # firing regardless of which TSB zone is active.
    recs = _load_recommendations(tsb=100.0, ctl=20.0, atl=40.0)  # deep in "success" zone
    assert "Острая нагрузка высока. Добавьте восстановительные дни" in recs
    assert "Низкая хроническая нагрузка. Постепенно увеличивайте объем тренировок" in recs
