# shellcheck shell=bash
# scripts/start-linux.sh 与 scripts/start-macos.sh 的共用实现：
# 依次准备 venv、Python 依赖、Camoufox 引擎、config.json、前端产物，然后拉起控制台。
# 调用方先设置 GROK_SCRIPT_DIR、PLATFORM_LABEL、PYTHON_CANDIDATES（空格分隔），再 source 本文件。
# 需兼容 macOS 自带的 bash 3.2，勿使用 mapfile / declare -A 等 4.x 特性。

set -euo pipefail

PLATFORM_LABEL="${PLATFORM_LABEL:-$(uname -s)}"
PYTHON_CANDIDATES="${PYTHON_CANDIDATES:-python3 python}"
SCRIPT_NAME="${SCRIPT_NAME:-$(basename "$0")}"

HOST="${GROK_WEB_HOST:-127.0.0.1}"
PORT="${GROK_WEB_PORT:-8787}"
MODE="serve"
SKIP_INSTALL=0
REBUILD_WEB=0
WITH_OUTLOOKEMAIL=0
OPEN_UI=0
HOST_EXPLICIT=0
PORT_EXPLICIT=0
ROOT_DIR=""
VENV_PY=""
PY=""
ISSUES=0

if [[ -t 1 ]]; then
  C_OK=$'\033[32m'
  C_WARN=$'\033[33m'
  C_ERR=$'\033[31m'
  C_DIM=$'\033[2m'
  C_END=$'\033[0m'
else
  C_OK=""
  C_WARN=""
  C_ERR=""
  C_DIM=""
  C_END=""
fi

step() { printf '%s==>%s %s\n' "$C_DIM" "$C_END" "$*"; }
ok() { printf '%s[ok]%s %s\n' "$C_OK" "$C_END" "$*"; }
warn() { printf '%s[!]%s %s\n' "$C_WARN" "$C_END" "$*" >&2; }
die() { printf '%s[x]%s %s\n' "$C_ERR" "$C_END" "$*" >&2; exit 1; }
bad() { ISSUES=$((ISSUES + 1)); printf '%s[x]%s %s\n' "$C_ERR" "$C_END" "$*"; }
has() { command -v "$1" >/dev/null 2>&1; }

usage() {
  cat <<EOF
用法: ${SCRIPT_NAME} [选项]

在 ${PLATFORM_LABEL} 上一键准备运行环境并启动 Grok Register 控制台。

选项:
  --host <地址>        监听地址，默认 ${HOST}（局域网访问用 0.0.0.0）
  --port <端口>        监听端口，默认 ${PORT}
  --docker             改用 docker compose 部署（构建并后台启动）
  --with-outlookemail  配合 --docker，同时启动可选 OutlookEmail 邮箱池
  --skip-install       跳过依赖安装与前端构建，直接启动
  --rebuild-web        强制重新构建前端
  --open               启动后自动打开浏览器
  --check              只体检运行环境，不启动服务
  -h, --help           显示本帮助

环境变量:
  GROK_PYTHON          指定 Python 解释器（首次创建 .venv 时使用）
  GROK_WEB_HOST        默认监听地址
  GROK_WEB_PORT        默认监听端口
  GROK_CONFIG_FILE     自定义配置文件路径，默认 <项目>/config.json
EOF
  if [[ -n "${EXTRA_USAGE:-}" ]]; then
    printf '\n%s\n' "$EXTRA_USAGE"
  fi
}

parse_args() {
  while (( $# )); do
    case "$1" in
      --host)
        (( $# >= 2 )) || die "--host 需要一个值"
        HOST="$2"
        HOST_EXPLICIT=1
        shift 2
        ;;
      --host=*)
        HOST="${1#*=}"
        HOST_EXPLICIT=1
        shift
        ;;
      --port)
        (( $# >= 2 )) || die "--port 需要一个值"
        PORT="$2"
        PORT_EXPLICIT=1
        shift 2
        ;;
      --port=*)
        PORT="${1#*=}"
        PORT_EXPLICIT=1
        shift
        ;;
      --docker) MODE="docker"; shift ;;
      --with-outlookemail) WITH_OUTLOOKEMAIL=1; shift ;;
      --skip-install) SKIP_INSTALL=1; shift ;;
      --rebuild-web) REBUILD_WEB=1; shift ;;
      --open) OPEN_UI=1; shift ;;
      --check) MODE="check"; shift ;;
      -h|--help) usage; exit 0 ;;
      *) die "未知参数: $1（用 --help 查看用法）" ;;
    esac
  done
  [[ -n "$HOST" ]] || die "--host 不能为空"
  [[ "$PORT" =~ ^[0-9]+$ ]] || die "--port 需要是数字: $PORT"
}

