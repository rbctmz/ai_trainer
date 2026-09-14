"""Жёсткий таймаут платного smoke и агрегация токенов в ``scripts/dsh_pilot_preflight.sh``.

Реального модельного вызова и сети здесь нет: ``dsh`` подменён стабом в
``tmp_path/bin``, который умеет зависать (игнорируя SIGTERM), запускать потомка и
выходить, падать и завершаться успешно, а ``zstd`` — выводить файл сессии «как
есть», чтобы тест не зависел от внешнего бинаря. Проверяются только гарантии
процесса: по истечении лимита умирает вся группа процессов прогона (включая
внуков, игнорирующих SIGTERM), скрипт выходит с 124, метрики печатают
``timed_out``/``timeout_seconds`` (и эффективный grace — ``timeout_grace_seconds``),
а обычные пути (успех, код возврата модели) и прежний гейтинг не меняются.

Сессия синтетическая, но в **реальной вложенной форме** harness 0.1.0-rc.6
(снята с сохранённой сессии пилота #577): сверенный шаг модели —
``{"type":"assistant/message","data":{"turn":..,"step":..,"usage":{..}}}``, а
стриминговый чанк того же шага — ``{"type":"assistant/chunk","data":{"chunk":
{"type":"usage","usage":{..}}}}`` с теми же числами. Обе записи описывают один
запрос, поэтому тест закрепляет и то, что токены собираются, и то, что один шаг
не считается дважды (``usage_duplicate_records_skipped``). Парсер, читавший
usage только в корне записи (``rec["usage"]``), давал ``tokens_*=0`` на реальной
сессии — это и был измеренный пробел пилота #577. Отдельным тестом закреплено,
что вложенная форма читается, а верхнеуровневая распознаётся только там, где она
единственная.

Отдельно закрыт вопрос границ: ``DSH_PILOT_TIMEOUT_SECONDS`` принимается только
в ``1..900``, ``DSH_PILOT_TIMEOUT_GRACE_SECONDS`` — только в ``1..10``, а значения
вне диапазона, ``0``, отрицательные, нечисловые и **явно пустые** отвергаются до
платного вызова (ноль обращений к стабу, exit 1) — иначе «жёсткий лимит 600 c»
был бы обещанием, которое снимается одной переменной окружения. Допуск верхних
границ проверяется без ожидания: стаб завершается сразу, поэтому тест на
``900``/``10`` подтверждает, что значение прошло валидацию и платный прогон
действительно начался, — а не то, что лимит кто-то выдержал; отдельная проверка
времени (`elapsed < 20`) падает, если границу начнут «проверять» ожиданием.

Процессные гарантии закрыты четырьмя независимыми тестами: (1) группа умирает по
таймауту; (2) потомок, переживший своего лидера, добивается, а прогон не
принимается как чистый (``leftover_processes_killed``); (3) лимит считается
монотонными часами — замороженный ``date`` его не растягивает; (4) сбой
извлечения метрик (``zstd``/парсер) не подменяет таймаутный ``124``. Проверка
живости PID считает зомби завершённым: в контейнере, где PID 1 не пожинает
сирот, убитый внук остаётся ``<defunct>``, и ``os.kill(pid, 0)`` по нему успешен.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

import pytest


pytestmark = pytest.mark.smoke

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = ROOT / "scripts" / "dsh_pilot_preflight.sh"

# Сохранённая сессия единственного авторизованного платного прогона пилота
# (#577). Каталог `logs/` в git не попадает, поэтому тест, читающий её,
# пропускается там, где артефакта нет; сама сессия не изменяется и не коммитится.
PRESERVED_PILOT_SESSION = (
    ROOT
    / "logs"
    / "dsh-pilot-577"
    / "sessions"
    / "--private-tmp-dsh-pilot-577-wt--"
    / "session-82e185f4-86d3-46d2-b963-74da0d1e347a"
    / "session.jsonl.zstd"
)

# Синтетическая сессия в РЕАЛЬНОЙ вложенной форме harness 0.1.0-rc.6: на каждый
# шаг — стриминговый чанк с usage и сверенное сообщение с теми же числами (две
# записи одного запроса), плюс вызов инструмента. Сумма по шагам = 11/7/3/1,
# то есть ровно те числа, что печатают метрики; без дедупликации было бы вдвое
# больше.
SESSION_NESTED_SHAPE = "\n".join(
    [
        # Шаг 1: ожидается usage {"inputTokens": 8, "outputTokens": 5,
        # "cacheReadTokens": 2, "reasoningTokens": 1}.
        '{"type":"assistant/chunk","seq":2,"time":2,"data":{"turn":1,"step":1,'
        '"chunk":{"type":"usage","usage":{"inputTokens":8,"outputTokens":5,'
        '"cacheReadTokens":2,"reasoningTokens":1}}}}',
        '{"type":"tool/call","seq":3,"time":3,"data":{"turn":1,"step":1,'
        '"callId":"call_1","name":"read","arguments":"{}"}}',
        '{"type":"assistant/message","seq":4,"time":4,"data":{"turn":1,"step":1,'
        '"message":{"role":"assistant","content":[]},'
        '"usage":{"inputTokens":8,"outputTokens":5,"cacheReadTokens":2,"reasoningTokens":1}}}',
        '{"type":"step/end","seq":5,"time":5,"data":{"turn":1,"step":1}}',
        # Шаг 2: ожидается usage {"inputTokens": 3, "outputTokens": 2,
        # "cacheReadTokens": 1, "reasoningTokens": 0}.
        '{"type":"assistant/chunk","seq":6,"time":6,"data":{"turn":1,"step":2,'
        '"chunk":{"type":"usage","usage":{"inputTokens":3,"outputTokens":2,'
        '"cacheReadTokens":1,"reasoningTokens":0}}}}',
        '{"type":"assistant/message","seq":7,"time":7,"data":{"turn":1,"step":2,'
        '"message":{"role":"assistant","content":[]},'
        '"usage":{"inputTokens":3,"outputTokens":2,"cacheReadTokens":1,"reasoningTokens":0}}}',
        '{"type":"step/end","seq":8,"time":8,"data":{"turn":1,"step":2}}',
        '{"type":"user/message","seq":9,"time":9,"data":{"content":[{"type":"text","text":"go"}]}}',
    ]
)

# Сессия без единой записи usage: метрики обязаны сказать «недоступно», а не
# напечатать нули (ноль токенов — это утверждение об измерении, которого не было).
SESSION_WITHOUT_USAGE = "\n".join(
    [
        '{"type":"step/end","seq":2,"time":2,"data":{"turn":1,"step":1}}',
        '{"type":"tool/call","seq":3,"time":3,"data":{"turn":1,"step":1,'
        '"callId":"call_1","name":"read","arguments":"{}"}}',
        '{"type":"user/message","seq":4,"time":4,"data":{"content":[{"type":"text","text":"go"}]}}',
    ]
)

# Форма прежних стабов и прежнего парсера: usage в КОРНЕ записи. Harness так не
# пишет — в реальной сессии usage лежит в `data` (см. runbook), поэтому такая
# сессия обязана дать «недоступно», а не посчитанные числа.
SESSION_FLAT_SHAPE = (
    '{"type":"step/end","usage":{"inputTokens":11,"outputTokens":7,'
    '"cacheReadTokens":3,"reasoningTokens":1}}'
)

# Стаб `dsh`: бесплатные вызовы отвечают как закреплённый профиль, «платный»
# прогон эмулируется по STUB_MODE. В режиме sleep_forever стаб игнорирует SIGTERM
# и оставляет внука, который тоже игнорирует SIGTERM — именно он выжил бы, если
# бы скрипт убивал только прямое ребёнка.
_STUB_DSH = """#!/usr/bin/env bash
# Стаб dsh для теста таймаута: без сети и без модели.
STUB_LOG="${STUB_LOG:?STUB_LOG}"
log() { printf '%s\\n' "$*" >> "$STUB_LOG"; }

