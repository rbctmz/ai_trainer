"""Fail-closed boundary for offline maintenance of an explicitly chosen DB."""
from __future__ import annotations

from pathlib import Path

from config.database_paths import ScratchPathError, assert_disjoint_database_families


def validate_maintenance_target(
    database_path: str | Path | None, *, apply: bool,
    confirmed: bool = False, stopped: bool = False, backup: str | Path | None = None,
) -> Path:
    """Allow owned scratch, or confirmed offline operator writes with matched backup.

    Caller is responsible for stopping writers; the flag is an attestation, not
    process detection. Fingerprints compare all supported logical DB content.
    """
    from scripts import scratch_runtime

    if database_path is None or not str(database_path).strip():
        raise ScratchPathError("operator_confirmation_required", purpose="bootstrap")
    scope = scratch_runtime.scope_from_environment()
    if apply and scope is None and (not confirmed or not stopped or backup is None):
        raise ScratchPathError("operator_confirmation_required", purpose="bootstrap")
    try:
        target = Path(database_path).expanduser()
        if target.is_symlink() or not target.is_file():
            raise FileNotFoundError("database missing or not a regular file")
        target = target.resolve(strict=True)
        if scope is not None:
            if scope.validate_target(target, purpose="bootstrap") is None:
                raise ScratchPathError("scratch_target_unowned", purpose="bootstrap")
        elif apply:
            from scripts.sqlite_backup_restore import inspect_relocation_database
            backup_path = Path(backup).expanduser()
            if backup_path.is_symlink() or not backup_path.is_file():
                raise ScratchPathError("operator_confirmation_required", purpose="bootstrap")
            backup_path = backup_path.resolve(strict=True)
            assert_disjoint_database_families(target, [backup_path])
            if inspect_relocation_database(target) != inspect_relocation_database(backup_path):
                raise ScratchPathError("operator_confirmation_required", purpose="bootstrap")
        return target
    except ScratchPathError:
        raise
    except FileNotFoundError:
        raise
    except Exception:
        raise ScratchPathError("scratch_identity_unknown", purpose="bootstrap") from None
