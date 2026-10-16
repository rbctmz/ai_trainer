"""Historical replay must reject code outside its captured implementation pins."""
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

pytestmark = pytest.mark.smoke
ROOT = Path(__file__).resolve().parents[2]
REPLAY = ROOT / "docs/reports/2026-10-15-coach-answer-verification/replay.py"


def test_native_review_replay_rejects_current_unpinned_implementation(tmp_path):
    captured = REPLAY.with_name("offline-replay.json")
    original = captured.read_bytes()
    output = tmp_path / "replayed.json"
    result = subprocess.run([sys.executable, str(REPLAY), str(output)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "implementation" in result.stderr.lower() and "pin" in result.stderr.lower()
    assert not output.exists()
    assert captured.read_bytes() == original
    assert json.loads(original)["base_commit"] == "f1b03ce"


@pytest.mark.parametrize("changed", [None, *range(4)])
def test_replay_guard_accepts_only_a_complete_matching_pin_set(tmp_path, monkeypatch, changed):
    verify = runpy.run_path(str(REPLAY))["_verify_implementation"]
    paths = verify.__globals__["IMPLEMENTATION"]
    pins = {}
    for index, relative in enumerate(paths):
        content = f"captured implementation {index}".encode()
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        pins[relative] = hashlib.sha256(content).hexdigest()
    (tmp_path / "offline-replay.json").write_text(json.dumps({"implementation_sha256": pins}))
    monkeypatch.setitem(verify.__globals__, "ROOT", tmp_path)
    monkeypatch.setitem(verify.__globals__, "__file__", str(tmp_path / "replay.py"))
    if changed is None:
        assert verify() == pins
    else:
        (tmp_path / paths[changed]).write_text("different implementation")
        with pytest.raises(RuntimeError, match="historical pins"):
            verify()
