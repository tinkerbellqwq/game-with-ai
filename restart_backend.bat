@echo off
chcp 65001 >nul 2>&1
title Backend Server - 谁是卧底

echo ========================================
echo   谁是卧底 - 后端服务
echo ========================================
echo.

:: 切换到项目目录
cd /d %~dp0

:: 停止现有后端进程
echo [1/2] 停止现有后端进程...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo       终止 PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul

:: 启动后端（带热重载）
echo [2/2] 启动后端服务 (热重载模式)...
echo.
echo ========================================
echo   URL:  http://localhost:8000
echo   文档: http://localhost:8000/docs
echo   按 Ctrl+C 停止服务
echo ========================================
echo.

:: 直接在当前窗口运行 uvicorn，支持热重载
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

:: 如果退出，暂停显示错误
echo.
echo 服务已停止
pause
