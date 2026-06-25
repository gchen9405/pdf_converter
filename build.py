#!/usr/bin/env python3
"""One-shot, cross-platform builder for the Docling PDF -> TXT executable.

Normally launched by build.bat (Windows) or build.sh (macOS/Linux), which pick
a Python 3.12 interpreter and set platform env first. It can also be run
directly with a 3.10-3.12 interpreter:

    python build.py [--with-ocr] [--build-root DIR]
                    [--skip-install] [--skip-prefetch] [--clean]

Stages (all in one run):
    1. create an isolated build venv
    2. install CPU-only PyTorch + Docling + PyInstaller (pinned)
    3. pre-download the Docling model weights
    4. freeze a standalone onedir executable with PyInstaller
    5. smoke-test the built exe on a sample PDF

Only stdlib is used here, so it runs on the system interpreter before the venv
exists. All heavy work happens inside the venv via subprocess calls.
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
IS_WIN = os.name == "nt"

# ---- pinned, verified-compatible versions ---------------------------------
TORCH = "torch==2.7.0"
TORCHVISION = "torchvision==0.22.0"
TORCH_INDEX = "https://download.pytorch.org/whl/cpu"
DOCLING_OCR = "docling[easyocr]==2.107.0"   # adds easyocr + scikit-image


def log(msg: str) -> None:
    print("\n=== %s ===" % msg, flush=True)


def run(cmd, env=None) -> None:
    printable = " ".join(str(c) for c in cmd)
    print("$ " + printable, flush=True)
    result = subprocess.run([str(c) for c in cmd], env=env)
    if result.returncode != 0:
        raise SystemExit("\n[build] command failed (exit %d):\n    %s"
                         % (result.returncode, printable))


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if IS_WIN else "bin/python")


def default_build_root() -> Path:
    """A short path on Windows to dodge the 260-char MAX_PATH limit."""
    if IS_WIN:
        candidates = [Path("C:/pdfc")]
        user = os.environ.get("USERPROFILE")
        if user:
            candidates.append(Path(user) / "pdfc")
        for cand in candidates:
            try:
                cand.mkdir(parents=True, exist_ok=True)
                return cand
            except Exception:
                continue
        return candidates[0]
    return PROJECT / ".build"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ocr", "--with-ocr", dest="ocr", action="store_true",
                    help="Bundle EasyOCR so scanned PDFs convert too (larger build).")
    ap.add_argument("--build-root", type=Path, default=None,
                    help="Where the venv/models/work/dist dirs live.")
    ap.add_argument("--check-only", action="store_true",
                    help="Fast check: install + prefetch + convert the sample "
                         "from source, then STOP (skip the PyInstaller freeze).")
    ap.add_argument("--skip-install", action="store_true",
                    help="Reuse an existing venv (skip pip install).")
    ap.add_argument("--skip-prefetch", action="store_true",
                    help="Reuse already-downloaded model weights.")
    ap.add_argument("--clean", action="store_true",
                    help="Delete the build root first for a fully fresh build.")
    args = ap.parse_args()

    if sys.version_info[:2] < (3, 10) or sys.version_info[0] != 3:
        raise SystemExit(
            "Docling needs Python 3.10-3.12, but this is %s.\n"
            "Run via build.bat / build.sh (which select 3.12), or call a 3.12 "
            "interpreter explicitly." % platform.python_version())

    build_root = (args.build_root or default_build_root()).resolve()
    if args.clean and build_root.exists():
        log("Cleaning %s" % build_root)
        shutil.rmtree(build_root, ignore_errors=True)
    build_root.mkdir(parents=True, exist_ok=True)

    venv = build_root / "venv"
    models = build_root / "models"
    work = build_root / "work"
    dist = build_root / "dist"
    vpy = venv_python(venv)

    print("Project    : %s" % PROJECT)
    print("Build root : %s" % build_root)
    print("Interpreter: %s (%s)" % (platform.python_version(), sys.executable))
    print("OCR        : %s" % ("yes (EasyOCR)" if args.ocr else "no"))
    started = time.time()

    # 1) venv ----------------------------------------------------------------
    if not vpy.exists():
        log("Creating build venv")
        run([sys.executable, "-m", "venv", str(venv)])
    else:
        print("\nReusing existing venv at %s" % venv)

    # 2) install -------------------------------------------------------------
    if not args.skip_install:
        log("Upgrading pip / wheel / setuptools")
        run([vpy, "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools"])

        # The PyTorch CPU index hosts Windows/Linux wheels (avoids the multi-GB
        # CUDA download). macOS torch ships only on regular PyPI, so skip the
        # index there.
        if sys.platform == "darwin":
            log("Installing PyTorch (macOS wheels from PyPI)")
            run([vpy, "-m", "pip", "install", TORCH, TORCHVISION])
        else:
            log("Installing CPU-only PyTorch (from the PyTorch CPU index)")
            run([vpy, "-m", "pip", "install", TORCH, TORCHVISION,
                 "--index-url", TORCH_INDEX])

        log("Installing Docling + PyInstaller (pinned, from requirements.txt)")
        run([vpy, "-m", "pip", "install", "-r", str(PROJECT / "requirements.txt")])

        if args.ocr:
            log("Adding EasyOCR support")
            run([vpy, "-m", "pip", "install", DOCLING_OCR])

        log("Verifying imports")
        run([vpy, "-c",
             "import torch, torchvision, docling; "
             "print('imports OK:', 'torch', torch.__version__, "
             "'| torchvision', torchvision.__version__)"])
    else:
        print("\nSkipping install (per --skip-install)")

    # 3) prefetch model weights ---------------------------------------------
    if args.skip_prefetch and models.is_dir():
        print("\nReusing model weights at %s" % models)
    else:
        log("Pre-downloading Docling model weights")
        cmd = [vpy, str(PROJECT / "prefetch_models.py"), "--out", str(models)]
        if args.ocr:
            cmd.append("--ocr")
        run(cmd)

    # 3b) optional fast functional check from source (no PyInstaller) --------
    if args.check_only:
        log("Functional check: converting the sample from source (no freeze)")
        src_out = build_root / "src_out"
        if src_out.exists():
            shutil.rmtree(src_out, ignore_errors=True)
        env = dict(os.environ)
        env["DOCLING_ARTIFACTS_PATH"] = str(models)   # use prefetched weights
        env["HF_HUB_OFFLINE"] = "1"                    # prove offline loading
        env["TRANSFORMERS_OFFLINE"] = "1"
        env["KMP_DUPLICATE_LIB_OK"] = "TRUE"
        run([vpy, str(PROJECT / "app" / "pdf2txt.py"),
             "-i", str(PROJECT / "sample_pdfs"), "-o", str(src_out)], env=env)
        produced = src_out / "sample.txt"
        text = (produced.read_text(encoding="utf-8", errors="ignore")
                if produced.exists() else "")
        ok = "quick brown fox" in text.lower()
        bar = "=" * 68
        print("\n" + bar)
        if ok:
            print("FUNCTIONAL CHECK PASSED in %.0f s" % (time.time() - started))
            print("Docling install + offline model load + Markdown -> .txt all work.")
            print("\nSample output (%d chars), first 400:\n%s" % (len(text), text[:400]))
            print("\nNOTE: this did NOT build the .exe. Re-run without --check-only")
            print("(add --skip-install --skip-prefetch to reuse this venv) to also")
            print("validate the PyInstaller packaging.")
            print(bar)
            return 0
        print("FUNCTIONAL CHECK FAILED: %s missing or unexpected content." % produced)
        print(bar)
        return 2

    # 4) build ---------------------------------------------------------------
    log("Freezing the executable with PyInstaller (onedir)")
    env = dict(os.environ)
    env["PDF2TXT_MODELS_DIR"] = str(models)
    env["PDF2TXT_OCR"] = "1" if args.ocr else "0"
    run([vpy, "-m", "PyInstaller", str(PROJECT / "pdf2txt.spec"),
         "--noconfirm", "--clean",
         "--distpath", str(dist), "--workpath", str(work)], env=env)

    app_dir = dist / "pdf2txt"
    exe = app_dir / ("pdf2txt.exe" if IS_WIN else "pdf2txt")
    if not exe.exists():
        raise SystemExit("Build finished but the executable is missing: %s" % exe)

    # 5) smoke test ----------------------------------------------------------
    log("Smoke-testing the built executable on a sample PDF")
    smoke = build_root / "_smoketest"
    if smoke.exists():
        shutil.rmtree(smoke, ignore_errors=True)
    s_in, s_out = smoke / "input", smoke / "output"
    s_in.mkdir(parents=True, exist_ok=True)
    sample = PROJECT / "sample_pdfs" / "sample.pdf"
    shutil.copy(str(sample), str(s_in / "sample.pdf"))

    run([exe, "-i", str(s_in), "-o", str(s_out)])
    produced = s_out / "sample.txt"
    passed = (produced.exists()
              and "quick brown fox" in produced.read_text(encoding="utf-8",
                                                          errors="ignore").lower())

    elapsed = time.time() - started
    bar = "=" * 68
    print("\n" + bar)
    if passed:
        print("BUILD SUCCEEDED in %.0f s" % elapsed)
        print("")
        print("Your standalone application folder:")
        print("    %s" % app_dir)
        print("")
        print("To use it: put PDFs in an 'input' folder next to the executable,")
        print("run it, and collect the .txt files from 'output'. Or:")
        print("    %s --input <pdf-folder> --output <txt-folder>" % exe.name)
        print("")
        print("Smoke test: PASS  (sample.pdf converted to text correctly).")
        print(bar)
        return 0

    print("BUILD COMPLETED in %.0f s, but the SMOKE TEST FAILED." % elapsed)
    print("The executable exists at:\n    %s" % exe)
    print("...but it did not convert the sample PDF correctly.")
    print("Scroll up for the first missing-module / metadata error and add the")
    print("offending package to collect_all / copy_metadata in pdf2txt.spec.")
    print(bar)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
