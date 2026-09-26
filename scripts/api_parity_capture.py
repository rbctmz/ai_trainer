#!/usr/bin/env python3
"""Differential parity check for the product API (issue #602, AC3).

Captures the response of every parameterless GET endpoint against a
deterministic seeded database, so the same capture can be produced on two
revisions and compared. Used to prove that breaking the api -> state ->
streamlit dependency did not change endpoint behaviour.

Usage:

    PYTHONPATH=. python scripts/api_parity_capture.py capture --out /tmp/base.json
    git switch <candidate>
    PYTHONPATH=. python scripts/api_parity_capture.py capture --out /tmp/cand.json
    PYTHONPATH=. python scripts/api_parity_capture.py compare /tmp/base.json /tmp/cand.json

Two kinds of non-determinism are normalised rather than compared, because they
differ on every request by design and are not part of the payload contract:

* timestamps of "now" (readiness observed_at_utc, today/generated_at,
  checkpoint.created_at, planning/history date). Freezing the clock is not an
  option here: subclassing datetime.datetime segfaults under pandas' C
  extension (exit 139), so the values are masked instead. Field names still
  have to match, and date-only fields are deliberately left alone.
* ICS event UIDs, which are uuid4() in models/training_planner.py.

Exit code is 0 when the captures match, 1 when they differ, 2 on usage errors.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

# Each shape gets its own token. Masking every shape to one token would hide a
# format-only regression (a dropped `Z`, `T` replaced by a space, a lost offset),
# because the masked captures would still compare equal. The value is what
# varies per request; the shape is part of the payload contract.
TIMESTAMP_PATTERNS = (
    (re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z"), "<timestamp:iso-z>"),
    (re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?[+-]\d{2}:\d{2}"), "<timestamp:iso-offset>"),
    (re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"), "<timestamp:iso>"),
    (re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?"), "<timestamp:space>"),
)
UID_PATTERN = re.compile(r"UID:[0-9a-f]{32}")


def normalise(text: str) -> str:
    """Mask values that change on every request by design."""
    text = UID_PATTERN.sub("UID:<normalised>", text)
    for pattern, token in TIMESTAMP_PATTERNS:
        text = pattern.sub(token, text)
    return text


def _seed(db: Any) -> None:
    """Deterministic dataset: demo activities plus a small active plan.

    The plan matters: without it the planning endpoints answer with their
    "no plan" stub, and a regression in the state facade would have nowhere to
    show.
    """
    from models.planning_checkpoints import build_planning_checkpoint
    from services.demo_mode import (
        _build_demo_activities,
        _build_demo_health,
        _build_demo_hrv,
        _build_demo_sleep,
        _build_demo_training_status,
    )

    db.save_activities(_build_demo_activities())
    db.save_hrv_data(_build_demo_hrv())
    db.sync_sleep_data(_build_demo_sleep())
    db.sync_daily_health(_build_demo_health())
    db.sync_training_status(_build_demo_training_status())

    today = datetime.date.today()
    start_week = today - datetime.timedelta(days=today.weekday())
    daily_plan = []
    templates = []
    for week in range(4):
        for day in (1, 3, 5):
            dt = datetime.datetime.combine(
                start_week + datetime.timedelta(weeks=week, days=day),
                datetime.time.min,
            )
            daily_plan.append((dt, 100, {"bike": 100.0}))
            templates.append(
                {
                    "sport": "bike",
                    "sport_label": "Вело",
                    "session_focus": "Аэробная база",
                    "export_name": f"Сессия {week}-{day}",
                    "phase": "base",
                    "session_role": "easy",
                }
            )
    event_date = start_week + datetime.timedelta(weeks=5)
    db.save_planning_checkpoint(
        build_planning_checkpoint(
            {
                "goal_type": "Триатлон",
                "distance": "Олимпийка",
                "event_date": event_date.isoformat(),
                "events": [
                    {"date": event_date.isoformat(), "priority": "A", "label": "Старт"}
                ],
                "weeks_to_race": 5,
                "start_week": start_week,
                "weekly_tss_plan": [300, 300, 300, 300, 200],
                "base_weekly_tss_plan": [300, 300, 300, 300, 200],
                "phases": ["base", "base", "build", "build", "taper"],
                "daily_plan": daily_plan,
                "session_templates": templates,
                "weekly_summary": [],
                "constraint_summary": {
                    "load_state": "balanced",
                    "available_day_indices": list(range(7)),
                    "notes": [],
                },
                "planner_mix": None,
                "planner_weights": None,
                "plan_revision": "2026-01-01T00:00:00",
                "near_term_edit_version": 0,
                "near_term_edit_rollback_target_checkpoint_id": None,
            }
        )
    )


def capture() -> dict[str, Any]:
    """Return the normalised response of every parameterless GET endpoint."""
    from fastapi.testclient import TestClient

    from api.deps import get_database
    from api.main import app
    from data.database import Database

    spec = app.openapi()
    paths = sorted(
        path
        for path, ops in spec.get("paths", {}).items()
        if "get" in {method.lower() for method in ops} and "{" not in path
    )

    tmp = Path(tempfile.mkdtemp())
    db = Database(str(tmp / "parity.db"))
    _seed(db)
    app.dependency_overrides[get_database] = lambda: db

    captured: dict[str, Any] = {}
    try:
        client = TestClient(app)
        for path in paths:
            response = client.get(path)
            content_type = response.headers.get("content-type", "")
            if "json" in content_type:
                try:
                    body: Any = response.json()
                except ValueError:
                    body = response.text[:2000]
            else:
                body = response.text[:2000]
            captured[path] = {
                "status": response.status_code,
                "content_type": content_type.split(";")[0],
                "body": body,
            }
    finally:
        app.dependency_overrides.clear()
    return captured


def _walk(left: Any, right: Any, trail: str = "") -> list[tuple[str, Any, Any]]:
    out: list[tuple[str, Any, Any]] = []
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            out += _walk(left.get(key), right.get(key), f"{trail}.{key}")
    elif isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            out.append((f"{trail}[]", f"length {len(left)}", f"length {len(right)}"))
        else:
            for index, (a, b) in enumerate(zip(left, right)):
                out += _walk(a, b, f"{trail}[{index}]")
    elif left != right:
        out.append((trail, left, right))
    return out


def _command_capture(args: argparse.Namespace) -> int:
    # Hermetic: chat endpoints read Settings.CHATS_DIR, which defaults to the
    # operator's real chats. Set before the app is imported.
    tmp = Path(tempfile.mkdtemp())
    os.environ["CHATS_DIR"] = str(tmp / "chats")

    captured = capture()
    payload = normalise(json.dumps(captured, ensure_ascii=False, sort_keys=True, default=str))
    Path(args.out).write_text(payload, encoding="utf-8")

    non_200 = {path: row["status"] for path, row in captured.items() if row["status"] != 200}
    print(f"endpoints captured: {len(captured)}")
    print(f"sha256: {hashlib.sha256(payload.encode('utf-8')).hexdigest()}")
    print(f"bytes:  {len(payload.encode('utf-8'))}")
    print(f"non-200: {non_200 if non_200 else 'none'}")
    return 0


def _command_compare(args: argparse.Namespace) -> int:
    left = json.loads(Path(args.left).read_text(encoding="utf-8"))
    right = json.loads(Path(args.right).read_text(encoding="utf-8"))

    only_left = sorted(set(left) - set(right))
    only_right = sorted(set(right) - set(left))
    if only_left or only_right:
        print(f"endpoints only in {args.left}: {only_left}")
        print(f"endpoints only in {args.right}: {only_right}")

    differing = [path for path in sorted(set(left) & set(right)) if left[path] != right[path]]
    print(f"identical endpoints: {len(set(left) & set(right)) - len(differing)}")
    print(f"differing endpoints: {len(differing)}")
    for path in differing:
        print(f"--- {path}")
        for trail, a, b in _walk(left[path], right[path])[:12]:
            print(f"    {trail}")
            print(f"      left : {a!r}")
            print(f"      right: {b!r}")

    if differing or only_left or only_right:
        return 1
    print("PARITY OK: captures are identical")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capture", help="write a normalised capture to --out")
    cap.add_argument("--out", required=True)
    cap.set_defaults(func=_command_capture)

    cmp_ = sub.add_parser("compare", help="compare two captures")
    cmp_.add_argument("left")
    cmp_.add_argument("right")
    cmp_.set_defaults(func=_command_compare)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