python_ok() {
  "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

find_bootstrap_python() {
  local candidate
  if [[ -n "${GROK_PYTHON:-}" ]]; then
    python_ok "$GROK_PYTHON" || die "GROK_PYTHON 不可用或低于 3.10: ${GROK_PYTHON}"
    printf '%s\n' "$GROK_PYTHON"
    return 0
  fi
  for candidate in $PYTHON_CANDIDATES; do
    if has "$candidate" && python_ok "$candidate"; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

ensure_python() {
  if [[ -x "$VENV_PY" ]]; then
    PY="$VENV_PY"
    ok "Python $("$PY" -V 2>&1 | awk '{print $2}')（.venv）"
    return 0
  fi
  local boot
  boot="$(find_bootstrap_python)" \
    || die "未找到 Python 3.10+（候选: ${PYTHON_CANDIDATES}），可用 GROK_PYTHON 指定路径"
  step "创建虚拟环境 .venv（$("$boot" -V 2>&1)）"
  "$boot" -m venv "$ROOT_DIR/.venv" || die "创建 .venv 失败：Debian/Ubuntu 需先安装 python3-venv"
  PY="$VENV_PY"
  [[ -x "$PY" ]] || die "创建 .venv 后仍找不到解释器: ${PY}"
  ok "虚拟环境就绪"
}

file_sha256() {
  if has shasum; then
    shasum -a 256 "$1" | awk '{print $1}'
  elif has sha256sum; then
    sha256sum "$1" | awk '{print $1}'
  else
    "$PY" -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"
  fi
}

deps_ready() {
  "$PY" -c 'import fastapi, uvicorn, camoufox' >/dev/null 2>&1
}

ensure_requirements() {
  local req="$ROOT_DIR/requirements.txt"
  local stamp="$ROOT_DIR/.venv/.requirements.sha256"
  local want have=""
  [[ -f "$req" ]] || die "缺少 requirements.txt: ${req}"
  want="$(file_sha256 "$req")"
  if [[ -f "$stamp" ]]; then
    have="$(cat "$stamp" 2>/dev/null || true)"
  fi
  if [[ "$want" == "$have" ]] && deps_ready; then
    ok "Python 依赖已就绪"
    return 0
  fi
  step "安装 Python 依赖（requirements.txt）"
  "$PY" -m pip install --upgrade pip >/dev/null 2>&1 || warn "pip 自升级失败，继续安装依赖"
  "$PY" -m pip install -r "$req" || die "依赖安装失败：检查网络或代理后重试"
  printf '%s\n' "$want" >"$stamp"
  ok "Python 依赖安装完成"
}

camoufox_ready() {
  local root browsers
  root="$("$PY" -m camoufox path 2>/dev/null | tail -1 || true)"
  [[ -n "$root" ]] || return 1
  browsers="$root/browsers"
  [[ -d "$browsers" ]] || return 1
  [[ -n "$(ls -A "$browsers" 2>/dev/null || true)" ]]
}

ensure_camoufox() {
  if camoufox_ready; then
    ok "Camoufox 浏览器引擎已下载"
    return 0
  fi
  step "下载 Camoufox 浏览器引擎（首次约数百 MB）"
  "$PY" -m camoufox fetch || die "Camoufox 下载失败：检查网络或代理后重试"
  ok "Camoufox 引擎就绪"
}

config_path() {
  printf '%s\n' "${GROK_CONFIG_FILE:-$ROOT_DIR/config.json}"
}

ensure_config() {
  local target
  target="$(config_path)"
  # 与容器入口共用 scripts/seed_config.py：缺失时按模板生成，已存在时只补新增键。
  "$PY" "$ROOT_DIR/scripts/seed_config.py" \
    --target "$target" \
    --template "$ROOT_DIR/config.example.json" \
    --no-container-defaults \
    || die "配置准备失败: ${target}"
}

frontend_sources_changed() {
  # git pull 会把改动文件的 mtime 刷新成检出时间，只看 dist 是否存在会一直跑旧包。
  local dist="$1"
  local newer
  newer=$(find "$ROOT_DIR/front" \
    -path "$ROOT_DIR/front/node_modules" -prune -o \
    -path "$ROOT_DIR/front/dist" -prune -o \
    -type f -newer "$dist" -print 2>/dev/null | head -n 1)
  [[ -n "$newer" ]]
}

ensure_frontend() {
  local dist="$ROOT_DIR/front/dist/index.html"
  if (( ! REBUILD_WEB )) && [[ -f "$dist" ]]; then
    if frontend_sources_changed "$dist"; then
      warn "前端源码比产物新，重新构建（跳过可加 --skip-install）"
    else
      ok "前端产物已存在"
      return 0
    fi
  fi
  if ! has npm; then
    warn "未找到 npm，跳过前端构建；未构建时访问 / 会返回 503（API 仍可用）"
    return 0
  fi
  if [[ ! -d "$ROOT_DIR/front/node_modules" ]]; then
    step "安装前端依赖（npm install）"
    npm --prefix "$ROOT_DIR/front" install || die "npm install 失败"
  fi
  step "构建前端（npm run build）"
  npm --prefix "$ROOT_DIR/front" run build || die "前端构建失败"
  ok "前端构建完成"
}

port_busy() {
  "$PY" - "$HOST" "$PORT" <<'PY' >/dev/null 2>&1
import socket
import sys

host, port = sys.argv[1], int(sys.argv[2])
probe = "127.0.0.1" if host in ("0.0.0.0", "::", "*", "") else host
sock = socket.socket()
sock.settimeout(0.6)
try:
    sys.exit(0 if sock.connect_ex((probe, port)) == 0 else 1)
finally:
    sock.close()
PY
}

display_url() {
  local shown="$HOST"
  if [[ "$HOST" == "0.0.0.0" || "$HOST" == "::" ]]; then
    shown="127.0.0.1"
  fi
  printf 'http://%s:%s\n' "$shown" "$PORT"
}

compose_port() {
  local value=""
  if (( PORT_EXPLICIT )); then
    printf '%s\n' "$PORT"
    return 0
  fi
  if [[ -f "$ROOT_DIR/.env" ]]; then
    value="$(sed -n 's/^GROK_WEB_PORT=\([0-9]\{1,\}\).*/\1/p' "$ROOT_DIR/.env" | tail -1)"
  fi
  printf '%s\n' "${value:-8787}"
}

run_docker() {
  has docker || die "未找到 docker：请先安装 Docker Engine 或 Docker Desktop"
  docker compose version >/dev/null 2>&1 \
    || die "当前 Docker 缺少 compose 插件（需要 Docker Compose v2）"
  cd "$ROOT_DIR"
  if [[ ! -f .env ]]; then
    cp .env.example .env
    ok "已按 .env.example 生成 .env（端口、密钥、PUID 可在其中调整）"
  fi
  if (( PORT_EXPLICIT )); then
    export GROK_WEB_PORT="$PORT"
  fi
  if (( HOST_EXPLICIT )); then
    export GROK_WEB_BIND="$HOST"
  fi

  set -- compose
  if (( WITH_OUTLOOKEMAIL )); then
    set -- "$@" --profile outlookemail
  fi
  set -- "$@" up -d --build
  step "docker $*"
  docker "$@" || die "docker compose 启动失败，用 docker compose logs 查看原因"
  ok "容器已在后台启动"
  printf '  控制台: http://127.0.0.1:%s\n' "$(compose_port)"
  printf '  日志:   docker compose logs -f grok-register\n'
  printf '  状态:   docker compose ps\n'
  printf '  停止:   docker compose down\n'
}

run_check() {
  local boot="" cfg
  if [[ -x "$VENV_PY" ]]; then
    PY="$VENV_PY"
    ok ".venv 就绪：$("$PY" -V 2>&1)"
  elif boot="$(find_bootstrap_python)"; then
    PY="$boot"
    warn "尚未创建 .venv（首次启动自动创建），当前解释器: $("$PY" -V 2>&1)"
  else
    bad "未找到 Python 3.10+（候选: ${PYTHON_CANDIDATES}），可用 GROK_PYTHON 指定"
  fi

  if [[ -n "$PY" ]]; then
    if deps_ready; then
      ok "Python 依赖已安装"
    else
      warn "Python 依赖未安装（启动时自动安装）"
    fi
    if camoufox_ready; then
      ok "Camoufox 浏览器引擎已下载"
    else
      warn "Camoufox 引擎未下载（启动时自动下载，约数百 MB）"
    fi
    if port_busy; then
      warn "端口 ${PORT} 已被占用，启动前请释放或改用 --port"
    else
      ok "端口 ${PORT} 可用"
    fi
  fi

  cfg="$(config_path)"
  if [[ -f "$cfg" ]]; then
    ok "配置文件: ${cfg}"
  else
    warn "缺少配置文件（启动时按 config.example.json 生成）: ${cfg}"
  fi

  if [[ -f "$ROOT_DIR/front/dist/index.html" ]]; then
    if frontend_sources_changed "$ROOT_DIR/front/dist/index.html"; then
      warn "前端产物比源码旧（启动时会自动重新构建）"
    else
      ok "前端产物已构建"
    fi
  elif has npm; then
    warn "前端未构建（启动时执行 npm run build）"
  else
    bad "前端未构建且未安装 npm/Node.js 22+：控制台页面会返回 503"
  fi

  if has docker; then
    ok "Docker 可用（--docker 走容器部署）"
  else
    warn "未安装 Docker（只影响 --docker 模式）"
  fi

  if (( ISSUES )); then
    die "体检发现 ${ISSUES} 个必须处理的问题"
  fi
  ok "体检通过，可直接运行 ${SCRIPT_NAME} 启动"
}

open_ui() {
  local url="$1" opener=""
  if has open; then
    opener="open"
  elif has xdg-open; then
    opener="xdg-open"
  fi
  if [[ -z "$opener" ]]; then
    warn "未找到打开浏览器的命令，请手动访问 ${url}"
    return 0
  fi
  # 等服务起来再打开，避免首屏 502。
  ( sleep 2; "$opener" "$url" >/dev/null 2>&1 || true ) &
}

run_serve() {
  ensure_python
  if (( SKIP_INSTALL )); then
    warn "--skip-install：跳过依赖安装与前端构建"
  else
    ensure_requirements
    ensure_camoufox
    ensure_frontend
  fi
  ensure_config
  if port_busy; then
    die "端口 ${PORT} 已被占用：改用 --port 换端口，或先停掉占用进程"
  fi
  if [[ ! -f "$ROOT_DIR/front/dist/index.html" ]]; then
    warn "前端未构建，控制台页面会返回 503（API 仍可用）"
  fi
  ok "启动控制台 $(display_url)（Ctrl+C 停止）"
  if (( OPEN_UI )); then
    open_ui "$(display_url)"
  fi
  cd "$ROOT_DIR"
  exec "$PY" -m backend.web.cli --host "$HOST" --port "$PORT"
}

grok_main() {
  [[ -n "${GROK_SCRIPT_DIR:-}" ]] || die "内部错误：GROK_SCRIPT_DIR 未设置"
  ROOT_DIR="$(cd "$GROK_SCRIPT_DIR/.." && pwd)"
  VENV_PY="$ROOT_DIR/.venv/bin/python"
  parse_args "$@"
  step "Grok Register · ${PLATFORM_LABEL}（${ROOT_DIR}）"
  case "$MODE" in
    docker) run_docker ;;
    check) run_check ;;
    *) run_serve ;;
  esac
}
