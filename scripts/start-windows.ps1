#Requires -Version 5.1
<#
.SYNOPSIS
    Windows 一键启动：准备 .venv、Python 依赖、Camoufox 引擎、config.json 与前端产物后拉起控制台。
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\start-windows.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\start-windows.ps1 -BindHost 0.0.0.0 -Port 9000
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\start-windows.ps1 -Docker
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\start-windows.ps1 -Check
#>
[CmdletBinding()]
param(
    # -Host 是 PowerShell 保留变量名，监听地址只能叫 -BindHost。
    [string]$BindHost = '',
    [string]$Port = '',
    [switch]$Docker,
    [switch]$WithOutlookEmail,
    [switch]$SkipInstall,
    [switch]$RebuildWeb,
    [switch]$Open,
    [switch]$Check,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
# 控制台默认代码页可能是 936/437，先切到 UTF-8 才能正常显示中文提示。
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$ScriptName = 'scripts\start-windows.ps1'
$RootDir = Split-Path -Parent $PSScriptRoot
$VenvDir = Join-Path $RootDir '.venv'
$VenvPy = Join-Path $VenvDir 'Scripts\python.exe'
$HostExplicit = $PSBoundParameters.ContainsKey('BindHost')
$PortExplicit = $PSBoundParameters.ContainsKey('Port')
$script:Py = $null
$script:PyPre = @()
$script:Issues = 0

if (-not $BindHost) {
    $BindHost = if ($env:GROK_WEB_HOST) { $env:GROK_WEB_HOST } else { '127.0.0.1' }
}
if (-not $Port) {
    $Port = if ($env:GROK_WEB_PORT) { $env:GROK_WEB_PORT } else { '8787' }
}

function Write-Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor DarkGray }
function Write-Ok([string]$Message) { Write-Host "[ok] $Message" -ForegroundColor Green }
function Write-Warn([string]$Message) { Write-Host "[!] $Message" -ForegroundColor Yellow }
function Write-Bad([string]$Message) {
    $script:Issues++
    Write-Host "[x] $Message" -ForegroundColor Red
}
function Stop-WithError([string]$Message) {
    Write-Host "[x] $Message" -ForegroundColor Red
    exit 1
}
function Test-Command([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Show-Usage {
    @"
用法: $ScriptName [选项]

在 Windows 上一键准备运行环境并启动 Grok Register 控制台。

选项:
  -BindHost <地址>     监听地址，默认 $BindHost（局域网访问用 0.0.0.0；-Host 是保留名，故用 -BindHost）
  -Port <端口>         监听端口，默认 $Port
  -Docker              改用 docker compose 部署（构建并后台启动）
  -WithOutlookEmail    配合 -Docker，同时启动可选 OutlookEmail 邮箱池
  -SkipInstall         跳过依赖安装与前端构建，直接启动
  -RebuildWeb          强制重新构建前端
  -Open                启动后自动打开浏览器
  -Check               只体检运行环境，不启动服务
  -Help                显示本帮助

环境变量:
  GROK_PYTHON          指定 Python 解释器（首次创建 .venv 时使用）
  GROK_WEB_HOST        默认监听地址
  GROK_WEB_PORT        默认监听端口
  GROK_CONFIG_FILE     自定义配置文件路径，默认 <项目>\config.json

Windows 提示:
  提示「禁止运行脚本」时: powershell -ExecutionPolicy Bypass -File $ScriptName
  未安装 Python 3.10+ 时: winget install Python.Python.3.12
  未安装 Node.js 22+ 时:  winget install OpenJS.NodeJS.LTS
  懒人入口: 双击 scripts\start-windows.bat（等价于本脚本，可带同样的参数）
"@ | Write-Host
}

function Get-PythonCandidates {
    $list = @()
    # py 启动器能挑到最新的 3.x，比裸 python 更可靠（后者可能是 Store 占位程序）。
    if (Test-Command 'py') {
        foreach ($ver in @('-3.13', '-3.12', '-3.11', '-3.10', '-3')) {
            $list += [pscustomobject]@{ File = 'py'; Pre = @($ver) }
        }
    }
    foreach ($name in @('python3', 'python')) {
        if (Test-Command $name) {
            $list += [pscustomobject]@{ File = $name; Pre = @() }
        }
    }
    return $list
}

function Test-PythonVersion($Candidate) {
    try {
        $argv = @()
        if ($Candidate.Pre) { $argv += $Candidate.Pre }
        $argv += @('-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)')
        & $Candidate.File @argv *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Get-PythonVersionText($Candidate) {
    try {
        $argv = @()
        if ($Candidate.Pre) { $argv += $Candidate.Pre }
        $argv += '-V'
        return ((& $Candidate.File @argv 2>&1) | Select-Object -First 1)
    } catch {
        return 'Python ?'
    }
}

function Find-BootstrapPython {
    if ($env:GROK_PYTHON) {
        $cand = [pscustomobject]@{ File = $env:GROK_PYTHON; Pre = @() }
        if (-not (Test-PythonVersion $cand)) {
            Stop-WithError "GROK_PYTHON 不可用或低于 3.10: $($env:GROK_PYTHON)"
        }
        return $cand
    }
    foreach ($cand in Get-PythonCandidates) {
        if (Test-PythonVersion $cand) { return $cand }
    }
    return $null
}

function Invoke-Python {
    param([string[]]$Arguments, [switch]$Quiet)
    $argv = @()
    if ($script:PyPre) { $argv += $script:PyPre }
    $argv += $Arguments
    if ($Quiet) { & $script:Py @argv *> $null } else { & $script:Py @argv }
    return ($LASTEXITCODE -eq 0)
}

function Initialize-Python {
    if (Test-Path -LiteralPath $VenvPy) {
        $script:Py = $VenvPy
        $script:PyPre = @()
        Write-Ok "$((& $VenvPy -V 2>&1) | Select-Object -First 1)（.venv）"
        return
    }
    $boot = Find-BootstrapPython
    if (-not $boot) {
        Stop-WithError '未找到 Python 3.10+：安装后重试（winget install Python.Python.3.12），或用 GROK_PYTHON 指定路径'
    }
    Write-Step "创建虚拟环境 .venv（$(Get-PythonVersionText $boot)）"
    $argv = @()
    if ($boot.Pre) { $argv += $boot.Pre }
    $argv += @('-m', 'venv', $VenvDir)
    & $boot.File @argv
    if ($LASTEXITCODE -ne 0) { Stop-WithError '创建 .venv 失败：确认 Python 安装时包含了 venv 模块' }
    if (-not (Test-Path -LiteralPath $VenvPy)) {
        Stop-WithError "创建 .venv 后仍找不到解释器: $VenvPy"
    }
    $script:Py = $VenvPy
    $script:PyPre = @()
    Write-Ok '虚拟环境就绪'
}

function Test-DepsReady {
    if (-not $script:Py) { return $false }
    return (Invoke-Python -Arguments @('-c', 'import fastapi, uvicorn, camoufox') -Quiet)
}

function Install-Requirements {
    $req = Join-Path $RootDir 'requirements.txt'
    $stamp = Join-Path $VenvDir '.requirements.sha256'
    if (-not (Test-Path -LiteralPath $req)) { Stop-WithError "缺少 requirements.txt: $req" }
    $want = (Get-FileHash -LiteralPath $req -Algorithm SHA256).Hash.ToLower()
    $have = ''
    if (Test-Path -LiteralPath $stamp) {
        $have = ((Get-Content -LiteralPath $stamp -Raw -ErrorAction SilentlyContinue) + '').Trim().ToLower()
    }
    if ($want -eq $have -and (Test-DepsReady)) {
        Write-Ok 'Python 依赖已就绪'
        return
    }
    Write-Step '安装 Python 依赖（requirements.txt）'
    if (-not (Invoke-Python -Arguments @('-m', 'pip', 'install', '--upgrade', 'pip') -Quiet)) {
        Write-Warn 'pip 自升级失败，继续安装依赖'
    }
    if (-not (Invoke-Python -Arguments @('-m', 'pip', 'install', '-r', $req))) {
        Stop-WithError '依赖安装失败：检查网络或代理后重试'
    }
    Set-Content -LiteralPath $stamp -Value $want -Encoding ascii
    Write-Ok 'Python 依赖安装完成'
}

function Test-CamoufoxReady {
    if (-not $script:Py) { return $false }
    $root = ''
    try {
        $argv = @()
        if ($script:PyPre) { $argv += $script:PyPre }
        $argv += @('-m', 'camoufox', 'path')
        $root = ((& $script:Py @argv 2>$null) | Select-Object -Last 1)
    } catch {
        return $false
    }
    if (-not $root) { return $false }
    $browsers = Join-Path ($root.ToString().Trim()) 'browsers'
    if (-not (Test-Path -LiteralPath $browsers)) { return $false }
    return ($null -ne (Get-ChildItem -LiteralPath $browsers -Force -ErrorAction SilentlyContinue |
        Select-Object -First 1))
}

function Install-Camoufox {
    if (Test-CamoufoxReady) {
        Write-Ok 'Camoufox 浏览器引擎已下载'
        return
    }
    Write-Step '下载 Camoufox 浏览器引擎（首次约数百 MB）'
    if (-not (Invoke-Python -Arguments @('-m', 'camoufox', 'fetch'))) {
        Stop-WithError 'Camoufox 下载失败：检查网络或代理后重试'
    }
    Write-Ok 'Camoufox 引擎就绪'
}

function Get-ConfigPath {
    if ($env:GROK_CONFIG_FILE) { return $env:GROK_CONFIG_FILE }
    return (Join-Path $RootDir 'config.json')
}

function Initialize-Config {
    $target = Get-ConfigPath
    # 与容器入口共用 scripts\seed_config.py：缺失时按模板生成，已存在时只补新增键。
    $argv = @(
        (Join-Path $RootDir 'scripts\seed_config.py'),
        '--target', $target,
        '--template', (Join-Path $RootDir 'config.example.json'),
        '--no-container-defaults'
    )
    if (-not (Invoke-Python -Arguments $argv)) {
        Stop-WithError "配置准备失败: $target"
    }
}

function Test-FrontendStale {
    # git pull 会把改动文件的 mtime 刷新成检出时间，只看 dist 是否存在会一直跑旧包。
    param([string]$Dist)
    if (-not (Test-Path -LiteralPath $Dist)) { return $true }
    $frontDir = Join-Path $RootDir 'front'
    $builtAt = (Get-Item -LiteralPath $Dist).LastWriteTimeUtc
    # 不进 node_modules / dist：前者动辄几万个文件，全量枚举会明显拖慢启动
    $newer = Get-ChildItem -LiteralPath $frontDir -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne 'node_modules' -and $_.Name -ne 'dist' } |
        ForEach-Object {
            if ($_.PSIsContainer) {
                Get-ChildItem -LiteralPath $_.FullName -Recurse -File -Force -ErrorAction SilentlyContinue
            } else {
                $_
            }
        } |
        Where-Object { $_.LastWriteTimeUtc -gt $builtAt } |
        Select-Object -First 1
    return [bool]$newer
}

function Build-Frontend {
    $dist = Join-Path $RootDir 'front\dist\index.html'
    if ((-not $RebuildWeb) -and (Test-Path -LiteralPath $dist)) {
        if (Test-FrontendStale -Dist $dist) {
            Write-Warn '前端源码比产物新，重新构建（跳过可加 -SkipInstall）'
        }
        else {
            Write-Ok '前端产物已存在'
            return
        }
    }
    if (-not (Test-Command 'npm')) {
        Write-Warn '未找到 npm，跳过前端构建；未构建时访问 / 会返回 503（API 仍可用）'
        return
    }
    $frontDir = Join-Path $RootDir 'front'
    if (-not (Test-Path -LiteralPath (Join-Path $frontDir 'node_modules'))) {
        Write-Step '安装前端依赖（npm install）'
        & npm --prefix $frontDir install
        if ($LASTEXITCODE -ne 0) { Stop-WithError 'npm install 失败' }
    }
    Write-Step '构建前端（npm run build）'
    & npm --prefix $frontDir run build
    if ($LASTEXITCODE -ne 0) { Stop-WithError '前端构建失败' }
    Write-Ok '前端构建完成'
}

function Test-PortBusy {
    $probe = $BindHost
    if ($BindHost -in @('0.0.0.0', '::', '*', '')) { $probe = '127.0.0.1' }
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync($probe, [int]$Port)
        if ($task.Wait(700)) { return $client.Connected }
        return $false
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Get-DisplayUrl {
    $shown = $BindHost
    if ($BindHost -eq '0.0.0.0' -or $BindHost -eq '::') { $shown = '127.0.0.1' }
    return "http://${shown}:$Port"
}

function Open-Ui([string]$Url) {
    # 等服务起来再打开，避免首屏连接被拒。
    try {
        Start-Job -ScriptBlock { Start-Sleep -Seconds 2; Start-Process $using:Url } | Out-Null
    } catch {
        Write-Warn "无法自动打开浏览器，请手动访问 $Url"
    }
}

function Get-ComposePort {
    if ($PortExplicit) { return $Port }
    $envFile = Join-Path $RootDir '.env'
    if (Test-Path -LiteralPath $envFile) {
        $hit = Select-String -LiteralPath $envFile -Pattern '^GROK_WEB_PORT=([0-9]+)' |
            Select-Object -Last 1
        if ($hit) { return $hit.Matches[0].Groups[1].Value }
    }
    return '8787'
}

function Invoke-DockerCompose {
    if (-not (Test-Command 'docker')) {
        Stop-WithError '未找到 docker：请先安装并启动 Docker Desktop'
    }
    & docker compose version *> $null
    if ($LASTEXITCODE -ne 0) {
        Stop-WithError 'docker compose 不可用：确认 Docker Desktop 已启动且自带 Compose v2'
    }
    Push-Location $RootDir
    try {
        if (-not (Test-Path -LiteralPath (Join-Path $RootDir '.env'))) {
            Copy-Item -LiteralPath (Join-Path $RootDir '.env.example') `
                -Destination (Join-Path $RootDir '.env')
            Write-Ok '已按 .env.example 生成 .env（端口、密钥、PUID 可在其中调整）'
        }
        if ($PortExplicit) { $env:GROK_WEB_PORT = $Port }
        if ($HostExplicit) { $env:GROK_WEB_BIND = $BindHost }

        $argv = @('compose')
        if ($WithOutlookEmail) { $argv += @('--profile', 'outlookemail') }
        $argv += @('up', '-d', '--build')
        Write-Step "docker $($argv -join ' ')"
        & docker @argv
        if ($LASTEXITCODE -ne 0) {
            Stop-WithError 'docker compose 启动失败，用 docker compose logs 查看原因'
        }
        Write-Ok '容器已在后台启动'
        Write-Host "  控制台: http://127.0.0.1:$(Get-ComposePort)"
        Write-Host '  日志:   docker compose logs -f grok-register'
        Write-Host '  状态:   docker compose ps'
        Write-Host '  停止:   docker compose down'
    } finally {
        Pop-Location
    }
}

function Invoke-Check {
    if (Test-Path -LiteralPath $VenvPy) {
        $script:Py = $VenvPy
        $script:PyPre = @()
        Write-Ok ".venv 就绪：$((& $VenvPy -V 2>&1) | Select-Object -First 1)"
    } else {
        $boot = Find-BootstrapPython
        if ($boot) {
            $script:Py = $boot.File
            $script:PyPre = $boot.Pre
            Write-Warn "尚未创建 .venv（首次启动自动创建），当前解释器: $(Get-PythonVersionText $boot)"
        } else {
            Write-Bad '未找到 Python 3.10+：winget install Python.Python.3.12，或用 GROK_PYTHON 指定'
        }
    }

    if ($script:Py) {
        if (Test-DepsReady) { Write-Ok 'Python 依赖已安装' }
        else { Write-Warn 'Python 依赖未安装（启动时自动安装）' }
        if (Test-CamoufoxReady) { Write-Ok 'Camoufox 浏览器引擎已下载' }
        else { Write-Warn 'Camoufox 引擎未下载（启动时自动下载，约数百 MB）' }
        if (Test-PortBusy) { Write-Warn "端口 $Port 已被占用，启动前请释放或改用 -Port" }
        else { Write-Ok "端口 $Port 可用" }
    }

    $cfg = Get-ConfigPath
    if (Test-Path -LiteralPath $cfg) { Write-Ok "配置文件: $cfg" }
    else { Write-Warn "缺少配置文件（启动时按 config.example.json 生成）: $cfg" }

    if (Test-Path -LiteralPath (Join-Path $RootDir 'front\dist\index.html')) {
        if (Test-FrontendStale -Dist (Join-Path $RootDir 'front\dist\index.html')) {
            Write-Warn '前端产物比源码旧（启动时会自动重新构建）'
        } else {
            Write-Ok '前端产物已构建'
        }
    } elseif (Test-Command 'npm') {
        Write-Warn '前端未构建（启动时执行 npm run build）'
    } else {
        Write-Bad '前端未构建且未安装 npm/Node.js 22+：控制台页面会返回 503'
    }

    if (Test-Command 'docker') { Write-Ok 'Docker 可用（-Docker 走容器部署）' }
    else { Write-Warn '未安装 Docker（只影响 -Docker 模式）' }

    if ($script:Issues -gt 0) {
        Stop-WithError "体检发现 $($script:Issues) 个必须处理的问题"
    }
    Write-Ok "体检通过，可直接运行 $ScriptName 启动"
}

function Start-Console {
    Initialize-Python
    if ($SkipInstall) {
        Write-Warn '-SkipInstall：跳过依赖安装与前端构建'
    } else {
        Install-Requirements
        Install-Camoufox
        Build-Frontend
    }
    Initialize-Config
    if (Test-PortBusy) {
        Stop-WithError "端口 $Port 已被占用：改用 -Port 换端口，或先停掉占用进程"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $RootDir 'front\dist\index.html'))) {
        Write-Warn '前端未构建，控制台页面会返回 503（API 仍可用）'
    }
    $url = Get-DisplayUrl
    Write-Ok "启动控制台 $url（Ctrl+C 停止）"
    if ($Open) { Open-Ui $url }
    Push-Location $RootDir
    try {
        & $script:Py -m backend.web.cli --host $BindHost --port $Port
        exit $LASTEXITCODE
    } finally {
        Pop-Location
    }
}

if ($Help) {
    Show-Usage
    exit 0
}
if (-not $BindHost) { Stop-WithError '-BindHost 不能为空' }
if ($Port -notmatch '^[0-9]+$') { Stop-WithError "-Port 需要是数字: $Port" }
if ([int]$Port -lt 1 -or [int]$Port -gt 65535) { Stop-WithError "-Port 超出范围: $Port" }
if ($WithOutlookEmail -and -not $Docker) {
    Write-Warn '-WithOutlookEmail 只在 -Docker 模式下生效'
}

Write-Step "Grok Register · Windows（$RootDir）"
if ($Docker) {
    Invoke-DockerCompose
} elseif ($Check) {
    Invoke-Check
} else {
    Start-Console
}
