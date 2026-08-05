"""
Build: stable_assistant_api.py -> audiodg.exe (Microsoft metadata)
Usage: python build_exe.py
"""
import subprocess, sys, os, shutil

EXE_NAME = "audiodg"
MAIN     = "stable_assistant_api.py"
COMPANY  = "Microsoft Corporation"
PRODUCT  = "Windows Audio Device Graph Isolator"
VERSION  = "10.0.19041.1202"
DESC     = "Windows Audio Device Graph Isolator"


def clean():
    for p in ("dist","build","__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    for f in os.listdir("."):
        if f.endswith(".spec"): os.remove(f)
    print("[Build] Cleaned.")


def build():
    os.makedirs("dist", exist_ok=True)
    cmd = [
        sys.executable, "-m", "nuitka",
        "--onefile",
        "--windows-console-mode=disable",
        f"--windows-company-name={COMPANY}",
        f"--windows-product-name={PRODUCT}",
        f"--windows-product-version={VERSION}",
        f"--windows-file-version={VERSION}",
        f"--windows-file-description={DESC}",
        f"--output-filename={EXE_NAME}",
        "--output-dir=dist",
        "--assume-yes-for-downloads",
        "--python-flag=no_docstrings",
        "--python-flag=no_asserts",
        "--python-flag=no_annotations",
        "--enable-plugin=pyqt6",
        "--remove-output",
        MAIN,
    ]
    subprocess.run(cmd, check=True)


def report():
    out = os.path.join("dist", EXE_NAME + ".exe")
    if os.path.exists(out):
        mb = os.path.getsize(out) / 1024 / 1024
        print(f"\n[Build] Done: {os.path.abspath(out)}  ({mb:.1f} MB)")
        print(f"[Build] Task Manager: {EXE_NAME}.exe | {COMPANY} | {VERSION}")
        print(f"[Build] Run: dist\\{EXE_NAME}.exe")
    else:
        print("[Build] FAILED — exe not found.")


if __name__ == "__main__":
    clean()
    build()
    report()
