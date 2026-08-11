"""
Builds the LR desktop agent (the floating product-key panel + launcher)
into a single distributable LR_Agent.exe used by the combined Admin Panel.

Usage (from repo root):
    python installer/build/build_agent.py

Output:
    installer/build/output/LR_Agent.exe
"""

import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
BUILD_DIR = ROOT_DIR / "installer" / "build"

OUTPUT_DIR = BUILD_DIR / "output"
WORK_DIR = BUILD_DIR / "work"
SPEC_DIR = BUILD_DIR / "specs"

APP_NAME = "LR_Agent"
ENTRY_SCRIPT = ROOT_DIR / "agent" / "main.py"


def main():

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    SPEC_DIR.mkdir(parents=True, exist_ok=True)

    icon_path = BUILD_DIR.parent / "resources" / "lr_agent.ico"

    command = [
        sys.executable, "-m", "PyInstaller",
        str(ENTRY_SCRIPT),
        "--name", APP_NAME,
        "--onefile",
        "--windowed",
        "--noconfirm",
        "--distpath", str(OUTPUT_DIR),
        "--workpath", str(WORK_DIR),
        "--specpath", str(SPEC_DIR),
        "--paths", str(ROOT_DIR),
    ]

    if icon_path.exists():
        command += ["--icon", str(icon_path)]

    print("Running:", " ".join(command))

    subprocess.run(command, check=True)

    exe_path = OUTPUT_DIR / f"{APP_NAME}.exe"
    print(f"\nDone. Folder ready at: {OUTPUT_DIR / APP_NAME}")
    print(f"Exe inside that folder: {exe_path}")


if __name__ == "__main__":
    main()
