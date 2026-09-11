"""Issue #557 M4: fail-closed intervention gate and version-qualified ownership.

AC6 requires that a pending Recovery Replan created by an older rule version
stops being actionable under the current rules — including when the newer
evaluation is `data_gap`, because that path deliberately does not update the
evidence head (issue #552 policy).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, timedelta

import pytest

from data.database import Database
from models.readiness import readiness_status_for_score
from models.readiness_conflicts import (
    READINESS_CONFLICT_RULE_VERSION,
    detect_readiness_conflicts,
)

pytestmark = pytest.mark.smoke

TODAY = date(2026, 7, 9)
OLD_VERSION = "readiness_conflicts_v1"
VERSION_CHANGE_REASON = "superseded_by_rule_version_change"
CHECKPOINT_ID = 1


def _conflict_report(today: date) -> dict:
    session = {
        "date": (today + timedelta(days=1)).isoformat(),
        "days_until": 1,
        "role": "quality",
        "tss": 60.0,
        "name": "Качественная",
        "sport_label": "вело",
        "phase": "Build",
    }
    return {
        "as_of": today.isoformat(),
        "horizon_days": 3,
        "readiness": {"score": 38.0, "status": "low", "confidence": 0.8},
        "sessions_evaluated": [session],
        "conflicts": [dict(session, severity="high", kind="low_readiness_quality_session")],
        "silence": False,
        "data_gap": False,
        "reason": "Готовность low расходится с планом.",
    }


def _pending_recovery_proposal(db: Database, *, rule_version: str | None):
    params: dict = {"base_checkpoint_id": CHECKPOINT_ID}
    preview: dict = {"variants": [{"kind": "keep"}]}
    if rule_version is not None:
        params["rule_version"] = rule_version
        preview["rule_version"] = rule_version
    return db.save_coach_proposal(
        action="recovery_replan",
        params=params,
        preview=preview,
        source="recovery_replan",
        source_key=f"source-{rule_version}",
        active_key=f"active-{rule_version}",
    )


def _conflict_state(db: Database) -> dict:
    """Create an evidence head whose outcome is `conflict` for the checkpoint."""
    return db.save_recovery_decision(
        fingerprint="conflict-fp",
        outcome="conflict",
        reason="conflict",
        report=_conflict_report(TODAY),
        plan_checkpoint_id=CHECKPOINT_ID,
        date=f"{TODAY.isoformat()}T00:00:00",
    )


def _attach_evidence(
    db: Database,
    proposal_id: int,
    revision: int,
    rule_version: str,
    event_id: str | None = None,
) -> None:
    """Attach evidence ownership to a hand-built proposal (test helper)."""
    params = json.dumps(
        {
            "base_checkpoint_id": CHECKPOINT_ID,
            "evidence_fingerprint": "conflict-fp",
            "evidence_revision": revision,
            "rule_version": rule_version,
        }
    )
    conn = sqlite3.connect(db.db_path)
    if event_id is None:
        conn.execute(
            "UPDATE coach_proposals SET params_json = ? WHERE id = ?",
            (params, proposal_id),
        )
    else:
        conn.execute(
            "UPDATE coach_proposals SET params_json = ?, decision_event_id = ? WHERE id = ?",
            (params, event_id, proposal_id),
        )
    conn.commit()
    conn.close()


def _evidence_head(db: Database) -> list:
    conn = sqlite3.connect(db.db_path)
    rows = conn.execute(
        "SELECT revision, fingerprint, outcome FROM recovery_evidence_heads"
    ).fetchall()
    conn.close()
    return rows


def _table_counts(db: Database) -> dict[str, int]:
    conn = sqlite3.connect(db.db_path)
    counts = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("planning_checkpoints", "intervals_plan_deliveries")
    }
    conn.close()
    return counts


# ------------------------------------------------------- version-qualified sweep


def test_sweep_supersedes_version_incompatible_pending_proposal_on_data_gap(tmp_path):
    from api.recovery_replan_loop import run_recovery_replan_loop

    db = Database(str(tmp_path / "version_sweep.db"))
    pending = _pending_recovery_proposal(db, rule_version=OLD_VERSION)

    # An empty database evaluates to `data_gap`: the evidence head must not be
    # touched, yet an old-rule proposal cannot stay actionable.
    result = run_recovery_replan_loop(db, today=TODAY)
    assert result["outcome"] == "data_gap"

    stored = db.get_coach_proposal(pending["id"])
    assert stored["status"] == "superseded"
    assert stored["result"]["reason"] == VERSION_CHANGE_REASON
    assert stored["resolved_at"]
    assert any(
        row["id"] == pending["id"]
        for row in db.get_coach_proposals(days=36500, status="superseded")
    )


def test_sweep_supersedes_legacy_unstamped_pending_proposal(tmp_path):
    db = Database(str(tmp_path / "legacy_sweep.db"))
    pending = _pending_recovery_proposal(db, rule_version=None)

    changed = db.supersede_incompatible_recovery_proposals(
        READINESS_CONFLICT_RULE_VERSION
    )

    assert changed == 1
    stored = db.get_coach_proposal(pending["id"])
    assert stored["status"] == "superseded"
    assert stored["result"]["reason"] == VERSION_CHANGE_REASON


def test_compatible_version_survives_the_sweep_and_stays_claimable(tmp_path):
    db = Database(str(tmp_path / "compatible.db"))
    saved = _conflict_state(db)
    pending = _pending_recovery_proposal(db, rule_version=OLD_VERSION)
    _attach_evidence(db, pending["id"], saved["evidence_revision"], OLD_VERSION, "event-1")

    changed = db.supersede_incompatible_recovery_proposals(
        READINESS_CONFLICT_RULE_VERSION, compatible_rule_versions=(OLD_VERSION,)
    )
    assert changed == 0
    assert db.get_coach_proposal(pending["id"])["status"] == "pending"

    claim = db.claim_current_recovery_proposal(
        pending["id"],
        current_rule_version=READINESS_CONFLICT_RULE_VERSION,
        compatible_rule_versions=(OLD_VERSION,),
    )
    assert claim["state"] == "claimed"
    assert claim["proposal"]["status"] == "applying"


def test_sweep_leaves_an_applying_proposal_alone(tmp_path):
    db = Database(str(tmp_path / "applying.db"))
    pending = _pending_recovery_proposal(db, rule_version=OLD_VERSION)
    db.transition_coach_proposal_status(pending["id"], "pending", "applying")

    changed = db.supersede_incompatible_recovery_proposals(
        READINESS_CONFLICT_RULE_VERSION
    )

    assert changed == 0
    assert db.get_coach_proposal(pending["id"])["status"] == "applying"


# ----------------------------------------------------------------- claim guard


def test_claim_rejects_version_mismatch_and_leaves_the_head_untouched(tmp_path):
    db = Database(str(tmp_path / "claim_version.db"))
    saved = _conflict_state(db)
    pending = _pending_recovery_proposal(db, rule_version=OLD_VERSION)
    _attach_evidence(db, pending["id"], saved["evidence_revision"], OLD_VERSION)
    head_before = _evidence_head(db)

    claim = db.claim_current_recovery_proposal(
        pending["id"], current_rule_version=READINESS_CONFLICT_RULE_VERSION
    )

    assert claim["state"] == "superseded"
    assert claim["proposal"]["status"] == "superseded"
    assert claim["proposal"]["result"]["reason"] == VERSION_CHANGE_REASON
    assert _evidence_head(db) == head_before


def test_approve_api_rejects_version_mismatch_without_mutating_anything(tmp_path):
    from fastapi import HTTPException

    from api.routers.decisions import approve_proposal

    db = Database(str(tmp_path / "approve_version.db"))
    saved = _conflict_state(db)
    pending = _pending_recovery_proposal(db, rule_version=OLD_VERSION)
    _attach_evidence(db, pending["id"], saved["evidence_revision"], OLD_VERSION)

    with pytest.raises(HTTPException) as exc_info:
        approve_proposal(pending["id"], db=db)

    assert exc_info.value.status_code == 409
    assert db.get_coach_proposal(pending["id"])["status"] == "superseded"
    assert _table_counts(db) == {"planning_checkpoints": 0, "intervals_plan_deliveries": 0}


def test_concurrent_claim_and_sweep_have_one_terminal_winner(tmp_path):
    """The write lock must leave exactly one terminal outcome."""
    db_path = str(tmp_path / "race.db")
    setup = Database(db_path)
    saved = _conflict_state(setup)
    pending = _pending_recovery_proposal(setup, rule_version=OLD_VERSION)
    _attach_evidence(setup, pending["id"], saved["evidence_revision"], OLD_VERSION)

    barrier = threading.Barrier(2)
    outcomes: dict[str, object] = {}

    def claim_thread():
        connection = Database(db_path)
        barrier.wait()
        outcomes["claim"] = connection.claim_current_recovery_proposal(
            pending["id"],
            current_rule_version=READINESS_CONFLICT_RULE_VERSION,
            compatible_rule_versions=(OLD_VERSION,),
        )

    def sweep_thread():
        connection = Database(db_path)
        barrier.wait()
        outcomes["swept"] = connection.supersede_incompatible_recovery_proposals(
            READINESS_CONFLICT_RULE_VERSION
        )

    threads = [threading.Thread(target=claim_thread), threading.Thread(target=sweep_thread)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    final = Database(db_path).get_coach_proposal(pending["id"])
    assert final["status"] in {"applying", "superseded"}
    if final["status"] == "applying":
        # The claim won the write lock before the version became current.
        assert outcomes["claim"]["state"] == "claimed"
    else:
        assert final["result"]["reason"] == VERSION_CHANGE_REASON
        assert outcomes["claim"]["state"] in {"superseded", "not_pending"}


# ------------------------------------------------------------ fingerprint/gate


def test_fingerprint_includes_the_rule_version():
    from api.recovery_replan_loop import _fingerprint

    base_report = _conflict_report(TODAY)
    current = {**base_report, "rule_version": READINESS_CONFLICT_RULE_VERSION}
    older = {**base_report, "rule_version": OLD_VERSION}

    assert _fingerprint(current, 1) != _fingerprint(older, 1)
    assert _fingerprint(current, 1) != _fingerprint(base_report, 1)


def _readiness(
    *,
    legacy_score,
    legacy_confidence,
    intervention_score,
    intervention_confidence,
) -> dict:
    return {
        "score": legacy_score,
        "status": readiness_status_for_score(legacy_score),
        "confidence": legacy_confidence,
        "intervention_score": intervention_score,
        "intervention_confidence": intervention_confidence,
        "eligible_inputs": () if intervention_score is None else ("resting_hr", "tsb"),
        "drivers": [],
        "as_of_date": TODAY.isoformat(),
    }


def _quality_session(days_until: int = 1) -> dict:
    return {
        "date": (TODAY + timedelta(days=days_until)).isoformat(),
        "days_until": days_until,
        "role": "quality",
        "tss": 60.0,
        "name": "Качественная",
        "sport_label": "вело",
        "phase": "Build",
    }


def test_gate_ignores_legacy_score_and_confidence():
    """The intervention gate must read the intervention channel only."""
    report = detect_readiness_conflicts(
        _readiness(
            legacy_score=38.0,
            legacy_confidence=1.0,
            intervention_score=None,
            intervention_confidence=0.2,
        ),
        [_quality_session()],
        today=TODAY,
    )

    assert report["data_gap"] is True
    assert report["conflicts"] == []
    assert report["rule_version"] == READINESS_CONFLICT_RULE_VERSION
    assert report["readiness"]["intervention_score"] is None


def test_gate_reports_conflicts_from_intervention_inputs():
    report = detect_readiness_conflicts(
        _readiness(
            legacy_score=80.0,
            legacy_confidence=1.0,
            intervention_score=38.0,
            intervention_confidence=0.6,
        ),
        [_quality_session()],
        today=TODAY,
    )

    assert report["data_gap"] is False
    assert report["conflicts"]
    assert report["conflicts"][0]["severity"] == "high"
    assert report["rule_version"] == READINESS_CONFLICT_RULE_VERSION


def test_gate_derives_intervention_status_from_the_intervention_score():
    """Review P1: severity must follow the intervention score, not legacy status."""
    healthy_intervention = detect_readiness_conflicts(
        _readiness(
            legacy_score=38.0,          # legacy says low...
            legacy_confidence=1.0,
            intervention_score=80.0,    # ...but the intervention channel is strong
            intervention_confidence=1.0,
        ),
        [_quality_session()],
        today=TODAY,
    )
    assert healthy_intervention["data_gap"] is False
    assert healthy_intervention["conflicts"] == []
    assert healthy_intervention["readiness"]["status"] == "strong"
    assert healthy_intervention["readiness"]["legacy_status"] == "low"

    weak_intervention = detect_readiness_conflicts(
        _readiness(
            legacy_score=65.0,          # legacy says ready...
            legacy_confidence=1.0,
            intervention_score=38.0,    # ...but the intervention channel is low
            intervention_confidence=1.0,
        ),
        [_quality_session()],
        today=TODAY,
    )
    assert weak_intervention["conflicts"]
    assert weak_intervention["conflicts"][0]["severity"] == "high"
    assert weak_intervention["readiness"]["status"] == "low"
    assert weak_intervention["readiness"]["legacy_status"] == "ready"


def test_gate_requires_an_eligible_primary_measurement():
    """Review P1: without an eligible primary measurement the gate must stay silent."""
    device_only = detect_readiness_conflicts(
        {
            **_readiness(
                legacy_score=38.0,
                legacy_confidence=1.0,
                intervention_score=38.0,
                intervention_confidence=0.6,
            ),
            "eligible_inputs": ["training_readiness", "tsb"],
        },
        [_quality_session()],
        today=TODAY,
    )
    assert device_only["data_gap"] is True
    assert device_only["conflicts"] == []
    assert "первичн" in device_only["reason"].lower()

    empty_eligible = detect_readiness_conflicts(
        {
            **_readiness(
                legacy_score=38.0,
                legacy_confidence=1.0,
                intervention_score=38.0,
                intervention_confidence=0.6,
            ),
            "eligible_inputs": [],
        },
        [_quality_session()],
        today=TODAY,
    )
    assert empty_eligible["data_gap"] is True

    # A malformed eligible_inputs payload fails closed as well.
    malformed = detect_readiness_conflicts(
        {
            **_readiness(
                legacy_score=38.0,
                legacy_confidence=1.0,
                intervention_score=38.0,
                intervention_confidence=0.6,
            ),
            "eligible_inputs": "resting_hr",
        },
        [_quality_session()],
        today=TODAY,
    )
    assert malformed["data_gap"] is True

    with_primary = detect_readiness_conflicts(
        {
            **_readiness(
                legacy_score=38.0,
                legacy_confidence=1.0,
                intervention_score=38.0,
                intervention_confidence=0.6,
            ),
            "eligible_inputs": ["resting_hr"],
        },
        [_quality_session()],
        today=TODAY,
    )
    assert with_primary["data_gap"] is False
    assert with_primary["conflicts"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("intervention_score", "38"),          # a string is not a measurement
        ("intervention_score", float("nan")),
        ("intervention_score", float("inf")),
        ("intervention_score", -5.0),
        ("intervention_score", 140.0),
        ("intervention_confidence", "0.6"),
        ("intervention_confidence", float("nan")),
        ("intervention_confidence", float("inf")),
        ("intervention_confidence", -0.2),
        ("intervention_confidence", 1.5),
    ],
)
def test_gate_fails_closed_on_invalid_intervention_numbers(field, value):
    """Review P2: malformed numbers must give data_gap, never a crash or a conflict."""
    readiness = {
        **_readiness(
            legacy_score=38.0,
            legacy_confidence=1.0,
            intervention_score=38.0,
            intervention_confidence=0.6,
        ),
        "eligible_inputs": ["resting_hr"],
        field: value,
    }

    report = detect_readiness_conflicts(readiness, [_quality_session()], today=TODAY)

    assert report["data_gap"] is True
    assert report["conflicts"] == []
    assert report["silence"] is True
    assert field in report["readiness"]["invalid_inputs"]


def test_gate_reports_invalid_inputs_separately_from_a_low_confidence():
    valid_but_weak = detect_readiness_conflicts(
        {
            **_readiness(
                legacy_score=38.0,
                legacy_confidence=1.0,
                intervention_score=38.0,
                intervention_confidence=0.2,
            ),
            "eligible_inputs": ["resting_hr"],
        },
        [_quality_session()],
        today=TODAY,
    )
    assert valid_but_weak["data_gap"] is True
    assert valid_but_weak["readiness"]["invalid_inputs"] == []
    assert "confidence" in valid_but_weak["reason"]


def test_status_helper_is_robust_to_invalid_scores():
    assert readiness_status_for_score(float("nan")) == "unknown"
    assert readiness_status_for_score("38") == "unknown"
    assert readiness_status_for_score(None) == "unknown"
    assert readiness_status_for_score(38.0) == "low"


def test_conflict_evidence_describes_only_intervention_eligible_factors():
    """Review P2: audit text must not claim an excluded factor drove the decision."""
    readiness = {
        **_readiness(
            legacy_score=38.0,
            legacy_confidence=1.0,
            intervention_score=38.0,
            intervention_confidence=0.6,
        ),
        "eligible_inputs": ["resting_hr", "tsb"],
        "drivers": [
            {
                "key": "hrv",
                "label": "HRV",
                "score": 20.0,
                "intervention_score_input": 20.0,
                "evidence": "HRV 30.0 мс против базовых 37.0 (−18.9%)",
                "observation_status": "unverified",
                "intervention_eligible": False,
            },
            {
                "key": "resting_hr",
                "label": "Пульс покоя",
                "score": 35.0,
                "intervention_score_input": 35.0,
                "evidence": "Пульс покоя 68.0 уд/мин против базовых 50.0",
                "observation_status": "confirmed_today",
                "intervention_eligible": True,
            },
        ],
        "factors": [],
    }

    report = detect_readiness_conflicts(readiness, [_quality_session()], today=TODAY)

    assert report["conflicts"], "the gate must still fire"
    evidence = " | ".join(report["conflicts"][0]["evidence"])
    assert "Пульс покоя" in evidence
    assert "HRV" not in evidence, "an ineligible factor must not be quoted as the driver"


def test_report_echoes_freshness_and_eligible_inputs_into_the_evidence_block():
    """Review P2: audit/evidence identity must reflect the fresh-factor set."""
    from api.recovery_replan_loop import _fingerprint

    freshness = {
        "state": "provisional",
        "anchor": TODAY.isoformat(),
        "confirmed_today": ["resting_hr"],
        "outdated": [],
        "unverified": ["sleep", "hrv"],
        "invalid": [],
        "missing": [],
        "intervention_eligible": ["resting_hr"],
        "blocked_reason": None,
    }
    readiness = {
        **_readiness(
            legacy_score=38.0,
            legacy_confidence=1.0,
            intervention_score=38.0,
            intervention_confidence=0.6,
        ),
        "eligible_inputs": ["resting_hr"],
        "freshness": freshness,
    }

    report = detect_readiness_conflicts(readiness, [_quality_session()], today=TODAY)

    block = report["readiness"]
    assert block["eligible_inputs"] == ["resting_hr"]
    assert block["freshness"] == freshness

    # The evidence identity hashes that block, so a changed fresh-factor set
    # produces a different fingerprint.
    other = detect_readiness_conflicts(
        {**readiness, "freshness": {**freshness, "state": "fresh", "confirmed_today": ["resting_hr", "hrv"]}},
        [_quality_session()],
        today=TODAY,
    )
    assert _fingerprint(report, 1) != _fingerprint(other, 1)
