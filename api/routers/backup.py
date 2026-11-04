"""Server-selected backup checks; sync handlers run outside the event loop."""
from fastapi import APIRouter, Depends, Query
from api.backup_contract import BackupCheckRequest, BackupStatus
from api.deps import get_database
from data.database import Database
from config.settings import Settings
from services.snapshot_runtime import backup_status, get_runtime

router = APIRouter(prefix='/api/backup', tags=['backup'])


def get_backup_database(demo: bool = Query(False)) -> Database | None:
    if demo or not Settings.AUTO_BACKUP_ENABLED or Settings.ACCEPTANCE_MODE:
        return None  # Disabled status must not initialize/migrate a source store.
    return get_database(demo=False)


@router.get('/status', response_model=BackupStatus)
def status(demo: bool = Query(False), db: Database | None = Depends(get_backup_database)) -> dict:
    return backup_status(db, demo=demo)


@router.post('/check', response_model=BackupStatus)
def check(_request: BackupCheckRequest | None = None, demo: bool = Query(False), db: Database | None = Depends(get_backup_database)) -> dict:
    if db is None:
        return backup_status(db, demo=demo)
    return get_runtime(db).check('manual_retry')
