#!/usr/bin/env bash
# DeepSeek Harness pilot preflight (developer preview, pinned 0.1.0-rc.6).
#
# Назначение: воспроизводимо подготовить изолированный запуск DSH и — только по
# явному разрешению — выполнить один read-only smoke. Скрипт никогда не берёт
# креды из проектного `.env`: DSH сам отказывается читать `DEEPSEEK_BASE_URL`
# оттуда, а ключ и endpoint обязаны приходить из окружения запускающего процесса.
#
# Режимы:
#   prepare   (по умолчанию, бесплатно, без вызова модели) — проверить версию,
#             worktree без `.env`, чистоту дерева, материализовать профиль
#             `headless` в отдельном DSH_HOME, проверить наличие кред и показать
#             точную команду платного smoke.
#   smoke     (только с --allow-paid-call) — один headless-прогон read-only
#             задачи, с записью exit code, длительности, SHA промпта, пути
#             сессии и проверкой, что дерево осталось неизменным.
#
# Примеры:
#   scripts/dsh_pilot_preflight.sh
#   DEEPSEEK_API_KEY=... scripts/dsh_pilot_preflight.sh --smoke --allow-paid-call
#
# Явная лазейка для расхождения профиля (по умолчанию выключена и не ослабляет
# проверку): DSH_PILOT_ACCEPT_CONFIG_DRIFT=1 понижает расхождение эффективного
# провайдера/модели/режима разрешений до громкого предупреждения.
set -euo pipefail

DSH_VERSION_PIN="0.1.0-rc.6"
PROFILE="headless"
WORKTREE="${DSH_PILOT_WORKTREE:-/tmp/dsh-pilot-wt}"
PILOT_HOME="${DSH_PILOT_HOME:-/tmp/dsh-home-pilot}"
PROMPT_FILE="${DSH_PILOT_PROMPT:-}"
MODE="prepare"
ALLOW_PAID=0
# Закреплённая конфигурация эксперимента (runbook, «Неподвижные правила»). Любое
# расхождение эффективного профиля — провал, а не предупреждение: иначе пилот
# молча измеряет не ту модель/провайдера.
PIN_PROVIDER="deepseek-official"
PIN_MODEL="deepseek-v4-flash"
PIN_PERMISSION_MODE="workspace-write"
ACCEPT_DRIFT="${DSH_PILOT_ACCEPT_CONFIG_DRIFT:-0}"

usage() {
  sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    prepare|--prepare) MODE="prepare" ;;
    smoke|--smoke) MODE="smoke" ;;
    --allow-paid-call) ALLOW_PAID=1 ;;
    -h|--help) usage 0 ;;
    *) echo "неизвестный аргумент: $1" >&2; usage 2 ;;
  esac
  shift
done

fail() { echo "ПРЕДПОЛЁТ НЕ ПРОЙДЕН: $*" >&2; exit 1; }
ok() { echo "  ✔ $*"; }
warn() { echo "  ! $*" >&2; }

# --- разбор эффективной конфигурации профиля -------------------------------
# `--dump-config` печатает скомпонованное дерево (без вычисления !!js): записи
# `agent-default-model` и `sandbox-policy` показывают, что реально применилось —
# включая пользовательский слой $DSH_HOME/profiles/<profile>/cordis.patch.yml.
# Функции читают дамп со stdin, поэтому dsh вызывается один раз и разбор
# проверяется на сохранённом дампе.
effective_provider() {
  awk '
    /^- id: agent-default-model$/ { entry=1; next }
    entry && /^- / { entry=0 }
    entry && /^    provider: .+/ { sub(/^    provider: /, ""); print; exit }
  '
}
effective_model() {
  awk '
    /^- id: agent-default-model$/ { entry=1; next }
    entry && /^- / { entry=0 }
    entry && /^    model: .+/ { sub(/^    model: /, ""); print; exit }
  '
}
# Литерал в sandbox-policy означает, что базовое `process.env.DSH_PERMISSION_MODE`
# перекрыто (обычно пользовательским слоем) — это и есть эффективный режим.
effective_sandbox_mode() {
  awk '
    /^- id: sandbox-policy$/ { entry=1; next }
    entry && /^- / { entry=0 }
    entry && /^    mode: .+/ { sub(/^    mode: /, ""); print; exit }
  '
}

