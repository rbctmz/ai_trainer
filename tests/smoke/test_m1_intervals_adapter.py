"""M1 (#270) §11 step 3 — Intervals adapter ``sync_intervals_data`` (gate M1-T4).

The Intervals-only vertical: without any Garmin credentials the adapter still
populates ``activities`` (and its provider-links) through the SAME common-ingest
funnel Garmin uses, and CTL/ATL are computed from that Intervals-only load. This
covers slice-spec §3 + the five review refinements:

- Database-first contract — the core takes a ``Database``, not a StateManager.
- ``days=N`` is an explicit historical-window override (exact ``[now-N, now]``,
  ``bootstrapped=False``); the high-water cursor never moves backward.
- Fail-closed provider response: a malformed / non-list payload, a network/429
  error and a normalization error all mark the chunk dirty (no cursor advance);
  a missing API key fails fast BEFORE the runner runs; ``athlete_id="0"`` is valid.
- Chunk-boundary dedup: an activity returned by two adjacent chunks is ingested
  exactly once (``ingested == new``, ``updated == 0``).
- Result semantics: ``new``/``updated`` from ``canonical_created``,
  ``new + updated == ingested``, clean-response ``skipped == 0``.

The fake provider is a real ``IntervalsICUClient`` subclass whose ``_request_json``
is overridden, so the fail-closed behavior tested is the production code path
(same parser, same exception), not a re-implementation in the test.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from config.settings import Settings
from data.database import Database
from models.signals_engine import training_load_metrics
from services.intervals_icu import (
    IntervalsICUClient,
    IntervalsICUConfigurationError,
    IntervalsICUError,
)
from services.intervals_sync import IntervalsSyncResult, sync_intervals_data
from services.sync import SyncProgressUpdate
from services.sync_cursor import ChunkFetch, run_windowed_sync

pytestmark = pytest.mark.smoke

NOW = datetime(2026, 7, 23)


def _row(
    intervals_id: str = "i_777",
    *,
    external_id: str | None = "555111",
    source: str | None = "GARMIN_CONNECT",
    icu_training_load: Any = 90,
    start_date_local: str = "2026-07-10T06:30:00",
    moving_time: Any = 5700,
    **overrides: Any,
) -> dict[str, Any]:
    row = {
        "id": intervals_id,
        "external_id": external_id,
        "source": source,
        "start_date": "2026-07-10T04:30:00Z",
        "start_date_local": start_date_local,
        "type": "Ride",
        "name": "Morning Ride",
        "icu_training_load": icu_training_load,
        "moving_time": moving_time,
    }
    row.update(overrides)
    return row


class FakeIntervalsClient(IntervalsICUClient):
    """A real ``IntervalsICUClient`` whose network layer is replaced by a
    programmable responder, so list_activities' parsing/exception path is the
    production code path. ``configured=True`` unless explicitly disabled."""

    def __init__(self, responder, *, configured: bool = True, athlete_id: str = "0"):
        super().__init__(api_key="test-key" if configured else "", athlete_id=athlete_id)
        self._responder = responder

    def _request_json(self, method, path, payload=None, params=None):
        return self._responder(method, path, params)


def _ids(db: Database) -> set[str]:
    conn = sqlite3.connect(db.db_path)
    ids = {r[0] for r in conn.execute("SELECT activity_id FROM activities")}
    conn.close()
    return ids


def _links(db: Database) -> list[tuple[str, str]]:
    conn = sqlite3.connect(db.db_path)
    rows = list(
        conn.execute(
            "SELECT provider, provider_activity_id FROM activity_provider_links"
        )
    )
    conn.close()
    return rows


def _activities_df(db: Database) -> pd.DataFrame:
    conn = sqlite3.connect(db.db_path)
    df = pd.read_sql_query("SELECT date, tss FROM activities", conn)
    conn.close()
    return df


# --- M1-T4: Intervals-only vertical ------------------------------------------


def test_m1_t4_intervals_only_populates_activities_and_load(tmp_path):
    """Without Garmin creds the adapter populates activities + provider-links and
    CTL/ATL compute (non-zero) from the Intervals-only load."""
    db = Database(str(tmp_path / "t4.db"))

    def responder(method, path, params):
        return [_row("i_A"), _row("i_B", source="STRAVA", external_id="X1")]

    client = FakeIntervalsClient(responder)

    result = sync_intervals_data(db, client=client, now=NOW)

    assert isinstance(result, IntervalsSyncResult)
    assert result.source == "intervals"
    # Intervals-only: even the Garmin-attributed copy stays on its standalone
    # intervals_<id> canonical as `unmatched` until a real Garmin activity lands
    # (M0 coexistence — _resolve_garmin_coordinate, single claimant + no Garmin
    # link). Both rows populate activities through the common ingest.
    assert _ids(db) == {"intervals_i_A", "intervals_i_B"}
    assert len(_links(db)) == 2  # two intervals links

    df = _activities_df(db)
    assert not df.empty
    assert df["tss"].notna().any()
    metrics = training_load_metrics(df, as_of=NOW.date())
    assert metrics["ctl"] > 0.0
    assert metrics["atl"] > 0.0


def test_m1_t4_not_garmin_gated(tmp_path, monkeypatch):
    """The adapter is gated only on the Intervals API key, never on Garmin auth."""
    import services.garmin as garmin_service

    db = Database(str(tmp_path / "notgarmin.db"))
    monkeypatch.setattr(garmin_service, "is_authenticated", lambda state: False)

    def responder(method, path, params):
        return [_row("i_A")]

    client = FakeIntervalsClient(responder)
    result = sync_intervals_data(db, client=client, now=NOW)
    assert result.halted is False
    assert _ids(db) == {"intervals_i_A"}  # standalone (no Garmin activity to join)


# --- result semantics --------------------------------------------------------


def test_result_new_updated_from_canonical_created(tmp_path):
    db = Database(str(tmp_path / "counts.db"))

    def responder(method, path, params):
        return [_row("i_A"), _row("i_B", source="STRAVA", external_id="X1")]

    client = FakeIntervalsClient(responder)
    first = sync_intervals_data(db, client=client, now=NOW)
    # two brand-new canonical rows
    assert first.new == 2
    assert first.updated == 0
    assert first.ingested == 2
    assert first.new + first.updated == first.ingested

    second = sync_intervals_data(db, client=client, now=NOW)
    # both already exist -> updated, nothing new
    assert second.new == 0
    assert second.updated == 2
    assert second.ingested == 2
    assert second.new + second.updated == second.ingested


def test_result_clean_response_skipped_is_zero(tmp_path):
    """A clean list response has skipped == 0 (list_activities filters no-id rows
    by failing closed, never silently dropping)."""
    db = Database(str(tmp_path / "skip.db"))

    def responder(method, path, params):
        return [_row("i_A")]

    client = FakeIntervalsClient(responder)
    result = sync_intervals_data(db, client=client, now=NOW)
    assert result.skipped == 0


# --- provider-fallback TSS (D2) ----------------------------------------------


def test_provider_fallback_tss(tmp_path):
    """D2: a row with icu_training_load and no local streams uses the provider
    fallback, explicitly marked."""
    db = Database(str(tmp_path / "tss.db"))

    def responder(method, path, params):
        return [_row("i_A", icu_training_load=72, source="STRAVA", external_id="X1")]

    client = FakeIntervalsClient(responder)
    sync_intervals_data(db, client=client, now=NOW)

    conn = sqlite3.connect(db.db_path)
    row = conn.execute(
        "SELECT tss, tss_method FROM activities WHERE activity_id=?", ("intervals_i_A",)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == 72
    assert row[1] == "intervals_icu_provider_fallback"


# --- fail-closed provider response -------------------------------------------


def test_list_activities_raises_on_non_list_payload(tmp_path):
    """Fail-closed: a non-list payload (dict) is rejected at the client boundary,
    not silently coerced to an empty list that would advance the cursor."""
    client = FakeIntervalsClient(lambda method, path, params: {"not": "a list"})

    with pytest.raises(IntervalsICUError):
        client.list_activities(date(2026, 7, 1), date(2026, 7, 23))


def test_429_makes_chunk_dirty_and_holds_cursor(tmp_path):
    """A 429 on the 2nd chunk marks it dirty: cursor halts at the 1st clean
    chunk's boundary, the error is a warning (not an exception), and a later run
    with clean data re-fetches the rest idempotently."""
    db = Database(str(tmp_path / "dirty429.db"))
    calls: list[Any] = []
    first_boundary = (NOW - timedelta(days=90) + timedelta(days=30)).strftime("%Y-%m-%d")

    def responder(method, path, params):
        calls.append(params)
        if len(calls) == 1:
            return [_row("i_first")]  # clean first chunk
        raise IntervalsICUError("Intervals.icu вернул HTTP 429")

    client = FakeIntervalsClient(responder)
    result = sync_intervals_data(db, client=client, now=NOW, chunk_days=30)

    assert result.halted is True
    assert any("429" in w for w in result.warnings)
    assert db.get_sync_cursor("intervals", "activities") == first_boundary
    assert _ids(db) == {"intervals_i_first"}  # only the clean chunk landed

    # next run all-clean completes, idempotently
    calls.clear()

    def clean(method, path, params):
        return [_row("i_second", source="STRAVA", external_id="X2")]

    retry = sync_intervals_data(
        db, client=FakeIntervalsClient(clean), now=NOW, chunk_days=30
    )
    assert retry.halted is False
    assert _ids(db) == {"intervals_i_first", "intervals_i_second"}
    assert db.get_sync_cursor("intervals", "activities") == NOW.strftime("%Y-%m-%d")


def test_malformed_element_in_list_makes_chunk_dirty(tmp_path):
    """A non-mapping element, or an element without an id, must NOT be silently
    dropped: the whole chunk is dirty and the cursor does not advance."""
    db = Database(str(tmp_path / "malformed.db"))

    def responder(method, path, params):
        # a bare string inside the list — not a valid activity mapping
        return ["not-a-mapping"]

    client = FakeIntervalsClient(responder)
    result = sync_intervals_data(db, client=client, now=NOW)
    assert result.halted is True
    assert result.warnings
    assert db.get_sync_cursor("intervals", "activities") is None  # cursor unmoved
    assert _ids(db) == set()


def test_normalization_error_makes_chunk_dirty(tmp_path):
    """A row that passes list_activities (id present) but fails normalization
    (e.g. an empty-string id strips to nothing) marks the chunk dirty rather than
    losing the activity — exercises the normalize-error branch of fetch_chunk."""
    db = Database(str(tmp_path / "normerr.db"))

    def responder(method, path, params):
        bad = _row("i_A")
        bad["id"] = ""  # non-None but empty -> normalize fails
        return [bad]

    client = FakeIntervalsClient(responder)
    result = sync_intervals_data(db, client=client, now=NOW)
    assert result.halted is True
    assert result.warnings
    assert db.get_sync_cursor("intervals", "activities") is None
    assert _ids(db) == set()


# --- preflight: missing API key fails fast -----------------------------------


def test_missing_api_key_raises_configuration_error(tmp_path, monkeypatch):
    """Preflight: a missing API key raises IntervalsICUConfigurationError BEFORE
    any fetch or cursor work."""
    monkeypatch.setattr(Settings, "INTERVALS_ICU_API_KEY", None)
    db = Database(str(tmp_path / "nokey.db"))

    with pytest.raises(IntervalsICUConfigurationError):
        sync_intervals_data(db, now=NOW)

    assert db.get_sync_cursor("intervals", "activities") is None


def test_athlete_id_zero_is_valid(tmp_path):
    """athlete_id='0' is the documented default and must not be treated as
    misconfigured."""
    db = Database(str(tmp_path / "zero.db"))

    def responder(method, path, params):
        return [_row("i_A")]

    client = FakeIntervalsClient(lambda *a: [_row("i_A")], athlete_id="0")
    result = sync_intervals_data(db, client=client, now=NOW)
    assert result.halted is False
    assert _ids(db) == {"intervals_i_A"}


# --- chunk-boundary dedup ----------------------------------------------------


def test_chunk_boundary_activity_dedups_to_one_ingest(tmp_path):
    """Adjacent chunks share a boundary date; if the same activity is returned by
    both, it is ingested exactly once (ingested == new, updated == 0)."""
    db = Database(str(tmp_path / "dedup.db"))
    returned = {"count": 0}

    def responder(method, path, params):
        returned["count"] += 1
        # always return the same activity regardless of the chunk window
        return [_row("i_A")]

    client = FakeIntervalsClient(responder)
    result = sync_intervals_data(db, client=client, now=NOW, chunk_days=30)

    assert returned["count"] >= 2  # the activity showed up in 2+ chunks
    assert result.ingested == 1
    assert result.new == 1
    assert result.updated == 0
    assert _ids(db) == {"intervals_i_A"}


# --- historical override (days=N) --------------------------------------------


def test_historical_days_forces_exact_window(tmp_path):
    """Explicit days=N resolves to exact [now-N, now] with bootstrapped=False,
    and the high-water cursor never moves backward."""
    db = Database(str(tmp_path / "hist.db"))
    db.set_sync_cursor("intervals", "activities", "2026-07-15")

    client = FakeIntervalsClient(lambda *a: [])
    result = sync_intervals_data(db, client=client, now=NOW, days=120)

    assert result.bootstrapped is False
    assert result.window_start == (NOW - timedelta(days=120)).strftime("%Y-%m-%d")
    assert result.window_end == NOW.strftime("%Y-%m-%d")
    # cursor is monotonic: a 120-day historical reload ending at NOW does not
    # pull the high-water boundary below the prior 2026-07-15 mark.
    assert db.get_sync_cursor("intervals", "activities") == NOW.strftime("%Y-%m-%d")


def test_historical_days_must_be_positive_int(tmp_path):
    db = Database(str(tmp_path / "baddays.db"))
    client = FakeIntervalsClient(lambda *a: [])
    for bad in (0, -5, 2.5, "ten"):
        with pytest.raises(ValueError):
            sync_intervals_data(db, client=client, now=NOW, days=bad)  # type: ignore[arg-type]


# =============================================================================
# P1 review fixes (#281)
# =============================================================================

# --- P1.1: progress callback emits one SyncProgressUpdate (SyncJobManager) ----


def test_progress_callback_emits_single_sync_progress_update(tmp_path):
    """P1.1: the adapter must emit ONE object compatible with the existing
    SyncJobManager contract, which calls ``run_sync(on_progress)`` where
    ``on_progress(update: SyncProgressUpdate)`` takes a SINGLE argument and reads
    ``update.percent``/``message``/``step_text``/``stats_message``. The old
    ``Callable[[int, str], None]`` + ``on_progress(10, msg)`` shape raised
    TypeError against that contract before any fetch ran."""
    db = Database(str(tmp_path / "progress.db"))

    def responder(method, path, params):
        return [_row("i_A")]

    received: list[SyncProgressUpdate] = []

    def on_progress(update: SyncProgressUpdate) -> None:
        received.append(update)

    sync_intervals_data(db, client=FakeIntervalsClient(responder), now=NOW, on_progress=on_progress)

    # at least the open (10) and close (100) events
    assert len(received) >= 2
    percents = [u.percent for u in received]
    assert 10 in percents and 100 in percents
    # each event is a SyncProgressUpdate with the documented fields
    for u in received:
        assert isinstance(u, SyncProgressUpdate)
        assert isinstance(u.percent, int)
        assert isinstance(u.message, str)
    assert received[0].percent == 10
    assert received[-1].percent == 100


# --- P1.2: strict provider activity id validation ----------------------------


@pytest.mark.parametrize(
    "bad_id",
    [
        None,
        "",
        "   ",
        ["1"],
        {"id": "1"},
        True,
        False,
    ],
    ids=["none", "empty", "whitespace", "list", "mapping", "bool_true", "bool_false"],
)
def test_list_activities_rejects_non_scalar_or_empty_id(bad_id):
    """P1.2: ``id`` must be a non-bool scalar str/int whose str().strip() is
    non-empty. A complex id like ``[1]`` used to pass list_activities, normalize
    to ``intervals_[1]`` and persist, advancing the cursor. Now it raises so the
    chunk stays dirty (no cursor advance past lost/garbage data)."""
    client = FakeIntervalsClient(lambda method, path, params: [{"id": bad_id}])
    with pytest.raises(IntervalsICUError):
        client.list_activities(date(2026, 7, 1), date(2026, 7, 23))


@pytest.mark.parametrize("good_id", ["i_777", 555111, "  555  "], ids=["str", "int", "padded_str"])
def test_list_activities_accepts_scalar_str_int_id(good_id):
    """A scalar str/int id (padded or not) is accepted by list_activities."""
    client = FakeIntervalsClient(lambda method, path, params: [{"id": good_id}])
    rows = client.list_activities(date(2026, 7, 1), date(2026, 7, 23))
    assert len(rows) == 1


def test_complex_id_keeps_chunk_dirty_and_cursor_unmoved(tmp_path):
    """End-to-end: a payload with ``id=[1]`` marks the chunk dirty via
    list_activities' raise, the cursor does not advance, and no canonical row is
    persisted (no ``intervals_[1]``)."""
    db = Database(str(tmp_path / "complex.db"))
    client = FakeIntervalsClient(lambda method, path, params: [{"id": [1]}])
    result = sync_intervals_data(db, client=client, now=NOW)

    assert result.halted is True
    assert result.warnings
    assert db.get_sync_cursor("intervals", "activities") is None
    assert _ids(db) == set()
    assert "intervals_[1]" not in _ids(db)


# --- P1.3: window_days validated at the generic runner boundary --------------


def _no_fetch(chunk_start, chunk_end):
    raise AssertionError("fetch_chunk must not be called on an invalid window_days")


@pytest.mark.parametrize("bad", [0, -5, 2.5, "ten", True, False], ids=["zero", "negative", "float", "string", "bool_true", "bool_false"])
def test_run_windowed_sync_rejects_invalid_window_days_at_boundary(tmp_path, bad):
    """P1.3: ``window_days`` is validated INSIDE the generic runner (its contract
    says positive int), not only in the adapter wrapper. ``window_days=-5`` used
    to return a FALSE success (start>end → 0 chunks → halted=False, no fetch).
    Now it raises ValueError before any fetch."""
    db = Database(str(tmp_path / "runner-bad.db"))
    with pytest.raises(ValueError):
        run_windowed_sync(
            db,
            "intervals",
            "activities",
            fetch_chunk=_no_fetch,
            now=NOW,
            window_days=bad,  # type: ignore[arg-type]
        )


def test_run_windowed_sync_positive_window_days_gives_exact_window(tmp_path):
    """A positive int window_days yields the exact [now-N, now] historical window
    with bootstrapped=False and a single fetch."""
    db = Database(str(tmp_path / "runner-ok.db"))
    fetched: list = []

    def fetch(chunk_start, chunk_end):
        fetched.append((chunk_start, chunk_end))
        return ChunkFetch(candidates=[], dirty=False)

    result = run_windowed_sync(
        db,
        "intervals",
        "activities",
        fetch_chunk=fetch,
        now=NOW,
        window_days=120,
    )
    assert result.bootstrapped is False
    assert result.window_start == (NOW - timedelta(days=120)).strftime("%Y-%m-%d")
    assert result.window_end == NOW.strftime("%Y-%m-%d")
    assert len(fetched) == 2  # 120 days / 90-day chunks
    assert result.halted is False


# --- P1.4: historical override must validate the saved cursor first -----------
# Codex review: window_days bypassed resolve_window_from_cursor, so a future or
# corrupt persisted cursor was never parsed/checked. A future cursor let the
# historical run fetch from the provider, "succeed", and leave the cursor at the
# future date — so later incremental syncs stayed broken. The override drives the
# START date, but the persisted cursor must still be validated first (symmetry
# with the normal path's fail-closed on future/corrupt cursors).


def test_historical_override_rejects_future_cursor_before_fetch(tmp_path):
    """A future cursor must fail closed BEFORE any provider fetch, even when the
    start date comes from ``window_days`` rather than the cursor. Repro: cursor
    2026-07-30 (after NOW 2026-07-23) used to let the sync fetch, succeed, and
    leave the cursor in the future."""
    db = Database(str(tmp_path / "hist-future.db"))
    db.set_sync_cursor("intervals", "activities", "2026-07-30")  # valid date, ahead of now

    fetch_calls: list = []

    def fetch(chunk_start, chunk_end):
        fetch_calls.append((chunk_start, chunk_end))
        return ChunkFetch(candidates=[], dirty=False)

    with pytest.raises(ValueError, match="ahead of now"):
        run_windowed_sync(
            db,
            "intervals",
            "activities",
            fetch_chunk=fetch,
            now=NOW,
            window_days=120,
        )

    assert fetch_calls == []  # no provider contact on a bad cursor
    # cursor untouched (still the future value, not silently advanced/lowered)
    assert db.get_sync_cursor("intervals", "activities") == "2026-07-30"


def test_historical_override_rejects_corrupt_cursor_before_fetch(tmp_path):
    """A corrupt persisted cursor is caught on the read path even under the
    override, mirroring the non-historical corrupt-cursor gate."""
    db = Database(str(tmp_path / "hist-corrupt.db"))
    conn = sqlite3.connect(db.db_path)
    conn.execute(
        "INSERT INTO sync_cursors (provider, domain, cursor_value) VALUES (?, ?, ?)",
        ("intervals", "activities", "garbage"),
    )
    conn.commit()
    conn.close()

    fetch_calls: list = []

    def fetch(chunk_start, chunk_end):
        fetch_calls.append(1)
        return ChunkFetch(candidates=[], dirty=False)

    with pytest.raises(ValueError):
        run_windowed_sync(
            db,
            "intervals",
            "activities",
            fetch_chunk=fetch,
            now=NOW,
            window_days=120,
        )

    assert fetch_calls == []
    # cursor untouched
    conn = sqlite3.connect(db.db_path)
    val = conn.execute(
        "SELECT cursor_value FROM sync_cursors WHERE provider='intervals' AND domain='activities'"
    ).fetchone()[0]
    conn.close()
    assert val == "garbage"


def test_adapter_historical_override_rejects_future_cursor_end_to_end(tmp_path):
    """End-to-end through the adapter: a future cursor under days=N fails fast
    (no fetch, cursor unchanged) rather than leaving the cursor in the future."""
    db = Database(str(tmp_path / "adapter-future.db"))
    db.set_sync_cursor("intervals", "activities", "2026-07-30")

    responder_calls: list = []

    def responder(method, path, params):
        responder_calls.append(params)
        return []

    client = FakeIntervalsClient(responder)
    with pytest.raises(ValueError, match="ahead of now"):
        sync_intervals_data(db, client=client, now=NOW, days=120)

    assert responder_calls == []  # provider never contacted
    assert db.get_sync_cursor("intervals", "activities") == "2026-07-30"


def test_historical_override_valid_cursor_still_works(tmp_path):
    """Regression: a VALID past cursor under window_days does NOT raise — the
    override processes its exact window (the cursor only happens not to drive the
    start date). This guards against over-eager rejection."""
    db = Database(str(tmp_path / "hist-valid.db"))
    db.set_sync_cursor("intervals", "activities", "2026-07-15")  # valid, before now

    fetched: list = []

    def fetch(chunk_start, chunk_end):
        fetched.append((chunk_start, chunk_end))
        return ChunkFetch(candidates=[], dirty=False)

    result = run_windowed_sync(
        db,
        "intervals",
        "activities",
        fetch_chunk=fetch,
        now=NOW,
        window_days=120,
    )
    assert result.halted is False
    assert len(fetched) == 2  # 120-day override processed
    assert result.window_start == (NOW - timedelta(days=120)).strftime("%Y-%m-%d")
    # monotonic cursor advances to now (>= the prior 2026-07-15)
    assert db.get_sync_cursor("intervals", "activities") == NOW.strftime("%Y-%m-%d")
