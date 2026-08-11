"""Source contract for the shared workout-strip intensity scale."""
from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKOUT_STRIP = REPO_ROOT / "web" / "components" / "WorkoutStrip.tsx"


def test_relative_rpe_height_uses_the_declared_1_to_10_scale():
    source = WORKOUT_STRIP.read_text(encoding="utf-8")

    assert "const RPE_SCALE_MAX = 10;" in source
    assert "/ RPE_SCALE_MAX) * 100" in source
    assert "/ 8) * 100" not in source
