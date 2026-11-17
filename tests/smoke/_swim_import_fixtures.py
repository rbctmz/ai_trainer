"""Anonymous rich import examples; never read private trainer material."""

import hashlib
from copy import deepcopy
from tests.smoke._swim_program_fixtures import example_program

SOURCE_ID = "44444444-4444-4444-8444-444444444444"
PROGRAM_ID_V2 = "55555555-5555-4555-8555-555555555555"
SOURCE = "Synthetic source: 1000 metres; timed pattern; retain ranges.\n"


def meters(node_id, value, **extra):
    return {
        "kind": "swim",
        "id": node_id,
        "name": "Synthetic swim",
        "quantity": {"kind": "distance", "meters": value},
        **extra,
    }


def rich_program():
    return {
        "schema_version": 2,
        "origin": "trainer_authored",
        "id": PROGRAM_ID_V2,
        "title": "Synthetic rich program",
        "source_id": SOURCE_ID,
        "source_text": SOURCE,
        "source_sha256": hashlib.sha256(SOURCE.encode()).hexdigest(),
        "source_spans": [{"start": 0, "end": len(SOURCE)}],
        "workouts": [
            {
                "id": "one",
                "title": "Pool work",
                "environment": "pool",
                "pool_length_meters": 25,
                "steps": [
                    meters("one.fixed", 1000),
                    {
                        "kind": "group",
                        "id": "one.timed",
                        "name": "Timed cycle",
                        "repeat": {
                            "kind": "time",
                            "seconds": 1800,
                            "finish": "current_cycle",
                        },
                        "steps": [meters("one.crawl", 175), meters("one.legs", 25)],
                    },
                ],
            }
        ],
    }


def exact_program_v2():
    raw = deepcopy(example_program())
    raw["schema_version"] = 2
    raw["source_id"] = SOURCE_ID
    raw["source_sha256"] = hashlib.sha256(raw["source_text"].encode()).hexdigest()
    raw["source_spans"] = [{"start": 0, "end": len(raw["source_text"])}]

    def convert(node):
        node = deepcopy(node)
        if node["kind"] == "swim":
            node["quantity"] = {
                "kind": "distance",
                "meters": node.pop("distance_meters"),
            }
        elif node["kind"] == "group":
            value = node.pop("repetitions")
            node["repeat"] = {
                "kind": "count",
                "count": {"minimum": value, "maximum": value},
            }
            node["steps"] = [convert(x) for x in node["steps"]]
            if "effort" in node:
                node["effort"]["scope"] = "across_repetitions"
        else:
            for key in ("seconds", "breaths"):
                if key in node:
                    value = node[key]
                    node[key] = {"minimum": value, "maximum": value}
        return node

    for workout in raw["workouts"]:
        workout["steps"] = [convert(x) for x in workout["steps"]]
    return raw
