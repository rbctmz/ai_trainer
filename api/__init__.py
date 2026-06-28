"""FastAPI layer over the existing AI Trainer business logic.

This package is a thin HTTP boundary. It must NOT contain training logic:
metrics, planning, HRV, and AI all live in ``models/``, ``data/`` and
``services/`` and are reused as-is. Routers translate those functions into
JSON for the Next.js frontend (see ``docs/SPEC_WEB_MIGRATION.md``).
"""
