"""Scenario failures must retain synthetic diagnostics before fixture cleanup."""
from pathlib import Path
import os
import subprocess
import sys
import textwrap

import pytest

from scripts.scratch_pytest import fresh_child_environment

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('outcome', ['failed', 'passed', 'diagnostic_failure'])
def test_e2e_call_report_captures_failure_without_masking_it(tmp_path, outcome):
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'pytest.ini').write_text('[pytest]\nmarkers = e2e: synthetic harness probe\n')
    (project / 'conftest.py').write_text(textwrap.dedent('''
        from pathlib import Path
        import shutil
        import pytest
        from scripts.scratch_pytest import bootstrap_pytest
        from tests.e2e import conftest as harness
        pytest_plugins = ['tests.e2e.conftest']
        scope = bootstrap_pytest()
        harness.ARTIFACTS_ROOT = Path(__file__).parent / 'artifacts'
        class Page:
            url = 'http://127.0.0.1/synthetic-planning'
            def screenshot(self, *, path, full_page):
                Path(path).write_bytes(b'synthetic screenshot')
        @pytest.fixture
        def web_stack():
            runtime = scope.root / 'scenario-runtime'
            runtime.mkdir()
            api, next_log = runtime / 'api.log', runtime / 'next.log'
            api.write_text('synthetic API error details')
            next_log.write_text('synthetic Next log')
            stack = harness.WebStack('http://127.0.0.1', 'http://127.0.0.1',
                runtime, api, next_log, Page(), ['synthetic browser error'])
            yield stack
            shutil.rmtree(runtime)
            (Path(__file__).parent / 'cleaned').write_text('yes')
    '''))
    (project / 'test_probe.py').write_text(textwrap.dedent(f'''
        import pytest
        pytestmark = pytest.mark.e2e
        def test_scenario(web_stack):
            if {outcome == 'diagnostic_failure'!r}:
                def fail(**_kwargs):
                    raise OSError('synthetic diagnostics unavailable')
                web_stack.capture_failure = fail
            assert {outcome == 'passed'!r}, 'original synthetic scenario failure'
    '''))
    env = fresh_child_environment({'PATH': os.defpath, 'PYTHONPATH': str(ROOT),
        'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTHONDONTWRITEBYTECODE': '1'})
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/run_isolated_tests.py'),
        '-m', 'e2e', '-q', '--tb=short'], cwd=project, env=env,
        capture_output=True, text=True, timeout=30)
    assert result.returncode == (0 if outcome == 'passed' else 1), result.stdout + result.stderr
    assert (project / 'cleaned').read_text() == 'yes'
    runs = list((project / 'artifacts').glob('*'))
    if outcome == 'failed':
        assert len(runs) == 1, result.stdout + result.stderr
        run = runs[0]
        assert (run / 'api.log').read_text() == 'synthetic API error details'
        assert (run / 'next.log').read_text() == 'synthetic Next log'
        assert (run / 'stage.txt').read_text() == 'сценарий'
        assert 'original synthetic scenario failure' in (run / 'error.txt').read_text()
        assert (run / 'screenshot.png').exists()
        assert 'synthetic browser error' in (run / 'js-errors.txt').read_text()
        assert (run / 'url.txt').read_text() == 'http://127.0.0.1/synthetic-planning'
    else:
        assert not runs
    if outcome != 'passed':
        assert 'original synthetic scenario failure' in result.stdout
    if outcome == 'diagnostic_failure':
        assert 'synthetic diagnostics unavailable' in result.stdout
