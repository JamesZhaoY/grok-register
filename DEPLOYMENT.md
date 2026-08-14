# 部署说明

Docker Compose 是推荐方式。容器内使用 Xvfb 运行有头 Camoufox，因此无桌面、只有 SSH 的 Linux 服务器也能运行。

## Docker Compose：本地构建

要求：Docker Engine、Docker Compose。buildx 插件可选——镜像刻意不使用 BuildKit 专属语法，旧版构建器也能构建。

```bash
cp .env.example .env
docker compose build
docker compose up -d
docker compose ps
```

也可以让一键脚本代跑（自动生成 `.env`，并打印日志与停止命令）：

```bash
scripts/start-linux.sh --docker
scripts/start-linux.sh --docker --with-outlookemail   # 同时启动可选邮箱池
```

访问：`http://服务器IP:8787`

查看状态：

```bash
curl http://127.0.0.1:8787/api/health
docker compose logs -f grok-register
```

验证 Camoufox：

```bash
docker compose run --rm grok-register python /app/docker/camoufox_smoke.py
```

停止或更新：

```bash
docker compose down
git pull
docker compose up -d --build
```

## Docker 配置

Docker 读取：

```text
data/config.json
```

使用已有根目录配置：

```bash
mkdir -p data
cp config.json data/config.json
docker compose restart grok-register
```

没有 `data/config.json` 时，首次启动会由 `scripts/seed_config.py` 从 `config.example.json` 生成。该脚本也负责后续升级：

- 已有配置只补齐模板里的新增键，不覆盖已填写的值
- 容器内强制 `browser_headless=false`、授权目录指向挂载卷、`outlookemail_api_base` 指向内部服务名（仅首次生成时写入）
- 配置文件损坏时先备份为 `config.json.broken-<UTC时间戳>` 再按模板重建，容器不会因 JSON 解析失败反复重启

本机启动脚本共用同一份逻辑，但会带上 `--no-container-defaults`，因此容器专用值不会写进根目录 `config.json`。

持久化目录：

```text
data/    配置、账号、Web 登录、CPA / Grok2API 授权文件
logs/    运行日志，每次启动一份 container-<UTC时间戳>.log，container-latest.log 指向最新
```

`.env` 常用设置：

```dotenv
GROK_REGISTER_IMAGE=grok-register:local
GROK_WEB_PORT=8787
GROK_WEB_BIND=0.0.0.0
GROK_SHM_SIZE=1gb
GROK_WEB_COOKIE_SECURE=auto
PUID=
PGID=
GROK_LOG_KEEP=20
GROK_LOG_MAX_SIZE=20m
GROK_LOG_MAX_FILE=5
GROK_STOP_GRACE=30s
```

| 变量 | 说明 |
| --- | --- |
| `GROK_WEB_BIND` | 端口映射的宿主机监听地址。反向代理场景设 `127.0.0.1`，控制台就不会直接暴露到公网 |
| `GROK_WEB_COOKIE_SECURE` | 会话 Cookie 的 `Secure` 标记。`auto`（默认）按请求协议判断，`1` 恒开，`0` 恒关。纯 HTTP 下恒开会让浏览器丢弃 Cookie，登录后立刻 401 |
| `PUID` / `PGID` | 把容器内运行用户重映射到宿主 UID/GID（`id -u` / `id -g`），解决 bind mount 属主不一致。留空则沿用镜像内的 `app`（10001） |
| `GROK_LOG_KEEP` | `logs/` 里保留的启动日志份数，`0` 表示不清理 |
| `GROK_LOG_MAX_SIZE` / `GROK_LOG_MAX_FILE` | `docker logs` 的 json-file 轮转上限，避免日志占满磁盘 |
| `GROK_STOP_GRACE` | 停止容器时留给 Camoufox 收尾的时间，太短会留下残留进程 |

容器入口 `docker/entrypoint.sh` 的排障开关（一般不用改）：

| 变量 | 说明 |
| --- | --- |
| `GROK_SKIP_CHOWN=1` | 跳过属主修正。数据量很大且属主已正确时启动更快 |
| `GROK_FORCE_CHOWN=1` | 强制递归修正属主。宿主机手工放入文件后使用 |
| `GROK_LOG_TO_FILE=0` | 不写 `logs/container-*.log`，只保留 `docker logs` |
| `GROK_DISABLE_XVFB=1` | 不套 Xvfb 直接运行（宿主已提供显示器或排障时） |
| `GROK_CONFIG_TEMPLATE` | 首次生成配置的模板路径，默认 `/app/config.example.json` |
| `GROK_RUN_USER` | 容器内运行用户，默认 `app` |

