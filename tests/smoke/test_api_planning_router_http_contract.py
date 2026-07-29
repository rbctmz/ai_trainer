"""HTTP round-trip контракт для planning: FastAPI-валидация `Query(...)` (issue #248).

Соседний direct-call свит (`test_api_planning_router_contract.py`, #246) вызывает
router-функции напрямую, в обход ASGI/DI-слоя FastAPI. Поэтому декларативные
`Query(ge=…, le=…, pattern=…)`-guard'ы на path/query там НЕ исполняются: при
прямом вызове `days: int = Query(180, ge=1, le=365)` — это просто дефолт, границы
не проверяются (см. docstring соседнего файла). Снятие/послабление такого
констрейнта прошло бы молча — тот же класс «рефакторинг ломает api тихо» из
ATAM-карты #201, но на уровне декларативной валидации FastAPI.

Этот файл закрывает остаток #248 тонким `TestClient`-слоем. `planning.py` —
ЕДИНСТВЕННЫЙ роутер с path/query `Query`-констрейнтами (`events.days`,
`export/workout.fmt`, `export/workout.leg`, `export/workout.session_id`);
остальные роутеры валидируют только
тело запроса через Pydantic `Field(...)`, а оно уже пинается при конструировании
модели в direct-call тестах (#242/#246). Поэтому HTTP-слой сводится к одному
роутеру, а не к свипу.

Паттерн на каждый констрейнт: нарушение границы → 422, включительная граница →
НЕ 422 (404 на пустой БД, либо 200 через sentinel для `/events`). Кейс на 200
попутно пинует второй непокрытый direct-call'ом слой — реальный
`Depends(get_database)` и сериализацию возвращаемого dict по аннотации. Happy-path
бизнес-логику здесь СОЗНАТЕЛЬНО не переисполняем (это задача #246) — только
конверт валидации.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import planning_service as ps
from api.deps import get_database
from api.main import app
from data.database import Database

PLANNING = "/api/planning"


@pytest.fixture
def client(tmp_path):
    """TestClient с временной пустой SQLite вместо реальной БД.

    Переопределяем `get_database`, а не полагаемся на дефолт: (1) герметичность —
    реальная `ai_trainer.db` не открывается ни в одном кейсе; (2) заодно
    исполняется реальный DI-путь FastAPI, которого нет в direct-call свите.
    """
    db = Database(str(tmp_path / "http_contract.db"))
    app.dependency_overrides[get_database] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_database, None)


# --- GET /events?days=  (Query days: ge=1, le=365) --------------------------


@pytest.mark.parametrize("days", [0, -1, 366, 400])
def test_events_rejects_days_outside_1_365(client, days):
    # Нарушение границы обязано отклоняться ASGI-слоем ДО хендлера, поэтому сетевой
    # discover_intervals_events не вызывается — кейс герметичен без монкейпатча.
    resp = client.get(f"{PLANNING}/events", params={"days": days})
    assert resp.status_code == 422


@pytest.mark.parametrize("days", [1, 365])
def test_events_accepts_inclusive_days_and_serializes_body(client, monkeypatch, days):
    # Включительные границы (1 и 365) обязаны проходить валидацию — иначе кто-то
    # молча ужал `ge`/`le`. Провайдер подменён sentinel'ом: кейс остаётся
    # герметичным и заодно пинует round-trip — реальный DI + сериализация dict в JSON.
    sentinel = {"count": 0, "events": [], "read_only": True}
    monkeypatch.setattr(ps, "discover_intervals_events", lambda **_k: sentinel)
    resp = client.get(f"{PLANNING}/events", params={"days": days})
    assert resp.status_code == 200
    assert resp.json() == sentinel


# --- GET /export/workout/{index}?fmt=&leg=&session_id= ----------------------


@pytest.mark.parametrize("fmt", ["bad", "gpx", "TCX"])
def test_export_workout_rejects_fmt_outside_pattern(client, fmt):
    # pattern="^(tcx|fit_csv|tcx_activity)$" — полноякорный и регистрозависимый,
    # поэтому произвольная строка и "TCX" (регистр) одинаково вне контракта.
    resp = client.get(f"{PLANNING}/export/workout/0", params={"fmt": fmt})
    assert resp.status_code == 422


@pytest.mark.parametrize("fmt", ["tcx", "fit_csv", "tcx_activity"])
def test_export_workout_accepts_each_pattern_alt_then_404(client, fmt):
    # Каждый член альтернации обязан проходить валидацию (иначе pattern сузили
    # молча); на пустой БД тело хендлера отдаёт 404, а НЕ 422. Это же исполняет
    # реальный Depends(get_database).
    resp = client.get(f"{PLANNING}/export/workout/0", params={"fmt": fmt})
    assert resp.status_code == 404


@pytest.mark.parametrize("leg", [0, 3, -1])
def test_export_workout_rejects_leg_outside_1_2(client, leg):
    resp = client.get(f"{PLANNING}/export/workout/0", params={"fmt": "tcx", "leg": leg})
    assert resp.status_code == 422


@pytest.mark.parametrize("leg", [1, 2])
def test_export_workout_accepts_inclusive_leg_then_404(client, leg):
    # leg на включительной границе валиден → 404 (нет активного плана), не 422.
    resp = client.get(f"{PLANNING}/export/workout/0", params={"fmt": "tcx", "leg": leg})
    assert resp.status_code == 404


def test_export_workout_rejects_empty_session_id(client):
    resp = client.get(
        f"{PLANNING}/export/workout/0",
        params={"fmt": "tcx", "session_id": ""},
    )
    assert resp.status_code == 422


def test_export_workout_accepts_nonempty_session_id_then_404(client):
    resp = client.get(
        f"{PLANNING}/export/workout/0",
        params={"fmt": "tcx", "session_id": "ats_leaf"},
    )
    assert resp.status_code == 404


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
