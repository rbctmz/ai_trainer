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

# ---------------------------------------------------------------------------
# AC4: набор атрибутов состояния, который API действительно читает
# ---------------------------------------------------------------------------

# Набор снят ПРОБНИКОМ, а не grep-ом, как требует AC4. Grep по api/ находит
# только state.database в api/routers/system.py, но ленивые свойства читают БД
# шире, а get_dashboard_goal_plan ходит ещё в goal_plan и
# latest_planning_checkpoint. Пин обязателен: иначе следующая правка молча
# сузит фасад, и падение будет в рантайме, а не в тесте.
API_STATE_SURFACE = frozenset(
    {
        "ai_coach",
        "database",
        "goal_plan",
        "latest_execution_feedback",
        "latest_planning_checkpoint",
        "planning_checkpoint_history",
        "refresh_planning_checkpoint_cache",
        "resolved_goal_plan_context",
    }
)

# Эндпоинты, которые получают состояние через Depends(get_headless_state).
API_STATE_ENDPOINTS = ("/api/dashboard/summary", "/api/dashboard/widgets")


def _probe_api_state_surface(tmp_path, paths) -> set[str]:
    """Прогнать эндпоинты через TestClient и вернуть реально прочитанные атрибуты.

    Записываются только УСПЕШНЫЕ чтения: если атрибут исчез, он пропадёт из
    набора и пин упадёт. Так регрессия ловится тестом, а не в рантайме —
    потребители вроде get_dashboard_goal_plan читают через getattr(..., None)
    и без пина деградируют молча.
    """
    from fastapi.testclient import TestClient

    from api.deps import get_database, get_headless_state
    from api.main import app
    from data.database import Database
    from services.demo_mode import (
        _build_demo_activities,
        _build_demo_health,
        _build_demo_hrv,
        _build_demo_sleep,
        _build_demo_training_status,
    )
    from utils.app_state import HeadlessState, SessionDict

    class _RecordingState(HeadlessState):
        def __init__(self, session, database=None):
            object.__setattr__(self, "accessed", [])
            if database is not None:
                session["database"] = database
            super().__init__(session)

        def __getattribute__(self, item):
            value = object.__getattribute__(self, item)
            if not item.startswith("_"):
                object.__getattribute__(self, "accessed").append(item)
            return value

    db = Database(str(tmp_path / "state_surface.db"))
    # Пустая БД уводит dashboard в ранний возврат `if activities_df.empty`,
    # и тогда состояние не спрашивают вообще: проба вернула бы пустой набор и
    # ничего не запинила. Данные обязательны для непустой проверки.
    db.save_activities(_build_demo_activities())
    db.save_hrv_data(_build_demo_hrv())
    db.sync_sleep_data(_build_demo_sleep())
    db.sync_daily_health(_build_demo_health())
    db.sync_training_status(_build_demo_training_status())

    state = _RecordingState(SessionDict(), db)
    app.dependency_overrides[get_database] = lambda: db
    app.dependency_overrides[get_headless_state] = lambda: state
    try:
        client = TestClient(app)
        for path in paths:
            response = client.get(path)
            assert response.status_code == 200, f"{path} -> {response.status_code}"
    finally:
        app.dependency_overrides.clear()

    # object.__getattribute__ в обход рекордера: обычное чтение state.accessed
    # само попало бы в набор и сломало пин.
    return set(object.__getattribute__(state, "accessed"))


def test_api_state_surface_is_pinned_by_a_probe(tmp_path) -> None:
    """AC4: API читает ровно этот набор атрибутов состояния.

    Если тест упал — API начал читать новое свойство состояния (или перестал
    читать старое). Это осознанное изменение контракта: расширьте фасад в
    utils/app_state.py и обновите API_STATE_SURFACE, а не «чините» пин.
    """
    observed = _probe_api_state_surface(tmp_path, API_STATE_ENDPOINTS)

    assert observed == set(API_STATE_SURFACE), (
        "набор атрибутов состояния, который читает API, изменился: "
        f"новые={sorted(observed - API_STATE_SURFACE)}, "
        f"пропали={sorted(API_STATE_SURFACE - observed)}"
    )


def test_api_state_probe_is_not_vacuous(tmp_path) -> None:
    """Проба обязана что-то увидеть: пустая БД даёт пустой набор.

    Регрессия этого теста означает, что эндпоинты снова ушли в ранний возврат
    и пин выше перестал что-либо проверять, оставаясь зелёным.
    """
    observed = _probe_api_state_surface(tmp_path, API_STATE_ENDPOINTS)

    assert "database" in observed, (
        "проба не увидела ни одного обращения к состоянию — пин вырожден"
    )
    assert len(observed) >= 3, f"подозрительно узкий набор: {sorted(observed)}"

# ---------------------------------------------------------------------------
# services/data_cache.py: headless-контракт и регистрация сброса (#645)
# ---------------------------------------------------------------------------

_DATA_CACHE_PROBE = """
import sys
sys.path.insert(0, {root!r})
sys.modules["streamlit"] = None  # модуль обязан импортироваться и без него
from services import data_cache
print("imported=True")
loaders = (
    "_load_activities_cached",
    "_load_activities_between_cached",
    "_load_hrv_cached",
    "_load_sleep_cached",
    "_load_daily_health_cached",
)
print("wrapped=" + ",".join(name for name in loaders if hasattr(getattr(data_cache, name), "clear")))
"""


def _probe_data_cache_headless() -> dict[str, str]:
    """Импортировать data_cache в отдельном процессе с заблокированным Streamlit.

    Отдельный процесс обязателен: pytest уже импортировал модуль, и проверка в
    текущем интерпретаторе дала бы ложный результат.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _DATA_CACHE_PROBE.format(root=str(REPO_ROOT))],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    parsed: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            parsed[key] = value
    return parsed


def test_data_cache_imports_without_streamlit() -> None:
    """Модуль обещает headless-импорт (issue #602); до #645 обещание было ложно.

    На уровне модуля стоял импорт из state, а state/__init__.py тянет
    state/manager.py с import streamlit — то есть try/except вокруг streamlit и
    _passthrough были мёртвым кодом.
    """
    probe = _probe_data_cache_headless()

    assert probe.get("imported") == "True"
    # Сырой @st.cache_data при st = None уронил бы импорт; раз импорт прошёл,
    # ни один загрузчик не обёрнут напрямую и все пять деградировали в passthrough.
    assert probe.get("wrapped") == "", (
        "загрузчики остались обёрнуты в кэш при недоступном Streamlit: "
        f"{probe.get('wrapped')}"
    )


def test_data_cache_registers_its_clearer_at_import() -> None:
    """Регистрация сброса при импорте — то, что тест по имени не проверял.

    test_data_cache_registers_its_clearer сбрасывает реестр и регистрирует фейк,
    поэтому удаление строки register_cache_clearer(clear_data_caches) не уронило
    бы ни одного теста.
    """
    import importlib

    from services import cache_registry, data_cache

    cache_registry.reset_registry()
    try:
        importlib.reload(data_cache)
        assert data_cache.clear_data_caches in cache_registry.registered_clearers(), (
            "импорт data_cache не зарегистрировал свой сброс в headless-реестре"
        )
    finally:
        cache_registry.reset_registry()

