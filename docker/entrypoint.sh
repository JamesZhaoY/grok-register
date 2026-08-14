#!/usr/bin/env bash
# 容器入口：准备目录与配置 → 校正属主 → 轮转启动日志 → 在 Xvfb 下以非 root 拉起服务。
#
# 可选环境变量：
#   PUID / PGID           把运行用户重映射到宿主 UID/GID，解决 bind mount 属主不一致
#   GROK_SKIP_CHOWN=1     跳过属主修正（数据目录很大且属主已正确时启动更快）
#   GROK_FORCE_CHOWN=1    强制递归修正属主（宿主机手工放入文件后使用）
#   GROK_LOG_TO_FILE=0    不落盘 logs/container-*.log，只保留 docker logs
#   GROK_LOG_KEEP=20      logs/ 保留的启动日志份数，0 表示不清理
#   GROK_DISABLE_XVFB=1   不套 Xvfb 直接运行（宿主已提供显示器或排障时）
#   GROK_CONFIG_TEMPLATE  首次生成配置的模板，默认 /app/config.example.json
#   GROK_RUN_USER         容器内运行用户，默认 app
set -euo pipefail

APP_DIR="${GROK_APP_DIR:-/app}"
DATA_DIR="${GROK_DATA_DIR:-${APP_DIR}/data}"
LOG_DIR="${GROK_LOG_DIR:-${APP_DIR}/logs}"
CONFIG_FILE="${GROK_CONFIG_FILE:-${DATA_DIR}/config.json}"
CONFIG_TEMPLATE="${GROK_CONFIG_TEMPLATE:-${APP_DIR}/config.example.json}"
RUN_USER="${GROK_RUN_USER:-app}"
RUN_HOME="${GROK_RUN_HOME:-/home/${RUN_USER}}"
CACHE_DIR="${XDG_CACHE_HOME:-/opt/camoufox-cache}"
LOG_FILE=""

log() { printf '[docker] %s\n' "$*"; }
warn() { printf '[docker] %s\n' "$*" >&2; }
die() { warn "$*"; exit 1; }
has() { command -v "$1" >/dev/null 2>&1; }
is_root() { [[ "$(id -u)" -eq 0 ]]; }
run_group() { id -gn "$RUN_USER" 2>/dev/null || echo "$RUN_USER"; }

RUN_USER_EXISTS=0
if id -u "$RUN_USER" >/dev/null 2>&1; then
  RUN_USER_EXISTS=1
fi

prepare_dirs() {
  local dir
  for dir in "$DATA_DIR" "$LOG_DIR" "$DATA_DIR/accounts" "$DATA_DIR/cpa_auth" \
    "$DATA_DIR/grok2api_auth" "$DATA_DIR/screenshots/registration-failures" \
    "$DATA_DIR/screenshots/relogin-failures"; do
    mkdir -p "$dir" || die "无法创建目录: $dir（检查挂载权限）"
  done
  # 应用侧的 data/ 由 backend/shared/paths.py 固定为 ${APP_DIR}/data，改这里只影响预创建。
  if [[ "$DATA_DIR" != "${APP_DIR}/data" ]]; then
    warn "GROK_DATA_DIR=${DATA_DIR} 与应用固定的 ${APP_DIR}/data 不一致，账号数据仍会写入后者"
  fi
}

