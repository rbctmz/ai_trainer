"""Additive, path-free automatic-backup contract shared by API envelopes."""
from typing import Literal
from pydantic import BaseModel, ConfigDict


class BackupStatus(BaseModel):
    model_config = ConfigDict(extra='forbid')
    state: Literal['disabled', 'unknown', 'ready', 'degraded']
    last_checked_at: str | None
    last_snapshot_at: str | None
    last_snapshot_id: str | None
    reason_code: Literal['backup_busy', 'backup_timeout', 'backup_io_error',
                         'backup_integrity_failed', 'backup_identity_unknown',
                         'backup_state_unwritable', 'backup_retention_failed',
                         'backup_reset_pins_unknown'] | None


class BackupCheckRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')


class BackupMutationResponse(BaseModel):
    """Preserve existing domain payloads while validating additive backup health."""
    model_config = ConfigDict(extra='allow')
    backup: BackupStatus
