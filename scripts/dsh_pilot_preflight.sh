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
#             сессии и проверкой, что дерево осталось неизменным. Платный вызов
#             ограничен жёстким лимитом 600 c (DSH_PILOT_TIMEOUT_SECONDS,
#             допустимо 1..900; пустое значение — отказ, а не дефолт): лимит
#             отсчитывается монотонными часами (time.monotonic), поэтому перевод
#             настенных часов его не растягивает. По истечении вся группа
#             процессов прогона получает SIGTERM, затем через
#             DSH_PILOT_TIMEOUT_GRACE_SECONDS (допустимо 1..10, по умолчанию 5) —
#             SIGKILL, и скрипт выходит с кодом 124. Группа проверяется и после
#             выхода её лидера: потомок, переживший лидера, добивается, а прогон
#             признаётся недействительным (leftover_processes_killed=yes).
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
NODE_DIR="${DSH_PILOT_NODE_DIR:-}"
MODE="prepare"
ALLOW_PAID=0
# Закреплённая конфигурация эксперимента (runbook, «Неподвижные правила»). Любое
# расхождение эффективного профиля — провал, а не предупреждение: иначе пилот
# молча измеряет не ту модель/провайдера.
PIN_PROVIDER="deepseek-official"
PIN_MODEL="deepseek-v4-flash"
PIN_PERMISSION_MODE="workspace-write"
ACCEPT_DRIFT="${DSH_PILOT_ACCEPT_CONFIG_DRIFT:-0}"
# Жёсткий лимит платного smoke и grace-период перед SIGKILL. Значения читаются
# здесь, но проверяются только перед самим платным вызовом (шаг 7): бесплатный
# prepare не должен зависеть от настроек таймаута.
# Развёртка `-`, а не `:-`: явно пустое значение обязано дойти до валидации и
# упасть. С `:-` `DSH_PILOT_TIMEOUT_SECONDS=` (нерасширившаяся переменная в CI,
# обнулённая настройка) тихо подменялось бы дефолтом, ветка отказа для `''`
# стала бы недостижимой, и платный вызов стартовал бы с дефолтным лимитом.
# Дефолт поднят с 300 до 600 c: оплаченный прогон пилота #577 на задаче из трёх
# файлов (74 tool calls, 57 шагов) упёрся в 300 c на середине работы и не выдал
# ни финального ответа, ни коммита — то есть лимит обрывал задачу такого размера.
# Верхняя граница остаётся жёсткой: 900 c — предел, после которого «лимит» уже
# не защищал бы бюджет от зависшего вызова.
TIMEOUT_SECONDS="${DSH_PILOT_TIMEOUT_SECONDS-600}"
TIMEOUT_GRACE_SECONDS="${DSH_PILOT_TIMEOUT_GRACE_SECONDS-5}"
# Верхние границы закреплены константами, чтобы «жёсткий лимит» из шапки был
# проверяемым фактом, а не обещанием: не более 900 c на сам прогон и не более
# 10 c на grace после SIGTERM (иначе уже оплаченный прогон растягивался бы).
TIMEOUT_MAX_SECONDS=900
TIMEOUT_GRACE_MAX_SECONDS=10