公网 HTTPS 场景默认的 `auto` 已经够用：反代转发 `X-Forwarded-Proto: https` 时会自动加上 `Secure`。
想强制固定（例如反代不转发协议头）再写死：

```dotenv
GROK_WEB_COOKIE_SECURE=1
```

如果 `data/config.json` 中的代理是 `http://127.0.0.1:7897`，Compose 会自动改用宿主机地址 `host.docker.internal:7897`。宿主机代理软件必须开启“允许局域网连接”或监听 `0.0.0.0`，否则容器仍然连不上。

## 可选 OutlookEmail 邮箱池

`compose.yaml` 已把上游 [`assast/outlookEmail`](https://github.com/assast/outlookEmail) 镜像作为可选 `outlookemail` profile 接入。默认的 `docker compose up -d` 只启动 Grok Register；选择 OutlookEmail 邮箱、导入账号、读取验证码或停用邮箱时启动完整组合：

```bash
cp .env.example .env
```

先在 `.env` 至少修改：

```dotenv
OUTLOOKEMAIL_PORT=5000
OUTLOOKEMAIL_LOGIN_PASSWORD=请设置强密码
OUTLOOKEMAIL_SECRET_KEY=请设置随机长字符串
```

生成 `SECRET_KEY`：

```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

启动：

```bash
docker compose --profile outlookemail pull outlook-email
docker compose --profile outlookemail up -d
docker compose --profile outlookemail ps
```

端口：

| 服务 | 容器端口 | 默认宿主机端口 | 监听范围 |
| --- | ---: | ---: | --- |
| Grok Register | 8787 | 8787 | 所有网卡，可用 `GROK_WEB_BIND` 收窄 |
| OutlookEmail | 5000 | 5000 | 所有网卡，可用 `OUTLOOKEMAIL_BIND` 收窄 |

浏览器访问 `http://服务器IP:5000`，使用 `OUTLOOKEMAIL_LOGIN_PASSWORD` 登录。在 OutlookEmail 设置页生成“对外 API Key”，然后在 Grok Register 的“系统设置 → Outlook 邮箱池”填写：

```text
API Base: http://outlook-email:5000
API Key:  OutlookEmail 页面生成的对外 API Key
```

如果使用 `temp` 来源，可填写相同的管理网页登录密码，主服务会自动获取 Session Cookie。数据持久化到：

```text
outlookemail-data/
```

停止全部服务：

```bash
docker compose --profile outlookemail down
```

OutlookEmail 的在线 Docker 更新功能需要挂载 `/var/run/docker.sock`，该 socket 具备宿主 Docker 管理能力。无需在线更新时可在 `.env` 设置：

```dotenv
OUTLOOKEMAIL_DOCKER_UPDATE_ENABLED=false
```

端口默认公开到所有宿主机网卡；公网服务器应通过防火墙、反向代理或安全组限制 `5000` 的访问来源。

## 使用 GHCR 镜像

将镜像名改为全小写：

```dotenv
GROK_REGISTER_IMAGE=ghcr.io/kaibush/grok-register:latest
```

```bash
docker compose pull
docker compose up -d
```

私有镜像先登录：

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u GITHUB_USER --password-stdin
```

GitHub Actions 规则：

- `master` / `main`：构建并发布 amd64
- `v*` 标签：构建并发布 amd64、arm64
- Pull Request：只测试和构建，不发布
- `workflow_dispatch`：支持手动触发

需要免登录分发时，在 GitHub Packages 将容器包设为 Public。

## 本机 Python 运行

要求：Python 3.10+、Node.js 22+。Linux 还需要 Camoufox（Firefox 分支）的图形运行库，否则注册时
浏览器会以 `libgtk-3.so.0: cannot open shared object file` 失败：

```bash
sudo .venv/bin/python -m playwright install-deps firefox            # Debian/Ubuntu，推荐
sudo dnf install -y gtk3 alsa-lib dbus-glib libXt libXtst nss       # RHEL/Fedora
sudo pacman -S --needed gtk3 alsa-lib dbus-glib libxt libxtst nss   # Arch
```

`scripts/start-linux.sh --check` 会用 `ldd` 扫引擎目录，缺库时直接列出 soname。Docker 部署不需要这一步，
镜像里已经装好（清单见 `Dockerfile` 的 runtime 阶段）。

一键脚本会准备 `.venv`、依赖、Camoufox 引擎、`config.json` 与前端产物后启动控制台：

```bash
scripts/start-linux.sh                    # Linux
scripts/start-linux.sh --xvfb             # 无桌面服务器，套 Xvfb 跑有头 Camoufox
scripts/start-macos.sh                    # macOS
scripts/start-linux.sh --check            # 只体检环境
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-windows.ps1   # Windows
```

`--host 0.0.0.0` 开放局域网，`--port` 换端口，`--docker` 转交 compose 部署（Windows 用 `-BindHost` / `-Port` / `-Docker`）。

手动步骤：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m camoufox fetch

cd front && npm install && npm run build && cd ..
cp config.example.json config.json
./start-web.sh
```

本机读取根目录 `config.json`，访问 `http://127.0.0.1:8787`。

## 反向代理

将域名反代到：

```text
http://127.0.0.1:8787
```

建议同时在 `.env` 设置，让容器端口只监听回环地址：

```dotenv
GROK_WEB_BIND=127.0.0.1
```

反向代理需转发 `Host`、`X-Forwarded-For` 和 `X-Forwarded-Proto`。转发了协议头，HTTPS 部署就会自动
给会话 Cookie 加上 `Secure`（`GROK_WEB_COOKIE_SECURE` 默认 `auto`）；不转发时手动设成 `1`。

## 资源建议

- 内存：至少 2 GB
- 共享内存：默认 `1gb`
- 磁盘：预留 5 GB
- amd64 镜像内容大小：约 1.04 GB

多并发时可在 `.env` 提高 `GROK_SHM_SIZE`。

## 常见问题

### 构建报 the --mount option requires BuildKit

宿主机只装了发行版 `docker.io`、没有 buildx 插件时，`docker compose build` 会退回旧版构建器
（日志里是 `Sending build context to Docker daemon` 和 `Step 4/37` 这种输出），报错长这样：

```text
WARN[0000] Docker Compose requires buildx plugin to be installed
the --mount option requires BuildKit. Refer to https://docs.docker.com/go/buildkit/
```

镜像已经改成旧版构建器可直接构建，`git pull` 后重跑即可：

```bash
git pull
docker compose up -d --build
```

compose 退回旧版构建器时走的是 classic build API，单独 `export DOCKER_BUILDKIT=1` 不生效。想让构建更快、
能复用 npm/apt 缓存，就装官方 buildx 插件（可选）：

```bash
sudo apt install -y docker-buildx-plugin
docker buildx version
```

### 配置未生效

Docker 修改 `data/config.json` 后重启：

```bash
docker compose restart grok-register
```

检查容器配置路径：

```bash
docker compose exec grok-register \
  python -c "import os; print(os.environ['GROK_CONFIG_FILE'])"
```

应为 `/app/data/config.json`。

### 宿主机代理连接失败

确认代理软件允许 Docker 网桥访问，并检查容器内解析：

```bash
docker compose exec grok-register getent hosts host.docker.internal
```

Linux 宿主机使用 `127.0.0.1` 监听代理时，需在代理软件中开启 Allow LAN；只改容器配置地址不能绕过宿主机监听限制。

### 浏览器启动失败

```bash
docker compose run --rm grok-register python /app/docker/camoufox_smoke.py
docker compose logs --tail=200 grok-register
```

### 挂载目录不可写

容器启动时会直接报出类似 `运行用户 app 无法写入 /app/data` 并退出。宿主机的 `data/`、`logs/` 属主与容器内运行用户不一致时，在 `.env` 填入宿主账号：

```dotenv
PUID=1000
PGID=1000
```

对应 `id -u` 与 `id -g` 的输出。宿主机手工放入过文件时，可临时用 `GROK_FORCE_CHOWN=1` 启动一次做全量属主修正。

### 端口被占用

在 `.env` 修改：

```dotenv
GROK_WEB_PORT=18787
```

然后：

```bash
docker compose up -d --force-recreate
```
