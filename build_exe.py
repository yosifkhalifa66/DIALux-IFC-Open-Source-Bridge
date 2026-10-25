"""
PyInstaller automated build script for DIALux IFC Bridge.
Produces a standalone single-file or folder executable in dist/
"""
import os
import sys
import subprocess
import shutil

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(ROOT_DIR, "dist")
BUILD_DIR = os.path.join(ROOT_DIR, "build")

def build():
    print("=" * 60)
    print("BUILDING DIALUX IFC BRIDGE STANDALONE EXECUTABLE")
    print("=" * 60)
    
    main_script = os.path.join(ROOT_DIR, "main.py")
    assert os.path.exists(main_script), f"Main script not found: {main_script}"
    
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name", "DialuxIFCBridge",
        "--windowed", # No console window on launch
        "--collect-all", "customtkinter",
        "--collect-all", "tkinterdnd2",
        "--collect-all", "ifcopenshell",
        "--collect-submodules", "numpy",
        "--paths", ROOT_DIR,
        "--distpath", DIST_DIR,
        "--workpath", BUILD_DIR,
        main_script
    ]
    
    print("Running command:")
    print(" ".join(cmd))
    
    result = subprocess.run(cmd, cwd=ROOT_DIR)
    if result.returncode != 0:
        print(f"\n[FAIL] PyInstaller failed with code {result.returncode}")
        sys.exit(result.returncode)
        
    exe_path = os.path.join(DIST_DIR, "DialuxIFCBridge", "DialuxIFCBridge.exe")
    if not os.path.exists(exe_path):
        # In case of onefile
        exe_path = os.path.join(DIST_DIR, "DialuxIFCBridge.exe")
        
    print("\n" + "=" * 60)
    print(f"BUILD SUCCESSFUL! Executable created at:\n{exe_path}")
    print("=" * 60)

if __name__ == "__main__":
    build()
