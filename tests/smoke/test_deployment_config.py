"""Security and runtime guardrails for the self-hosted Docker topology."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"

if not COMPOSE_PATH.exists():
    pytest.skip(
        "self-hosted deployment config is not present in this checkout",
        allow_module_level=True,
    )


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _non_comment_lines(relative_path: str) -> set[str]:
    return {
        line.strip()
        for line in _read(relative_path).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_backend_build_context_excludes_secrets_and_personal_data() -> None:
    ignored = _non_comment_lines(".dockerignore")

    assert ".env" in ignored, ".env secrets must never enter the backend image"
    assert "*.db" in ignored, "personal SQLite databases must never enter the image"


def test_backend_runs_as_one_process_without_copying_env_file() -> None:
    dockerfile = _read("Dockerfile.api")

    assert "COPY .env" not in dockerfile, ".env must be injected only at container runtime"
    assert "--workers" not in dockerfile, (
        "multiple uvicorn workers would split process-local sync state and database caches"
    )


def test_compose_keeps_application_ports_private_and_database_persistent() -> None:
    compose = _read("docker-compose.yml")
    published_app_port = re.compile(
        r'^\s*-\s*["\']?[^\n#]*:(?:8000|3000)["\']?\s*$',
        re.MULTILINE,
    )

    assert not published_app_port.search(compose), (
        "FastAPI and Next.js ports must stay private behind the authenticated edge"
    )
    assert "DATABASE_PATH: /data/ai_trainer.db" in compose, (
        "SQLite must use the persistent /data volume rather than the container filesystem"
    )
    assert "ai_trainer_data:/data" in compose, (
        "the API service must mount the named data volume at /data"
    )


def test_edge_routes_api_directly_inside_compose_network() -> None:
    compose = _read("docker-compose.yml")
    caddyfile = _read("deploy/Caddyfile")
    dockerfile = _read("web/Dockerfile")

    assert "API_BASE_URL:" not in compose, (
        "Compose must not advertise a runtime Next rewrite that Next.js bakes at build time"
    )
    assert "handle /api/*" in caddyfile, (
        "the authenticated edge must route same-origin API calls separately"
    )
    assert "reverse_proxy api:8000" in caddyfile, (
        "API traffic must reach the private FastAPI service over Compose DNS"
    )
    assert "next.config.mjs" in dockerfile, (
        "the runtime image must retain the repository's production Next configuration"
    )
    assert "standalone" not in dockerfile, (
        "standalone output would freeze the API proxy target at image build time"
    )


def test_caddy_authenticates_every_request_without_short_upstream_timeout() -> None:
    compose = _read("docker-compose.yml")
    caddyfile = _read("deploy/Caddyfile")

    assert "SITE_ADDRESS: ${DOMAIN:-:8080}" in compose, (
        "an empty DOMAIN must resolve to the explicit local HTTP listener :8080"
    )
    assert "{$SITE_ADDRESS}" in caddyfile, (
        "Caddy must consume the already-resolved site address from Compose"
    )
    assert "basic_auth" in caddyfile, (
        "the only host-facing service must reject unauthenticated requests"
    )
    assert "reverse_proxy web:3000" in caddyfile, (
        "the authenticated edge must forward requests only to the web service"
    )
    assert "response_header_timeout" not in caddyfile, (
        "the edge must not terminate long-running Garmin sync requests prematurely"
    )
