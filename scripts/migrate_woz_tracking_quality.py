"""Add the Issue D quality-rating column to a local ignored WoZ CSV."""
from __future__ import annotations

import csv
import os
from pathlib import Path
import tempfile


QUALITY_COLUMN = "качество_сессии_1_5"
REACTION_COLUMN = "реакция_1_5"
NOTE_COLUMN = "заметка"


def migrate(path: str | Path = "docs/woz_tracking.csv") -> bool:
    """Migrate atomically; return False when the schema is already current."""
    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8", newline="") as source:
        rows = list(csv.reader(source))
    if not rows:
        raise ValueError("WoZ tracking CSV is empty")
    header = list(rows[0])
    if QUALITY_COLUMN in header:
        return False
    if REACTION_COLUMN not in header or NOTE_COLUMN not in header:
        raise ValueError("WoZ tracking CSV does not match the legacy schema")
    reaction_index = header.index(REACTION_COLUMN)
    note_index = header.index(NOTE_COLUMN)
    if note_index != reaction_index + 1:
        raise ValueError("reaction and note columns are not adjacent")

    migrated = [header[:reaction_index] + [QUALITY_COLUMN] + header[reaction_index:]]
    expected = len(header)
    for line_number, raw in enumerate(rows[1:], start=2):
        row = list(raw)
        if len(row) == expected - 1:
            # Historical hand-written rows sometimes omitted the empty reaction field.
            row.insert(reaction_index, "")
        if len(row) != expected:
            raise ValueError(f"row {line_number} has {len(row)} fields; expected {expected}")
        migrated.append(row[:reaction_index] + [""] + row[reaction_index:])

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{csv_path.name}.", dir=csv_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as target:
            csv.writer(target).writerows(migrated)
        os.replace(temp_name, csv_path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
    return True


if __name__ == "__main__":
    changed = migrate()
    print("migrated" if changed else "already current")