# 让容器内运行用户对齐宿主 UID/GID，宿主机就能直接读写 data/ 与 logs/。
remap_run_user() {
  local want_uid="${PUID:-}" want_gid="${PGID:-}"
  if [[ -z "$want_uid" && -z "$want_gid" ]]; then
    return 0
  fi
  if (( ! RUN_USER_EXISTS )); then
    warn "容器内不存在用户 ${RUN_USER}，忽略 PUID/PGID"
    return 0
  fi
  if ! has usermod || ! has groupmod; then
    warn "镜像缺少 usermod/groupmod，忽略 PUID/PGID"
    return 0
  fi

  local cur_uid cur_gid group
  cur_uid="$(id -u "$RUN_USER")"
  cur_gid="$(id -g "$RUN_USER")"
  group="$(run_group)"
  if [[ -n "$want_gid" && "$want_gid" != "$cur_gid" ]]; then
    if groupmod -o -g "$want_gid" "$group"; then
      log "运行组 ${group} GID: ${cur_gid} → ${want_gid}"
    else
      warn "GID 调整失败: ${want_gid}"
    fi
  fi
  if [[ -n "$want_uid" && "$want_uid" != "$cur_uid" ]]; then
    if usermod -o -u "$want_uid" "$RUN_USER"; then
      log "运行用户 ${RUN_USER} UID: ${cur_uid} → ${want_uid}"
    else
      warn "UID 调整失败: ${want_uid}"
    fi
  fi
  # HOME 与 Camoufox 缓存必须跟随新 UID，否则浏览器无法写入 profile。
  chown -R "$RUN_USER":"$(run_group)" "$RUN_HOME" "$CACHE_DIR" 2>/dev/null || true
}

seed_config() {
  # 与本机启动脚本共用同一份配置补齐逻辑。
  local seeder="${APP_DIR}/scripts/seed_config.py"
  local python_bin="python"
  has python || python_bin="python3"
  [[ -f "$seeder" ]] || die "缺少配置脚本: ${seeder}"
  "$python_bin" "$seeder" --target "$CONFIG_FILE" --template "$CONFIG_TEMPLATE" \
    || die "配置准备失败，容器退出"
}

# bind mount 可能由宿主机 root 创建。目录属主已正确时跳过递归 chown，
# 避免账号数据变多后每次启动都全量遍历。
fix_ownership() {
  if ! is_root; then
    log "以 uid=$(id -u) 运行，跳过属主修正"
    return 0
  fi
  if (( ! RUN_USER_EXISTS )); then
    return 0
  fi
  if [[ "${GROK_SKIP_CHOWN:-0}" == "1" ]]; then
    log "GROK_SKIP_CHOWN=1，跳过属主修正"
    return 0
  fi

  local group target_uid dir owner
  group="$(run_group)"
  target_uid="$(id -u "$RUN_USER")"
  for dir in "$DATA_DIR" "$LOG_DIR"; do
    owner="$(stat -c '%u' "$dir" 2>/dev/null || echo "")"
    if [[ "${GROK_FORCE_CHOWN:-0}" != "1" && "$owner" == "$target_uid" ]]; then
      continue
    fi
    log "修正属主: ${dir} → ${RUN_USER}:${group}"
    chown -R "$RUN_USER":"$group" "$dir" || warn "属主修正未完全成功: ${dir}"
  done
  # 配置文件常被宿主机手工放入，单独兜一次属主，保证设置页能保存。
  if [[ -f "$CONFIG_FILE" ]]; then
    chown "$RUN_USER":"$group" "$CONFIG_FILE" 2>/dev/null || true
  fi
}

# 提前把「权限不对」变成一条可读报错，而不是后面某次写库时的 Python 堆栈。
assert_writable() {
  local dir
  for dir in "$DATA_DIR" "$LOG_DIR"; do
    if is_root && (( RUN_USER_EXISTS )) && has gosu; then
      gosu "$RUN_USER" test -w "$dir" \
        || die "运行用户 ${RUN_USER} 无法写入 ${dir}：检查挂载目录权限，或用 PUID/PGID 对齐宿主用户"
    else
      [[ -w "$dir" ]] || die "当前用户无法写入 ${dir}：检查挂载目录权限"
    fi
  done
}

