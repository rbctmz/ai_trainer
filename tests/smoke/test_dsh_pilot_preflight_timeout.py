"""Жёсткий таймаут платного smoke в ``scripts/dsh_pilot_preflight.sh``.

Реального модельного вызова и сети здесь нет: ``dsh`` подменён стабом в
``tmp_path/bin``, который умеет зависать (игнорируя SIGTERM), запускать потомка и
выходить, падать и завершаться успешно, а ``zstd`` — выводить файл сессии «как
есть», чтобы тест не зависел от внешнего бинаря. Проверяются только гарантии
процесса: по истечении лимита умирает вся группа процессов прогона (включая
внуков, игнорирующих SIGTERM), скрипт выходит с 124, метрики печатают
``timed_out``/``timeout_seconds`` (и эффективный grace — ``timeout_grace_seconds``),
а обычные пути (успех, код возврата модели) и прежний гейтинг не меняются.

Отдельно закрыт вопрос границ: ``DSH_PILOT_TIMEOUT_SECONDS`` принимается только
в ``1..300``, ``DSH_PILOT_TIMEOUT_GRACE_SECONDS`` — только в ``1..10``, а значения
вне диапазона, ``0``, отрицательные, нечисловые и **явно пустые** отвергаются до
платного вызова (ноль обращений к стабу, exit 1) — иначе «жёсткий лимит 300 c»
был бы обещанием, которое снимается одной переменной окружения. Допуск верхних
границ проверяется без ожидания: стаб завершается сразу, поэтому тест на
``300``/``10`` подтверждает, что значение прошло валидацию и платный прогон
действительно начался, — а не то, что лимит кто-то выдержал.

Процессные гарантии закрыты четырьмя независимыми тестами: (1) группа умирает по
таймауту; (2) потомок, переживший своего лидера, добивается, а прогон не
принимается как чистый (``leftover_processes_killed``); (3) лимит считается
монотонными часами — замороженный ``date`` его не растягивает; (4) сбой
извлечения метрик (``zstd``/парсер) не подменяет таймаутный ``124``. Проверка
живости PID считает зомби завершённым: в контейнере, где PID 1 не пожинает
сирот, убитый внук остаётся ``<defunct>``, и ``os.kill(pid, 0)`` по нему успешен.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

import pytest


pytestmark = pytest.mark.smoke

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = ROOT / "scripts" / "dsh_pilot_preflight.sh"

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
    printf '%s\\n' \\
      '{"type":"step/end","usage":{"inputTokens":11,"outputTokens":7,"cacheReadTokens":3,"reasoningTokens":1}}' \\
      '{"type":"tool/call"}' \\
      '{"type":"user/message"}' \\
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

    def env(self, **overrides: str | None) -> dict[str, str]:
        """Изолированное окружение запуска: реальные DSH_*/DEEPSEEK_* не наследуются."""
        env = {
            "PATH": os.pathsep.join([str(self.bin_dir), os.environ.get("PATH", "/usr/bin:/bin")]),
            "HOME": str(self.home),
            "DSH_PILOT_WORKTREE": str(self.worktree),
            "DSH_PILOT_HOME": str(self.home / "dsh-home"),
            "DSH_PILOT_PROMPT": str(self.prompt),
            "DEEPSEEK_API_KEY": "stub-key-never-used",
            "STUB_LOG": str(self.log_file),
            "STUB_PIDS": str(self.pids_file),
            "STUB_MODE": "normal",
            "STUB_EXIT_CODE": "0",
            "STUB_SESSION": "yes",
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
    )
    try:
        yield harness
    finally:
        harness.kill_leftovers()


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
    """Короткий DSH_PILOT_TIMEOUT_SECONDS соблюдается, а не подменяется дефолтом 300 c."""
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
        assert elapsed < 20, f"лимит 2 c не соблюдён (похоже на дефолт 300 c): {elapsed:.1f}s"
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
    """Без переопределения лимит равен 300 c; обычный прогон не помечен таймаутом."""
    env = pilot.env()
    env.pop("DSH_PILOT_TIMEOUT_SECONDS")
    result = pilot.smoke(env=env)

    assert result.returncode == 0, result.stdout
    assert "timeout_seconds=300" in result.stdout
    assert "timed_out=no" in result.stdout
    assert "exit_code=0" in result.stdout
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
    """Опечатка в лимите — отказ до платного вызова, а не тихий откат к 300 c."""
    env = pilot.env(DSH_PILOT_TIMEOUT_SECONDS="1O")  # буква O вместо нуля
    result = pilot.smoke(env=env)

    assert result.returncode == 1, result.stdout
    assert "DSH_PILOT_TIMEOUT_SECONDS" in result.stdout
    assert "paid-run" not in pilot.log_text()


@pytest.mark.parametrize(
    ("variable", "expected_range"),
    [
        ("DSH_PILOT_TIMEOUT_SECONDS", "1..300"),
        ("DSH_PILOT_TIMEOUT_GRACE_SECONDS", "1..10"),
    ],
)
def test_explicitly_empty_setting_fails_before_paid_run(
    pilot: _Pilot, variable: str, expected_range: str
) -> None:
    """Явно пустое значение — отказ, а не подстановка дефолта 300/5.

    Пустая переменная (нерасширившаяся подстановка в CI, обнулённая настройка)
    раньше молча получала дефолт: ветка отказа для ``''`` была недостижима, и
    платный вызов стартовал. Разница между «не задано» и «задано пустым» обязана
    сохраняться до валидации: «не задано» — это по-прежнему дефолт 300/5, и он
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
        "301",
        "86400",
        "0",
        "-5",
        "1O",
        # 20 значащих цифр: `[ -gt ]` считает в 64 битах и падает ошибкой, которую
        # условие `if` принимает за «ложь» — без проверки длины такой лимит прошёл бы.
        "99999999999999999999",
    ],
)
def test_limit_outside_1_300_fails_before_paid_run(pilot: _Pilot, value: str) -> None:
    """Верхняя граница обязательна: 301/86400 (и 0/минус/мусор) — отказ, ноль вызовов."""
    env = pilot.env(DSH_PILOT_TIMEOUT_SECONDS=value)
    result = pilot.smoke(env=env)

    assert result.returncode == 1, result.stdout
    # Сообщение обязано называть и наблюдаемое значение, и допустимый диапазон.
    assert f"DSH_PILOT_TIMEOUT_SECONDS='{value}'" in result.stdout
    assert "1..300" in result.stdout
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


