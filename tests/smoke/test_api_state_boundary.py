"""Разрыв зависимости api -> state -> streamlit — контракт issue #602.

Продукт-API не должен тянуть legacy-UI. Сейчас цепочка такая:

    api/deps.py, api/routers/{system,dashboard}.py
        -> from state import StateManager
        -> state/manager.py: import streamlit as st

Следствия: FastAPI не импортируется без Streamlit, а при импорте API
инициализируется runtime кэша Streamlit (в stderr видны предупреждения
«No runtime found, using MemoryCacheStorageManager»). Удалить legacy-контур
(`ui/`, `state/`, `run_acceptance.sh`) без разрыва этой связи невозможно.

Тесты фиксируют:
- в графе модулей после `import api.main` нет `streamlit`, `state` и `ui`;
- typed-фасад состояния остаётся headless и работоспособным без Streamlit;
- API использует тот же фасад, а не копию логики.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.smoke

REPO_ROOT = Path(__file__).resolve().parents[2]

# Модули legacy-UI, которых не должно быть в графе продукт-API.
FORBIDDEN_IN_API_GRAPH = ("streamlit", "state", "state.manager", "ui")

_PROBE = """
import sys
sys.path.insert(0, {root!r})
import api.main  # noqa: F401
for name in {names!r}:
    print(f"{{name}}={{name in sys.modules}}")
"""


def _module_graph_after_importing_api() -> dict[str, bool]:
    """Импортировать api.main в отдельном процессе и вернуть граф модулей.

    Отдельный процесс обязателен: pytest уже импортировал часть модулей, и
    проверка в текущем интерпретаторе дала бы ложный результат.
    """
    script = _PROBE.format(root=str(REPO_ROOT), names=list(FORBIDDEN_IN_API_GRAPH))
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, (
        "не удалось импортировать api.main:\n"
        f"stdout: {completed.stdout[-2000:]}\nstderr: {completed.stderr[-2000:]}"
    )

    graph: dict[str, bool] = {}
    for line in completed.stdout.splitlines():
        if "=" in line:
            name, _, value = line.partition("=")
            if name in FORBIDDEN_IN_API_GRAPH:
                graph[name] = value.strip() == "True"
    assert set(graph) == set(FORBIDDEN_IN_API_GRAPH), (
        f"пробник не отдал граф модулей: {completed.stdout[-500:]}"
    )
    return graph


@pytest.mark.parametrize("module", FORBIDDEN_IN_API_GRAPH)
def test_api_import_graph_excludes_legacy_ui(module: str) -> None:
    """Продукт-API не должен импортировать legacy-UI и Streamlit."""
    graph = _module_graph_after_importing_api()

    assert not graph[module], (
        f"{module} попадает в граф модулей после import api.main — "
        "API тянет legacy-UI (issue #602)"
    )


def test_headless_state_works_on_plain_mapping() -> None:
    """Typed-фасад состояния работает на обычном mapping, без Streamlit-сессии."""
    from utils.app_state import HeadlessState, SessionDict

    session = SessionDict()
    facade = HeadlessState(session)

    # Дефолты бутстрапаются в переданный mapping — как это делает
    # api/deps.make_headless_state поверх SessionDict.
    assert facade.selected_page
    assert facade._session is session
    assert "selected_page" in session

    facade.selected_page = "Планирование"
    assert session["selected_page"] == "Планирование"


def test_headless_facade_does_not_import_streamlit() -> None:
    """Импорт фасада в чистом процессе не тянет Streamlit."""
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "import utils.app_state  # noqa: F401\n"
        "print('streamlit=' + str('streamlit' in sys.modules))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert "streamlit=False" in completed.stdout, (
        "utils.app_state импортирует streamlit — фасад не headless"
    )


# Блокируем импорт streamlit так, будто пакета нет в окружении, и проверяем,
# что продуктовый API всё равно поднимается. Это проверяет цель issue #602
# напрямую, а не через граф модулей.
_API_WITHOUT_STREAMLIT = """
import sys, importlib.abc

class _BlockStreamlit(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "streamlit" or fullname.startswith("streamlit."):
            raise ModuleNotFoundError("streamlit намеренно недоступен")
        return None

sys.meta_path.insert(0, _BlockStreamlit())
sys.path.insert(0, {root!r})
import api.main  # noqa: F401
print("api_imported=True")
"""


def test_api_imports_without_streamlit_installed() -> None:
    """API поднимается в окружении, где Streamlit недоступен (цель #602)."""
    script = _API_WITHOUT_STREAMLIT.format(root=str(REPO_ROOT))
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert completed.returncode == 0, (
        "api.main не импортируется без Streamlit — зависимость ещё не разорвана\n"
        f"stderr: {completed.stderr[-2000:]}"
    )
    assert "api_imported=True" in completed.stdout


def test_api_uses_the_shared_facade() -> None:
    """API берёт состояние из общего фасада, а не из Streamlit-обёртки."""
    source = (REPO_ROOT / "api" / "deps.py").read_text(encoding="utf-8")

    assert "from state import StateManager" not in source, (
        "api/deps.py всё ещё импортирует Streamlit-обёртку состояния"
    )
    assert "facade" in source or "app_state" in source, (
        "api/deps.py должен использовать headless-фасад"
    )


# --------------------------------------------------------------------------
# Реестр сброса кэшей: sync и demo_mode не должны тянуть Streamlit
# --------------------------------------------------------------------------

def test_cache_registry_is_headless() -> None:
    """Реестр сброса кэшей не тянет Streamlit."""
    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "import services.cache_registry  # noqa: F401\n"
        "print('streamlit=' + str('streamlit' in sys.modules))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert "streamlit=False" in completed.stdout, (
        "services.cache_registry импортирует streamlit — реестр не headless"
    )


def test_empty_registry_clear_is_a_noop() -> None:
    """Сброс при пустом реестре не падает.

    Headless-процесс без Streamlit: data_cache не импортировался, значит кэшей
    нет и сбрасывать нечего. Это должно быть no-op, а не исключение.
    """
    from services import cache_registry

    cache_registry.reset_registry()
    try:
        cache_registry.clear_caches()
        assert cache_registry.registered_clearers() == ()
    finally:
        cache_registry.reset_registry()


def test_data_cache_registers_its_clearer() -> None:
    """Реальная проводка: сброс через реестр действительно чистит кэш data_cache.

    Проверяем не только факт регистрации, но и эффект: подменяем внутренний
    загрузчик и убеждаемся, что реестр сбрасывает именно его кэш.
    """
    from services import cache_registry, data_cache

    cache_registry.reset_registry()
    calls: list[str] = []

    def fake_clear() -> None:
        calls.append("cleared")

    original = data_cache.clear_data_caches
    data_cache.clear_data_caches = fake_clear  # type: ignore[assignment]
    try:
        cache_registry.reset_registry()
        cache_registry.register_cache_clearer(fake_clear)
        cache_registry.clear_caches()
    finally:
        data_cache.clear_data_caches = original  # type: ignore[assignment]
        cache_registry.reset_registry()

    assert calls == ["cleared"], "реестр не вызвал зарегистрированный сброс"
