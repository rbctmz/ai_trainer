import os
import socket
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
RUN_WEB = ROOT / "run_web.sh"


def _run_web_with_ports(api_port: str, web_port: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["API_PORT"] = api_port
    env["WEB_PORT"] = web_port
    return subprocess.run(
        [str(RUN_WEB)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
    )


def test_run_web_rejects_invalid_api_port_before_startup() -> None:
    result = _run_web_with_ports("not-a-port", "3000")

    assert result.returncode == 1
    assert "API_PORT must be a TCP port" in result.stdout
    assert "Starting FastAPI" not in result.stdout
    assert "Installing/юстируем web dependencies" not in result.stdout


def test_run_web_rejects_same_api_and_web_port_before_startup() -> None:
    result = _run_web_with_ports("3010", "3010")

    assert result.returncode == 1
    assert "API_PORT and WEB_PORT must be different" in result.stdout
    assert "Starting FastAPI" not in result.stdout
    assert "Installing/юстируем web dependencies" not in result.stdout


def test_run_web_rejects_busy_api_port_before_startup() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", 0))
        except PermissionError:
            pytest.skip("environment does not allow opening a local listening socket")
        sock.listen()
        busy_port = sock.getsockname()[1]

        result = _run_web_with_ports(str(busy_port), str(busy_port + 1))

    assert result.returncode == 1
    assert f"API port :{busy_port} is already in use" in result.stdout
    assert "API_PORT=" in result.stdout
    assert "WEB_PORT=" in result.stdout
    assert "Starting FastAPI" not in result.stdout
    assert "Installing/юстируем web dependencies" not in result.stdout
