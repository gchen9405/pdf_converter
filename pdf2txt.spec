# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the Docling PDF -> TXT converter (ONEDIR build).
#
# Requires PyInstaller >= 6.11 and pyinstaller-hooks-contrib >= 2026.1
# (the modern hooks handle torch's versioned shared libs, transformers'
#  metadata, and the TorchScript-safe 'pyz+py' collection mode).
#
# build.py drives this and sets two env vars:
#     PDF2TXT_MODELS_DIR  -> absolute path to the pre-downloaded model weights
#     PDF2TXT_OCR         -> "1" to also bundle EasyOCR, else "0"
#
# Manual build:
#     pyinstaller pdf2txt.spec --noconfirm --clean
#
# Intentionally ONEDIR (not --onefile): with torch, onefile re-extracts ~GB to
# a temp dir on every launch -- slow, and it trips corporate antivirus far more
# than an in-place onedir folder. Keep UPX OFF (it corrupts torch/MKL libs).

import os

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
    copy_metadata,
)

# SPECPATH is the directory containing this spec file (injected by PyInstaller).
PROJECT = SPECPATH
APP = os.path.join(PROJECT, "app", "pdf2txt.py")
RTHOOK = os.path.join(PROJECT, "app", "rthook_offline.py")
MODELS = os.environ.get("PDF2TXT_MODELS_DIR") or os.path.join(PROJECT, "models")
WITH_OCR = os.environ.get("PDF2TXT_OCR") == "1"

if not os.path.isdir(MODELS):
    raise SystemExit(
        "[pdf2txt.spec] model weights not found at %r.\n"
        "Run prefetch_models.py first (build.py does this automatically)." % MODELS
    )

datas, binaries, hiddenimports = [], [], []

# ---------------------------------------------------------------------------
# 1) Over-collect the whole ML stack. collect_all() returns
#    (datas, binaries, hiddenimports) and also copies each package's metadata.
#    Wrapped in try/except so an absent optional package can't break the build.
# ---------------------------------------------------------------------------
collect_all_pkgs = [
    "docling", "docling_core", "docling_ibm_models", "docling_parse",
    "transformers", "huggingface_hub", "tokenizers", "safetensors",
    "accelerate",
    "torch", "torchvision",
    "rtree", "pypdfium2",
]
if WITH_OCR:
    # EasyOCR + its heavier, lazily-imported native deps.
    collect_all_pkgs += ["easyocr", "skimage", "shapely", "pyclipper", "bidi"]

for pkg in collect_all_pkgs:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:
        print("[pdf2txt.spec] collect_all skipped %s: %s" % (pkg, exc))

# ---------------------------------------------------------------------------
# 2) Distribution metadata that importlib.metadata.version() reads at run time.
#    transformers/torch/docling do hard version checks that fail in a frozen
#    app if the *.dist-info is missing.
# ---------------------------------------------------------------------------
metadata_pkgs = [
    "torch", "torchvision", "transformers", "tokenizers", "safetensors",
    "huggingface-hub", "tqdm", "numpy", "regex", "requests", "packaging",
    "filelock", "pyyaml", "pillow", "scipy",
    "docling", "docling-core", "docling-ibm-models", "docling-parse",
]
for name in metadata_pkgs:
    try:
        datas += copy_metadata(name)
    except Exception as exc:
        print("[pdf2txt.spec] copy_metadata skipped %s: %s" % (name, exc))

try:
    # transformers inspects the metadata of its entire dependency tree.
    datas += copy_metadata("transformers", recursive=True)
except Exception as exc:
    print("[pdf2txt.spec] copy_metadata(transformers, recursive): %s" % exc)

# ---------------------------------------------------------------------------
# 3) Hidden imports loaded dynamically (importlib) and missed by static analysis.
# ---------------------------------------------------------------------------
hiddenimports += [
    "torchvision._C",
    "torchvision.io.image",
    "PIL._tkinter_finder",
    "pydantic.deprecated.decorator",
]
if WITH_OCR:
    hiddenimports += ["easyocr.model.vgg_model", "easyocr.model.model"]

for pkg in ("torch", "transformers", "huggingface_hub",
            "docling", "docling_core", "docling_ibm_models"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# 4) Bundle the pre-downloaded model weights.
#    Lands at  dist/pdf2txt/_internal/models  -> sys._MEIPASS/models at run time.
# ---------------------------------------------------------------------------
datas += [(MODELS, "models")]

# ---------------------------------------------------------------------------
# 5) Assemble.
# ---------------------------------------------------------------------------
a = Analysis(
    [APP],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[RTHOOK],
    excludes=[
        "tkinter", "matplotlib", "PyQt5", "PyQt6", "PySide2", "PySide6",
        "IPython", "notebook", "jupyter", "pytest",
    ],
    noarchive=False,
    # Keep real .py sources for libraries that use TorchScript/JIT/inspect.
    module_collection_mode={
        "torch": "pyz+py",
        "torchvision": "pyz+py",
        "transformers": "pyz+py",
    },
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,        # ONEDIR: binaries go into COLLECT below
    name="pdf2txt",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                    # UPX corrupts torch/MKL shared libs -> OFF
    console=True,                 # keep a console window for logs/progress
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,             # build on the SAME arch you deploy to
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="pdf2txt",
)
