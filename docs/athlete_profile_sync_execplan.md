# Sync Athlete Profile (FTP/Weight) From Intervals.icu Instead Of Static Env Vars

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

This document must be maintained in accordance with `.agent/PLANS.md`.

## Purpose / Big Picture

Today the numbers this app uses to judge how hard a bike ride was — specifically FTP, "Functional Threshold Power," the highest average power a rider can sustain for about an hour, used as the yardstick for Training Stress Score (TSS) — come from three plain environment variables (`USER_FTP`, `USER_LTHR`, `USER_MAX_HR`) that a person typed into a `.env` file once and that the app never checks against reality again. This plan was triggered by a concrete, measured failure of that model: for a real ride on 2026-07-04 (Garmin `activity_id=23477418874`, "Петербург - IntervalCoach - Aerobic Build", 140.23 minutes, average power 111W), this app computed `tss=44.9`, while the athlete's actual training tool, IntervalCoach (built on the Intervals.icu platform, `https://intervalcoach.app`), reported `TSS=160` for the exact same ride — a 3.5x discrepancy that went unnoticed for weeks because nothing in this app ever compares its numbers to an external source of truth.

After this change, the app will fetch the athlete's real FTP and body weight from Intervals.icu — a training-analytics service this athlete already uses, which already has a working, authenticated API client in this repository at `services/intervals_icu.py` — and store that profile locally, refreshing it periodically instead of trusting a value someone typed into `.env` and never revisited. A user (or an operator debugging a TSS complaint) will be able to run a sync, then query the new profile table and see the FTP that was actually used to compute TSS for a given activity, when it was fetched, and where it came from (`intervals_icu` or `env_fallback`). The observable, user-facing proof of success is this: after this plan's Milestone 4, recomputing TSS for `activity_id=23477418874` using the synced FTP produces a number close to IntervalCoach's `160`, not the old `44.9`, and this can be shown by running the smoke test added in Milestone 4 and by inspecting the `tss`/`tss_ftp_used` columns for that row after a real or simulated sync.

## Progress

- [x] (2026-07-05, prior investigation session) Root-caused the TSS discrepancy for `activity_id=23477418874` and confirmed, from three independent sources, that the FTP baked into `.env` (`USER_FTP=250`) is wrong. Filed as GitHub issue `#101` (the TSS-formula bug: average power used instead of normalized power) and issue `#102` (this plan's parent issue: the athlete profile should not live in a static env var). See `Surprises & Discoveries` below for the exact numbers.
- [ ] Milestone 1: add `IntervalsICUClient.get_athlete_profile()` plus a pure normalizer function, covered by an isolated smoke test using a fake HTTP response (no network, no code elsewhere touched yet).
- [ ] Milestone 2: add a local `athlete_profile` table to `data/database.py` with a save/read pair, covered by a smoke test against a temporary SQLite file (no network, no other module touched yet).
- [ ] Milestone 3: add `services/intervals_icu.py::sync_athlete_profile(state)` that calls Milestone 1's client method and Milestone 2's save function, with graceful no-op behavior when Intervals.icu is not configured or the call fails.
- [ ] Milestone 4: make `data/data_processor.py`'s TSS resolution and `data/database.py`'s retroactive TSS repair read FTP/LTHR from the synced profile (falling back to the existing `Settings.USER_FTP`/`Settings.USER_LTHR` when no synced profile row exists), and add the end-to-end regression test using the real `activity_id=23477418874` numbers.
- [ ] Milestone 5: wire `sync_athlete_profile(state)` into the place a user actually triggers ("Sync now" flow / `services/sync.py` or the equivalent UI action) so the profile refreshes without a separate manual step, and update `CLAUDE.md`/`docs/` to describe the new data source.

Use timestamps in this list as work proceeds; the entries above with no timestamp have not started yet.

## Surprises & Discoveries

- Observation: the static `.env` FTP value was wrong by a wide margin, and nothing in the app could have caught this on its own.
  Evidence: for `activity_id=23477418874`, `.env` has `USER_FTP=250` (`config/settings.py:66` reads it via `int(os.getenv("USER_FTP", 250))`). Garmin's own per-activity estimate (`functionalThresholdPower` field, returned by the installed `garminconnect` library's `Garmin.get_activity(activity_id)` method, under `summaryDTO`) is `168`. Intervals.icu's athlete profile (fetched live via `GET /api/v1/athlete/{athlete_id}`, the same authenticated call this plan adds a wrapper for) reports `sportSettings[0].ftp = 159` for cycling, plus a model-based `sportSettings[0].mmp_model.ftp = 134` and `criticalPower = 132`. The IntervalCoach web dashboard shows `eFTP = 152W`. All four independent numbers cluster between 130W and 170W; none of them is anywhere near 250W.

