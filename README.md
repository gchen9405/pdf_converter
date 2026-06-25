# pdf2txt — offline PDF → TXT converter (IBM Docling)

A standalone executable that reads every PDF in a folder and writes a `.txt`
file for each, using **IBM Docling**. All model weights are **bundled inside the
executable**, so it runs **fully offline** — nothing is downloaded when the exe
runs.

By default each `.txt` file contains **Docling Markdown** (headings, tables, and
structure preserved), written directly into the `.txt` — no intermediate `.md`
file is created. The `.txt` extension is deliberate: downstream tools that only
accept `.txt` (e.g. a GraphRAG text reader, which treats file contents as
opaque) ingest markdown-inside-`.txt` fine. Pass `--plain` for plain text
instead; the extension stays `.txt` either way.

This repository is the **build recipe**, not a prebuilt binary. You run one
script on the target machine and it produces the executable. The heavy install
happens **once**, on that machine.

---

## TL;DR — build it on Windows

1. Install **Python 3.12** from <https://www.python.org/downloads/> — tick
   *“Add python.exe to PATH”*. (Only needed to *build*; the finished exe is
   self-contained.)
2. Copy this whole folder to the machine (USB/zip — no GitHub needed).
3. Double-click **`build.bat`** (or run it in a terminal).
   - For scanned/image PDFs too: `build.bat --with-ocr`
4. Wait for the one-time install + build. At the end it **self-tests** the exe
   and prints where it is:
   ```
   BUILD SUCCEEDED ...
   Your standalone application folder:
       C:\pdfc\dist\pdf2txt
   Smoke test: PASS
   ```

That `pdf2txt` folder is the whole app. You can move or zip it anywhere.

---

## Using the built program