echo "== 1. Версия harness =="
installed="$(dsh --version 2>/dev/null | tr -d '[:space:]')"
[ "$installed" = "$DSH_VERSION_PIN" ] || fail "установлена '$installed', закреплена '$DSH_VERSION_PIN' (обновлять во время эксперимента нельзя)"
ok "dsh $installed (закреплено)"

echo "== 2. Изолированный worktree без .env =="
[ -d "$WORKTREE" ] || fail "нет worktree $WORKTREE (создайте: git worktree add --detach $WORKTREE main)"
[ ! -e "$WORKTREE/.env" ] || fail "$WORKTREE/.env существует — DSH откажется стартовать; нужен worktree без проектного .env"
ok "worktree $WORKTREE, проектного .env нет"
dirty="$(git -C "$WORKTREE" status --porcelain)"
[ -z "$dirty" ] || fail "дерево worktree не чистое:\n$dirty"
START_SHA="$(git -C "$WORKTREE" rev-parse HEAD)"
ok "дерево чистое, starting SHA $START_SHA"

echo "== 3. Отдельный DSH_HOME и профиль =="
mkdir -p "$PILOT_HOME"
# --dump-config материализует профиль и печатает дерево плагинов; модельного вызова нет.
if ! (cd "$WORKTREE" && DSH_HOME="$PILOT_HOME" dsh --profile "$PROFILE" --dump-config >/dev/null 2>&1); then
  fail "профиль '$PROFILE' не поднялся в $PILOT_HOME"
fi
ok "DSH_HOME=$PILOT_HOME, профиль '$PROFILE' материализован (без вызова модели)"

echo "== 4. Креды приходят из окружения, а не из файла =="
if [ -n "${DEEPSEEK_API_KEY:-}" ]; then ok "DEEPSEEK_API_KEY: задан (значение не печатается)"; else echo "  ! DEEPSEEK_API_KEY не задан — платный smoke невозможен"; fi
if [ -n "${DEEPSEEK_BASE_URL:-}" ]; then ok "DEEPSEEK_BASE_URL: задан в окружении (значение не печатается)"; else ok "DEEPSEEK_BASE_URL: не задан — будет официальный endpoint профиля"; fi
if grep -q '^DEEPSEEK_BASE_URL=' "$WORKTREE/.env" 2>/dev/null; then fail "endpoint найден в .env worktree"; fi

echo "== 5. Эффективный профиль: провайдер, модель, режим разрешений =="
if ! CONFIG_DUMP="$(cd "$WORKTREE" && DSH_HOME="$PILOT_HOME" dsh --profile "$PROFILE" --dump-config 2>/dev/null)"; then
  fail "не удалось прочитать эффективную конфигурацию профиля '$PROFILE' (dsh --profile $PROFILE --dump-config)"
fi
printf '%s\n' "$CONFIG_DUMP" | grep -E "^\s+(provider|model):" | sed 's/^/  /' || true

DRIFT=0
drift() {
  DRIFT=$((DRIFT + 1))
  if [ "$ACCEPT_DRIFT" = "1" ]; then
    warn "РАСХОЖДЕНИЕ ПРОФИЛЯ (принято через DSH_PILOT_ACCEPT_CONFIG_DRIFT=1): $*"
  else
    echo "  ✘ расхождение: $*" >&2
  fi
}

OBSERVED_PROVIDER="$(printf '%s\n' "$CONFIG_DUMP" | effective_provider)"
OBSERVED_MODEL="$(printf '%s\n' "$CONFIG_DUMP" | effective_model)"
[ -n "$OBSERVED_PROVIDER" ] || drift "не удалось определить эффективного провайдера из --dump-config профиля '$PROFILE'"
[ -n "$OBSERVED_MODEL" ] || drift "не удалось определить эффективную модель из --dump-config профиля '$PROFILE'"
[ -z "$OBSERVED_PROVIDER" ] || [ "$OBSERVED_PROVIDER" = "$PIN_PROVIDER" ] \
  || drift "провайдер: ожидался '$PIN_PROVIDER', наблюдался '$OBSERVED_PROVIDER'"
[ -z "$OBSERVED_MODEL" ] || [ "$OBSERVED_MODEL" = "$PIN_MODEL" ] \
  || drift "модель: ожидалась '$PIN_MODEL', наблюдалась '$OBSERVED_MODEL'"

