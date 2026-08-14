#!/usr/bin/env bash
# macOS 一键启动：准备 .venv、Python 依赖、Camoufox 引擎、config.json 与前端产物后拉起控制台。
#   scripts/start-macos.sh                 # 本机运行，默认 127.0.0.1:8787
#   scripts/start-macos.sh --open          # 启动后自动打开浏览器
#   scripts/start-macos.sh --docker        # 交给 Docker Desktop 里的 compose 部署
#   scripts/start-macos.sh --check         # 只体检环境
set -euo pipefail

GROK_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="scripts/start-macos.sh"
PLATFORM_LABEL="macOS"
# 优先 Homebrew 的 python3，其次 python.org 安装包，最后系统自带（可能低于 3.10）。
PYTHON_CANDIDATES="python3.13 python3.12 python3.11 python3.10 python3"
EXTRA_USAGE="macOS 提示:
  未安装 Python 3.10+ 时: brew install python@3.12
  未安装 Node.js 22+ 时:  brew install node
  Camoufox 首次运行会被 Gatekeeper 拦一次，在「系统设置 → 隐私与安全性」放行即可"

# shellcheck source=scripts/_lib.sh
. "$GROK_SCRIPT_DIR/_lib.sh"

if [[ "$(uname -s)" != "Darwin" ]]; then
  warn "当前系统不是 macOS（$(uname -s)），Linux 请用 scripts/start-linux.sh"
fi

grok_main "$@"
