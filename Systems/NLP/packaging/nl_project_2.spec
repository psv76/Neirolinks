from pathlib import Path

root = Path(SPECPATH).parent


def collect_data_tree(source, destination):
    return [
        (str(path), str(Path(destination) / path.parent.relative_to(source)))
        for path in source.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    ]


datas = [
    *collect_data_tree(root / "resources" / "catalogs", "resources/catalogs"),
    *collect_data_tree(root / "resources" / "autocad", "resources/autocad"),
    *collect_data_tree(
        root / "src" / "nl_project_2" / "persistence" / "migrations",
        "nl_project_2/persistence/migrations",
    ),
]

excluded_qt_modules = [
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtPrintSupport",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtVirtualKeyboard",
    "PySide6.QtWebChannel",
    "PySide6.QtWebChannelQuick",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebView",
    "PySide6.QtWebViewQuick",
]

analysis = Analysis(
    [str(root / "tools" / "package_entry.py")],
    pathex=[str(root / "src"), str(root / "tools")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_qt_modules,
    noarchive=False,
    optimize=0,
)


def keep_binary(entry):
    destination = entry[0].replace("\\", "/").lower()
    filename = Path(destination).name
    if "/pyside6/plugins/" in f"/{destination}":
        return destination.endswith(
            (
                "pyside6/plugins/platforms/qoffscreen.dll",
                "pyside6/plugins/platforms/qwindows.dll",
            )
        )
    if destination.startswith("pyside6/qt6") and filename.endswith(".dll"):
        return filename in {"qt6core.dll", "qt6gui.dll", "qt6network.dll", "qt6widgets.dll"}
    if destination.startswith(("pyside6/", "shiboken6/")) and filename.startswith(
        ("msvcp", "vcruntime")
    ):
        return False
    return filename != "opengl32sw.dll"


analysis.binaries = [entry for entry in analysis.binaries if keep_binary(entry)]
analysis.datas = [
    entry
    for entry in analysis.datas
    if not entry[0].replace("\\", "/").lower().startswith("pyside6/qml/")
]
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="NLProject2",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="NLProject2",
)
