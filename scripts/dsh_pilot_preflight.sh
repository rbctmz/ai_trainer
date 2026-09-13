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
set -euo pipefail

DSH_VERSION_PIN="0.1.0-rc.6"
PROFILE="headless"
WORKTREE="${DSH_PILOT_WORKTREE:-/tmp/dsh-pilot-wt}"
PILOT_HOME="${DSH_PILOT_HOME:-/tmp/dsh-home-pilot}"
PROMPT_FILE="${DSH_PILOT_PROMPT:-}"
MODE="prepare"
ALLOW_PAID=0

usage() {
  sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    prepare) MODE="prepare" ;;
    smoke) MODE="smoke" ;;
    --allow-paid-call) ALLOW_PAID=1 ;;
    -h|--help) usage 0 ;;
    *) echo "неизвестный аргумент: $1" >&2; usage 2 ;;
  esac
  shift
done

fail() { echo "ПРЕДПОЛЁТ НЕ ПРОЙДЕН: $*" >&2; exit 1; }
ok() { echo "  ✔ $*"; }

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

echo "== 5. Модель и режим разрешений профиля =="
(cd "$WORKTREE" && DSH_HOME="$PILOT_HOME" dsh --profile "$PROFILE" --dump-config 2>/dev/null) \
  | grep -E "^\s+(provider|model):" | sed 's/^/  /' || true
ok "permission mode по умолчанию: workspace-write (переопределяется DSH_PERMISSION_MODE)"

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

echo "== 6. Read-only smoke (платный вызов) =="
[ "$ALLOW_PAID" -eq 1 ] || fail "smoke требует --allow-paid-call: платный модельный вызов разрешается владельцем отдельно"
[ -n "${DEEPSEEK_API_KEY:-}" ] || fail "DEEPSEEK_API_KEY не задан в окружении запуска"
[ -n "$PROMPT_FILE" ] && [ -f "$PROMPT_FILE" ] || fail "DSH_PILOT_PROMPT должен указывать на файл с задачей"

PROMPT_SHA="$(shasum -a 256 "$PROMPT_FILE" | cut -d' ' -f1)"
STARTED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
START_EPOCH="$(date +%s)"
set +e
(cd "$WORKTREE" && DSH_HOME="$PILOT_HOME" dsh --profile "$PROFILE" "$(cat "$PROMPT_FILE")")
EXIT_CODE=$?
set -e
DURATION=$(( $(date +%s) - START_EPOCH ))

echo "== 7. Проверка read-only и метрики =="
after="$(git -C "$WORKTREE" status --porcelain)"
if [ -z "$after" ]; then ok "дерево после smoke не изменилось (read-only подтверждён)"; else echo "  ! дерево изменилось:"; echo "$after"; fi

SESSION_DIR="$PILOT_HOME/sessions"
SESSION_FILE="$(find "$SESSION_DIR" -name 'session.jsonl.zstd' -newermt "-${DURATION} seconds" 2>/dev/null | head -1 || true)"

echo
echo "--- экспериментальные метрики пилота ---"
printf 'dsh_version=%s\n' "$DSH_VERSION_PIN"
printf 'profile=%s\n' "$PROFILE"
printf 'starting_sha=%s\n' "$START_SHA"
printf 'prompt_sha256=%s\n' "$PROMPT_SHA"
printf 'started_at=%s\n' "$STARTED_AT"
printf 'duration_seconds=%s\n' "$DURATION"
printf 'exit_code=%s\n' "$EXIT_CODE"
printf 'worktree_clean_after=%s\n' "$([ -z "$after" ] && echo yes || echo no)"
printf 'session_file=%s\n' "${SESSION_FILE:-not found}"
if [ -n "${SESSION_FILE:-}" ] && command -v zstd >/dev/null 2>&1; then
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
fi
echo "cost=not captured (нужна таблица цен; токены записаны выше)"
exit "$EXIT_CODE"