# Режим разрешений: базовое значение берётся из окружения, но пользовательский
# слой DSH_HOME может перекрыть его литералом в sandbox-policy.
SANDBOX_MODE="$(printf '%s\n' "$CONFIG_DUMP" | effective_sandbox_mode)"
case "$SANDBOX_MODE" in
  *'!!js'*|'') EFFECTIVE_PERMISSION_MODE="${DSH_PERMISSION_MODE:-$PIN_PERMISSION_MODE}" ;;
  *) EFFECTIVE_PERMISSION_MODE="$SANDBOX_MODE" ;;
esac
[ "$EFFECTIVE_PERMISSION_MODE" = "$PIN_PERMISSION_MODE" ] \
  || drift "режим разрешений: ожидался '$PIN_PERMISSION_MODE', наблюдался '$EFFECTIVE_PERMISSION_MODE' (DSH_PERMISSION_MODE=${DSH_PERMISSION_MODE:-<не задан>}, sandbox-policy=${SANDBOX_MODE:-<нет>})"

if [ -n "${DSH_TELEMETRY_MODE:-}" ] && [ "$DSH_TELEMETRY_MODE" != "DISABLED" ]; then
  drift "DSH_TELEMETRY_MODE=$DSH_TELEMETRY_MODE — пилот обязан идти с выключенной телеметрией (ожидалось DISABLED)"
fi
if [ -n "${DSH_TOOLS_MODE:-}" ]; then
  case "$DSH_TOOLS_MODE" in
    read-only|full) ok "DSH_TOOLS_MODE=$DSH_TOOLS_MODE (допустимо)" ;;
    *) drift "DSH_TOOLS_MODE=$DSH_TOOLS_MODE — ожидалось read-only или full" ;;
  esac
fi

if [ "$DRIFT" -gt 0 ] && [ "$ACCEPT_DRIFT" != "1" ]; then
  fail "эффективный профиль отличается от закреплённого: провайдер '$PIN_PROVIDER', модель '$PIN_MODEL', режим '$PIN_PERMISSION_MODE'. Используйте свежий пустой DSH_PILOT_HOME (переиспользованный \$DSH_HOME/profiles/$PROFILE/cordis.patch.yml может перекрывать значения) или, осознанно и письменно, DSH_PILOT_ACCEPT_CONFIG_DRIFT=1."
fi
if [ "$DRIFT" -gt 0 ]; then
  warn "профиль отличается от закреплённого, но прогон продолжен по DSH_PILOT_ACCEPT_CONFIG_DRIFT=1 (наблюдалось: provider=${OBSERVED_PROVIDER:-unknown}, model=${OBSERVED_MODEL:-unknown}, permission_mode=${EFFECTIVE_PERMISSION_MODE:-unknown})"
else
  ok "профиль соответствует закреплённому: provider=$PIN_PROVIDER, model=$PIN_MODEL, permission_mode=$PIN_PERMISSION_MODE"
fi

if [ "$MODE" = "prepare" ]; then
  cat <<EOF

Подготовка завершена. Платный модельный вызов НЕ выполнялся.

Команда одного read-only smoke (запускать только после явного разрешения владельца):

  DSH_PILOT_WORKTREE=$WORKTREE \\
  DSH_PILOT_HOME=$PILOT_HOME \\
  DSH_PILOT_PROMPT=<файл с read-only задачей> \\
  scripts/dsh_pilot_preflight.sh --smoke --allow-paid-call

EOF
  exit 0
fi

echo "== 6. Готовность метрик (до платного вызова) =="
# Метрики оплаченного прогона обязаны быть извлекаемы: без zstd/python3 данные
# сессии теряются, поэтому проверяем их ДО вызова модели, а не после.
command -v zstd >/dev/null 2>&1 || fail "нет исполняемого 'zstd' в PATH — без него нельзя распаковать \$DSH_HOME/sessions/*.jsonl.zstd; установите zstd (например: brew install zstd) и повторите"
command -v python3 >/dev/null 2>&1 || fail "нет исполняемого 'python3' в PATH — без него нельзя агрегировать токены и шаги; установите python3 и повторите"
ok "zstd и python3 доступны — метрики сессии будут извлечены"