Inside the app folder (`...\dist\pdf2txt\`):

```
pdf2txt.exe            <- the program
_internal\             <- bundled libraries + model weights (keep next to the exe)
```

**Easiest way:** create an `input` folder next to `pdf2txt.exe`, drop your PDFs
in, and run `pdf2txt.exe`. Results appear in an `output` folder.

**Or pass folders explicitly:**

```bat
pdf2txt.exe --input  "C:\path\to\pdfs" --output "C:\path\to\txt"
pdf2txt.exe --input  "C:\docs" --recursive          REM include subfolders
pdf2txt.exe --plain  --input "C:\docs"               REM plain text instead of Markdown
pdf2txt.exe --ocr    --input "C:\scans"              REM scanned PDFs (needs a --with-ocr build; see "How OCR works")
pdf2txt.exe report1.pdf report2.pdf                  REM specific files
```

Output is **Docling Markdown written into `.txt` files** by default (structure
preserved, ready for a `.txt`-only GraphRAG ingest). Add `--plain` if you want
plain text rather than Markdown — the extension is `.txt` either way.

Run `pdf2txt.exe --help` for all options. One bad PDF won’t stop the batch — it
is reported and the rest continue; a summary is printed at the end.

---

## What gets built & how big it is

Docling is a deep-learning toolkit, so the bundle includes **PyTorch + the
Docling model weights**. Expect:

| Build | Approx. size | Handles |
|-------|--------------|---------|
| `build.bat` (default) | **~2–2.8 GB** | digital PDFs (text extracted directly) |
| `build.bat --with-ocr` | **~2.5–3.5 GB** | digital **and** scanned/image-only PDFs |

The default build extracts text directly from the PDF’s text layer (fast, no
OCR). Scanned/image-only PDFs need the `--with-ocr` build.

---

## How OCR works (two switches, both required)

OCR is gated by **two** independent switches — one at build time, one at run
time — and you need **both** for OCR to actually run:

1. **`build.bat --with-ocr` (build time)** — bundles the EasyOCR engine and its
   weights *into* the exe. A default build ships **without** them, so its exe
   simply *cannot* OCR, no matter what flags you pass.
2. **`pdf2txt.exe --ocr` (run time)** — tells that exe to actually use the
   bundled OCR engine on scanned/image-only PDFs.

The `--ocr` flag exists on **every** build (it's always a valid argument), but
it only does something on a `--with-ocr` build. If you pass `--ocr` to a default
build, the program does **not** error: it prints a warning, then continues
**without OCR** (digital PDFs still convert fine; a scanned PDF just yields an
almost-empty `.txt`):

```
[warn] --ocr requested, but this build has no OCR model bundled;
continuing WITHOUT OCR. Rebuild with --with-ocr to enable it.
```

So: build with `--with-ocr` **and** run with `--ocr`. One without the other
gives you no OCR.

---

## How it works (for the curious)

- **`build.bat` / `build.sh`** — thin OS wrappers: find Python 3.12, set safe
  env (UTF-8, OpenMP guard, short temp dir), then call `build.py`.
- **`build.py`** — the cross-platform brain. Creates an isolated **build venv**,
  installs the pinned deps into it, pre-downloads the models, runs PyInstaller,
  and smoke-tests the exe. (Uses only the standard library, so it runs before
  the venv exists.)
- **`prefetch_models.py`** — downloads the Docling layout + table-structure
  weights (and EasyOCR weights with `--ocr`) into a local folder.
- **`pdf2txt.spec`** — the PyInstaller recipe (which packages to collect, which
  metadata to copy, the runtime hook, and the bundled `models` folder).
- **`app/pdf2txt.py`** — the application itself.
- **`app/rthook_offline.py`** — runs before any import in the frozen exe to
  point Docling at the bundled weights and force offline mode.

Offline is enforced with `DOCLING_ARTIFACTS_PATH` (bundled weights) plus
`HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1`.

### Pinned versions (verified)
- `docling==2.107.0` (→ `docling-slim[standard]`, the full local pipeline)
- `torch==2.7.0` + `torchvision==0.22.0` (CPU-only, from the PyTorch CPU index)
- `pyinstaller==6.21.0`, `pyinstaller-hooks-contrib==2026.6`
- OCR build adds `docling[easyocr]` (`easyocr==1.7.2` + `scikit-image`)
- Build interpreter: **Python 3.12**

---

## Cross-platform note (important)

A compiled executable is **OS- and CPU-specific**. PyInstaller on Windows makes
a **Windows** exe; on macOS a **macOS** app; on Linux a **Linux** binary. There
is no single file that runs on all three.

This project is cross-platform at the **recipe** level: the *same* sources +
`build.py` produce a native executable on each OS.
- **Windows:** `build.bat`  → `pdf2txt.exe`
- **macOS / Linux:** `./build.sh` → `pdf2txt` (useful for local testing)

Build on the **same OS and CPU architecture** you’ll deploy to.

---

## Troubleshooting

- **“Python 3.12 was not found.”** Install it (tick *Add to PATH*) and re-run.
  Check what’s installed with `py --list`.
- **Build seems to hang.** First run downloads PyTorch + Docling + model
  weights (often >1 GB total) — slow on a VPN. Let it finish. Re-running with
  `--skip-install` / `--skip-prefetch` reuses what’s already there.
- **Antivirus / SmartScreen warns about the exe.** Unsigned PyInstaller apps
  are common false positives. The build is **onedir** (not a self-extracting
  onefile) specifically to minimize this. On a managed laptop, ask IT to
  allow-list the `pdf2txt` folder (send them the source + this README).
- **“path too long” during build.** `build.bat` already builds under a short
  path (`C:\pdfc`, falling back to `%USERPROFILE%\pdfc`). If your account can’t
  create `C:\pdfc`, the fallback handles it automatically.
- **A `--with-ocr` build fails to freeze.** OCR pulls extra native libraries
  that occasionally need a tweak. The plain build is rock-solid; use it unless
  you specifically need scanned-PDF support. The first missing-module error in
  the log tells you exactly which package to add to `collect_all` /
  `copy_metadata` in `pdf2txt.spec`.
- **Scanned PDF produced an (almost) empty `.txt`.** That PDF has no text
  layer — rebuild with `build.bat --with-ocr` and run with `--ocr`.

---

## Rebuilding / iterating

```bat
build.bat                          REM full clean-ish build (reuses venv if present)
build.bat --with-ocr               REM include OCR
build.bat --check-only             REM fast: install+prefetch+convert sample, NO freeze
build.py --skip-install            REM reuse venv, redo prefetch+build  (advanced)
build.py --clean                   REM wipe the build root and start fresh
```

(`build.py` flags can be appended to `build.bat` — they’re forwarded.)

`--check-only` is a quick sanity check: it verifies Docling installs and converts
a PDF to Markdown-in-`.txt` from source, then stops before the slow PyInstaller
freeze. To then build the exe reusing that venv/models:
`build.bat --skip-install --skip-prefetch`.