usage() {
  sed -n '2,33p' "$0" | sed 's/^# \{0,1\}//'
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

echo "== 0. Node runtime для DSH =="
# DSH 0.1.0-rc.6 загружает плагины через API, которых нет в части Node 20
# runtime. Номер версии сам по себе не является доказательством: проверяем ровно
# нужные capability до первого запуска dsh и тем более до платного вызова.
# Явный каталог позволяет выбрать уже установленный runtime без установки
# пакетов и без изменения системного symlink. Он обязан быть абсолютным и
# содержать node: молчаливый откат на PATH снова запустил бы smoke не тем runtime.
if [ -n "$NODE_DIR" ]; then
  case "$NODE_DIR" in
    /*) ;;
    *) fail "DSH_PILOT_NODE_DIR='$NODE_DIR' — нужен absolute path к каталогу с исполняемым node" ;;
  esac
  [ -d "$NODE_DIR" ] || fail "DSH_PILOT_NODE_DIR='$NODE_DIR' — каталог не существует"
  [ -x "$NODE_DIR/node" ] || fail "DSH_PILOT_NODE_DIR='$NODE_DIR' — нет исполняемого '$NODE_DIR/node'"
  NODE_DIR="$(cd "$NODE_DIR" && pwd -P)"
  export PATH="$NODE_DIR:$PATH"
fi
command -v node >/dev/null 2>&1 || fail "Node runtime не найден в PATH; задайте DSH_PILOT_NODE_DIR абсолютным каталогом с совместимым node"
NODE_PATH="$(command -v node)"
NODE_VERSION="$(node --version 2>/dev/null || true)"
[ -n "$NODE_VERSION" ] || fail "Node runtime '$NODE_PATH' не сообщил версию"
if ! node -e '
const zlib = require("node:zlib");
const moduleApi = require("node:module");
const missing = [];
if (typeof Promise.withResolvers !== "function") missing.push("Promise.withResolvers");
if (typeof zlib.createZstdDecompress !== "function") missing.push("node:zlib.createZstdDecompress");
if (typeof moduleApi.stripTypeScriptTypes !== "function") missing.push("node:module.stripTypeScriptTypes");
if (missing.length) {
  console.error(missing.join(", "));
  process.exit(1);
}
' >/dev/null 2>&1; then
  fail "Node runtime '$NODE_PATH' ($NODE_VERSION) несовместим с DSH $DSH_VERSION_PIN: нужны Promise.withResolvers, node:zlib.createZstdDecompress и node:module.stripTypeScriptTypes; выберите совместимый уже установленный runtime через DSH_PILOT_NODE_DIR"
fi
ok "node_path=$NODE_PATH"
ok "node_version=$NODE_VERSION"
ok "Node runtime содержит обязательные API загрузчика DSH"

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

echo "== 3a. Бесплатная проверка загрузчика headless =="
# --dump-config не загружает весь runtime плагинов и ранее проходил даже там,
# где настоящий headless запуск падал до agent loop. --help проходит тот же
# загрузчик приложения, но не отправляет запрос модели и не требует API key.
if ! (cd "$WORKTREE" && DSH_HOME="$PILOT_HOME" dsh --profile "$PROFILE" --help >/dev/null 2>&1); then
  fail "headless loader check не прошёл: 'dsh --profile $PROFILE --help' завершился с ошибкой на Node '$NODE_PATH' ($NODE_VERSION); платный smoke заблокирован"
fi
HEADLESS_LOADER_CHECK=pass
ok "headless_loader_check=$HEADLESS_LOADER_CHECK"

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

  DSH_PILOT_NODE_DIR=$(dirname "$NODE_PATH") \\
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

# --- жёсткий лимит платного вызова -----------------------------------------
# Без лимита зависший модельный вызов держит preflight неограниченно долго и
# жжёт бюджет. Мусор в лимите — отказ ДО платного вызова, а не тихий откат к
# 600 c: молчаливая потеря гарантии в этом скрипте запрещена (ср. drift профиля).
# Верхняя граница здесь так же обязательна, как нижняя: `86400` в этом поле
# означало бы «лимита нет», а неограниченный grace растягивал бы прогон уже
# после SIGTERM, то есть оплаченное время шло бы и дальше.
# $1 — имя переменной, $2 — значение, $3 — верхняя граница, $4 — значение по
# умолчанию, $5 — почему верхняя граница важна. Сообщение всегда называет и
# наблюдаемое значение, и допустимый диапазон.
require_seconds_in_range() {
  local name="$1" value="$2" max="$3" default="$4" why="$5"
  case "$value" in
    ''|*[!0-9]*) fail "$name='$value' — нужно целое число секунд в диапазоне 1..$max (по умолчанию $default); $why" ;;
  esac
  # Длина проверяется отдельно, и это не педантизм: `[ -gt ]` считает в 64 битах,
  # а 20-значное значение роняет сравнение ошибкой (rc=2), которую условие `if`
  # принимает за «ложь» — то есть пропустило бы лимит. Порог в 9 цифр безопасен
  # для 64-битного сравнения и всё равно отсекает всё, что больше 900.
  if [ "${#value}" -gt 9 ] || [ "$value" -lt 1 ] || [ "$value" -gt "$max" ]; then
    fail "$name='$value' — допустимый диапазон 1..$max c (по умолчанию $default); $why"
  fi
}
require_seconds_in_range DSH_PILOT_TIMEOUT_SECONDS "$TIMEOUT_SECONDS" \
  "$TIMEOUT_MAX_SECONDS" 600 \
  "значение вне диапазона означало бы, что жёсткого лимита нет"
require_seconds_in_range DSH_PILOT_TIMEOUT_GRACE_SECONDS "$TIMEOUT_GRACE_SECONDS" \
  "$TIMEOUT_GRACE_MAX_SECONDS" 5 \
  "больший grace растягивал бы уже оплаченный прогон после SIGTERM"
# Ведущие нули приводим к десятичной форме: в арифметике bash `$((0900))` — это
# 576, поэтому без нормализации напечатанный лимит разошёлся бы с фактическим
# дедлайном. Проверка выше уже гарантировала, что здесь только цифры.
TIMEOUT_SECONDS=$((10#$TIMEOUT_SECONDS))
TIMEOUT_GRACE_SECONDS=$((10#$TIMEOUT_GRACE_SECONDS))

# Почему группа процессов, а не один PID: dsh запускает дочерние процессы
# (shell, инструменты), и убийство только прямого ребёнка оставило бы внуков
# работать и тратить бюджет. На macOS нет ни `setsid`, ни GNU `timeout`, поэтому
# группа создаётся job control'ом: `set -m` делает фоновый job лидером своей
# группы процессов, и её pgid совпадает с PID лидера — значит `kill -- -PGID`
# бьёт по всем потомкам сразу. Проверено локально: внук, игнорирующий SIGTERM,
# умирает от SIGKILL по группе.
#
# Живость группы считается по *живым*, а не по зомби членам: `kill -0 -- -PGID`
# видит и `<defunct>`, а в контейнере, где PID 1 не пожинает сирот, убитый
# потомок остаётся таким навсегда — тогда группа выглядела бы живой вечно.
# Зомби не может выполняться и не тратит бюджет, поэтому он не считается
# выжившим. Если `ps` недоступен, остаётся консервативный откат на `kill -0`
# (зомби тогда считается живым — как было до этой проверки).
smoke_group_alive() {
  local pgid="$1" table=""
  if table="$(ps -A -o pgid=,stat= 2>/dev/null)" && [ -n "$table" ]; then
    printf '%s\n' "$table" | awk -v pgid="$pgid" '$1 == pgid && $2 !~ /^Z/ { live = 1 } END { exit live ? 0 : 1 }'
    return $?
  fi
  kill -0 -- "-$pgid" 2>/dev/null
}

# --- монотонная шкала времени ------------------------------------------------
# `date +%s` — настенные часы: перевод времени (коррекция NTP, ручная правка)
# назад растянул бы «жёсткий» лимит ровно на величину коррекции, то есть лимит
# перестал бы быть верхней границей. `$SECONDS` для этого тоже не годится: bash
# считает его через gettimeofday (bug-bash, «$SECONDS and timeout values use
# realtime gettimeofday()»), то есть по тем же настенным часам. Замер берётся у
# python3: `time.monotonic()` — CLOCK_MONOTONIC (на macOS mach_absolute_time),
# adjustable=False. Новых требований к окружению это не добавляет: python3 и так
# обязателен для метрик сессии (шаг 6, отказ до платного вызова).
monotonic_ms() { python3 -c 'import time; print(int(time.monotonic() * 1000))'; }

# Завершает всю группу: SIGTERM, grace-период, затем SIGKILL. Возврат 1 означает,
# что смерть группы подтвердить не удалось (SIGKILL не перехватывается, но
# процесс мог остаться в непрерываемом сне) — это громкий провал, а не «ок».
terminate_smoke_group() {
  local pgid="$1" waited=0
  kill -TERM -- "-$pgid" 2>/dev/null || true
  # Как только группа опустела, эскалация не нужна.
  while [ "$waited" -lt "$TIMEOUT_GRACE_SECONDS" ]; do
    smoke_group_alive "$pgid" || return 0
    sleep 1
    waited=$((waited + 1))
  done
  kill -KILL -- "-$pgid" 2>/dev/null || true
  waited=0
  while smoke_group_alive "$pgid"; do
    [ "$waited" -lt 50 ] || return 1
    sleep 0.1
    waited=$((waited + 1))
  done
  return 0
}

ok "жёсткий лимит платного прогона: ${TIMEOUT_SECONDS}s, затем через ${TIMEOUT_GRACE_SECONDS}s SIGKILL всей группе процессов (timeout_seconds/timeout_grace_seconds, exit 124)"

PROMPT_SHA="$(shasum -a 256 "$PROMPT_FILE" | cut -d' ' -f1)"
# Настенные часы дальше участвуют только в читаемой метке времени: ни лимит, ни
# длительность от них не зависят (см. monotonic_ms).
STARTED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
# Старт отсчёта берётся ДО запуска: несколько миллисекунд, потраченных на запуск
# DSH, только укорачивают фактический лимит, то есть в безопасную сторону.
# Проверка часов стоит до платного вызова: недоказуемая граница — это отказ, а не
# «прогон без лимита».
if ! SMOKE_START_MS="$(monotonic_ms)"; then
  fail "не удалось прочитать монотонные часы (python3 time.monotonic) — жёсткий лимит ${TIMEOUT_SECONDS}s недоказуем, платный вызов не стартует"
fi
case "$SMOKE_START_MS" in
  ''|*[!0-9]*) fail "не удалось прочитать монотонные часы (python3 time.monotonic вернул '$SMOKE_START_MS') — жёсткий лимит ${TIMEOUT_SECONDS}s недоказуем, платный вызов не стартует" ;;
esac
SMOKE_LAST_MS="$SMOKE_START_MS"
# Опорная метка времени начала прогона: поиск файла сессии идёт по ней, а не по
# `-newermt "-N seconds"` (на BSD/macOS такая запись не матчит свежие файлы, и
# оплаченные метрики молча терялись бы).
RUN_STAMP="/tmp/.dsh-pilot-smoke-start.$$"
: > "$RUN_STAMP" || fail "не удалось создать метку времени $RUN_STAMP"

TIMED_OUT=no
CLOCK_ERROR=no
LEFTOVERS_KILLED=no
LEFTOVER_PGID=""
SMOKE_PID=""
# Выход скрипта идёт через одну точку: таймаут обязан доехать наружу кодом 124
# даже если пост-обработка (извлечение метрик, git-проверки) оборвётся ошибкой
# под `set -e` — иначе падение zstd/парсера подменяло бы таймаут чужим кодом.
smoke_exit() {
  local code=$?
  rm -f "$RUN_STAMP"
  if [ "${TIMED_OUT:-no}" = yes ] && [ "$code" -ne 124 ]; then
    echo "  ✘ пост-обработка таймаутного прогона оборвалась кодом $code — наружу всё равно идёт 124 (таймаут не маскируется сбоем метрик)" >&2
    exit 124
  fi
  exit "$code"
}
trap smoke_exit EXIT
# Прогон живёт в отдельной группе процессов, поэтому Ctrl-C/Ctrl-\ по скрипту
# терминал больше не доставляет ей: без этой ловушки прерывание preflight
# оставляло бы оплаченный dsh работать. Watchdog-процесса нет вовсе — лимит
# отсчитывается самим скриптом, так что после выхода «своего» процесса не
# остаётся.
trap 'if [ -n "$SMOKE_PID" ]; then terminate_smoke_group "$SMOKE_PID" || true; fi; exit 130' INT TERM HUP

# set +e: ненулевой exit самого процесса DSH — это измеряемый результат smoke, а
# не ошибка preflight; падение самого скрипта также превратится в exit_code.
set +e
# set -m только на время запуска: фоновому job'у нужна своя группа процессов,
# но monitor mode не должен менять поведение остальной части скрипта.
set -m
( cd "$WORKTREE" && exec env DSH_HOME="$PILOT_HOME" dsh --profile "$PROFILE" "$(cat "$PROMPT_FILE")" ) &
SMOKE_PID=$!
set +m
# Отсчёт лимита — в фоне не оставляем: опрос идёт здесь же, поэтому «повисший»
# прогон обнаруживается, а лишний процесс-сторож не создаётся (иначе после
# preflight оставался бы ещё и он). Шаг 0.2 c, а не 1 c: иначе быстрый прогон
# ждал бы лишнюю секунду, а лимит срабатывал бы с секундной задержкой. Часы
# читаются на каждой итерации, поэтому выход за лимит ограничен шагом опроса
# (≤0.2 c); цена — один короткоживущий python3 на итерацию, то есть примерно
# 5 % одного ядра во время платного прогона.
SMOKE_DEADLINE_MS=$(( SMOKE_START_MS + TIMEOUT_SECONDS * 1000 ))
while kill -0 "$SMOKE_PID" 2>/dev/null; do
  SMOKE_NOW_MS="$(monotonic_ms)"
  case "$SMOKE_NOW_MS" in
    ''|*[!0-9]*)
      echo "  ✘ монотонные часы перестали читаться (python3 time.monotonic вернул '$SMOKE_NOW_MS') — жёсткий лимит ${TIMEOUT_SECONDS}s недоказуем, поэтому платный прогон останавливается (fail-closed)" >&2
      CLOCK_ERROR=yes
      break
      ;;
  esac
  SMOKE_LAST_MS="$SMOKE_NOW_MS"
  [ "$SMOKE_NOW_MS" -lt "$SMOKE_DEADLINE_MS" ] || { TIMED_OUT=yes; break; }
  sleep 0.2
done
if [ "$TIMED_OUT" = yes ]; then
  echo "  ✘ ТАЙМАУТ: платный прогон не уложился в ${TIMEOUT_SECONDS}s — убиваю всю группу процессов (SIGTERM, затем через ${TIMEOUT_GRACE_SECONDS}s SIGKILL); это НЕ результат модели, exit code 124" >&2
  # Сюда попадает и остановленный (SIGTTIN/SIGSTOP) процесс: SIGTERM такому не
  # доставляется, но SIGKILL по группе его снимает.
  terminate_smoke_group "$SMOKE_PID" \
    || echo "  ✘ не удалось подтвердить смерть всей группы процессов smoke (pgid $SMOKE_PID)" >&2
elif [ "$CLOCK_ERROR" = yes ]; then
  terminate_smoke_group "$SMOKE_PID" \
    || echo "  ✘ не удалось подтвердить смерть всей группы процессов smoke (pgid $SMOKE_PID)" >&2
elif smoke_group_alive "$SMOKE_PID"; then
  # Лидер вышел, но его группа — нет: асинхронный потомок DSH остался бы
  # работать (и тратить бюджет) после preflight. Прогон принимается только после
  # того, как группа пуста: проверяем и добиваем её ДО `wait`, а не после «ок».
  echo "  ✘ группа процессов smoke пережила своего лидера (pgid $SMOKE_PID) — асинхронный потомок DSH остался бы работать после preflight; убиваю всю группу" >&2
  terminate_smoke_group "$SMOKE_PID" \
    || echo "  ✘ не удалось подтвердить смерть всей группы процессов smoke (pgid $SMOKE_PID)" >&2
  LEFTOVERS_KILLED=yes
  LEFTOVER_PGID="$SMOKE_PID"
fi
wait "$SMOKE_PID"
EXIT_CODE=$?
SMOKE_PID=""
# Финальный замер — тоже монотонный: перевод настенных часов не должен делать
# длительность оплаченного прогона отрицательной или произвольной.
SMOKE_END_MS="$(monotonic_ms)"
case "$SMOKE_END_MS" in ''|*[!0-9]*) SMOKE_END_MS="$SMOKE_LAST_MS" ;; esac
set -e
[ -n "${EXIT_CODE:-}" ] || EXIT_CODE=1
# Таймаут — не «результат модели»: наружу и в метрики идёт конвенциональный 124,
# а не 143/137 от доставленного сигнала.
[ "$TIMED_OUT" = no ] || EXIT_CODE=124
# Нечитаемые часы — тоже не результат модели: код 1 (fail-closed), а не чужой.
[ "$CLOCK_ERROR" = no ] || EXIT_CODE=1
DURATION=$(( (SMOKE_END_MS - SMOKE_START_MS + 500) / 1000 ))

echo "== 8. Проверка read-only и метрики =="
[ "$TIMED_OUT" = no ] \
  || echo "  ✘ прогон прерван таймаутом ${TIMEOUT_SECONDS}s — ответа модели нет, прогон не засчитывается (timed_out=yes, exit 124)" >&2
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
# Провал извлечения метрик (#578 review, P1): для нетаймаутного прогона он
# фатален — runbook требует метрики для зачёта smoke, иначе успешный по коду
# модели прогон засчитывался бы без оплаченных чисел. Для таймаутного прогона
# доминирует 124, поэтому решение принимается ниже и отдельно.
METRICS_FAIL=0
# --- агрегация токенов из session.jsonl.zstd --------------------------------
# Разбор читает usage НА ЛЮБОЙ ГЛУБИНЕ записи, а не только в её корне. Это
# оплаченный урок пилота #577: harness 0.1.0-rc.6 пишет usage вложенно внутри
# `data`, поэтому парсер, смотревший только `rec.get("usage")`, получал
# tokens_*=0, и первая оплаченная сессия осталась без измеренных токенов.
# Точные формы, наблюдавшиеся в сохранённой сессии пилота #577
# (`logs/dsh-pilot-577/.../session.jsonl.zstd`, 1614 записей):
#   1) сверенный шаг модели — `{"type":"assistant/message","data":{"turn":N,
#      "step":M,"usage":{"inputTokens":..,"outputTokens":..,"cacheReadTokens":..,
#      "reasoningTokens":..}}}` — авторитетная запись шага (57 штук);
#   2) стриминговый чанк того же шага — `{"type":"assistant/chunk","data":{"turn":N,
#      "step":M,"chunk":{"type":"usage","usage":{...}}}}` с ТЕМИ ЖЕ числами (57 штук).
# Обе записи описывают один запрос к провайдеру, поэтому суммировать их вместе
# нельзя: это удвоило бы токены. Дубль снимается структурно: у записи берётся
# только первый (ближайший к корню) найденный usage, поэтому у `assistant/chunk`
# это `data.chunk.usage`, а у `assistant/message` — `data.usage`. Вторым рубежом
# идёт дедупликация по (turn, step, значения usage): повтор с теми же числами в
# том же шаге считается одним измерением, разные шаги и разные значения —
# разными. Пропуски любых других форм (в т.ч. `data.message.usage`) считаются
# как есть, без удвоения.
PARSER_PY='
import json, sys
KEYS = ("inputTokens", "outputTokens", "cacheReadTokens", "reasoningTokens")
tok = dict.fromkeys(KEYS, 0)
calls = steps = user_msgs = 0
usage_records = usage_duplicates = parse_errors = 0
seen = set()

def nearest_usage(node):
    """usage, ближайший к корню записи: обход в ширину, первое совпадение.

    Обход в ширину, а не в глубину, важен: у одной записи может быть несколько
    usage на разной глубине, и «первый по глубине» — это измерение этой записи,
    а не вложенная копия (иначе один запрос считался бы дважды).
    """
    queue = [node]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            value = current.get("usage")
            if isinstance(value, dict) and any(key in value for key in KEYS):
                return value
            queue.extend(current.values())
        elif isinstance(current, list):
            queue.extend(current)
    return None

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        rec = json.loads(line)
    except Exception:
        # Строка-обрезок не должна обнулять уже посчитанное: ошибка считается и
        # печатается, но остальные записи остаются измеренными.
        parse_errors += 1
        continue
    if not isinstance(rec, dict):
        continue
    rtype = rec.get("type")
    data = rec.get("data")
    data = data if isinstance(data, dict) else {}
    usage = nearest_usage(rec)
    if usage is not None:
        values = []
        for key in KEYS:
            raw = usage.get(key)
            try:
                values.append(int(raw or 0))
            except Exception:
                values.append(0)
        signature = (str(data.get("turn", "")), str(data.get("step", "")), tuple(values))
        if signature in seen:
            usage_duplicates += 1
        else:
            seen.add(signature)
            usage_records += 1
            for key, value in zip(KEYS, values):
                tok[key] += value
    calls += 1 if rtype == "tool/call" else 0
    steps += 1 if rtype == "step/end" else 0
    user_msgs += 1 if rtype == "user/message" else 0

print(f"usage_records={usage_records}")
print(f"usage_duplicate_records_skipped={usage_duplicates}")
print(f"session_parse_errors={parse_errors}")
if usage_records == 0:
    reason = "usage records absent in the whole session"
    if parse_errors:
        reason = f"usage records absent and {parse_errors} record(s) unreadable"
    print(f"tokens_input=not available ({reason})")
    print(f"tokens_output=not available ({reason})")
    print(f"tokens_cache_read=not available ({reason})")
    print(f"tokens_reasoning=not available ({reason})")
else:
    # `.format(**tok)` вместо f-строк с ключами: блок исполняется как
    # `python3 -c "$PARSER_PY"`, и одиночная кавычка внутри ключа закрыла бы
    # аргумент -c, обрезав остаток кода (проверено: f"{{{tok[chr(39)+key+chr(39)]}}}").
    print("tokens_input={inputTokens}".format(**tok))
    print("tokens_output={outputTokens}".format(**tok))
    print("tokens_cache_read={cacheReadTokens}".format(**tok))
    print("tokens_reasoning={reasoningTokens}".format(**tok))
print(f"tool_calls={calls}")
print(f"steps={steps}")
print(f"human_messages_in_session={user_msgs}  # больше 1 => были вмешательства")
'
emit_metrics() {
  [ "$METRICS_DONE" -eq 0 ] || return 0
  METRICS_DONE=1
  echo
  echo "--- экспериментальные метрики пилота ---"
  printf 'dsh_version=%s\n' "$DSH_VERSION_PIN"
  printf 'node_path=%s\n' "$NODE_PATH"
  printf 'node_version=%s\n' "$NODE_VERSION"
  printf 'headless_loader_check=%s\n' "$HEADLESS_LOADER_CHECK"
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
  printf 'timeout_seconds=%s\n' "$TIMEOUT_SECONDS"
  printf 'timeout_grace_seconds=%s\n' "$TIMEOUT_GRACE_SECONDS"
  printf 'timed_out=%s\n' "$TIMED_OUT"
  printf 'worktree_clean_after=%s\n' "$WORKTREE_CLEAN"
  printf 'head_unchanged=%s\n' "$HEAD_UNCHANGED"
  printf 'leftover_processes_killed=%s\n' "$LEFTOVERS_KILLED"
  printf 'session_file=%s\n' "${SESSION_FILE:-not found}"
  if [ -n "${SESSION_FILE:-}" ]; then
    # Извлечение — best-effort: `zstd`/`python3` работают под `set -euo pipefail`,
    # и падение на битом или обрезанном session.jsonl.zstd иначе унесло бы с собой
    # код возврата всего скрипта (в таймаутном прогоне — вместо 124). Ошибка при
    # этом не молчит: она печатается и попадает в метрики строкой session_metrics,
    # а решение о коде возврата принимается независимо от неё.
    local metrics_lines
    if metrics_lines="$(zstd -dc "$SESSION_FILE" 2>/dev/null | python3 -c "$PARSER_PY")"; then
      printf '%s\n' "$metrics_lines"
      # Сессия без единой записи usage — не «нулевые токены», а отсутствие
      # измерения: печатать нули значило бы утверждать, что оплаченный прогон
      # израсходовал ровно ноль токенов. Одна явная строка говорит об этом прямо,
      # а для нетаймаутного прогона отсутствие метрик так же фатально, как сбой
      # извлечения (runbook требует метрики для зачёта smoke).
      if printf '%s\n' "$metrics_lines" | grep -q 'tokens_input=not available'; then
        METRICS_FAIL=1
        echo "  ✘ в сессии $SESSION_FILE нет ни одной записи usage — токены и стоимость недоступны (не нули), прогон нельзя засчитывать по метрикам (для таймаутного прогона наружу всё равно 124)" >&2
      fi
    else
      METRICS_FAIL=1
      echo "  ✘ не удалось извлечь метрики сессии из $SESSION_FILE: zstd/python3 вернули ошибку — оплаченные числа не собраны, прогон нельзя засчитывать (для таймаутного прогона наружу всё равно 124)" >&2
      printf 'session_metrics=not collected (extraction failed for %s — zstd/python3 вернули ошибку)\n' "$SESSION_FILE"
    fi
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
# Гарантия «после preflight не остаётся процессов оплаченного прогона» — часть
# контракта, поэтому выживший потомок не «предупреждение», а недействительный
# прогон: он уже был убит выше, но метрики не должны читаться как чистый успех.
check "$([ "$LEFTOVERS_KILLED" = no ] && echo 0 || echo 1)" \
  "группа процессов smoke не пережила своего лидера (процессов-сирот нет)" \
  "группа процессов smoke (pgid $LEFTOVER_PGID) пережила своего лидера — потомки были убиты, но прогон недействителен как чистый (leftover_processes_killed=yes)"

emit_metrics

# Таймаут доминирует над провалами read-only: у убитого прогона нет ни сессии,
# ни ответа модели, поэтому 124 — точный и отличимый от «модель упала» сигнал.
# Нарушения read-only при этом не скрываются: они уже напечатаны выше и видны в
# метриках (worktree_clean_after/head_unchanged). Метрики к этому моменту уже
# напечатаны, а страховку от сбоя в самой пост-обработке держит ловушка
# smoke_exit: 124 не может быть подменён кодом zstd/парсера.
if [ "$TIMED_OUT" = yes ]; then
  exit 124
fi
# Нечитаемые монотонные часы: прогон остановлен без доказуемой границы, поэтому
# это провал preflight (1), а не «результат модели» и не таймаут.
if [ "$CLOCK_ERROR" = yes ]; then
  exit 1
fi
# Провал извлечения метрик фатален, но только там, где нет таймаута (124 выше уже
# вернулся) и только если прогон иначе выглядел бы успешным: уже ненулевой код
# модели сохраняется как более информативный.
if [ "$METRICS_FAIL" = 1 ] && [ "$EXIT_CODE" -eq 0 ]; then
  exit 1
fi
if [ "$CHECK_FAIL" -ne 0 ]; then
  exit 1
fi
exit "$EXIT_CODE"
