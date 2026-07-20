"""The ASR catalog and ADR registry stay complete (Issue #201).

Cheap rot-guards: every ASR id from the analysis exists in the living
catalog, every registered ADR file exists, and AGENTS.md points agents at
the catalog.
"""
from pathlib import Path
import re

import pytest


pytestmark = pytest.mark.smoke

_ARCH = Path("docs/architecture")


def test_asr_catalog_covers_all_fourteen_asr_ids():
    catalog = (_ARCH / "asr_catalog.md").read_text(encoding="utf-8")
    expected = (
        [f"ASR-PERF-{n}" for n in range(1, 5)]
        + [f"ASR-REL-{n}" for n in range(1, 4)]
        + [f"ASR-MOD-{n}" for n in range(1, 4)]
        + ["ASR-SEC-1", "ASR-SEC-2", "ASR-DEP-1", "ASR-DEP-2"]
    )
    for asr_id in expected:
        assert asr_id in catalog, asr_id


def test_every_registered_adr_file_exists():
    catalog = (_ARCH / "asr_catalog.md").read_text(encoding="utf-8")
    referenced = re.findall(r"\((adr_\d{4}[a-z0-9_]*\.md)\)", catalog)
    assert len(referenced) >= 7, referenced
    for name in referenced:
        assert (_ARCH / name).exists(), name


def test_agents_md_points_at_the_living_catalog():
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    assert "docs/architecture/asr_catalog.md" in agents
