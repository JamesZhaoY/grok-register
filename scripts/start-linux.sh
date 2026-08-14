#!/usr/bin/env bash
# Linux 一键启动：准备 .venv、Python 依赖、Camoufox 引擎、config.json 与前端产物后拉起控制台。
#   scripts/start-linux.sh                 # 本机运行，默认 127.0.0.1:8787
#   scripts/start-linux.sh --host 0.0.0.0  # 允许局域网访问
#   scripts/start-linux.sh --xvfb          # 无桌面服务器：套 Xvfb 虚拟显示器跑有头浏览器
#   scripts/start-linux.sh --docker        # 交给 docker compose 部署
#   scripts/start-linux.sh --check         # 只体检环境
set -euo pipefail

GROK_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="scripts/start-linux.sh"
PLATFORM_LABEL="Linux"
PYTHON_CANDIDATES="python3.12 python3.11 python3.10 python3 python"
EXTRA_USAGE="Linux 专属:
  --xvfb               用 xvfb-run 包裹本脚本（无桌面服务器跑有头 Camoufox 时使用）"

# --xvfb 需要在进入通用参数解析前处理：命中后带着其余参数重新 exec 自己。
WANT_XVFB=0
FORWARD_ARGS=()
FORWARD_STR=""
for arg in "$@"; do
  if [[ "$arg" == "--xvfb" ]]; then
    WANT_XVFB=1
  else
    FORWARD_ARGS+=("$arg")
    FORWARD_STR="${FORWARD_STR} ${arg}"
  fi
done

if (( WANT_XVFB )) && [[ -z "${GROK_XVFB_WRAPPED:-}" ]]; then
  command -v xvfb-run >/dev/null 2>&1 \
    || { echo "[x] 未安装 xvfb-run：sudo apt install -y xvfb xauth" >&2; exit 1; }
  export GROK_XVFB_WRAPPED=1
  exec xvfb-run --auto-servernum \
    --server-args="-screen 0 ${XVFB_SCREEN:-1920x1080x24} -nolisten tcp" \
    "${BASH_SOURCE[0]}" ${FORWARD_ARGS[@]+"${FORWARD_ARGS[@]}"}
fi

# shellcheck source=scripts/_lib.sh
. "$GROK_SCRIPT_DIR/_lib.sh"

# 只在真正要在本机跑浏览器时提醒缺少显示器。
case "${FORWARD_STR} " in
  *" --docker "*|*" --check "*|*" --help "*|*" -h "*) ;;
  *)
    if [[ -z "${DISPLAY:-}" && -z "${GROK_XVFB_WRAPPED:-}" ]]; then
      warn "当前没有 DISPLAY：若配置里关闭了无头模式，请改用 --xvfb，或在系统设置中开启无头"
    fi
    ;;
esac

grok_main ${FORWARD_ARGS[@]+"${FORWARD_ARGS[@]}"}
