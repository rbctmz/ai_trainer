"""Dated, read-only observations for API and Coach; no readiness arithmetic."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from config.settings import Settings
from data.database import Database
from models.subjective_wellness import MAPPING_VERSION, SCALES


def build_subjective_wellness(db: Database, *, as_of: date | None = None) -> dict[str, Any]:
    """Read latest provider day without carrying answers across dates."""
    result: dict[str, Any] = {
        'status': 'missing', 'source': 'intervals', 'date': None,
        'age_days': None, 'provider_updated_at': None, 'received_at': None,
        'mapping_version': MAPPING_VERSION, 'items': [],
        'answered_current_keys': [],
    }
    try:
        anchor = as_of or datetime.now(ZoneInfo(Settings.ATHLETE_TIMEZONE)).date()
        row = db.get_subjective_wellness(anchor.isoformat())
    except Exception:
        return {**result, 'status': 'unavailable'}
    if row is None:
        return result
    age = (anchor - date.fromisoformat(row['date'])).days
    fields = row['observation']['fields']
    items = []
    for key, (label, values) in SCALES.items():
        field = fields[key]
        value = field['value']
        state = field['state']
        items.append({
            'key': key, 'label': label, 'value': value, 'state': state,
            'value_label': values[value - 1] if state == 'present' else (
                'Неизвестное значение источника' if state == 'invalid' else 'Нет ответа'
            ),
        })
    present = [item['key'] for item in items if item['state'] == 'present']
    return {
        **result, 'status': ('current' if age == 0 else 'stale') if present else 'missing',
        'date': row['date'], 'age_days': age, 'items': items,
        'mapping_version': row['observation']['mapping_version'],
        'provider_updated_at': row['observation']['provider_updated_at'],
        'received_at': row['received_at'],
        'answered_current_keys': present if age == 0 else [],
    }