- Observation: the average-power-vs-normalized-power bug (issue `#101`) and the FTP bug (this plan, issue `#102`) are separate and additive; fixing only one does not fully close the gap to IntervalCoach.
  Evidence: normalized power (NP) for this ride was computed two independent ways and agreed almost exactly: Garmin's own `normPower` field in the bulk activity-list payload (the same payload `data/data_processor.py` already parses for `avgPower`/`maxPower`) reports `135`, and an independent recomputation from the raw per-second power stream in a Garmin TCX export of this same activity (8427 one-second samples, parsed with the standard "30-second rolling average, raised to the 4th power, averaged, 4th root" formula that already exists but is unused in `utils/metrics.py:normalized_power`) gives `134.6`. Using NP=134.6 with the wrong FTP=250 gives `TSS≈67`, still far from `160`. Using NP=134.6 with the Intervals.icu FTP=159 gives `TSS≈163.3`, matching IntervalCoach's `160` within about 2%.

- Observation: Intervals.icu's REST API already returns everything this plan needs from a single authenticated GET request, with no new library or new credential required.
  Evidence: `services/intervals_icu.py` already defines `IntervalsICUClient` with working basic-auth request plumbing (`_request_json`, using `INTERVALS_ICU_API_KEY`/`INTERVALS_ICU_ATHLETE_ID` already present in `.env`). Calling `client._request_json("GET", f"/api/v1/athlete/{client.athlete_id}")` directly (ad hoc, to verify feasibility before writing this plan) returned a JSON object containing `icu_weight: 93.9` at the top level and a `sportSettings` list, where the entry for cycling (`sportSettings[0]`, the only one with `eFTPSupported: true`) contains `ftp`, `indoor_ftp`, and a nested `mmp_model` object with `ftp` and `criticalPower`.

- Observation: this app already has a precedent for "recompute a stored derived value whenever the input configuration changes," which this plan must extend rather than duplicate.
  Evidence: `data/database.py`'s `_repair_legacy_activity_tss` (around lines 389-441) already re-resolves every stored activity's `tss`/`source_tss`/`garmin_training_load` against `Settings.USER_FTP`/`Settings.USER_LTHR` every time `Database()` is constructed (called from `init_tables()`). This is why a `.env` change today already changes historical TSS values retroactively and silently; this plan's Milestone 4 must plug the new synced FTP into this exact mechanism rather than inventing a second, parallel recompute path.

## Decision Log

- Decision: store the synced profile in a new, small, dedicated table (`athlete_profile`) rather than folding it into an existing table or a generic key-value `user_settings` blob.
  Rationale: FTP/weight/LTHR are a fixed, known, small set of typed fields (not an open-ended bag of settings), and this repo's existing tables (`activities`, `daily_health`, `training_status`) already use the same "small typed table with an additive column-migration helper" shape (see `_ensure_activity_columns`, `_ensure_daily_health_columns` in `data/database.py`). Reusing that established shape keeps the new code idiomatic and easy for the next contributor to recognize.
  Date/Author: 2026-07-05 / Claude (planning session)

