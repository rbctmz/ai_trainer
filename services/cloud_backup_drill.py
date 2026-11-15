"""Read domain evidence from a validated, disposable restored database only."""
from contextlib import closing
from pathlib import Path

from data.database import Database
from services.sqlite_snapshot_core import readonly_connection


class _DrillReader(Database):
    def _connect(self):
        connection = readonly_connection(Path(self.db_path))
        connection.execute('PRAGMA query_only=ON')
        connection.execute('PRAGMA trusted_schema=OFF')
        connection.execute('PRAGMA busy_timeout=0')
        return connection


def verify_domains(path: Path) -> None:
    """Exercise actual persisted-domain readers, including historical identities.

    Whole-table typed fingerprints are checked before this call. Empty domains
    are valid; an unsupported/malformed schema or unreadable record is refused.
    No Settings path selection, migration, reset or provider call occurs here.
    """
    reader = _DrillReader(str(path), initialize=False)
    with closing(reader._connect()) as connection:
        for table, method in (
            ('planning_checkpoints', reader.get_planning_checkpoint),
            ('plan_actual_matches', reader.get_plan_actual_match),
            ('session_feedback', reader.get_session_feedback),
        ):
            for row in connection.execute(f'SELECT id FROM {table}'):
                recovered = method(row[0])
                if not recovered or recovered['id'] != row[0]:
                    raise ValueError('unreadable restored domain')
        reader.get_current_planning_checkpoint()
        reader.get_readiness_snapshots()
        reader.get_coach_decisions(days=36500, limit=100)
        # Provider/manual identities and raw JSON are covered without rewriting
        # by manifest fingerprints; these queries also require their schema.
        connection.execute('SELECT provider,provider_activity_id,provider_payload FROM activity_provider_links').fetchall()
        connection.execute('SELECT intervals_activity_id,garmin_activity_id,reason FROM activity_manual_links').fetchall()