def test_upper_bounds_300_and_10_are_accepted_and_observable(pilot: _Pilot) -> None:
    """Границы 300 и 10 принимаются: валидация не отказывает и стаб реально стартует.

    Ожидания 300 c здесь нет и быть не должно: стаб завершается сразу, поэтому
    проверяются ровно два факта — значение прошло валидацию (нет ни fail-closed
    отказа, ни таймаута) и платный прогон действительно начался (стаб получил
    вызов). Соблюдение самого лимита проверяется отдельными тестами с коротким
    лимитом; подменять 300 на маленькое число, чтобы «проверить границу», нельзя.
    """
    env = pilot.env(DSH_PILOT_TIMEOUT_SECONDS="300", DSH_PILOT_TIMEOUT_GRACE_SECONDS="10")
    started = time.monotonic()
    result = pilot.smoke(env=env)
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stdout
    # 1. Валидация значение приняла: ни отказа, ни сработавшего таймаута.
    assert "ПРЕДПОЛЁТ НЕ ПРОЙДЕН" not in result.stdout
    assert "ТАЙМАУТ" not in result.stdout
    # 2. Прогон дошёл до платного вызова: стаб запущен ровно один раз.
    assert pilot.paid_invocations() == 1, pilot.log_text()
    # 3. Лимит 300 c не выдерживался ожиданием — стаб вышел сам (иначе здесь было бы ~300 c).
    assert elapsed < 20, f"проверка границы 300 c ушла в ожидание лимита: {elapsed:.1f}s"
    assert "жёсткий лимит платного прогона: 300s" in result.stdout
    assert "через 10s SIGKILL" in result.stdout
    assert "timeout_seconds=300" in result.stdout
    assert "timeout_grace_seconds=10" in result.stdout
    assert "timed_out=no" in result.stdout


def test_default_grace_is_five_and_observable(pilot: _Pilot) -> None:
    """Дефолтный grace (5 c) виден и в строке лимита, и в метриках — без ожидания 300 c."""
    env = pilot.env()
    env.pop("DSH_PILOT_TIMEOUT_SECONDS")
    env.pop("DSH_PILOT_TIMEOUT_GRACE_SECONDS")
    started = time.monotonic()
    result = pilot.smoke(env=env)
    elapsed = time.monotonic() - started

    assert result.returncode == 0, result.stdout
    assert pilot.paid_invocations() == 1, pilot.log_text()
    assert elapsed < 20, f"дефолтный лимит 300 c выдерживался ожиданием: {elapsed:.1f}s"
    assert "жёсткий лимит платного прогона: 300s" in result.stdout
    assert "через 5s SIGKILL" in result.stdout
    assert "timeout_seconds=300" in result.stdout
    assert "timeout_grace_seconds=5" in result.stdout


def test_leading_zero_limit_cannot_smuggle_past_the_ceiling(pilot: _Pilot) -> None:
    """`0400` — это 400 c (отказ), а `0300` печатается канонически как 300."""
    rejected = pilot.smoke(env=pilot.env(DSH_PILOT_TIMEOUT_SECONDS="0400"))
    assert rejected.returncode == 1, rejected.stdout
    assert "DSH_PILOT_TIMEOUT_SECONDS='0400'" in rejected.stdout
    assert pilot.paid_invocations() == 0, pilot.log_text()

    accepted = pilot.smoke(env=pilot.env(DSH_PILOT_TIMEOUT_SECONDS="0300"))
    assert accepted.returncode == 0, accepted.stdout
    assert pilot.paid_invocations() == 1, pilot.log_text()
    assert "timeout_seconds=300" in accepted.stdout


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
