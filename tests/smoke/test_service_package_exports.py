from __future__ import annotations

from types import ModuleType

import pytest

import services


pytestmark = pytest.mark.smoke


def test_services_package_imports_submodules_lazily(monkeypatch: pytest.MonkeyPatch):
    sentinel = ModuleType("services.demo_mode")
    imported: list[tuple[str, str | None]] = []

    def fake_import_module(name: str, package: str | None = None):
        imported.append((name, package))
        return sentinel

    services.__dict__.pop("demo_mode", None)
    monkeypatch.setattr(services, "import_module", fake_import_module)

    loaded = services.__getattr__("demo_mode")

    assert loaded is sentinel
    assert services.demo_mode is sentinel
    assert imported == [(".demo_mode", "services")]


def test_services_package_rejects_unknown_export():
    with pytest.raises(AttributeError):
        services.__getattr__("missing_service")
