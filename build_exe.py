"""Build the self-contained Windows bundle and, when available, its installer."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
APP_DIST = DIST / "DialuxIFCBridge"
BUILD = ROOT / "build"
INSTALLER_SCRIPT = ROOT / "installer" / "DialuxIFCBridge.iss"
NATIVE_PROJECT = ROOT / "native" / "DialuxIfcNativeHost.csproj"
NATIVE_PUBLISH = BUILD / "nativehost"


def find_dialux_install() -> Path | None:
    candidates = [
        Path(os.environ["DIALUX_INSTALL_DIR"]) if os.environ.get("DIALUX_INSTALL_DIR") else None,
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "DIAL GmbH" / "DIALux",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "DIAL GmbH" / "DIALux",
    ]
    for candidate in candidates:
        if candidate and (candidate / "DIALux_x64.dll").is_file():
            return candidate
    return None


def find_inno_compiler() -> str | None:
    compiler = shutil.which("ISCC.exe") or shutil.which("ISCC")
    if compiler:
        return compiler
    for candidate in (
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def main() -> int:
    if os.name != "nt":
        print("The installer can only be built on Windows.", file=sys.stderr)
        return 2
    dialux_install = find_dialux_install()
    if dialux_install is None:
        print(
            "A DIALux evo installation is required to build the version-pinned native project adapter. "
            "Set DIALUX_INSTALL_DIR to its installation folder.",
            file=sys.stderr,
        )
        return 2
    dotnet = shutil.which("dotnet")
    if not dotnet:
        print("A .NET SDK capable of targeting net8.0-windows is required.", file=sys.stderr)
        return 2
    if NATIVE_PUBLISH.exists():
        shutil.rmtree(NATIVE_PUBLISH)
    subprocess.run(
        [
            dotnet,
            "publish",
            str(NATIVE_PROJECT),
            "--configuration",
            "Release",
            "--runtime",
            "win-x64",
            "--self-contained",
            "true",
            f"-p:DialuxInstall={dialux_install}",
            "-p:PublishSingleFile=false",
            "--output",
            str(NATIVE_PUBLISH),
        ],
        cwd=ROOT,
        check=True,
    )
    native_host = NATIVE_PUBLISH / "DialuxIfcNativeHost.exe"
    if not native_host.is_file():
        print(f"The native DIALux adapter was not produced at {native_host}.", file=sys.stderr)
        return 2
    runtime_config_path = native_host.with_name("DialuxIfcNativeHost.runtimeconfig.json")
    try:
        runtime_options = json.loads(runtime_config_path.read_text(encoding="utf-8"))["runtimeOptions"]
    except (OSError, KeyError, json.JSONDecodeError) as error:
        print(f"Could not verify the native adapter runtime configuration: {error}", file=sys.stderr)
        return 2
    required_runtime_files = ("coreclr.dll", "hostfxr.dll", "hostpolicy.dll")
    if not runtime_options.get("includedFrameworks") or not all(
        (NATIVE_PUBLISH / name).is_file() for name in required_runtime_files
    ):
        print(
            "The native DIALux adapter publish is not self-contained. "
            "Refusing to package a build that requires a separately installed .NET runtime.",
            file=sys.stderr,
        )
        return 2
    if APP_DIST.exists():
        shutil.rmtree(APP_DIST)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        "DialuxIFCBridge",
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD / "pyinstaller"),
        "--specpath",
        str(BUILD),
        "--collect-all",
        "ifcopenshell",
        "--collect-all",
        "customtkinter",
        "--collect-all",
        "tkinterdnd2",
        "--collect-all",
        "psutil",
        "--collect-all",
        "shapely",
        "--hidden-import",
        "ifcopenshell.geom",
        "--hidden-import",
        "ifcopenshell.util.unit",
        str(ROOT / "main.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    native_bundle = APP_DIST / "native"
    if native_bundle.exists():
        shutil.rmtree(native_bundle)
    shutil.copytree(NATIVE_PUBLISH, native_bundle, dirs_exist_ok=True)
    shutil.copy2(ROOT / "native" / "THIRD-PARTY-NOTICES.txt", native_bundle)

    compiler = find_inno_compiler()
    if compiler is None:
        print(
            "The application bundle was built at "
            f"{APP_DIST}, but the installer was not compiled. "
            "Install Inno Setup 6 and rerun this script to create the setup executable.",
            file=sys.stderr,
        )
        return 2
    (ROOT / "release").mkdir(parents=True, exist_ok=True)
    subprocess.run([compiler, str(INSTALLER_SCRIPT)], cwd=ROOT, check=True)
    print(f"Installer created in {ROOT / 'release'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
