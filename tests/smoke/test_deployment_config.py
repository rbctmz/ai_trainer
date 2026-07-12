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


def test_web_proxy_target_is_runtime_configured_inside_compose_network() -> None:
    compose = _read("docker-compose.yml")
    dockerfile = _read("web/Dockerfile")

    assert "API_BASE_URL: http://api:8000" in compose, (
        "Next.js must proxy API calls to the private Compose service"
    )
    assert "next.config.mjs" in dockerfile, (
        "the runtime image must retain Next config so API_BASE_URL is resolved at startup"
    )
    assert "standalone" not in dockerfile, (
        "standalone output would freeze the API proxy target at image build time"
    )


def test_caddy_authenticates_every_request_without_short_upstream_timeout() -> None:
    caddyfile = _read("deploy/Caddyfile")

    assert "basic_auth" in caddyfile, (
        "the only host-facing service must reject unauthenticated requests"
    )
    assert "reverse_proxy web:3000" in caddyfile, (
        "the authenticated edge must forward requests only to the web service"
    )
    assert "response_header_timeout" not in caddyfile, (
        "the edge must not terminate long-running Garmin sync requests prematurely"
    )
