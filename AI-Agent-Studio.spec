# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['app', 'app.main', 'app.ui.app_window', 'app.services.storage', 'app.services.runner', 'app.services.llm', 'app.services.chat', 'app.services.attachments', 'app.services.terminal_tool']
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:\\Users\\Ashish\\Desktop\\Desktop\\AI Working\\AI Environment\\AI Management\\Developed Softwares\\AI-Agent-Studio\\entry.py'],
    pathex=['C:\\Users\\Ashish\\Desktop\\Desktop\\AI Working\\AI Environment\\AI Management\\Developed Softwares\\AI-Agent-Studio'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AI-Agent-Studio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AI-Agent-Studio',
)
