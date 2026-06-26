"""Lazy service exports for the application service layer."""

from importlib import import_module
from types import ModuleType

__all__ = [
    "acceptance_mode",
    "data_cache",
    "demo_mode",
    "garmin",
    "intervals_icu",
    "sync",
]


def __getattr__(name: str) -> ModuleType:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = import_module(f".{name}", __name__)
    globals()[name] = module
    return module


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + __all__)
