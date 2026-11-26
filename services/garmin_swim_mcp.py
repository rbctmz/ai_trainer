"""Local, typed bridge into the Garmin AI Trainer draft gateway."""

import asyncio
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Literal

from config.settings import Settings

Action = Literal["preview_swim_workout", "get_swim_workout_draft", "send_swim_workout"]
_ACTIONS = {"preview_swim_workout", "get_swim_workout_draft", "send_swim_workout"}
_ENV = {"HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR",
        "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "NO_PROXY"}


class GarminSwimBridgeError(RuntimeError):
    """Sanitized failure. An attempted send might have reached Garmin."""


def configured_script() -> Path | None:
    value = Settings.GARMIN_SWIM_MCP_SCRIPT.strip()
    script = Path(value)
    if value and script.is_absolute() and script.name == "readonly_proxy.py" and script.is_file():
        return script
    return None


def call(action: Action, arguments: dict) -> dict:
    script = configured_script()
    if script is None or action not in _ACTIONS:
        raise GarminSwimBridgeError("Garmin swim gateway unavailable")
    env = {name: value for name, value in os.environ.items() if name in _ENV}
    try:
        response = subprocess.run(
            [sys.executable, str(script), "--swim-delivery"],
            input=json.dumps({"name": action, "arguments": arguments}, ensure_ascii=False),
            capture_output=True, encoding="utf-8", timeout=65 if action == "send_swim_workout" else 8,
            env=env, check=True,
        )
        result = json.loads(response.stdout)["result"]
        if not isinstance(result, dict):
            raise ValueError("bad result")
        return result
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError):
        raise GarminSwimBridgeError("Garmin swim gateway could not complete the action") from None


def scheduled_on(workout_id: int, day: str) -> bool:
    """Verify one workout against an independent exact-day Garmin calendar read."""
    script = configured_script()
    try:
        if script is None or type(workout_id) is not int or workout_id <= 0 or date.fromisoformat(day).isoformat() != day:
            return False
        return asyncio.run(_read_day(script, workout_id, day))
    except (OSError, RuntimeError, TimeoutError, ValueError, KeyError, TypeError):
        return False


async def _read_day(script: Path, workout_id: int, day: str) -> bool:
    process = await asyncio.create_subprocess_exec(
        sys.executable, str(script), stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        env={name: value for name, value in os.environ.items() if name in _ENV},
    )
    assert process.stdin is not None and process.stdout is not None

    async def send(method: str, params: dict, request_id: int | None = None) -> object:
        message = {"jsonrpc": "2.0", "method": method, "params": params}
        if request_id is not None:
            message["id"] = request_id
        process.stdin.write((json.dumps(message) + "\n").encode())
        await process.stdin.drain()
        if request_id is None:
            return None
        while line := await process.stdout.readline():
            reply = json.loads(line)
            if reply.get("id") == request_id:
                return reply["result"]
        raise ValueError("Garmin terminated without a result")

    try:
        async with asyncio.timeout(12):
            await send("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                     "clientInfo": {"name": "AI Trainer", "version": "1"}}, 1)
            await send("notifications/initialized", {})
            result = await send("tools/call", {"name": "get_scheduled_workouts",
                                                "arguments": {"start_date": day, "end_date": day}}, 2)
        return _verify_day(result, workout_id, day)
    finally:
        process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), timeout=2)
        except TimeoutError:
            if process.returncode is None:
                process.kill()
            await process.wait()


def _verify_day(result: object, workout_id: int, day: str) -> bool:
    if not isinstance(result, dict) or result.get("isError") or not isinstance(result.get("content"), list):
        return False
    matches = 0
    for block in result["content"]:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        try:
            data = json.loads(block["text"])
        except (ValueError, KeyError, TypeError):
            continue
        matches += sum(isinstance(item, dict) and item.get("workoutId") == workout_id
                       and item.get("scheduleDate") == day
                       for item in (data if isinstance(data, list) else [data]))
    return matches == 1
