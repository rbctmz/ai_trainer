#!/usr/bin/env python3
"""Repair runtime packages needed to launch the app."""

from __future__ import annotations

from pathlib import Path
import sys
import sysconfig

PATCH_MARKER_START = "# AI Trainer Streamlit proto case-collision repair: start"
PATCH_MARKER_END = "# AI Trainer Streamlit proto case-collision repair: end"
PATCH_BLOCK = f"""
{PATCH_MARKER_START}
from importlib.util import module_from_spec as _module_from_spec, spec_from_file_location as _spec_from_file_location
from pathlib import Path as _Path
import sys as _sys


def _load_case_collision_aliases() -> None:
    _package_dir = _Path(__file__).resolve().parent
    _exact_names = {{path.name for path in _package_dir.iterdir()}}
    for _duplicate in sorted(_package_dir.glob("* 2.py")):
        _target_name = _duplicate.name.replace(" 2", "", 1)
        if _target_name in _exact_names:
            continue
        _module_name = _duplicate.stem.replace(" 2", "", 1)
        _full_name = f"{{__name__}}.{{_module_name}}"
        if _full_name in _sys.modules:
            globals()[_module_name] = _sys.modules[_full_name]
            continue
        _spec = _spec_from_file_location(_full_name, _duplicate)
        if _spec is None or _spec.loader is None:
            continue
        _module = _module_from_spec(_spec)
        _sys.modules[_full_name] = _module
        _spec.loader.exec_module(_module)
        globals()[_module_name] = _module


_load_case_collision_aliases()
del _load_case_collision_aliases
del _module_from_spec
del _spec_from_file_location
del _Path
del _sys
{PATCH_MARKER_END}
""".strip()

SNIFFIO_INIT = """from ._impl import (
    AsyncLibraryNotFoundError,
    current_async_library,
    current_async_library_cvar,
    thread_local,
)

__all__ = [
    "AsyncLibraryNotFoundError",
    "current_async_library",
    "current_async_library_cvar",
    "thread_local",
]

__version__ = "1.3.1"
"""

SNIFFIO_IMPL = """from __future__ import annotations

import sys
from contextvars import ContextVar
from threading import local


class AsyncLibraryNotFoundError(RuntimeError):
    pass


current_async_library_cvar: ContextVar[str | None] = ContextVar(
    "current_async_library_cvar",
    default=None,
)
thread_local = local()


def current_async_library() -> str:
    thread_name = getattr(thread_local, "name", None)
    if thread_name is not None:
        return thread_name

    context_name = current_async_library_cvar.get()
    if context_name is not None:
        return context_name

    if "asyncio" in sys.modules:
        import asyncio

        try:
            if asyncio.current_task() is not None:
                return "asyncio"
        except RuntimeError:
            pass

    raise AsyncLibraryNotFoundError("unknown async library, or not in async context")
"""


def find_streamlit_proto_dir() -> Path:
    purelib = Path(sysconfig.get_paths()["purelib"])
    proto_dir = purelib / "streamlit" / "proto"
    if proto_dir.is_dir():
        return proto_dir
    raise FileNotFoundError(f"Streamlit proto directory not found: {proto_dir}")


def find_missing_aliases(proto_dir: Path) -> list[Path]:
    exact_names = {path.name for path in proto_dir.iterdir()}
    return [
        duplicate
        for duplicate in sorted(proto_dir.glob("* 2.py"))
        if duplicate.name.replace(" 2", "", 1) not in exact_names
    ]


def patch_proto_init(proto_dir: Path) -> bool:
    init_path = proto_dir / "__init__.py"
    content = init_path.read_text(encoding="utf-8")
    if PATCH_MARKER_START in content:
        return False
    patched = f"{content.rstrip()}\n\n{PATCH_BLOCK}\n"
    init_path.write_text(patched, encoding="utf-8")
    return True


def find_purelib_dir() -> Path:
    return Path(sysconfig.get_paths()["purelib"])


def repair_sniffio(purelib: Path) -> int:
    sniffio_dir = purelib / "sniffio"
    sniffio_dir.mkdir(exist_ok=True)

    repaired = 0
    init_path = sniffio_dir / "__init__.py"
    if not init_path.exists():
        init_path.write_text(SNIFFIO_INIT, encoding="utf-8")
        repaired += 1
        print("🔧 Recreated sniffio/__init__.py")

    impl_path = sniffio_dir / "_impl.py"
    if not impl_path.exists():
        impl_path.write_text(SNIFFIO_IMPL, encoding="utf-8")
        repaired += 1
        print("🔧 Recreated sniffio/_impl.py")

    version_path = sniffio_dir / "_version.py"
    if not version_path.exists():
        version_path.write_text('__version__ = "1.3.1"\n', encoding="utf-8")
        repaired += 1
        print("🔧 Recreated sniffio/_version.py")

    typed_path = sniffio_dir / "py.typed"
    if not typed_path.exists():
        typed_path.write_text("", encoding="utf-8")
        repaired += 1
        print("🔧 Recreated sniffio/py.typed")

    return repaired


def main() -> int:
    try:
        proto_dir = find_streamlit_proto_dir()
        purelib = find_purelib_dir()
    except FileNotFoundError as exc:
        print(f"⚠️ {exc}")
        return 1

    repaired_sniffio = repair_sniffio(purelib)
    missing_aliases = find_missing_aliases(proto_dir)
    if not missing_aliases and repaired_sniffio == 0:
        print("✅ Runtime packages are already consistent")
        return 0

    if missing_aliases:
        patched = patch_proto_init(proto_dir)
        for duplicate in missing_aliases:
            print(f"🔧 Registered alias for {duplicate.name.replace(' 2', '', 1)} via __init__.py")

        if patched:
            print("✅ Streamlit proto import repair installed")
        else:
            print("✅ Streamlit proto import repair already installed")

    if repaired_sniffio:
        print(f"✅ Repaired {repaired_sniffio} sniffio runtime file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
