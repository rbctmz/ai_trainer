"""Anonymous series with no athlete dates, identities or original coach text."""
from copy import deepcopy

PROGRAM_ID = "11111111-1111-4111-8111-111111111111"


def swim(node_id, metres, **extra):
    return {"kind": "swim", "id": node_id, "name": "Synthetic swim", "distance_meters": metres, **extra}


def rest(node_id, mode="open", **extra):
    return {"kind": "rest", "id": node_id, "mode": mode, "instructions": "Synthetic rest", **extra}


def group(node_id, repetitions, steps, **extra):
    return {"kind": "group", "id": node_id, "name": "Synthetic group", "repetitions": repetitions,
            "steps": steps, "last_rest": "unspecified", **extra}


def example_program():
    return {
        "schema_version": 1, "origin": "trainer_authored", "id": PROGRAM_ID,
        "title": "Synthetic swim program", "source_text": "Synthetic author source\n\n  preserve whitespace  \n",
        "source_week_label": "Example block", "source_label": "Synthetic author",
        "workouts": [
            {"id": "one", "title": "Example one", "environment": "pool", "pool_length_meters": 25,
             "steps": [swim("one.warm", 500, equipment=["fins"]), swim("one.drill", 300), swim("one.easy", 100),
                       group("one.main", 4, [swim("one.50", 50), rest("one.rest50", "fixed", seconds=50),
                            swim("one.100", 100), rest("one.rest60", "fixed", seconds=60), swim("one.150", 150),
                            rest("one.open")], instructions="Equal pace within each round"), swim("one.end", 100)]},
            {"id": "two", "title": "Example two", "environment": "pool", "pool_length_meters": 25,
             "steps": [swim("two.warm", 300), swim("two.drill", 300),
                       swim("two.buoy", 400, equipment=["pull_buoy"], instructions="Buoy at ankles"),
                       group("two.main", 3, [swim("two.100a", 100), swim("two.100b", 100),
                            swim("two.100c", 100, instructions="Higher subjective effort"),
                            rest("two.rest", "fixed", seconds=120)]), swim("two.end", 100)]},
            {"id": "three", "title": "Example three", "environment": "pool", "pool_length_meters": 25,
             "steps": [group("three.warm", 4, [swim("three.50", 50, stroke="drill"), swim("three.25", 25, stroke="backstroke")]),
                       swim("three.drill", 600, equipment=["fins"]), swim("three.easy", 100),
                       group("three.rounds", 4, [group("three.reps", 3, [swim("three.rep", 50),
                            rest("three.breaths", breaths=3)],
                            effort={"kind": "subjective", "start_percent": 50, "end_percent": 90}),
                            rest("three.round_rest", "approximate", seconds=120)]),
                       swim("three.end", 300, stroke="butterfly", equipment=["fins"], instructions="Kick drill")]}],
    }


def changed_program():
    program = deepcopy(example_program())
    program["title"] = "Explicit new version"
    return program
