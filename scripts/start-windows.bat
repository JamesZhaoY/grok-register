@echo off
rem Windows 懒人入口：双击即可启动，也可 start-windows.bat -Port 9000 传参给 PowerShell 脚本。
chcp 65001 >nul 2>&1
setlocal

set "PS_SCRIPT=%~dp0start-windows.ps1"
if not exist "%PS_SCRIPT%" (
    echo [x] Missing %PS_SCRIPT%
    pause
    exit /b 1
)

rem 优先 PowerShell 7（pwsh），没有就用系统自带的 Windows PowerShell 5.1。
set "PS_EXE=powershell"
where pwsh >nul 2>&1
if not errorlevel 1 set "PS_EXE=pwsh"

"%PS_EXE%" -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%" %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo [x] 启动失败，退出码 %RC%，请查看上方日志。 / Failed with exit code %RC%.
    pause
)
exit /b %RC%
