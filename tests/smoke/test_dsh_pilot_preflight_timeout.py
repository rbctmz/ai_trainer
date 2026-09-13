"""Жёсткий таймаут платного smoke в ``scripts/dsh_pilot_preflight.sh``.

Реального модельного вызова и сети здесь нет: ``dsh`` подменён стабом в
``tmp_path/bin``, который умеет зависать (игнорируя SIGTERM), падать и
завершаться успешно, а ``zstd`` — выводить файл сессии «как есть», чтобы тест не
зависел от внешнего бинаря. Проверяются только гарантии процесса: по истечении
лимита умирает вся группа процессов прогона (включая внуков, игнорирующих
SIGTERM), скрипт выходит с 124, метрики печатают ``timed_out``/``timeout_seconds``,
а обычные пути (успех, код возврата модели) и прежний гейтинг не меняются.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess
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
    while :; do sleep 1; done
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
_STUB_ZSTD = """#!/usr/bin/env bash
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


def _pid_alive(pid: int) -> bool:
    """Проверка живости по PID (а не по строке в логе стаба)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
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

    def pids(self) -> dict[str, int]:
        pids: dict[str, int] = {}
        if not self.pids_file.exists():
            return pids
        for line in self.pids_file.read_text(encoding="utf-8").splitlines():
            name, _, raw = line.partition("=")
            if name and raw.strip().isdigit():
                pids[name] = int(raw)
        return pids

    def wait_for_pids(self, timeout: float = 20.0) -> dict[str, int]:
        """Ждём, пока стаб запишет PID себя и внука (без угадывания sleep'ов)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pids = self.pids()
            if {"stub", "grandchild"} <= set(pids):
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


def test_prompt_never_read_project_env_and_always_passed_as_absolute_path(pilot: _Pilot) -> None:
    """Стаб видит cwd=worktree и абсолютный промпт; проектный .env не создаётся и не читается."""
    env = pilot.env()
    result = pilot.smoke(env=env)

    assert result.returncode == 0, result.stdout
    log = pilot.log_text()
    assert f"cwd={pilot.worktree}" in log
    assert not (pilot.worktree / ".env").exists()
