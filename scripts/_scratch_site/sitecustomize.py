"""Early audit in children of the isolated test runner; no production import."""
import os
import sys

if os.environ.get("AI_TRAINER_SCRATCH_SCOPE"):
    try:
        from scripts.scratch_runtime import scope_from_environment
        from scripts.scratch_pytest import install_sqlite_guard

        scope = scope_from_environment()
        install_sqlite_guard(scope)
    except Exception:
        # Python otherwise prints a sitecustomize error and continues unguarded.
        sys.stderr.write("scratch_identity_unknown: bootstrap\n")
        os._exit(2)
