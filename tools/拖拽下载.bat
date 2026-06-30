@echo off
chcp 65001 >nul
title HyperDownloader — 拖拽下载

REM 简单的拖拽下载批处理
REM 从浏览器拖拽链接到此文件即可开始下载

echo ============================================
echo   HyperDownloader Core — 拖拽下载
echo ============================================
echo.

REM 检查是否有拖入的文件/URL
if "%~1"=="" (
    echo 请将下载链接从浏览器拖拽到此文件上。
    echo 或直接在命令行输入: %~nx0 [URL]
    echo.
    pause
    exit /b
)

set "URL=%~1"

REM 如果拖入的是 .url 快捷方式文件，提取其中的 URL
if /i "%~x1"==".url" (
    for /f "tokens=2 delims==" %%a in ('find "URL=" "%~1"') do set "URL=%%a"
)

echo  链接: %URL%
echo.

py "%~dp0drag_drop_downloader.py" --cli "%URL%"

echo.
echo 下载完成！
pause
