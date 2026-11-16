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


class CloudBackupStatus(BaseModel):
    """Public cloud health; never expose repository paths, IDs or secrets."""
    model_config = ConfigDict(extra='forbid')
    state: Literal['disabled', 'unknown', 'ready', 'stale', 'degraded']
    last_attempt_at: str | None
    last_verified_at: str | None
    last_covered_check_at: str | None
    last_drill_at: str | None
    reason_code: Literal['cloud_busy', 'cloud_config_invalid', 'cloud_identity_unknown',
                         'cloud_snapshot_invalid', 'cloud_credentials_unavailable',
                         'cloud_auth_failed', 'cloud_network_failed', 'cloud_timeout',
                         'cloud_state_unwritable', 'cloud_local_backup_unavailable'] | None
    drill_warning: Literal['cloud_drill_due', 'cloud_drill_failed'] | None


class BackupMutationResponse(BaseModel):
    """Preserve existing domain payloads while validating additive backup health."""
    model_config = ConfigDict(extra='allow')
    backup: BackupStatus
