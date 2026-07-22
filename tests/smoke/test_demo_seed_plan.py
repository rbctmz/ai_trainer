"""#256: the demo dataset must include an active plan, built in the api layer.

/today's session card, the /planning adjust/adherence tabs, and the coach's plan
context are all empty without an active plan. The demo-seed endpoint
(api/routers/system.py::demo_seed) builds one via ``_seed_demo_plan`` AFTER the
base-data seed. It lives in the api layer — NOT services/demo_mode — because
build_plan is an api-level orchestration and services must not import api
(test_api_architecture::test_services_modules_do_not_depend_on_api, #194).
"""
from __future__ import annotations

from api import planning_service as ps
from api.routers.system import _seed_demo_plan
from data.database import Database


def test_seed_demo_plan_persists_active_plan(tmp_path):
    db = Database(str(tmp_path / "demo_plan.db"))

    plan_days = _seed_demo_plan(db)

    assert plan_days > 0, "demo plan must have planned days"
    active = ps.get_active_plan(db)
    assert active and active.get("daily_plan"), "an active plan must be persisted"
    assert active.get("goal_type"), "plan must carry a goal"
    # profile is seeded so the builder has FTP/LTHR regardless of the runner's .env
    assert db.get_athlete_profile()


def test_clear_all_data_wipes_demo_athlete_profile(tmp_path):
    """Codex/#256: the demo athlete profile seeded for the plan must NOT survive
    a demo clear. `deactivate_demo_mode` delegates to `clear_all_data`, so that
    method must wipe `athlete_profile` too — otherwise GET /api/athlete-profile
    keeps reporting stale demo FTP/LTHR after a reset."""
    db = Database(str(tmp_path / "demo_clear.db"))
    _seed_demo_plan(db)
    assert db.get_athlete_profile(), "profile seeded by _seed_demo_plan"

    db.clear_all_data()

    assert db.get_athlete_profile() is None, "clear must wipe the demo profile"