echo "== 7. Read-only smoke (платный вызов) =="
[ "$ALLOW_PAID" -eq 1 ] || fail "smoke требует --allow-paid-call: платный модельный вызов разрешается владельцем отдельно"
[ -n "$PROMPT_FILE" ] || fail "DSH_PILOT_PROMPT должен указывать на файл с задачей"
# Путь к промпту обязан быть абсолютным ДО входа в worktree: runbook показывает
# относительный путь из каталога вызова, а smoke выполняется с cwd=$WORKTREE.
[ -f "$PROMPT_FILE" ] || fail "файл промпта не найден: DSH_PILOT_PROMPT='$PROMPT_FILE' (каталог вызова $PWD). Пустой или отсутствующий промпт читать нельзя"
[ -r "$PROMPT_FILE" ] || fail "файл промпта не читается: '$PROMPT_FILE'"
PROMPT_PATH="$(realpath "$PROMPT_FILE" 2>/dev/null || true)"
[ -n "$PROMPT_PATH" ] || fail "не удалось разрешить DSH_PILOT_PROMPT='$PROMPT_FILE' в абсолютный путь (нужен realpath или существующий файл)"
[ -f "$PROMPT_PATH" ] || fail "разрешённый путь промпта не найден: '$PROMPT_PATH' (из '$PROMPT_FILE')"
[ -n "${DEEPSEEK_API_KEY:-}" ] || fail "DEEPSEEK_API_KEY не задан в окружении запуска"
PROMPT_FILE="$PROMPT_PATH"
ok "промпт разрешён в абсолютный путь: $PROMPT_FILE"
ok "cwd smoke будет $WORKTREE — промпт найден по абсолютному пути независимо от каталога вызова"

PROMPT_SHA="$(shasum -a 256 "$PROMPT_FILE" | cut -d' ' -f1)"
STARTED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
START_EPOCH="$(date +%s)"
# Опорная метка времени начала прогона: поиск файла сессии идёт по ней, а не по
# `-newermt "-N seconds"` (на BSD/macOS такая запись не матчит свежие файлы, и
# оплаченные метрики молча терялись бы).
RUN_STAMP="/tmp/.dsh-pilot-smoke-start.$$"
: > "$RUN_STAMP" || fail "не удалось создать метку времени $RUN_STAMP"
trap 'rm -f "$RUN_STAMP"' EXIT
# set +e: ненулевой exit самого процесса DSH — это измеряемый результат smoke, а
# не ошибка preflight; падение самого скрипта также превратится в exit_code.
set +e
(cd "$WORKTREE" && DSH_HOME="$PILOT_HOME" dsh --profile "$PROFILE" "$(cat "$PROMPT_FILE")")
EXIT_CODE=$?
set -e
[ -n "${EXIT_CODE:-}" ] || EXIT_CODE=1
DURATION=$(( $(date +%s) - START_EPOCH ))

echo "== 8. Проверка read-only и метрики =="
after="$(git -C "$WORKTREE" status --porcelain)"
END_SHA="$(git -C "$WORKTREE" rev-parse HEAD)"
HEAD_UNCHANGED=yes
[ "$END_SHA" = "$START_SHA" ] || HEAD_UNCHANGED=no
WORKTREE_CLEAN=yes
[ -z "$after" ] || WORKTREE_CLEAN=no

SESSIONS_ROOT="$PILOT_HOME/sessions"
# Сессия: самый свежий session.jsonl.zstd, появившийся не раньше старта прогона.
if [ -d "$SESSIONS_ROOT" ]; then
  # Только сессия, созданная этим прогоном: fallback на любую сессию из
  # DSH_PILOT_HOME (#576 review, P1) публиковал метрики прошлого прогона как
  # метрики оплаченного — токены и tool calls чужой сессии выглядели текущими.
  SESSION_FILE="$(find "$SESSIONS_ROOT" -name 'session.jsonl.zstd' -newer "$RUN_STAMP" 2>/dev/null | sort | tail -1 || true)"
else
  SESSION_FILE=""
fi