if [ "${1:-}" = "--version" ]; then
  printf '%s\\n' "0.1.0-rc.6"
  exit 0
fi

for arg in "$@"; do
  if [ "$arg" = "--help" ]; then
    log "loader-check"
    exit "${STUB_LOADER_EXIT_CODE:-0}"
  fi
done

for arg in "$@"; do
  if [ "$arg" = "--dump-config" ]; then
    printf '%s\\n' \\
      '- id: agent-default-model' \\
      '    provider: deepseek-official' \\
      '    model: deepseek-v4-flash' \\
      '- id: sandbox-policy' \\
      '    mode: workspace-write'
    exit 0
  fi
done

log "paid-run pid=$$ mode=${STUB_MODE:-normal} cwd=$PWD"

write_session() {
  if [ "${STUB_SESSION:-no}" = "yes" ]; then
    mkdir -p "${DSH_HOME:?}/sessions/stub-session"
    # Содержимое сессии пишет тест (реальная вложенная форма harness); стаб лишь
    # копирует file → file, чтобы JSON не проходил через разбор escapes в printf
    # (иначе \\n внутри JSON превратился бы в настоящий перевод строки и сломал запись).
    cat "${STUB_SESSION_CONTENT_FILE:?STUB_SESSION_CONTENT_FILE}" \\
      > "${DSH_HOME}/sessions/stub-session/session.jsonl.zstd"
  fi
}

case "${STUB_MODE:-normal}" in
  sleep_forever)
    trap '' TERM
    ( trap '' TERM; while :; do sleep 1; done ) &
    printf 'grandchild=%s\\n' "$!" >> "${STUB_PIDS:?STUB_PIDS}"
    printf 'stub=%s\\n' "$$" >> "${STUB_PIDS:?STUB_PIDS}"
    # Сессия пишется ДО зависания: таймаутный прогон с сохранённой сессией нужен,
    # чтобы проверить, что сбой извлечения метрик не съедает exit 124.
    write_session
    while :; do sleep 1; done
    ;;
  fork_and_exit)
    # Лидер запускает асинхронного потомка в наследственной группе процессов и
    # выходит сам. Потомок игнорирует SIGTERM, поэтому проверяется не только
    # обнаружение «группа пережила лидера», но и эскалация до SIGKILL.
    ( trap '' TERM; while :; do sleep 1; done ) &
    printf 'orphan=%s\\n' "$!" >> "${STUB_PIDS:?STUB_PIDS}"
    printf 'stub=%s\\n' "$$" >> "${STUB_PIDS:?STUB_PIDS}"
    write_session
    exit "${STUB_EXIT_CODE:-0}"
    ;;
  mutate)
    # «Прогон изменил дерево»: проверка read-only обязана это заметить.
    write_session
    printf 'mutated during smoke\\n' > "$PWD/pilot-mutated.txt"
    exit "${STUB_EXIT_CODE:-0}"
    ;;
  commit)
    # «Прогон закоммитил»: дерево остаётся чистым, поэтому спасти может только
    # проверка сдвига HEAD.
    write_session
    git -c user.email=stub@example.invalid -c user.name=stub -c commit.gpgsign=false \\
      -c core.hooksPath=/dev/null commit -q --allow-empty -m "smoke commit"
    exit "${STUB_EXIT_CODE:-0}"
    ;;
  *)
    write_session
    exit "${STUB_EXIT_CODE:-0}"
    ;;
esac
"""

# Стаб `node`: preflight проверяет не номер версии как таковой, а три API,
# нужные загрузчику DSH. Код `-e` здесь означает только эту capability-пробу;
# JavaScript и сеть в тестах не исполняются.
_STUB_NODE = """#!/usr/bin/env bash
if [ "${1:-}" = "--version" ]; then
  printf '%s\\n' "${STUB_NODE_VERSION:-v25.6.1}"
  exit 0
fi
if [ "${1:-}" = "-e" ]; then
  exit "${STUB_NODE_FEATURE_EXIT:-0}"
fi
exit 2
"""

# Стаб `zstd`: тест пишет файл сессии без сжатия, поэтому `-dc` = «как есть».
# Так проверка готовности метрик и агрегация токенов проходят без внешнего zstd.
# STUB_ZSTD_EXIT эмулирует битый/нечитаемый session.jsonl.zstd: извлечение метрик
# падает так же, как упал бы настоящий zstd (он выходит ненулевым кодом).
_STUB_ZSTD = """#!/usr/bin/env bash
if [ -n "${STUB_ZSTD_EXIT:-}" ]; then
  exit "${STUB_ZSTD_EXIT}"
fi
for arg in "$@"; do
  if [ -f "$arg" ]; then
    cat "$arg"
    exit 0
  fi
done
exit 1
"""


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _git(worktree: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(worktree), *args],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=60,
    )


def _state_from_proc(pid: int) -> str | None:
    """Состояние процесса из ``/proc/<pid>/stat`` (Linux, контейнеры).

    Поле 3 (после ``comm`` в скобках) — состояние: ``Z`` означает зомби. На
    macOS ``/proc`` нет, поэтому источник честно возвращает ``None``.
    """
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    try:
        return raw.rsplit(")", 1)[1].split()[0]
    except IndexError:
        return None


def _state_from_ps(pid: int) -> str | None:
    """Состояние процесса из ``ps -o stat= -p PID`` (BSD/macOS и Linux).

    ``None`` означает «состояние узнать не удалось» (нет процесса, нет ``ps``,
    песочница запрещает ``ps``) — вызывающий код трактует это консервативно.
    """
    try:
        completed = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    fields = completed.stdout.split()
    return fields[0] if fields else None


# Источники состояния процесса по порядку: сначала дешёвый и точный /proc, потом
# ps. Список отдельной константой, чтобы тест механизма мог проверить разбор
# состояния ``Z`` независимо от того, какой из источников доступен на машине.
_STATE_SOURCES = (_state_from_proc, _state_from_ps)


def _pid_state(pid: int) -> str | None:
    for source in _STATE_SOURCES:
        state = source(pid)
        if state is not None:
            return state
    return None


def _pid_alive(pid: int) -> bool:
    """Проверка живости по PID (а не по строке в логе стаба).

    Зомби считается завершённым. В контейнере, где PID 1 не пожинает сирот,
    убитый внук навсегда остаётся ``<defunct>``: ``os.kill(pid, 0)`` по нему
    успешен, но выполняться и тратить оплаченное время он не может, поэтому
    «живым» он не считается. Запущенный процесс остаётся живым: ``Z`` — это
    ровно состояние зомби, всё остальное (``S``, ``R``, ``I``, ``U``) — нет.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    state = _pid_state(pid)
    if state is not None and state.startswith("Z"):
        return False
    return True


def _wait_pid_gone(pid: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.05)
    return not _pid_alive(pid)


