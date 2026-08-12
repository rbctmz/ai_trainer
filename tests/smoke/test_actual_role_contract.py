"""Backend and Planning UI expose the same closed actual-role vocabulary."""
from __future__ import annotations

import re
from pathlib import Path


def test_actual_role_contract_matches_planner_and_web_selector() -> None:
    from models.session_quality_forecast import ACTUAL_SESSION_ROLES
    from models.training_planner import SESSION_ROLE_LABELS_RU

    expected = set(SESSION_ROLE_LABELS_RU)
    assert set(ACTUAL_SESSION_ROLES) == expected

    source = (
        Path(__file__).resolve().parents[2] / "web" / "app" / "planning" / "page.tsx"
    ).read_text(encoding="utf-8")
    match = re.search(r"const ACTUAL_ROLE_OPTIONS = \[([^\]]+)\] as const", source)
    assert match is not None
    web_roles = set(re.findall(r'"([a-z_]+)"', match.group(1)))
    assert web_roles == expected
