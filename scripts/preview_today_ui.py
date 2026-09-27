#!/usr/bin/env python3
"""Run a synthetic Today UI preview. Never starts the product API or opens a DB."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/e2e/fixtures/today_preview"
SCENARIOS = {
    "ordinary": "Обычный день",
    "two": "Две тренировки",
    "brick": "Брик",
    "proposal": "Изменение плана",
    "stale": "Устаревшие данные",
    "missing": "Нет оценки",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=3001)
    parser.add_argument("--web-port", type=int, default=3002)
    parser.add_argument("--api-port", type=int, default=8001)
    args = parser.parse_args()
    if len({args.port, args.web_port, args.api_port}) != 3:
        parser.error("Three distinct ports required")
    payloads = {
        key: json.loads((FIXTURES / f"{key}.json").read_text()) for key in SCENARIOS
    }
    buttons = "".join(
        f'<button data-s="{key}">{label}</button>' for key, label in SCENARIOS.items()
    )
    html = """<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Сегодня · дизайн-пилот</title><style>*{box-sizing:border-box}body{margin:0;background:#0f172a;color:#e2e8f0;font:14px system-ui;height:100dvh;display:flex;flex-direction:column}header{padding:12px 18px;border-bottom:1px solid #475569}p{margin:0 0 10px}nav{display:flex;flex-wrap:wrap;gap:8px}button{font:inherit;padding:8px 12px;border:1px solid #64748b;border-radius:8px;background:#1e293b;color:#e2e8f0;cursor:pointer}button[aria-pressed=true]{background:#1d4ed8;border-color:#93c5fd}iframe{width:100%;border:0;flex:1;min-height:0}</style><header><p><b>Сегодня · дизайн-пилот</b> · Синтетические данные · Сохранение отключено · Рабочий :3000 не изменён</p><nav aria-label="Тестовый сценарий">BUTTONS</nav></header><iframe id="app" title="Экран Сегодня"></iframe><script>function show(s){document.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',b.dataset.s===s));document.getElementById('app').src='http://'+location.hostname+':WEBPORT/today?scenario='+s;history.replaceState(null,'','/?scenario='+s)}document.querySelectorAll('button').forEach(b=>b.onclick=()=>show(b.dataset.s));let s=new URLSearchParams(location.search).get('scenario');show([...document.querySelectorAll('button')].some(b=>b.dataset.s===s)?s:'ordinary')</script></html>""".replace(
        "BUTTONS", buttons
    ).replace("WEBPORT", str(args.web_port))

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, data, mime="application/json"):
            raw = (
                data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
            ).encode()
            self.send_response(status)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.server.server_port == args.port:
                return self.respond(200, html, "text/html")
            path = urlparse(self.path).path
            if path == "/api/today":
                name = parse_qs(urlparse(self.headers.get("Referer", "")).query).get(
                    "scenario", ["ordinary"]
                )[0]
                return self.respond(200, payloads.get(name, payloads["ordinary"]))
            if path == "/api/adherence":
                return self.respond(
                    200, json.loads((FIXTURES / "adherence.json").read_text())
                )
            return self.respond(
                404, {"detail": "Этот раздел не входит в предпросмотр Сегодня."}
            )

        def do_POST(self):
            self.respond(
                409,
                {
                    "detail": "Это предпросмотр на тестовых данных. Сохранение плана отключено."
                },
            )

        do_PUT = do_POST
        do_DELETE = do_POST

    servers = []
    process = None
    stop = threading.Event()
    logs = Path(tempfile.mkdtemp(prefix="today-ui-preview-"))
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        # Fail before starting Next if any requested port is occupied; never kill another service.
        probe = ThreadingHTTPServer(("127.0.0.1", args.web_port), Handler)
        probe.server_close()
        for port in (args.port, args.api_port):
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            servers.append(server)
            threading.Thread(target=server.serve_forever, daemon=True).start()
        with (logs / "next.log").open("w") as log:
            process = subprocess.Popen(
                [
                    "npm",
                    "run",
                    "dev",
                    "--",
                    "-p",
                    str(args.web_port),
                    "-H",
                    "127.0.0.1",
                ],
                cwd=ROOT / "web",
                env={
                    **os.environ,
                    "API_BASE_URL": f"http://127.0.0.1:{args.api_port}",
                    "NEXT_TELEMETRY_DISABLED": "1",
                },
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        print(
            f"Preview http://localhost:{args.port}; pid={os.getpid()}; Next logs: {logs}/next.log",
            flush=True,
        )
        while not stop.wait(1):
            if process.poll() is not None:
                raise RuntimeError(f"Next exited; inspect {logs}/next.log")
    finally:
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        for server in servers:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
