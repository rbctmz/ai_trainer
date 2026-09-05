"""Contract guards for the dev-only component showcase (issue #548)."""

from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke
ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "web/app/showcase/page.tsx"
FIXTURES = ROOT / "web/lib/showcaseFixtures.ts"
STATE_CARD = ROOT / "web/components/showcase/ShowcaseStateCard.tsx"
NAV = ROOT / "web/components/Nav.tsx"
README = ROOT / "README.md"


def test_showcase_route_is_dev_only_and_provider_free() -> None:
    page = PAGE.read_text(encoding="utf-8")

    assert 'import { showDevTools } from "@/lib/flags"' in page
    assert 'if (!showDevTools) redirect("/today")' in page
    assert "fetcher" not in page
    assert "useSWR" not in page
    assert '"/api/' not in page


def test_showcase_reuses_product_components_and_typed_fixtures() -> None:
    page = PAGE.read_text(encoding="utf-8")
    fixtures = FIXTURES.read_text(encoding="utf-8")

    for component in ("DailyOutlook", "StatusRow", "TrainingScore", "WeekStrip"):
        assert component in page
    assert 'from "@/lib/types"' in fixtures
    for product_type in (
        "DailyOutlookData",
        "NextDay",
        "TodayState",
        "TrainingScoreData",
    ):
        assert product_type in fixtures
    assert "fetch(" not in fixtures
    assert '"/api/' not in fixtures


def test_showcase_covers_normal_loading_empty_error_and_responsive_states() -> None:
    page = PAGE.read_text(encoding="utf-8")
    state_card = STATE_CARD.read_text(encoding="utf-8")

    for state in ('state="normal"', 'state="loading"', 'state="empty"', 'state="error"'):
        assert state in page
    assert 'role="status"' in state_card
    assert 'role="alert"' in state_card
    assert 'uppercase tracking-wide text-ink-soft"' in state_card
    assert 'uppercase tracking-wide text-ink-faint"' not in state_card
    assert 'aria-hidden="true"' in state_card
    assert "состояние {STATE_LABELS[state]}" in state_card
    assert "md:grid-cols-2" in page
    assert "xl:grid-cols-4" in page


def test_showcase_is_discoverable_and_documented() -> None:
    nav = NAV.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")

    assert 'href="/showcase"' in nav
    assert "NEXT_PUBLIC_SHOW_DEV_TOOLS=true ./run_web.sh" in readme
    assert "web/lib/showcaseFixtures.ts" in readme
    assert "server-owned" in readme
