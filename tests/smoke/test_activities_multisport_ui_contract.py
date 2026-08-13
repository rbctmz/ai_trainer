"""Static web contracts for the expandable multisport activity row (#433)."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "web/app/activities/page.tsx"
TYPES = ROOT / "web/lib/types.ts"


def test_activity_types_expose_additive_multisport_group_contract() -> None:
    source = TYPES.read_text()

    assert 'group_kind?: "multisport";' in source
    assert "group_label?: string;" in source
    assert "segments?: Activity[];" in source
    assert '"stages"' in source


def test_activity_table_has_accessible_multisport_stage_disclosure() -> None:
    source = PAGE.read_text()

    assert "function MultisportSegments" in source
    assert "activity.segments?.length" in source
    assert "aria-expanded={expanded}" in source
    assert 'aria-label={`${expanded ? "Скрыть" : "Показать"} этапы: ${activity.group_label}`}' in source
    assert "<MultisportSegments activity={activity} onSelect={onSelect}" in source
    assert "onClick={() => onSelect(segment)}" in source
    assert 'aria-label={`Открыть этап: ${segment.sport_label ?? segment.sport}`}' in source
    assert "Этапы триатлона" in source
    assert 'stages: "по этапам"' in source