# Метрики печатаются ровно один раз, чтобы оплаченные числа не потерялись и при
# провале проверок read-only.
METRICS_DONE=0
emit_metrics() {
  [ "$METRICS_DONE" -eq 0 ] || return 0
  METRICS_DONE=1
  echo
  echo "--- экспериментальные метрики пилота ---"
  printf 'dsh_version=%s\n' "$DSH_VERSION_PIN"
  printf 'profile=%s\n' "$PROFILE"
  printf 'effective_provider=%s\n' "${OBSERVED_PROVIDER:-unknown}"
  printf 'effective_model=%s\n' "${OBSERVED_MODEL:-unknown}"
  printf 'permission_mode=%s\n' "${EFFECTIVE_PERMISSION_MODE:-unknown}"
  printf 'starting_sha=%s\n' "$START_SHA"
  printf 'ending_sha=%s\n' "${END_SHA:-unknown}"
  printf 'prompt_sha256=%s\n' "$PROMPT_SHA"
  printf 'started_at=%s\n' "$STARTED_AT"
  printf 'duration_seconds=%s\n' "$DURATION"
  printf 'exit_code=%s\n' "$EXIT_CODE"
  printf 'worktree_clean_after=%s\n' "$WORKTREE_CLEAN"
  printf 'head_unchanged=%s\n' "$HEAD_UNCHANGED"
  printf 'session_file=%s\n' "${SESSION_FILE:-not found}"
  if [ -n "${SESSION_FILE:-}" ]; then
    zstd -dc "$SESSION_FILE" 2>/dev/null | python3 -c '
import json, sys
tok_in = tok_out = cache = reasoning = calls = steps = user_msgs = 0
for line in sys.stdin:
    try:
        rec = json.loads(line)
    except Exception:
        continue
    if not isinstance(rec, dict):
        continue
    usage = rec.get("usage") or {}
    if isinstance(usage, dict) and usage:
        tok_in += int(usage.get("inputTokens") or 0)
        tok_out += int(usage.get("outputTokens") or 0)
        cache += int(usage.get("cacheReadTokens") or 0)
        reasoning += int(usage.get("reasoningTokens") or 0)
    calls += 1 if rec.get("type") == "tool/call" else 0
    steps += 1 if rec.get("type") == "step/end" else 0
    user_msgs += 1 if rec.get("type") == "user/message" else 0
print(f"tokens_input={tok_in}")
print(f"tokens_output={tok_out}")
print(f"tokens_cache_read={cache}")
print(f"tokens_reasoning={reasoning}")
print(f"tool_calls={calls}")
print(f"steps={steps}")
print(f"human_messages_in_session={user_msgs}  # больше 1 => были вмешательства")
'
  else
    printf 'session_metrics=not collected (session file not found in %s)\n' "$SESSIONS_ROOT"
  fi
  echo "cost=not captured (нужна таблица цен; токены записаны выше)"
}

# Проверки read-only копят нарушения: метрики печатаются, затем ненулевой exit.
CHECK_FAIL=0
check() {
  # $1 — 0/1 (успех/провал), $2 — сообщение об успехе, $3 — сообщение о провале.
  if [ "$1" -eq 0 ]; then
    ok "$2"
  else
    CHECK_FAIL=1
    echo "  ✘ $3" >&2
  fi
}
check "$([ -z "$after" ] && echo 0 || echo 1)" \
  "дерево worktree после smoke не изменилось (read-only подтверждён)" \
  "дерево worktree после smoke ИЗМЕНЕНО — read-only гарантия нарушена, прогон недействителен"
[ -z "$after" ] || { echo "  изменения в worktree:" >&2; echo "$after" >&2; }
check "$([ "$HEAD_UNCHANGED" = yes ] && echo 0 || echo 1)" \
  "HEAD не двигался: $START_SHA (чистое дерево без проверки SHA не доказывает read-only — коммит во время smoke оставил бы status пустым)" \
  "HEAD сдвинулся: $START_SHA -> $END_SHA — во время smoke сделан коммит, значит прогон не был read-only"
[ "$HEAD_UNCHANGED" = yes ] || echo "  HEAD после smoke: $END_SHA" >&2
check "$([ -n "${SESSION_FILE:-}" ] && echo 0 || echo 1)" \
  "сессия сохранена: ${SESSION_FILE:-}" \
  "файл сессии не найден в $SESSIONS_ROOT — оплаченные метрики потеряны, прогон нельзя засчитывать"

emit_metrics

if [ "$CHECK_FAIL" -ne 0 ]; then
  exit 1
fi
exit "$EXIT_CODE"
