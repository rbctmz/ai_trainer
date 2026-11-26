"""Synthetic Intervals transport used by controlled provider acceptance."""

class IntervalsSandbox:
    def __init__(self):
        self.events = []
        self.creates = 0
        self.lose_response = False
        self.mismatch = False

    def is_configured(self):
        return True

    def list_workout_events(self, oldest, newest, *, strict):
        assert strict and oldest == newest
        return [event for event in self.events if event["start_date_local"][:10] == oldest.isoformat()]

    def get_workout_event(self, event_id):
        return next(event for event in self.events if event["id"] == event_id)

    def create_event(self, payload):
        import re
        from services.intervals_icu import IntervalsICUError

        self.creates += 1
        rows = []
        pattern = re.compile(r"- (?P<cue>.+) (?P<amount>\d+)(?P<unit>mtr|s) intensity=(?P<role>active|rest)(?P<lap> Press lap)?$")
        for line in payload["description"].splitlines()[2:]:
            matched = pattern.fullmatch(line)
            assert matched, line
            row = {"text": matched["cue"], "intensity": matched["role"]}
            row["distance" if matched["unit"] == "mtr" else "duration"] = int(matched["amount"])
            if matched["lap"]:
                row["until_lap_press"] = True
            rows.append(row)
        if self.mismatch:
            rows[0]["distance"] -= 25
        record = {
            **payload,
            "id": 100 + self.creates,
            "workout_doc": {
                "options": {"pool_length": "25m"}, "steps": rows,
                "distance": sum(row.get("distance", 0) for row in rows),
            },
        }
        self.events.append(record)
        if self.lose_response:
            raise IntervalsICUError("simulated acknowledgement loss")
        return record


def garmin_repeat_program():
    from tests.smoke._swim_program_fixtures import example_program, group, rest, swim

    program = example_program()
    program["workouts"][0]["steps"] = [
        group("repeat", 2, [swim("technique", 25, stroke="drill", equipment=["fins"]),
                            rest("timed", "fixed", seconds=30)], last_rest="omit"),
        swim("cooldown", 25),
    ]
    return program


class GarminSandbox:
    def __init__(self):
        self.previews = {}
        self.results = {}
        self.calls = []
        self.lose_response = False
        self.hide_result = False
        self.defer_calendar = False

    def call(self, action, arguments):
        from uuid import uuid4
        from services.garmin_swim_mcp import GarminSwimBridgeError

        self.calls.append(action)
        if action == "preview_swim_workout":
            draft_id = "swim-" + uuid4().hex[:24]
            spec = arguments["spec"]
            assert spec["steps"][0]["repetitions"] == 2 and spec["steps"][0]["skip_last_rest"]
            draft = {**spec, "draft_id": draft_id, "confirmation_phrase": f"ОТПРАВИТЬ {draft_id}",
                     "payload_sha256": "a" * 64, "explicit_distance_meters": 75,
                     "fixed_rest_count": 1, "fixed_rest_seconds": 30}
            self.previews[draft_id] = draft
            return draft
        draft = self.previews[arguments["draft_id"]]
        if action == "send_swim_workout":
            assert arguments["confirmation"] == draft["confirmation_phrase"]
            assert draft["draft_id"] not in self.results, "Garmin received a second send"
            result = {"status": "uploaded", "name": draft["name"], "workout_id": 123,
                      "readback_verified": True, "calendar_scheduled": not self.defer_calendar,
                      "schedule_status": "sent_readback_unverified" if self.defer_calendar else "verified",
                      "schedule_date": draft["schedule_date"]}
            self.results[draft["draft_id"]] = result
            if self.lose_response:
                raise GarminSwimBridgeError("response lost")
            return result
        assert action == "get_swim_workout_draft"
        if self.hide_result:
            raise GarminSwimBridgeError("readback unavailable")
        return {**draft, "status": "uploaded", "result": self.results.get(draft["draft_id"])}

    def scheduled_on(self, workout_id, day):
        return any(item["workout_id"] == workout_id and item["schedule_date"] == day for item in self.results.values())
