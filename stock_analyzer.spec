# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置 — A股智能股票分析工具
生成: 单文件 exe + 控制台窗口 + 自动开浏览器
用法: pyinstaller stock_analyzer.spec
"""

import os

# 资源目录（static 前端文件）
static_dir = os.path.join(os.path.dirname(os.path.abspath(SPEC)), "static")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "scipy"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="A股智能股票分析工具",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 禁用UPX避免杀软误报
    console=True,  # 控制台窗口：显示启动日志
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
