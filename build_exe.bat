@echo off
chcp 65001 >nul
title A股智能股票分析工具 - 本地打包exe
echo ============================================================
echo    A股智能股票分析工具 - Windows exe 一键打包
echo ============================================================
echo.
echo    [推荐] 使用 GitHub Actions 云端自动打包，无需本机环境
echo    本脚本用于本地手动打包（可选）
echo.
cd /d "%~dp0"

echo [1/4] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.9+ 并勾选 "Add to PATH"
    pause
    exit /b 1
)

echo [2/4] 安装运行依赖 + 打包依赖...
pip install -r requirements.txt --break-system-packages >nul 2>&1
pip install -r build_requirements.txt --break-system-packages
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络连接
    pause
    exit /b 1
)

echo [3/4] 清理旧构建...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [4/4] 开始打包 (约需 2-5 分钟)...
pyinstaller --clean --noconfirm stock_analyzer.spec
if errorlevel 1 (
    echo [错误] 打包失败，请查看上方错误信息
    pause
    exit /b 1
)

echo.
echo ============================================================
echo    ✅ 打包完成！
echo.
echo    生成文件: dist\A股智能股票分析工具.exe
echo.
echo    使用说明:
echo      1. 首次运行请在同目录创建 .env 文件，填入:
echo         DEEPSEEK_API_KEY=你的Key
echo      2. 双击 exe 启动，将自动打开浏览器
echo      3. 关闭黑色窗口即停止服务
echo ============================================================
pause