- Decision: when Intervals.icu is not configured (`IntervalsICUClient.is_configured()` returns `False`, i.e. `INTERVALS_ICU_API_KEY` is empty) or a sync attempt fails, fall back to the existing static `Settings.USER_FTP`/`USER_LTHR`/`USER_MAX_HR` values exactly as today. Never raise or block a Garmin sync because the athlete-profile sync failed.
  Rationale: many users of this app will not have Intervals.icu configured at all (CLAUDE.md documents it as an optional integration alongside Garmin). The static env vars must remain a working, if potentially stale, fallback so this plan is strictly additive and cannot regress anyone's existing setup.
  Date/Author: 2026-07-05 / Claude (planning session)

- Decision: trigger the profile sync as its own small, independently callable function (`sync_athlete_profile`), not as code woven into `services/sync.py::sync_garmin_data`'s Garmin-specific pipeline, even though Milestone 5 will call it from the same user-facing "sync now" action.
  Rationale: `sync_garmin_data` is explicitly about Garmin data (it raises if `not garmin_service.is_authenticated(state)`) and returns a `GarminSyncResult` shaped entirely around Garmin domains (activities/HRV/sleep/health/training status). Intervals.icu is a separate external system with its own configuration and its own failure modes; keeping its sync function separate means it can be tested, called, and reasoned about on its own, and a future caller (a scheduled job, a settings-page "refresh profile" button, a CLI script) does not need to go through Garmin authentication to use it.
  Date/Author: 2026-07-05 / Claude (planning session)

- Decision: do not attempt to snapshot which FTP value was used per historical activity in this plan's first milestone. Keep the existing retroactive-recompute behavior (every activity's `tss` reflects whatever FTP is current at the time `_repair_legacy_activity_tss` runs), and only add a `tss_ftp_used` column that records the FTP value used the most recent time a given row's TSS was computed, purely as an observability aid.
  Rationale: issue `#102` explicitly flagged "should historical TSS be frozen at the value used when the activity happened, or should it keep tracking the athlete's current FTP" as an open design question, connected to a real risk already recorded in this project's other memory (the Recovery Replan decision log wants falsifiable, non-retroactively-changing numbers). Resolving that question fully (freezing TSS per-activity, or version-stamping every recompute) is a bigger, separate change than "stop trusting a stale env var," and forcing it into this plan would block the concrete, already-diagnosed bug fix on an unrelated design debate. Recording `tss_ftp_used` costs one column and gives the next contributor the evidence needed to make that later decision well.
  Date/Author: 2026-07-05 / Claude (planning session)

## Outcomes & Retrospective

Not started. This section must be filled in as each milestone completes, and a final retrospective written once Milestone 5 lands and the CLAUDE.md/docs update is merged.

## Context and Orientation

This section assumes no prior knowledge of the repository beyond a checkout of it.

`config/settings.py` is a plain class, `Settings`, whose class attributes are read once from environment variables via `os.getenv(...)` at import time. Lines 66-68 define `USER_FTP = int(os.getenv("USER_FTP", 250))`, `USER_LTHR = int(os.getenv("USER_LTHR", 170))`, and `USER_MAX_HR = int(os.getenv("USER_MAX_HR", 185))`. The actual values in this repository's `.env` file (not committed to version control, but present in this developer's checkout) are `USER_FTP=250`, `USER_LTHR=170`, `USER_MAX_HR=185`. "FTP" (Functional Threshold Power) is the highest average cycling power, in watts, a rider can sustain for about one hour; it is the denominator used to turn a ride's power data into a 0-100-ish difficulty score. "LTHR" (Lactate Threshold Heart Rate) is the equivalent concept for heart-rate-based effort scoring, used for runs and rides without a power meter.

`data/data_processor.py` contains `ActivityProcessor`, the class that turns a raw Garmin activity payload into the row eventually stored in the `activities` SQL table. Its static method `_power_tss(duration_minutes, avg_power, ftp)` (around lines 79-84) computes `TSS = duration_hours * (avg_power / ftp) ** 2 * 100` — this is the industry-standard formula, except that it is fed `avg_power` (simple average watts for the whole ride) instead of "normalized power," a smoothed metric that better reflects how hard variable-intensity efforts (with surges and coasting) actually felt; that mismatch is tracked separately as GitHub issue `#101` and is out of scope for this plan, but this plan's Milestone 4 touches the same function's `ftp` parameter, so both fixes will land in the same area of code even though they are logically independent. The broader method `resolve_tss(activity_data, ftp=None, lthr=None)` (roughly lines 210-301) is the single entry point that decides, per sport, which TSS-estimation strategy to use, and it is always called today with `ftp=Settings.USER_FTP` and `lthr=Settings.USER_LTHR` passed in literally by its caller.

