"""Регрессия: сбой setup сохраняет диагностические материалы до очистки времянок.

Хук ``E2E_FAIL_SETUP_AT`` (см. ``tests/e2e/conftest.py``) роняет setup на этапе
``api:demo-seed`` — FastAPI уже запущен (api.log существует), браузера ещё нет.
Проверяется, что в ``logs/e2e/<запуск>/`` появились error.txt, stage.txt с именем
этапа, js-errors.txt и скопированный api.log; временный каталог при этом удалён.
"""

from __future__ import annotations

import os
import shutil

import pytest

pytestmark = pytest.mark.e2e

FAIL_STAGE = "api:demo-seed"


@pytest.fixture(scope="module", autouse=True)
def _force_setup_failure():
    os.environ["E2E_FAIL_SETUP_AT"] = FAIL_STAGE
    yield
    os.environ.pop("E2E_FAIL_SETUP_AT", None)


def test_setup_failure_saves_diagnostics(request, tmp_path) -> None:
    artifacts_root = request.config.rootpath / "logs" / "e2e"
    existing = set(artifacts_root.glob("*")) if artifacts_root.exists() else set()

    with pytest.raises(RuntimeError, match="принудительный сбой setup"):
        request.getfixturevalue("web_stack")

    fresh = set(artifacts_root.glob("*")) - existing
    assert len(fresh) == 1, f"ожидался ровно один новый каталог диагностики: {fresh}"
    run_dir = fresh.pop()
    try:
        assert (run_dir / "stage.txt").read_text(encoding="utf-8") == FAIL_STAGE
        error_text = (run_dir / "error.txt").read_text(encoding="utf-8")
        assert "принудительный сбой setup" in error_text
        assert (run_dir / "api.log").exists() and (run_dir / "api.log").stat().st_size > 0
        assert (run_dir / "js-errors.txt").exists()
        assert not (run_dir / "screenshot.png").exists(), "браузер ещё не создан — снимка быть не должно"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
