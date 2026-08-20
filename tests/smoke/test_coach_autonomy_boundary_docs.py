"""Architecture contract for the coach autonomy boundary (Issue #466)."""

from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke

_ADR = Path("docs/architecture/adr_0010_coach_autonomy_boundary.md")
_CATALOG = Path("docs/architecture/asr_catalog.md")
_EXECPLAN = Path("docs/coach_autonomy_boundary_execplan.md")


def test_adr_0010_defines_three_axes_and_dda_negative_examples() -> None:
    text = _ADR.read_text(encoding="utf-8").lower()

    for axis in ("reversibility", "blast radius", "agency creep"):
        assert axis in text
    for explicit_verb in ("примени", "подтверди"):
        assert explicit_verb in text
    for vague_assent in ("согласен", "ок"):
        assert vague_assent in text
    assert "не авториз" in text


def test_adr_0010_classifies_required_action_examples() -> None:
    text = _ADR.read_text(encoding="utf-8").lower()

    assert "заметка" in text
    assert "node" in text
    assert "удален" in text
    assert "ftp" in text
    assert "external write" in text
    assert "create_plan_constraint" in text
    assert "retract_plan_constraint" in text
    assert "repair_plan_day" in text


def test_adr_0010_is_registered_and_audit_is_recorded() -> None:
    catalog = _CATALOG.read_text(encoding="utf-8")
    execplan = _EXECPLAN.read_text(encoding="utf-8").lower()

    assert "ADR-0010" in catalog
    assert "adr_0010_coach_autonomy_boundary.md" in catalog
    assert "api/routers/coach.py" in execplan
    assert "models/ai_tools.py" in execplan
    assert "separate fix issue" in execplan