prepare_logs() {
  if [[ "${GROK_LOG_TO_FILE:-1}" != "1" ]]; then
    log "GROK_LOG_TO_FILE=0：日志只输出到 docker logs"
    return 0
  fi
  LOG_FILE="${LOG_DIR}/container-$(date -u +%Y%m%d-%H%M%S).log"
  if ! : > "$LOG_FILE" 2>/dev/null; then
    warn "日志文件不可写，改为只输出到 docker logs: ${LOG_FILE}"
    LOG_FILE=""
    return 0
  fi
  if is_root && (( RUN_USER_EXISTS )); then
    chown "$RUN_USER":"$(run_group)" "$LOG_FILE" 2>/dev/null || true
  fi
  # 固定入口，排障时不用先去找最新时间戳。
  ln -sfn "$(basename "$LOG_FILE")" "${LOG_DIR}/container-latest.log" 2>/dev/null || true
  exec > >(tee -a "$LOG_FILE") 2>&1
}

prune_logs() {
  local keep="${GROK_LOG_KEEP:-20}"
  [[ "$keep" =~ ^[0-9]+$ ]] || keep=20
  if (( keep == 0 )); then
    return 0
  fi

  local -a files=()
  local candidate
  while IFS= read -r candidate; do
    if [[ -f "$candidate" && ! -L "$candidate" ]]; then
      files+=("$candidate")
    fi
  done < <(ls -1t "$LOG_DIR"/container-*.log 2>/dev/null || true)
  if (( ${#files[@]} <= keep )); then
    return 0
  fi

  local removed=0 file
  for file in "${files[@]:keep}"; do
    if [[ "$file" == "$LOG_FILE" ]]; then
      continue
    fi
    if rm -f "$file"; then
      removed=$((removed + 1))
    fi
  done
  if (( removed )); then
    log "已清理 ${removed} 个历史启动日志（保留最近 ${keep} 个）"
  fi
}

print_banner() {
  log "运行身份: uid=$(id -u) gid=$(id -g)，服务将以 ${RUN_USER} 运行"
  log "配置: ${CONFIG_FILE}"
  log "数据: ${DATA_DIR}"
  log "日志: ${LOG_FILE:-仅 docker logs}"
  log "DISPLAY=${DISPLAY}  分辨率=${XVFB_SCREEN:-1920x1080x24}"
}

run_app() {
  local -a cmd=("$@")
  if (( ${#cmd[@]} == 0 )); then
    cmd=(python -m backend.web.cli --host 0.0.0.0 --port 8787)
  fi

  if [[ "${GROK_DISABLE_XVFB:-0}" == "1" ]]; then
    log "GROK_DISABLE_XVFB=1：不启用 Xvfb"
  elif has xvfb-run; then
    log "Camoufox 模式: 有头（Xvfb 虚拟显示器）"
    cmd=(xvfb-run --auto-servernum \
      --server-args="-screen 0 ${XVFB_SCREEN:-1920x1080x24} -nolisten tcp" \
      "${cmd[@]}")
  else
    warn "未找到 xvfb-run，浏览器将直接使用 DISPLAY=${DISPLAY}"
  fi

  if is_root && (( RUN_USER_EXISTS )) && [[ "$RUN_USER" != "root" ]]; then
    if has gosu; then
      exec gosu "$RUN_USER" "${cmd[@]}"
    fi
    if has setpriv; then
      exec setpriv --reuid "$(id -u "$RUN_USER")" --regid "$(id -g "$RUN_USER")" \
        --init-groups "${cmd[@]}"
    fi
    warn "缺少 gosu/setpriv，将以 root 运行服务"
  fi
  exec "${cmd[@]}"
}

main() {
  prepare_dirs
  if is_root; then
    remap_run_user
  fi
  seed_config
  fix_ownership
  assert_writable
  prepare_logs
  prune_logs

  export HOME="$RUN_HOME"
  export XDG_CACHE_HOME="$CACHE_DIR"
  export DISPLAY="${DISPLAY:-:99}"
  export GROK_FORCE_HEADED="${GROK_FORCE_HEADED:-1}"
  export GROK_CONFIG_FILE="$CONFIG_FILE"

  print_banner
  run_app "$@"
}

main "$@"