@dataclass
class _Pilot:
    """Песочница preflight: отдельные worktree, DSH_HOME, стабы dsh/zstd."""

    worktree: Path
    home: Path
    bin_dir: Path
    prompt: Path
    pids_file: Path
    log_file: Path
    session_content_file: Path

    def set_session_content(self, content: str) -> None:
        """Содержимое сессии, которое стаб положит в ``$DSH_HOME/sessions``.

        Содержимое передаётся файлом, а не переменной окружения: JSON с
        экранированными ``\\n`` внутри (например, в аргументах tool call)
        искажался бы любым разбором escapes по пути.
        """
        self.session_content_file.write_text(f"{content}\n", encoding="utf-8")

    def env(self, **overrides: str | None) -> dict[str, str]:
        """Изолированное окружение запуска: реальные DSH_*/DEEPSEEK_* не наследуются."""
        env = {
            "PATH": os.pathsep.join([str(self.bin_dir), os.environ.get("PATH", "/usr/bin:/bin")]),
            "HOME": str(self.home),
            "DSH_PILOT_WORKTREE": str(self.worktree),
            "DSH_PILOT_HOME": str(self.home / "dsh-home"),
            "DSH_PILOT_PROMPT": str(self.prompt),
            "DSH_PILOT_NODE_DIR": str(self.bin_dir),
            "DEEPSEEK_API_KEY": "stub-key-never-used",
            "STUB_LOG": str(self.log_file),
            "STUB_PIDS": str(self.pids_file),
            "STUB_MODE": "normal",
            "STUB_EXIT_CODE": "0",
            "STUB_SESSION": "yes",
            "STUB_SESSION_CONTENT_FILE": str(self.session_content_file),
            "STUB_NODE_VERSION": "v25.6.1",
            "STUB_NODE_FEATURE_EXIT": "0",
            "STUB_LOADER_EXIT_CODE": "0",
            # Короткие лимиты: тест обязан быть быстрым и детерминированным.
            "DSH_PILOT_TIMEOUT_SECONDS": "5",
            "DSH_PILOT_TIMEOUT_GRACE_SECONDS": "1",
        }
        for locale_var in ("LANG", "LC_ALL", "TMPDIR"):
            if locale_var in os.environ:
                env[locale_var] = os.environ[locale_var]
        for key, value in overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return env

    def start(self, *args: str, env: dict[str, str]) -> subprocess.Popen[str]:
        return subprocess.Popen(
            ["bash", str(PREFLIGHT), *args],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def run(self, *args: str, env: dict[str, str], timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(PREFLIGHT), *args],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )

    def smoke(self, env: dict[str, str], timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
        return self.run("--smoke", "--allow-paid-call", env=env, timeout=timeout)

    def log_text(self) -> str:
        return self.log_file.read_text(encoding="utf-8") if self.log_file.exists() else ""

    def paid_invocations(self) -> int:
        """Сколько раз стаб реально был запущен как платный прогон.

        Строку ``paid-run`` пишет только платная ветка стаба: бесплатные
        ``--version`` и ``--dump-config`` выходят раньше логирования, поэтому
        ноль здесь означает «до платного вызова дело не дошло».
        """
        return self.log_text().count("paid-run")

    def pids(self) -> dict[str, int]:
        pids: dict[str, int] = {}
        if not self.pids_file.exists():
            return pids
        for line in self.pids_file.read_text(encoding="utf-8").splitlines():
            name, _, raw = line.partition("=")
            if name and raw.strip().isdigit():
                pids[name] = int(raw)
        return pids

    def wait_for_pids(self, names: frozenset[str] = frozenset({"stub", "grandchild"}), timeout: float = 20.0) -> dict[str, int]:
        """Ждём, пока стаб запишет нужные PID (без угадывания sleep'ов)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pids = self.pids()
            if names <= set(pids):
                return pids
            time.sleep(0.05)
        return self.pids()

    def kill_leftovers(self) -> None:
        """Аварийная уборка: тест не должен оставлять живые стабы даже при падении assert."""
        for pid in self.pids().values():
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                continue


@pytest.fixture
def pilot(tmp_path: Path) -> _Pilot:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(bin_dir / "dsh", _STUB_DSH)
    _write_executable(bin_dir / "node", _STUB_NODE)
    _write_executable(bin_dir / "zstd", _STUB_ZSTD)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Прочитай README.md и ничего не меняй.\n", encoding="utf-8")

    _git(worktree, "init", "-q")
    (worktree / "README.md").write_text("read-only пилот\n", encoding="utf-8")
    _git(worktree, "add", "README.md")
    _git(
        worktree,
        "-c",
        "user.email=pilot@example.invalid",
        "-c",
        "user.name=pilot",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "core.hooksPath=/dev/null",
        "commit",
        "-q",
        "-m",
        "init",
    )

    harness = _Pilot(
        worktree=worktree,
        home=home,
        bin_dir=bin_dir,
        prompt=prompt,
        pids_file=tmp_path / "stub-pids.txt",
        log_file=tmp_path / "stub-invocations.log",
        session_content_file=tmp_path / "stub-session.jsonl",
    )
    harness.set_session_content(SESSION_NESTED_SHAPE)
    try:
        yield harness
    finally:
        harness.kill_leftovers()


def test_incompatible_node_runtime_fails_before_dsh_or_paid_run(pilot: _Pilot) -> None:
    """Нет нужных API Node: preflight падает до любого запуска harness."""
    env = pilot.env(STUB_NODE_VERSION="v20.19.5", STUB_NODE_FEATURE_EXIT="9")
    result = pilot.run("--prepare", env=env)

    assert result.returncode == 1, result.stdout
    assert "Node runtime" in result.stdout
    assert "Promise.withResolvers" in result.stdout
    assert pilot.log_text() == ""
    assert pilot.paid_invocations() == 0


def test_headless_loader_failure_blocks_prepare_without_paid_run(pilot: _Pilot) -> None:
    """Capability-проба прошла, но реальный loader профиля нет: prepare не зачтён."""
    env = pilot.env(STUB_LOADER_EXIT_CODE="9")
    result = pilot.run("--prepare", env=env)

    assert result.returncode == 1, result.stdout
    assert "headless" in result.stdout
    assert "loader" in result.stdout
    assert pilot.log_text().count("loader-check") == 1
    assert pilot.paid_invocations() == 0


def test_compatible_runtime_prepare_records_runtime_and_loader(pilot: _Pilot) -> None:
    """Бесплатный prepare публикует наблюдаемый runtime и успешную loader-пробу."""
    env = pilot.env()
    result = pilot.run("--prepare", env=env)

    assert result.returncode == 0, result.stdout
    assert f"node_path={pilot.bin_dir / 'node'}" in result.stdout
    assert "node_version=v25.6.1" in result.stdout
    assert "headless_loader_check=pass" in result.stdout
    assert pilot.log_text().count("loader-check") == 1
    assert pilot.paid_invocations() == 0


def test_invalid_node_dir_fails_before_dsh_or_paid_run(pilot: _Pilot) -> None:
    """Явный runtime-dir валидируется, а не молча игнорируется в пользу PATH."""
    env = pilot.env(DSH_PILOT_NODE_DIR="relative/node-bin")
    result = pilot.run("--prepare", env=env)

    assert result.returncode == 1, result.stdout
    assert "DSH_PILOT_NODE_DIR" in result.stdout
    assert "absolute" in result.stdout
    assert pilot.log_text() == ""
    assert pilot.paid_invocations() == 0


def test_timeout_kills_whole_process_group_including_grandchild(pilot: _Pilot) -> None:
    """Зависший стаб (игнорирует SIGTERM) + его внук: выход 124 и ни одного живого PID."""
    env = pilot.env(
        STUB_MODE="sleep_forever",
        STUB_SESSION="no",
        DSH_PILOT_TIMEOUT_SECONDS="1",
        DSH_PILOT_TIMEOUT_GRACE_SECONDS="1",
    )
    try:
        result = pilot.smoke(env=env)

        assert result.returncode == 124, result.stdout
        assert "ТАЙМАУТ" in result.stdout
        assert "timed_out=yes" in result.stdout
        assert "timeout_seconds=1" in result.stdout
        assert "exit_code=124" in result.stdout

        pids = pilot.pids()
        assert {"stub", "grandchild"} <= set(pids), f"стаб не записал PID: {pids}"
        # Живость проверяется по PID, а не по строке в логе.
        assert _wait_pid_gone(pids["stub"]), f"процесс стаба {pids['stub']} пережил таймаут"
        assert _wait_pid_gone(pids["grandchild"]), (
            f"внук {pids['grandchild']} пережил таймаут: убит только прямой ребёнок"
        )
    finally:
        pilot.kill_leftovers()


def test_short_override_bounds_wall_clock_instead_of_default(pilot: _Pilot) -> None:
    """Короткий DSH_PILOT_TIMEOUT_SECONDS соблюдается, а не подменяется дефолтом 600 c."""
    env = pilot.env(
        STUB_MODE="sleep_forever",
        STUB_SESSION="no",
        DSH_PILOT_TIMEOUT_SECONDS="2",
        DSH_PILOT_TIMEOUT_GRACE_SECONDS="1",
    )
    started = time.monotonic()
    try:
        result = pilot.smoke(env=env)
        elapsed = time.monotonic() - started

        assert result.returncode == 124, result.stdout
        assert "timeout_seconds=2" in result.stdout
        assert "timed_out=yes" in result.stdout
        assert elapsed >= 1.5, f"прогон оборвался раньше лимита: {elapsed:.1f}s"
        assert elapsed < 20, f"лимит 2 c не соблюдён (похоже на дефолт 600 c): {elapsed:.1f}s"
    finally:
        pilot.kill_leftovers()


def test_group_member_surviving_its_leader_is_terminated(pilot: _Pilot) -> None:
    """Потомок, переживший лидера группы, добивается, а прогон не принимается как чистый.

    Здесь лидер выходит сам (не по таймауту), но оставляет в наследственной группе
    асинхронного потомка, игнорирующего SIGTERM. Пока группа не отслеживалась после
    смерти лидера, preflight возвращал успех, а этот потомок продолжал работать и
    тратить бюджет. Ожидания лимита тоже быть не должно: группа добивается сразу
    после выхода лидера, поэтому прогон не помечается таймаутом.
    """
    env = pilot.env(
        STUB_MODE="fork_and_exit",
        STUB_SESSION="yes",
        DSH_PILOT_TIMEOUT_SECONDS="10",
        DSH_PILOT_TIMEOUT_GRACE_SECONDS="1",
    )
    try:
        result = pilot.smoke(env=env)

        assert result.returncode == 1, result.stdout
        assert "пережила своего лидера" in result.stdout
        assert "leftover_processes_killed=yes" in result.stdout
        assert "timed_out=no" in result.stdout
        # Прогон был бы засчитан (сессия сохранена, дерево не менялось, HEAD не
        # двигался): ненулевой код вызван ровно выжившим потомком.
        assert "worktree_clean_after=yes" in result.stdout
        assert "head_unchanged=yes" in result.stdout
        assert "tokens_input=11" in result.stdout

        pids = pilot.pids()
        assert {"stub", "orphan"} <= set(pids), f"стаб не записал PID: {pids}"
        # Живость проверяется по PID, а не по строке в логе.
        assert _wait_pid_gone(pids["orphan"]), (
            f"потомок {pids['orphan']} пережил preflight: группа проверялась только по лидеру"
        )
    finally:
        pilot.kill_leftovers()


def test_hard_limit_does_not_depend_on_wall_clock(pilot: _Pilot) -> None:
    """Замороженный/переведённый назад ``date`` не растягивает жёсткий лимит.

    Воспроизведение находки ревью: пока дедлайн считался ``date +%s``, стаб
    ``date`` с фиксированным epoch (эмуляция коррекции NTP назад) держал лимит
    вечно — прогон не завершался даже спустя секунды после ``DSH_PILOT_TIMEOUT_SECONDS=2``.
    Теперь лимит считается монотонными часами, поэтому таймаут срабатывает.
    """
    _write_executable(pilot.bin_dir / "date", '#!/usr/bin/env bash\nprintf \'%s\\n\' "1700000000"\n')
    env = pilot.env(
        STUB_MODE="sleep_forever",
        STUB_SESSION="no",
        DSH_PILOT_TIMEOUT_SECONDS="2",
        DSH_PILOT_TIMEOUT_GRACE_SECONDS="1",
    )
    started = time.monotonic()
    try:
        result = pilot.smoke(env=env)
        elapsed = time.monotonic() - started

        assert result.returncode == 124, result.stdout
        assert "timed_out=yes" in result.stdout
        assert "exit_code=124" in result.stdout
        assert elapsed < 20, f"настенные часы растянули лимит 2 c: {elapsed:.1f}s"
        pids = pilot.pids()
        assert _wait_pid_gone(pids["grandchild"]), f"внук {pids['grandchild']} пережил таймаут"
    finally:
        pilot.kill_leftovers()


def test_hard_limit_is_measured_by_monotonic_clock() -> None:
    """Механизм: лимит и длительность считаются монотонной шкалой, а не ``date``.

    ``date +%s`` — настенные часы; ``$SECONDS`` в bash тоже идут через
    ``gettimeofday`` (bug-bash), поэтому «жёсткость» лимита держится только на
    монотонном источнике. Тест проверяет сам механизм, а не поведение при
    подмене ``date`` (его проверяет тест выше), и падает, если дедлайн снова
    начнут считать настенными часами.
    """
    script = PREFLIGHT.read_text(encoding="utf-8")
    code_lines = [line for line in script.splitlines() if not line.lstrip().startswith("#")]

    assert "time.monotonic()" in script, "лимит больше не опирается на монотонные часы"
    assert "monotonic_ms" in script
    for line in code_lines:
        assert not re.search(r"\bdate\s+\+%s", line), f"настенные часы вернулись в лимит: {line.strip()}"


def test_metrics_failure_does_not_mask_timeout_exit_code(pilot: _Pilot) -> None:
    """Сбой извлечения метрик на таймаутном прогоне: наружу всё равно 124, сбой виден.

    ``zstd`` выходит с кодом 9 (битый/обрезанный ``session.jsonl.zstd``), а
    извлечение идёт под ``set -euo pipefail``: без best-effort обработки код zstd
    становился кодом всего preflight и маскировал таймаут (в метриках при этом
    печаталось ``exit_code=124``, а процесс возвращал 9 — автоматика
    классифицировала бы прогон неверно).
    """
    env = pilot.env(
        STUB_MODE="sleep_forever",
        STUB_SESSION="yes",
        STUB_ZSTD_EXIT="9",
        DSH_PILOT_TIMEOUT_SECONDS="1",
        DSH_PILOT_TIMEOUT_GRACE_SECONDS="1",
    )
    try:
        result = pilot.smoke(env=env)

        assert result.returncode == 124, result.stdout
        assert result.returncode != 9
        assert "exit_code=124" in result.stdout
        assert "timed_out=yes" in result.stdout
        # Сбой не молчит: и громкое сообщение, и строка метрик с причиной.
        assert "не удалось извлечь метрики сессии" in result.stdout
        assert "session_metrics=not collected (extraction failed" in result.stdout
    finally:
        pilot.kill_leftovers()


def test_normal_run_reports_default_limit_and_keeps_metrics(pilot: _Pilot) -> None:
    """Без переопределения лимит равен 600 c; обычный прогон не помечен таймаутом."""
    env = pilot.env()
    env.pop("DSH_PILOT_TIMEOUT_SECONDS")
    result = pilot.smoke(env=env)

    assert result.returncode == 0, result.stdout
    assert "timeout_seconds=600" in result.stdout
    assert "timed_out=no" in result.stdout
    assert "exit_code=0" in result.stdout
    assert f"node_path={pilot.bin_dir / 'node'}" in result.stdout
    assert "node_version=v25.6.1" in result.stdout
    assert "headless_loader_check=pass" in result.stdout
    # Метрики сессии по-прежнему собираются (стаб zstd = «вывести как есть»),
    # а гарантии read-only по-прежнему подтверждаются.
    assert "tokens_input=11" in result.stdout
    assert "tool_calls=1" in result.stdout
    assert "worktree_clean_after=yes" in result.stdout
    assert "head_unchanged=yes" in result.stdout
    # Значение ключа не печатается даже при успешном прогоне.
    assert "stub-key-never-used" not in result.stdout


def test_normal_run_preserves_model_exit_code(pilot: _Pilot) -> None:
    """Ненулевой код модели — это её результат, а не таймаут: он доходит наружу."""
    env = pilot.env(STUB_MODE="normal", STUB_EXIT_CODE="7")
    result = pilot.smoke(env=env)

    assert result.returncode == 7, result.stdout
    assert result.returncode != 124
    assert "timed_out=no" in result.stdout
    assert "exit_code=7" in result.stdout


def _metric(result: subprocess.CompletedProcess[str], field: str) -> str:
    """Значение строки метрик ``field=...`` (одно поле — одна строка)."""
    matches = re.findall(rf"^{re.escape(field)}=(.*)$", result.stdout, re.MULTILINE)
    assert matches, f"в выводе нет строки метрик {field}=:\n{result.stdout}"
    return matches[-1]


# Агрегатор токенов живёт в preflight одной строкой $PARSER_PY и исполняется там
# как `python3 -c "$PARSER_PY"`. Тест читает ровно это содержимое, поэтому не
# дублирует логику парсера (иначе проверялась бы копия, а не то, что работает).
_PARSER_PY_PATTERN = re.compile(r"^PARSER_PY='\n(.*?)\n'\n", re.DOTALL | re.MULTILINE)


def _preflight_parser_source() -> str:
    match = _PARSER_PY_PATTERN.search(PREFLIGHT.read_text(encoding="utf-8"))
    assert match, "в preflight больше нет блока $PARSER_PY"
    return match.group(1)


def test_preflight_parser_source_is_safe_inside_the_shell_argument() -> None:
    """Блок ``$PARSER_PY`` исполняется как ``python3 -c "$PARSER_PY"``.

    Одиночная кавычка внутри блока закрыла бы аргумент ``-c``: остаток кода ушёл
    бы в шелл, а исполняемая часть падала бы с ``NameError`` на имени ключа.
    Ровно это и произошло при добавлении ``tok['inputTokens']`` — тест держит
    блок свободным от одиночных кавычек, а сборка строк идёт через ``.format``.
    """
    source = _preflight_parser_source()

    assert "'" not in source, "одиночная кавычка в $PARSER_PY ломает `python3 -c \"$PARSER_PY\"`"
    # Блок обязан оставаться исполняемым ровно в том виде, в каком его получит шелл.
    completed = subprocess.run(
        [sys.executable, "-c", source],
        input="",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert "usage_records=0" in completed.stdout
    assert "tokens_input=not available" in completed.stdout


def _run_preflight_parser(session_text: str) -> dict[str, str]:
    """Прогоняет парсер preflight на тексте сессии и разбирает строки метрик."""
    completed = subprocess.run(
        [sys.executable, "-c", _preflight_parser_source()],
        input=session_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=120,
    )
    parsed: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        field, separator, value = line.partition("=")
        if separator:
            # Хвостовой комментарий есть у human_messages_in_session.
            parsed[field] = value.split("  #", 1)[0].strip()
    return parsed


def test_nested_usage_is_aggregated_once_per_step(pilot: _Pilot) -> None:
    """Токены собираются из реальной вложенной формы, и один шаг не считается дважды.

    Регрессия пилота #577: парсер читал только ``rec["usage"]``, то есть корень
    записи, где harness usage не пишет, — на реальной сессии это дало
    ``tokens_input=0``. Здесь синтетическая сессия повторяет обе наблюдавшиеся
    формы одного шага: ``assistant/chunk.data.chunk.usage`` и
    ``assistant/message.data.usage`` с теми же числами. Ожидаемые итоги — сумма
    по двум шагам: 8+3=11 вход, 5+2=7 выход, 2+1=3 чтений кэша, 1+0=1 reasoning.
    """
    result = pilot.smoke(env=pilot.env())

    assert result.returncode == 0, result.stdout
    assert _metric(result, "tokens_input") == "11"
    assert _metric(result, "tokens_output") == "7"
    assert _metric(result, "tokens_cache_read") == "3"
    assert _metric(result, "tokens_reasoning") == "1"
    assert _metric(result, "tool_calls") == "1"
    assert _metric(result, "steps") == "2"
    assert _metric(result, "human_messages_in_session").startswith("1")
    # Два измерения шага (чанк и сообщение) засчитаны как одно: без дедупликации
    # здесь было бы 22/14/6/2 и usage_records=4.
    assert _metric(result, "usage_records") == "2"
    assert _metric(result, "usage_duplicate_records_skipped") == "2"


def test_session_without_usage_reports_unavailable_not_zero(pilot: _Pilot) -> None:
    """Сессия без записей usage: метрики недоступны, а не «нулевые токены».

    Ноль — это утверждение об измерении; когда измерения не было, честный ответ
    один: ``not available`` с причиной в той же строке. Прогон, чьи оплаченные
    числа отсутствуют, не засчитывается (как и при сбое извлечения), но это
    происходит уже ПОСЛЕ сбора метрик, поэтому числа и причина напечатаны.
    """
    pilot.set_session_content(SESSION_WITHOUT_USAGE)
    result = pilot.smoke(env=pilot.env())

    assert result.returncode == 1, result.stdout
    assert result.returncode != 124
    assert _metric(result, "usage_records") == "0"
    for field in ("tokens_input", "tokens_output", "tokens_cache_read", "tokens_reasoning"):
        value = _metric(result, field)
        assert value.startswith("not available"), f"{field}={value!r}: нули вместо недоступности"
        assert "usage records absent in the whole session" in value
    # Одной явной строки достаточно, чтобы это заметил оператор.
    assert "нет ни одной записи usage" in result.stdout
    assert "timed_out=no" in result.stdout
    # Токены остаются недоступными, а не «нулевыми»: нуля в этих полях нет вовсе.
    assert "tokens_input=0" not in result.stdout


def test_legacy_top_level_usage_is_not_mistaken_for_a_measurement(pilot: _Pilot) -> None:
    """Обе формы usage читаются, а реальное измерение берётся там, где его пишет harness.

    Раньше парсер читал только ``rec["usage"]`` (корень записи). Нетронутая
    сессия реального harness, где usage лежит в ``data``, давала ``tokens_*=0`` —
    это и есть пробел пилота #577. Здесь проверяются обе стороны: вложенная форма
    ``data.usage`` действительно читается (исправление), а верхнеуровневая —
    только когда она единственная, чего harness не делает.
    """
    pilot.set_session_content(SESSION_FLAT_SHAPE)
    result = pilot.smoke(env=pilot.env())

    assert result.returncode == 0, result.stdout
    assert _metric(result, "usage_records") == "1"
    assert _metric(result, "tokens_input") == "11"

    # Вложенная форма не теряется: числа шага 11/7/3/1 приходят из `data`, а не
    # остаются нулями, как это было на реальной сессии.
    pilot.set_session_content(SESSION_NESTED_SHAPE)
    nested = pilot.smoke(env=pilot.env())
    assert nested.returncode == 0, nested.stdout
    assert _metric(nested, "tokens_input") == "11"
    assert _metric(nested, "usage_records") == "2"


def test_usage_present_but_zero_is_a_measurement_not_unavailable(pilot: _Pilot) -> None:
    """Запись usage с нулями — это измеренный ноль, а не «недоступно»."""
    session = (
        '{"type":"assistant/message","data":{"turn":1,"step":1,'
        '"usage":{"inputTokens":0,"outputTokens":0,"cacheReadTokens":0,"reasoningTokens":0}}}'
    )
    pilot.set_session_content(session)
    result = pilot.smoke(env=pilot.env())

    assert result.returncode == 0, result.stdout
    assert _metric(result, "usage_records") == "1"
    assert _metric(result, "tokens_input") == "0"
    assert "tokens_input=not available" not in result.stdout


def test_preserved_paid_pilot_session_is_measured_with_the_real_shape() -> None:
    """Сохранённая сессия платного пилота #577 измеряется теми же числами.

    ``logs/`` в git не попадает, поэтому тест пропускается там, где артефакта
    нет. Сначала доказывается, что файл — настоящий zstd с заявленным числом
    записей (round-trip сжатия), затем те же метрики, что считает preflight,
    снимаются с него тем же содержимым ``$PARSER_PY``, которое preflight
    исполняет: тест не дублирует логику и не «доверяет» сохранённым числам.
    """
    if not PRESERVED_PILOT_SESSION.exists():
        pytest.skip(f"сохранённой сессии пилота нет: {PRESERVED_PILOT_SESSION}")
    if shutil.which("zstd") is None:
        pytest.skip("нет zstd: сохранённую сессию не распаковать")

    original = PRESERVED_PILOT_SESSION.read_bytes()
    assert original[:4] == b"\x28\xb5\x2f\xfd", "сохранённая сессия не является zstd-потоком"
    decompressed = subprocess.run(
        ["zstd", "-dc", str(PRESERVED_PILOT_SESSION)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=120,
    ).stdout
    lines = [line for line in decompressed.splitlines() if line.strip()]
    assert len(lines) == 1614, f"не тот артефакт: записей {len(lines)}"
    records = [json.loads(line) for line in lines]

    # Артефакт — настоящий zstd-поток именно этих записей (round-trip), а не
    # подсунутый распакованный файл: иначе тест «измерял» бы что угодно.
    with tempfile.TemporaryDirectory() as tmp:
        packed = Path(tmp) / "session.jsonl.zstd"
        subprocess.run(
            ["zstd", "-q", "-f", "-o", str(packed)],
            input=decompressed,
            check=True,
            timeout=120,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        assert (
            subprocess.run(
                ["zstd", "-dc", str(packed)],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=120,
            ).stdout
            == decompressed
        ), "round-trip zstd не совпал: сохранённая сессия повреждена"

    counts = Counter(record.get("type") for record in records)
    assert counts["assistant/message"] == 57
    assert counts["tool/call"] == 74
    assert counts["step/end"] == 57
    # Оба места, где harness пишет usage: ровно по одной записи на каждый из 57
    # шагов — по два измерения одного запроса, которые парсер обязан свести к одному.
    usage_bearing_chunks = sum(
        1
        for record in records
        if isinstance(record.get("data"), dict)
        and isinstance(record["data"].get("chunk"), dict)
        and isinstance(record["data"]["chunk"].get("usage"), dict)
    )
    assert usage_bearing_chunks == 57
    assert sum(1 for record in records if isinstance(record.get("data"), dict)
               and isinstance(record["data"].get("usage"), dict)) == 57

    parsed = _run_preflight_parser(decompressed.decode("utf-8"))
    assert parsed["usage_records"] == "57", parsed
    assert parsed["usage_duplicate_records_skipped"] == "57", parsed
    assert parsed["session_parse_errors"] == "0", parsed
    # Первое реальное измерение токенов оплаченного прогона. Числа сравниваются
    # с самим артефактом (а не с константой в тесте), но обязаны быть непустыми:
    # именно их отсутствие было пробелом, который закрывает эта проверка.
    for field in ("tokens_input", "tokens_output", "tokens_cache_read", "tokens_reasoning"):
        assert parsed[field].isdigit(), f"{field}={parsed[field]!r}: токены не измерены"
        assert int(parsed[field]) > 0, f"{field}={parsed[field]}: нулевое измерение"
    assert parsed["tool_calls"] == "74", parsed
    assert parsed["steps"] == "57", parsed


def test_sigint_to_preflight_leaves_no_smoke_processes(pilot: _Pilot) -> None:
    """Ctrl-C по preflight не оставляет оплаченный прогон работать в своей группе."""
    env = pilot.env(
        STUB_MODE="sleep_forever",
        STUB_SESSION="no",
        DSH_PILOT_TIMEOUT_SECONDS="10",
        DSH_PILOT_TIMEOUT_GRACE_SECONDS="1",
    )
    proc = pilot.start("--smoke", "--allow-paid-call", env=env)
    try:
        pids = pilot.wait_for_pids()
        assert {"stub", "grandchild"} <= set(pids), f"стаб не записал PID: {pids}"

        proc.send_signal(signal.SIGINT)
        proc.communicate(timeout=40)

        assert proc.returncode == 130, proc.returncode
        assert _wait_pid_gone(pids["stub"]), f"процесс стаба {pids['stub']} пережил SIGINT"
        assert _wait_pid_gone(pids["grandchild"]), f"внук {pids['grandchild']} пережил SIGINT"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
        pilot.kill_leftovers()


def test_dirty_worktree_after_smoke_still_fails_the_run(pilot: _Pilot) -> None:
    """Прогон оставил файл в worktree: read-only нарушен, exit 1 (а не 124)."""
    env = pilot.env(STUB_MODE="mutate")
    result = pilot.smoke(env=env)

    assert result.returncode == 1, result.stdout
    assert "read-only" in result.stdout
    assert "worktree_clean_after=no" in result.stdout
    assert "timed_out=no" in result.stdout


def test_moved_head_after_smoke_still_fails_the_run(pilot: _Pilot) -> None:
    """Прогон сделал коммит: чистое дерево не спасает, проверка HEAD обязана поймать."""
    env = pilot.env(STUB_MODE="commit")
    result = pilot.smoke(env=env)

    assert result.returncode == 1, result.stdout
    assert "HEAD сдвинулся" in result.stdout
    assert "worktree_clean_after=yes" in result.stdout
    assert "head_unchanged=no" in result.stdout
    assert "timed_out=no" in result.stdout


def test_missing_allow_paid_call_still_blocks_paid_run(pilot: _Pilot) -> None:
    """Прежний гейтинг: без --allow-paid-call платный вызов не стартует вообще."""
    env = pilot.env(STUB_MODE="sleep_forever", STUB_SESSION="no", DSH_PILOT_TIMEOUT_SECONDS="5")
    result = pilot.run("--smoke", env=env)

    assert result.returncode == 1, result.stdout
    assert "--allow-paid-call" in result.stdout
    assert "paid-run" not in pilot.log_text()
    assert "timed_out" not in result.stdout


def test_missing_api_key_still_blocks_paid_run(pilot: _Pilot) -> None:
    """Креды обязаны приходить из окружения — и это по-прежнему проверяется до вызова."""
    env = pilot.env()
    env.pop("DEEPSEEK_API_KEY")
    result = pilot.smoke(env=env)

    assert result.returncode == 1, result.stdout
    assert "DEEPSEEK_API_KEY" in result.stdout
    assert "paid-run" not in pilot.log_text()


def test_non_numeric_limit_fails_before_paid_run(pilot: _Pilot) -> None:
    """Опечатка в лимите — отказ до платного вызова, а не тихий откат к 600 c."""
    env = pilot.env(DSH_PILOT_TIMEOUT_SECONDS="1O")  # буква O вместо нуля
    result = pilot.smoke(env=env)

    assert result.returncode == 1, result.stdout
    assert "DSH_PILOT_TIMEOUT_SECONDS" in result.stdout
    assert "paid-run" not in pilot.log_text()


@pytest.mark.parametrize(
    ("variable", "expected_range"),
    [
        ("DSH_PILOT_TIMEOUT_SECONDS", "1..900"),
        ("DSH_PILOT_TIMEOUT_GRACE_SECONDS", "1..10"),
    ],
)
def test_explicitly_empty_setting_fails_before_paid_run(
    pilot: _Pilot, variable: str, expected_range: str
) -> None:
    """Явно пустое значение — отказ, а не подстановка дефолта 600/5.

    Пустая переменная (нерасширившаяся подстановка в CI, обнулённая настройка)
    раньше молча получала дефолт: ветка отказа для ``''`` была недостижима, и
    платный вызов стартовал. Разница между «не задано» и «задано пустым» обязана
    сохраняться до валидации: «не задано» — это по-прежнему дефолт 600/5, и он
    закреплён тестами ``test_normal_run_reports_default_limit_and_keeps_metrics``
    и ``test_default_grace_is_five_and_observable``.
    """
    env = pilot.env(**{variable: ""})
    result = pilot.smoke(env=env)

    assert result.returncode == 1, result.stdout
    # Сообщение называет наблюдаемое значение буквально пустым и допустимый диапазон.
    assert f"{variable}=''" in result.stdout
    assert expected_range in result.stdout
    assert "paid-run" not in pilot.log_text()
    assert pilot.paid_invocations() == 0, pilot.log_text()
    assert "timed_out=" not in result.stdout


def test_unreadable_monotonic_clock_fails_before_paid_run(pilot: _Pilot) -> None:
    """Недоказуемая граница — отказ до платного вызова, а не «прогон без лимита».

    Стаб ``python3`` ломается, поэтому монотонные часы прочитать нельзя. Скрипт
    обязан отказаться от платного вызова, а не запускать его без жёсткого лимита
    и не подменять шкалу настенными часами.
    """
    _write_executable(pilot.bin_dir / "python3", '#!/usr/bin/env bash\nexit 3\n')
    env = pilot.env()
    result = pilot.smoke(env=env)

    assert result.returncode == 1, result.stdout
    assert "монотонные часы" in result.stdout
    assert pilot.paid_invocations() == 0, pilot.log_text()
    assert "timed_out=" not in result.stdout


@pytest.mark.parametrize(
    "value",
    [
        "901",
        "3600",
        "86400",
        "0",
        "-5",
        "1O",
        # 20 значащих цифр: `[ -gt ]` считает в 64 битах и падает ошибкой, которую
        # условие `if` принимает за «ложь» — без проверки длины такой лимит прошёл бы.
        "99999999999999999999",
    ],
)
def test_limit_outside_1_900_fails_before_paid_run(pilot: _Pilot, value: str) -> None:
    """Верхняя граница обязательна: 901/86400 (и 0/минус/мусор) — отказ, ноль вызовов."""
    env = pilot.env(DSH_PILOT_TIMEOUT_SECONDS=value)
    result = pilot.smoke(env=env)

    assert result.returncode == 1, result.stdout
    # Сообщение обязано называть и наблюдаемое значение, и допустимый диапазон.
    assert f"DSH_PILOT_TIMEOUT_SECONDS='{value}'" in result.stdout
    assert "1..900" in result.stdout
    # Ноль платных вызовов: стаб не запускался вовсе (весь смысл отказа ДО вызова).
    assert pilot.paid_invocations() == 0, pilot.log_text()
    # Отказ раньше оплаченного прогона: метрик нет вовсе.
    assert "timed_out=" not in result.stdout


@pytest.mark.parametrize("value", ["999", "0", "-1", "grace"])
def test_grace_outside_1_10_fails_before_paid_run(pilot: _Pilot, value: str) -> None:
    """Grace больше 10 c растягивал бы уже оплаченный прогон: отказ до вызова."""
    env = pilot.env(DSH_PILOT_TIMEOUT_GRACE_SECONDS=value)
    result = pilot.smoke(env=env)

    assert result.returncode == 1, result.stdout
    assert f"DSH_PILOT_TIMEOUT_GRACE_SECONDS='{value}'" in result.stdout
    assert "1..10" in result.stdout
    assert pilot.paid_invocations() == 0, pilot.log_text()
    assert "timed_out=" not in result.stdout


def test_upper_bounds_900_and_10_are_accepted_and_observable(pilot: _Pilot) -> None:
    """Границы 900 и 10 принимаются: валидация не отказывает и стаб реально стартует.

    Ожидания 900 c здесь нет и быть не должно: стаб завершается сразу, поэтому
    проверяются ровно два факта — значение прошло валидацию (нет ни fail-closed
    отказа, ни таймаута) и платный прогон действительно начался (стаб получил
    вызов). Соблюдение самого лимита проверяется отдельными тестами с коротким
    лимитом; подменять 900 на маленькое число, чтобы «проверить границу», нельзя.
    Проверка времени обязательна: она падает, если тест начнёт ждать лимит.
    """
    env = pilot.env(DSH_PILOT_TIMEOUT_SECONDS="900", DSH_PILOT_TIMEOUT_GRACE_SECONDS="10")
    started = time.monotonic()
    result = pilot.smoke(env=env)
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stdout
    # 1. Валидация значение приняла: ни отказа, ни сработавшего таймаута.
    assert "ПРЕДПОЛЁТ НЕ ПРОЙДЕН" not in result.stdout
    assert "ТАЙМАУТ" not in result.stdout
    # 2. Прогон дошёл до платного вызова: стаб запущен ровно один раз.
    assert pilot.paid_invocations() == 1, pilot.log_text()
    # 3. Лимит 900 c не выдерживался ожиданием — стаб вышел сам (иначе здесь было бы ~900 c).
    assert elapsed < 20, f"проверка границы 900 c ушла в ожидание лимита: {elapsed:.1f}s"
    assert "жёсткий лимит платного прогона: 900s" in result.stdout
    assert "через 10s SIGKILL" in result.stdout
    assert "timeout_seconds=900" in result.stdout
    assert "timeout_grace_seconds=10" in result.stdout
    assert "timed_out=no" in result.stdout


def test_default_grace_is_five_and_observable(pilot: _Pilot) -> None:
    """Дефолтный grace (5 c) виден и в строке лимита, и в метриках — без ожидания лимита."""
    env = pilot.env()
    env.pop("DSH_PILOT_TIMEOUT_SECONDS")
    env.pop("DSH_PILOT_TIMEOUT_GRACE_SECONDS")
    started = time.monotonic()
    result = pilot.smoke(env=env)
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stdout
    assert pilot.paid_invocations() == 1, pilot.log_text()
    assert elapsed < 20, f"дефолтный лимит 600 c выдерживался ожиданием: {elapsed:.1f}s"
    assert "жёсткий лимит платного прогона: 600s" in result.stdout
    assert "через 5s SIGKILL" in result.stdout
    assert "timeout_seconds=600" in result.stdout
    assert "timeout_grace_seconds=5" in result.stdout


def test_leading_zero_limit_cannot_smuggle_past_the_ceiling(pilot: _Pilot) -> None:
    """`1000` — это 1000 c (отказ), а `0900` печатается канонически как 900."""
    rejected = pilot.smoke(env=pilot.env(DSH_PILOT_TIMEOUT_SECONDS="1000"))
    assert rejected.returncode == 1, rejected.stdout
    assert "DSH_PILOT_TIMEOUT_SECONDS='1000'" in rejected.stdout
    assert pilot.paid_invocations() == 0, pilot.log_text()

    accepted = pilot.smoke(env=pilot.env(DSH_PILOT_TIMEOUT_SECONDS="0900"))
    assert accepted.returncode == 0, accepted.stdout
    assert pilot.paid_invocations() == 1, pilot.log_text()
    # `$((0900))` в bash — это 576 (восьмеричная запись), поэтому без нормализации
    # напечатанный лимит разошёлся бы с фактическим дедлайном.
    assert "timeout_seconds=900" in accepted.stdout


def test_liveness_treats_reported_zombie_state_as_terminated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Зомби (состояние ``Z``) — не живой процесс, а запущенный процесс — живой.

    Проверяется решение хелпера по состоянию процесса: ``os.kill(pid, 0)`` по
    зомби успешен, поэтому одного его недостаточно. Стаб ``ps`` стоит здесь
    потому, что состояние процессов снаружи может быть недоступно (в песочнице
    агента ``ps`` запрещён), а проверяем мы именно разбор ``stat`` — источник
    ``/proc`` на Linux тестируется отдельным тестом ниже.
    """
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    _write_executable(
        stub_bin / "ps",
        '#!/usr/bin/env bash\nprintf \'%s\\n\' "${STUB_PS_STATE:?STUB_PS_STATE}"\n',
    )
    monkeypatch.setenv("PATH", os.pathsep.join([str(stub_bin), os.environ.get("PATH", "/usr/bin:/bin")]))
    monkeypatch.setenv("STUB_PS_STATE", "Z")
    # Источник /proc на Linux вернул бы реальное состояние, поэтому список
    # источников сужается до ps: тест про разбор состояния, а не про платформу.
    monkeypatch.setattr(sys.modules[__name__], "_STATE_SOURCES", (_state_from_ps,))

    running = subprocess.Popen(["sleep", "30"])
    try:
        # Живой процесс: состояние не Z, поэтому он обязан считаться живым.
        monkeypatch.setenv("STUB_PS_STATE", "S")
        assert _pid_alive(running.pid), "запущенный процесс посчитан завершённым"

        # Тот же PID, но состояние Z: работать он не может — значит завершён.
        monkeypatch.setenv("STUB_PS_STATE", "Z")
        assert not _pid_alive(running.pid), "зомби посчитан живым — тест зависел бы от окружения"
        monkeypatch.setenv("STUB_PS_STATE", "Z+")
        assert not _pid_alive(running.pid)
    finally:
        running.kill()
        running.wait()

    # Убитый и пожинанный процесс мёртв независимо от источника состояния.
    assert not _pid_alive(running.pid)


def test_liveness_reports_real_zombie_as_terminated() -> None:
    """Настоящий зомби (родитель не пожинает ребёнка) считается завершённым.

    Это ровно случай из находки ревью: в контейнере, где PID 1 не пожинает
    сирот, ``<defunct>`` остаётся навсегда. Тест пропускается там, где состояние
    процесса узнать нельзя (нет ``/proc`` и запрещён ``ps``) — там ту же логику
    проверяет тест механизма выше.
    """
    if not hasattr(os, "fork"):
        pytest.skip("нет os.fork на этой платформе")
    if _pid_state(os.getpid()) is None:
        pytest.skip("состояние процесса недоступно (нет /proc, ps недоступен)")

    pid = os.fork()
    if pid == 0:  # pragma: no cover — дочерняя ветка выходит немедленно
        os._exit(0)
    try:
        state = ""
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            state = _pid_state(pid) or ""
            if state.startswith("Z"):
                break
            time.sleep(0.05)
        assert state.startswith("Z"), f"не удалось получить зомби: state={state!r}"
        assert not _pid_alive(pid), "зомби посчитан живым — тест снова зависел бы от окружения"
    finally:
        os.waitpid(pid, 0)


def test_prepare_ignores_out_of_range_timeout_settings(pilot: _Pilot) -> None:
    """Бесплатный prepare не зависит от настроек таймаута: они проверяются только перед платным вызовом."""
    env = pilot.env(DSH_PILOT_TIMEOUT_SECONDS="86400", DSH_PILOT_TIMEOUT_GRACE_SECONDS="999")
    result = pilot.run(env=env)

    assert result.returncode == 0, result.stdout
    assert "Платный модельный вызов НЕ выполнялся" in result.stdout
    assert pilot.paid_invocations() == 0, pilot.log_text()


def test_prompt_never_read_project_env_and_always_passed_as_absolute_path(pilot: _Pilot) -> None:
    """Стаб видит cwd=worktree и абсолютный промпт; проектный .env не создаётся и не читается."""
    env = pilot.env()
    result = pilot.smoke(env=env)

    assert result.returncode == 0, result.stdout
    log = pilot.log_text()
    assert f"cwd={pilot.worktree}" in log
    assert not (pilot.worktree / ".env").exists()


def test_extraction_failure_is_fatal_for_non_timeout_run(pilot: _Pilot) -> None:
    """Сбой извлечения метрик на обычном прогоне — провал preflight, а не успех.

    #578 review (P1): ветка провала извлечения печатала ``session_metrics=not
    collected``, но не поднимала провал, поэтому прогон, чьи оплаченные числа
    потеряны (битый/обрезанный ``session.jsonl.zstd``), мог вернуть 0 — при том
    что runbook требует метрики для зачёта smoke.
    """
    env = pilot.env(STUB_SESSION="yes", STUB_ZSTD_EXIT="9")
    try:
        result = pilot.smoke(env=env)

        assert result.returncode == 1, result.stdout
        assert result.returncode != 0
        assert "session_metrics=not collected (extraction failed" in result.stdout
        assert "timed_out=no" in result.stdout
    finally:
        pilot.kill_leftovers()
