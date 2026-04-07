# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for The Blockheads – PC Edition.

Build:
  pip install pyinstaller
  pyinstaller blockheads_pc.spec

Output: dist/BlockheadsPC/  (folder)  or  dist/BlockheadsPC.exe  (Windows)
"""

import os
import sys

block_cipher = None

# ── Source files ──────────────────────────────────────────────────────────────
a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    # No data files bundled: assets are downloaded at first run
    datas=[],
    hiddenimports=[
        "pygame",
        "pygame.mixer",
        "pygame.font",
        "pygame.image",
        "pygame.transform",
        "numpy",
        "numpy.core",
        "numpy.core._methods",
        "numpy.lib.format",
        "http.cookiejar",
        "urllib.request",
        "urllib.parse",
        "zipfile",
        "threading",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "pandas",
        "IPython",
        "PIL",
        "Pillow",
        "cv2",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Executable ────────────────────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,      # One-dir mode (faster startup)
    name="BlockheadsPC",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=True,               # Keep console for error visibility
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Windows icon (ignored on Linux/macOS – they use the COLLECT bundle)
    icon=None,
)

# ── Bundle directory ──────────────────────────────────────────────────────────
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BlockheadsPC",
)
