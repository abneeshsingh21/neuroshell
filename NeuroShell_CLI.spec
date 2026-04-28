# -*- mode: python ; coding: utf-8 -*-
# NeuroShell CLI Build — Console Mode for VS Code Terminal Integration
# Build: pyinstaller NeuroShell_CLI.spec
# Output: dist/NeuroShell.exe (console=True)

a = Analysis(
    ['C:\\Users\\lenovo\\Desktop\\LLM model train\\neuroshell\\neuroshell_cli.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\lenovo\\Desktop\\LLM model train\\neuroshell\\assets', 'assets'),
           ('C:\\Users\\lenovo\\AppData\\Local\\Programs\\Python\\Python311\\Lib\\site-packages\\rich\\_unicode_data', 'rich/_unicode_data')],
    hiddenimports=['rich._unicode_data'],
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
    a.binaries,
    a.datas,
    [],
    name='NeuroShell-CLI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,          # <-- KEY DIFFERENCE: console=True for VS Code terminal
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:\\Users\\lenovo\\Desktop\\LLM model train\\neuroshell\\assets\\icon.ico'],
)
