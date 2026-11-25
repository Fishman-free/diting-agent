@echo off
rem Diting one-click launcher (desktop icon target).
rem Chinese output only after chcp 65001: cmd.exe parses each line with the
rem code page active at that moment, so non-ASCII bytes before chcp corrupt
rem parsing. Keep this file CRLF (see .gitattributes).
cd /d "%~dp0.."
chcp 65001 >nul

set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
    echo [谛听] 首次启动，正在创建独立虚拟环境并安装依赖（仅一次，约数分钟）...
    where uv >nul 2>&1
    if not errorlevel 1 (
        uv venv .venv
        uv pip install --python "%PY%" -e .
    ) else (
        python -m venv .venv
        "%PY%" -m pip install -e .
    )
    if not exist "%PY%" (
        echo [谛听] 虚拟环境创建失败：优先安装 uv，或手动 python -m venv .venv 后 pip install -e .
        pause
        exit /b 1
    )
)

if not exist "diting\knowledge\geoguard.db" (
    echo [谛听] 首次启动，正在构建种子知识库...
    "%PY%" -X utf8 -m diting.geo_guard.ingest --seed
    echo.
)

"%PY%" -X utf8 -m hermes_cli.main %*
if errorlevel 1 (
    echo.
    echo [谛听] 启动失败：请把上方报错反馈给维护者。
    pause
)