`data/database.py` defines the `Database` class, the only place that talks to the local SQLite file (whose path is `Settings.DATABASE_PATH`). Its `_repair_legacy_activity_tss(self, conn)` method (roughly lines 389-441) is called once every time a `Database` object is constructed (via `__init__` → `init_tables()`). It re-runs `ActivityProcessor.resolve_tss(...)` — again with `ftp=Settings.USER_FTP, lthr=Settings.USER_LTHR` — against every row already stored in the `activities` table, and overwrites `tss`/`tss_method`/`source_tss`/`garmin_training_load` if the freshly computed values differ from what is stored. This existing method is why changing `.env`'s `USER_FTP` today already changes historical activity TSS values the next time the app starts — there is no separate migration step to remember.

`services/intervals_icu.py` defines `IntervalsICUClient`, a small dataclass-like client for Intervals.icu (a third-party training-analytics website at `https://intervals.icu`; the athlete in this repository's live data also uses a branded frontend for the same underlying account/data at `https://intervalcoach.app`, referred to throughout this repository's docs and this plan as "IntervalCoach"). The client currently exposes `list_calendars()`, `test_connection()`, `create_event(s)`, and the private `_request_json(method, path, payload=None, params=None)` helper that this plan will reuse: it builds a `GET`/`POST` request against `f"{base_url}{path}"`, adds a Basic-Auth header built from `INTERVALS_ICU_API_KEY`, and raises `IntervalsICUConfigurationError` if `is_configured()` is `False` (i.e., the API key is blank) or `IntervalsICUError` on any HTTP or connection failure. `Settings.INTERVALS_ICU_API_KEY`, `Settings.INTERVALS_ICU_ATHLETE_ID`, and `Settings.INTERVALS_ICU_BASE_URL` are the three relevant env vars (already documented in this repo's root `CLAUDE.md`); `get_client()` at the bottom of `services/intervals_icu.py` builds an `IntervalsICUClient` from those settings, and `is_configured()` (module-level function) reports whether the key is present. Intervals.icu's real REST API exposes an athlete-profile endpoint at `GET /api/v1/athlete/{athlete_id}` (where `{athlete_id}` is the same value as `Settings.INTERVALS_ICU_ATHLETE_ID`, or the literal string `"0"` meaning "the authenticated athlete," which is what this repository's `.env` currently uses) that is not wrapped by any method on `IntervalsICUClient` yet; this plan's Milestone 1 adds that wrapper.

`tests/smoke/test_intervals_icu_service.py` is the existing test file for this module and shows the established mocking pattern: a `_FakeResponse` class with `read()`/`__enter__`/`__exit__` methods, and `monkeypatch.setattr(intervals_icu.urlrequest, "urlopen", fake_urlopen)` to intercept the outbound HTTP call without touching the network. New tests in this plan should follow that exact pattern.

`python -m pytest tests/smoke -q` is this repository's contributor-safe test command (documented in the root `CLAUDE.md`); it must stay green throughout this plan. As of the start of this plan, it reports 349 passed (confirmed 2026-07-05 in the same working tree used to write this plan).

## Plan of Work

Milestone 1 adds, to `services/intervals_icu.py`, a new method `IntervalsICUClient.get_athlete_profile()` that calls `self._request_json("GET", f"/api/v1/athlete/{self.athlete_id}")` and returns the raw parsed JSON dictionary, plus a new module-level pure function `normalize_athlete_profile(raw)` that takes that raw dictionary and returns a small, flat dictionary with exactly the fields this app needs: `ftp` (from `sportSettings[0]["ftp"]`, the cycling entry — cycling is identified as the entry with `"eFTPSupported": True`, not by assuming index 0, because the API does not document index 0 as stable), `weight_kg` (from top-level `icu_weight`), and `lthr` (Intervals.icu's athlete-profile payload does not currently expose lactate-threshold heart rate directly in the fields already observed; if it is absent, `normalize_athlete_profile` must return `None` for `lthr` rather than guessing, and Milestone 4's fallback logic must treat a `None` field as "use the static env default for this one field," not "use the static env default for the whole profile"). Guard every field lookup so a missing or reshaped API response degrades to `None` fields instead of raising, matching the defensive style already used elsewhere in this file (e.g., `is_configured()`).

Milestone 2 adds, to `data/database.py`, a new table `athlete_profile` with one logical row per profile snapshot (do not try to enforce a strict single-row table at the schema level; instead, always keep the most recent row and let `get_athlete_profile()` return the newest one by `synced_at`, mirroring how the rest of this codebase prefers "append and read the latest" over in-place single-row updates when the data is small and infrequent). Columns: `id` (autoincrement primary key), `ftp` (REAL, nullable), `weight_kg` (REAL, nullable), `lthr` (REAL, nullable), `source` (TEXT, e.g. `"intervals_icu"`), `synced_at` (TIMESTAMP, default `CURRENT_TIMESTAMP`). Add `Database.save_athlete_profile(self, profile: dict) -> None` (inserts a new row) and `Database.get_athlete_profile(self) -> dict | None` (selects the most recent row by `synced_at`, returns `None` if the table is empty), following the existing pattern of small, focused methods rather than a generic ORM-style layer. Add table creation to `init_tables()` alongside the other `CREATE TABLE IF NOT EXISTS` statements; no `_ensure_*_columns`-style migration helper is needed for a brand-new table (those helpers exist specifically to add columns to tables that already existed before the column was introduced).

Milestone 3 adds a new function `sync_athlete_profile(database) -> dict` to `services/intervals_icu.py` (taking the local `Database` instance, mirroring how `services/sync.py` already takes `state`/`database` objects rather than reaching for globals). It must: return early with a result like `{"synced": False, "reason": "not_configured"}` if `is_configured()` is `False`; otherwise call `get_client().get_athlete_profile()`, run it through `normalize_athlete_profile(...)`, call `database.save_athlete_profile(...)` with the normalized dict plus `"source": "intervals_icu"`, and return `{"synced": True, "profile": normalized}`; and catch `IntervalsICUError` (and any request-level exception) so a network hiccup here never propagates as an unhandled exception to whatever calls it — return `{"synced": False, "reason": str(exc)}` instead, matching the "never let an optional signal's failure break the main flow" philosophy already established in this codebase's Garmin sync code (see `services/sync.py`'s `_call_optional_client_method` and the surrounding warning-collection pattern, added for a related reason in a prior session's fix to issue `#90`).

Milestone 4 changes two call sites so FTP/LTHR come from the synced profile first, and the static `Settings` values only when no synced profile exists or the relevant field is `None`. First, add a small helper — a module-level function `resolve_athlete_ftp_lthr(database) -> tuple[float, float]` is a reasonable name and location (`data/data_processor.py`, near the top, close to where `Settings` is imported) — that calls `database.get_athlete_profile()`, and returns `(profile["ftp"] or Settings.USER_FTP, profile["lthr"] or Settings.USER_LTHR)` if a profile row exists, else `(Settings.USER_FTP, Settings.USER_LTHR)`. Second, change `data/database.py`'s `_repair_legacy_activity_tss` to call this helper instead of reading `Settings.USER_FTP`/`Settings.USER_LTHR` directly, so the retroactive-recompute behavior documented in `Surprises & Discoveries` picks up the synced value automatically the next time the app starts, exactly as it already does today for `.env` changes. Third, add the `tss_ftp_used` REAL column (nullable) to the `activities` table (an additive migration through the existing `_ensure_activity_columns` helper, the same mechanism used for prior additive columns in this table) and set it whenever `_repair_legacy_activity_tss` writes a new `tss`, so a future reader can see which FTP number produced a given stored TSS without needing to cross-reference the `athlete_profile` table's history.

Milestone 5 wires `sync_athlete_profile(database)` into whatever code path a user actually triggers today to mean "refresh my data" — at the time of writing this plan, that is `services/sync.py::sync_garmin_data(...)`, called from the Streamlit "Sync now" action and/or the `/api/sync` web endpoint (confirm the exact current call site by searching for `sync_garmin_data(` before editing, since this repository is mid-migration from Streamlit to a web stack and the caller may have moved). Call `sync_athlete_profile(state.database)` early in that flow (it is cheap, one HTTP GET, and does not depend on Garmin state), and fold any `{"synced": False, "reason": ...}` result into the existing `warnings` list on the sync result object rather than surfacing it as an error, consistent with how other optional-signal failures are already reported in that result type. Finally, update the root `CLAUDE.md`'s "Environment Variables" section to note that `USER_FTP`/`USER_LTHR` are now defaults used only when Intervals.icu is not configured or has not been synced yet, and add a short paragraph to whichever doc under `docs/` best fits (`docs/activity_tss_semantics_execplan.md` is the closest existing precedent and could gain a "See also" pointer to this plan, or a new short reference doc, whichever keeps `docs/` from duplicating explanations — decide at the time by checking what already exists then).

## Concrete Steps

Work from the repository root:

    cd /Users/gregkisel/Developer/ai_trainer

Confirm the starting state before making changes:

    python -m pytest tests/smoke -q

Expected: all tests pass (349 passed as of 2026-07-05, in this same working tree).

Reproduce the live evidence this plan is based on, to sanity-check the environment still behaves the same way before trusting the plan's numbers (requires `GARMIN_EMAIL`/`GARMIN_PASSWORD` and `INTERVALS_ICU_API_KEY`/`INTERVALS_ICU_ATHLETE_ID` to be set in `.env`, as they already are in this developer's checkout):

    python3 - <<'PY'
    from services import intervals_icu
    client = intervals_icu.get_client()
    profile = client._request_json("GET", f"/api/v1/athlete/{client.athlete_id}")
    cycling = next(s for s in profile["sportSettings"] if s.get("eFTPSupported"))
    print("ftp:", cycling["ftp"], "weight:", profile.get("icu_weight"))
    PY

Expected output (values may drift slightly over time as the athlete's fitness changes; the important thing is that it is nowhere near 250):

    ftp: 159 weight: 93.9

For Milestone 1, add the client method and normalizer to `services/intervals_icu.py`, then add a test to `tests/smoke/test_intervals_icu_service.py` following the existing `_FakeResponse`/`monkeypatch.setattr(intervals_icu.urlrequest, "urlopen", ...)` pattern, asserting that `get_athlete_profile()` calls `GET /api/v1/athlete/{athlete_id}` and that `normalize_athlete_profile(...)` picks the `sportSettings` entry with `eFTPSupported: true` and extracts `ftp`/`weight_kg`. Run:

    python -m pytest tests/smoke/test_intervals_icu_service.py -q

For Milestone 2, add the table and the two `Database` methods, then add a test to a smoke test file (either a new `tests/smoke/test_athlete_profile.py` or alongside existing `data/database.py`-focused tests if a clearly matching file already exists — check first) that creates a `Database(tmp_path/"...db")`, calls `save_athlete_profile({...})`, and asserts `get_athlete_profile()` returns the same values plus a `synced_at` timestamp, and that saving twice returns the newest row from `get_athlete_profile()`. Run:

    python -m pytest tests/smoke -q -k athlete_profile

For Milestone 3, add `sync_athlete_profile` and a test that monkeypatches `is_configured`/the HTTP call to prove both the success path (writes to a fake database double or a real temp `Database`) and the not-configured path (returns `{"synced": False, "reason": "not_configured"}` without touching the database).

For Milestone 4, add the `resolve_athlete_ftp_lthr` helper, change the two call sites, add the `tss_ftp_used` column, and add the end-to-end regression test using this activity's real numbers. A reasonable test shape, extending the existing `tests/smoke/test_activity_tss_reconciliation.py` file (the established home for this kind of test, per its use in the precedent `docs/activity_tss_semantics_execplan.md`):

    def test_bike_power_tss_uses_synced_ftp_not_stale_env_default(tmp_path, monkeypatch):
        database = Database(str(tmp_path / "athlete_profile_tss.db"))
        database.save_athlete_profile({"ftp": 159, "weight_kg": 93.9, "lthr": None, "source": "intervals_icu"})
        # feed an activity payload shaped like the real 2026-07-04 ride, with
        # avg_power=111 (the NP-vs-avg-power bug from issue #101 is out of
        # scope here; this test only proves FTP selection, so it is fine if
        # the resulting number does not yet match IntervalCoach's 160 until
        # #101 is also fixed)
        ...
        assert resolved["tss"] > 60  # old stale FTP=250 produced ~44.9; synced FTP=159 must move it meaningfully higher

Run the full suite after each milestone:

    python -m pytest tests/smoke -q

For Milestone 5, after wiring the call site, perform a real, manual, read-only-in-effect check: trigger a sync in whatever way this repository currently exposes it (Streamlit "Sync now" button via `./run.sh`, or `POST /api/sync` via `./run_web.sh`, depending on which is live at the time), then inspect the `athlete_profile` table's newest row and confirm `synced_at` updated and `ftp` matches what Intervals.icu currently reports.

## Validation and Acceptance

Acceptance is behavioral, not merely "the code compiles."

After Milestone 2, a fresh `Database` in a temp directory must support `save_athlete_profile`/`get_athlete_profile` round-tripping typed floats, and return `None` from `get_athlete_profile()` before anything has ever been saved — this is directly testable and must be shown passing.

After Milestone 3, calling `sync_athlete_profile(database)` against a real, configured Intervals.icu account must result in `database.get_athlete_profile()` returning a row whose `ftp` is in the same ballpark as the value fetched live in the "Concrete Steps" section above (approximately 150-170, not 250), and calling it with `INTERVALS_ICU_API_KEY` temporarily unset (or monkeypatched away in a test) must return `{"synced": False, "reason": "not_configured"}` and leave `get_athlete_profile()` returning whatever it returned before (i.e., it must not silently write a garbage row).

After Milestone 4, recomputing `resolve_tss(...)` for the real `activity_id=23477418874` activity data (average power 111W, duration 140.23 minutes) using the synced FTP=159 rather than the stale env FTP=250 must produce a TSS meaningfully larger than the previously stored `44.9` — the exact target of `160` (IntervalCoach's number) is not required by this plan alone, because closing that gap fully also requires issue `#101`'s normalized-power fix; this plan's acceptance bar is "FTP now comes from a real, checkable source and measurably changes the computed number in the right direction," not "TSS matches IntervalCoach exactly." If both this plan and issue `#101` are implemented together, the combined result must land within about 10% of IntervalCoach's `160` for this specific activity, per the arithmetic already verified in `Surprises & Discoveries`.

The full contributor-safe suite, `python -m pytest tests/smoke -q`, must stay green after every milestone, with the passed-test count increasing by exactly the number of new tests added in that milestone (no test silently skipped or removed).

## Idempotence and Recovery

`save_athlete_profile` always inserts a new row rather than updating in place, so calling it repeatedly (e.g., because a sync ran twice, or a user clicked "sync now" twice) is always safe and never corrupts state; `get_athlete_profile` always resolves to "the newest row," so re-running the sync simply produces a newer, equally valid answer. The new `athlete_profile` table is created with `CREATE TABLE IF NOT EXISTS`, matching every other table in this file, so re-running `init_tables()` (which already happens on every `Database()` construction) is always safe. The `tss_ftp_used` column is added through the existing additive `_ensure_activity_columns` migration helper, which already only adds a column if it is missing, so this step is also safe to re-run. If Milestone 3's sync fails partway (network drops mid-request), no partial row is written, because `save_athlete_profile` is only called after the full response is parsed successfully; the next successful sync simply adds a new, complete row. There is no destructive step anywhere in this plan; nothing needs a backup or a rollback script beyond normal git revert of the relevant commits.

## Artifacts and Notes

Live evidence captured while writing this plan (2026-07-05), from the same working tree, using the already-configured `.env` credentials:

    # Garmin: per-activity summary (via garminconnect's underlying Garmin.get_activity)
    summaryDTO.averagePower = 111.0
    summaryDTO.maxPower = 619.0
    summaryDTO.normalizedPower = 135.0
    summaryDTO.functionalThresholdPower = 168.0

    # Garmin: bulk activity-list payload (via Garmin.get_activities_by_date, the endpoint the real sync path uses)
    avgPower = 111.0
    maxPower = 619.0
    normPower = 135.0

    # Intervals.icu: GET /api/v1/athlete/{athlete_id}
    icu_weight = 93.9
    sportSettings[cycling].ftp = 159
    sportSettings[cycling].mmp_model.ftp = 134
    sportSettings[cycling].mmp_model.criticalPower = 132
    sportSettings[cycling].eFTPSupported = true

    # IntervalCoach web dashboard (screenshot, 90-day Analytics view)
    eFTP = 152 W (trend -9 W)

    # This app's stored value for the same activity, before this plan or #101
    tss = 44.9, tss_method = "power_tss_bike", source_tss = 209.4 (Garmin's own activityTrainingLoad, a different metric entirely, not TSS)

    # Recomputation using the real per-second power stream from a TCX export of this activity (8427 samples at 1 Hz), using the existing but currently-unused utils/metrics.py:normalized_power algorithm
    Normalized Power (recomputed from raw stream) = 134.6, matching Garmin's own normPower field almost exactly.

    # TSS recomputed with each FTP candidate, using NP=134.6 and this ride's actual moving duration (136.75 minutes)
    FTP=250 (stale env default):      TSS ≈ 66-68
    FTP=168 (Garmin auto-estimate):   TSS ≈ 146-150
    FTP=159 (Intervals.icu, sportSettings.ftp): TSS ≈ 163.3   <- matches IntervalCoach's 160 within ~2%
    FTP=152 (IntervalCoach eFTP):     TSS ≈ 179-183

The FTP=159 row is the one to trust operationally (it is the value the athlete has explicitly set/confirmed on Intervals.icu, as opposed to an auto-estimate), and is the reference number Milestone 4's regression test should be written against.

## Interfaces and Dependencies

At the end of this plan, `services/intervals_icu.py` must expose:

    class IntervalsICUClient:
        def get_athlete_profile(self) -> dict: ...

    def normalize_athlete_profile(raw: dict) -> dict:
        # returns {"ftp": float | None, "weight_kg": float | None, "lthr": float | None}
        ...

    def sync_athlete_profile(database) -> dict:
        # returns {"synced": bool, "profile": dict | None, "reason": str | None}
        ...

`data/database.py`'s `Database` class must additionally expose:

    def save_athlete_profile(self, profile: dict) -> None: ...
    def get_athlete_profile(self) -> dict | None: ...

`data/data_processor.py` must additionally expose:

    def resolve_athlete_ftp_lthr(database) -> tuple[float, float]: ...

No existing public function's signature changes in a way that breaks current callers: `resolve_tss(activity_data, ftp=None, lthr=None)` keeps accepting explicit `ftp`/`lthr` arguments exactly as today (callers that already pass `Settings.USER_FTP` directly keep working unchanged); only the two specific call sites named in Milestone 4 (`_repair_legacy_activity_tss`, and the Milestone 5 sync wiring) are changed to source those arguments from `resolve_athlete_ftp_lthr(database)` instead of `Settings` directly.

No new third-party library dependency is introduced. Intervals.icu access reuses the already-vendored, hand-rolled HTTP client in `services/intervals_icu.py` (built on Python's standard-library `urllib`, per that file's existing imports), not a new SDK.

Revision note (2026-07-05): created this ExecPlan from the investigation already recorded on GitHub issues `#101` and `#102`, at the user's request, before any implementation began. Formal tracking issue: `#102`. Issue `#101` (the separate average-power-vs-normalized-power bug) is referenced throughout for context but is explicitly out of scope for this plan's milestones.
