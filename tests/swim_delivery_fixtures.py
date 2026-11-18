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
