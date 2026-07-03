"""Smoke coverage for AITools._interpret_tsb's TSB-zone migration (issue #63).

_interpret_tsb used its own 5-bucket TSB split (10/0/-15/-30), independent
of and disagreeing with the canonical models.banister.tsb_zone()
(-20/-10/+10, 4 buckets). It now derives its Russian short-phrase from the
same tone the rest of the app uses. Feeds get_performance_metrics's
'form_state' field, part of an AI tool-calling result.
"""
from __future__ import annotations

from data.database import Database
from models.ai_tools import AITools


def _interpret_tsb(tmp_path, tsb: float) -> str:
    db = Database(str(tmp_path / "ai_tools.db"))
    return AITools(db)._interpret_tsb(tsb)


def test_interpret_tsb_matches_canonical_zone_boundaries(tmp_path):
    assert _interpret_tsb(tmp_path, -20.1) == "перегрузка"
    assert _interpret_tsb(tmp_path, -10.1) == "накопление"
    assert _interpret_tsb(tmp_path, -10.0) == "поддержание"
    assert _interpret_tsb(tmp_path, 10.0) == "пиковая форма"


def test_interpret_tsb_retires_khoroshaya_forma(tmp_path):
    # Previously 0 < tsb <= 10 returned "хорошая форма"; that bucket is
    # folded into "поддержание" now that the canonical table has 4 zones.
    assert _interpret_tsb(tmp_path, 5.0) == "поддержание"
    assert _interpret_tsb(tmp_path, 5.0) != "хорошая форма"
