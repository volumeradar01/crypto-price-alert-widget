# PyInstaller spec — freezes the widget into a self-contained folder.
# Build from the repo root:  pyinstaller packaging/CryptoPriceAlert.spec
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[
        "PySide6.QtNetwork",
        "PySide6.QtWebSockets",
        "PySide6.QtMultimedia",
        "win32com",
        "win32com.client",
        "win32timezone",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib", "numpy", "PIL", "scipy", "pandas",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick3D",
        "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtDesigner",
        "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtBluetooth",
        "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtSensors",
        "PySide6.QtSerialPort", "PySide6.QtNfc",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CryptoPriceAlert",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=os.path.join(SPECPATH, "app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CryptoPriceAlert",
)
