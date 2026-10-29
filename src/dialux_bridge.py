"""Windows DIALux discovery, foreground activation, and file clipboard support."""

from __future__ import annotations

import ctypes
import os
import re
import subprocess
import time
from ctypes import wintypes
from typing import Any

from .utils import logger

CF_HDROP = 15
GHND = 0x0042
SW_RESTORE = 9


class DROPFILES(ctypes.Structure):
    _fields_ = [
        ("pFiles", wintypes.DWORD),
        ("pt", wintypes.POINT),
        ("fNC", wintypes.BOOL),
        ("fWide", wintypes.BOOL),
    ]


def find_dialux_executable() -> str | None:
    if os.name != "nt":
        return None
    candidates = (
        r"C:\Program Files\DIAL GmbH\DIALux\DIALux.exe",
        r"C:\Program Files\DIAL GmbH\DIALux\DIALux_x64.exe",
        r"C:\Program Files (x86)\DIAL GmbH\DIALux\DIALux.exe",
    )
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT, r"Dial.Dialux.Document\shell\open\command"
        ) as key:
            command, _ = winreg.QueryValueEx(key, "")
        match = re.match(
            r'\s*(?:"([^"]+\.exe)"|(.+?\.exe)(?:\s|$))',
            command,
            flags=re.IGNORECASE,
        )
        executable = next((value for value in match.groups() if value), None) if match else None
        if executable and os.path.isfile(executable):
            return executable
    except (OSError, ImportError) as exc:
        logger.debug("DIALux registry lookup did not find an executable: %s", exc)
    return None


def _dialux_processes() -> list[dict[str, Any]]:
    try:
        import psutil
    except ImportError:
        psutil = None
    if psutil is not None:
        matches = []
        for process in psutil.process_iter(("name", "exe")):
            try:
                name = (process.info.get("name") or "").casefold()
                executable = (process.info.get("exe") or "").casefold()
                if "dialux" in name or "dialux" in executable:
                    matches.append(process.info)
            except (psutil.Error, OSError):
                continue
        return matches

    if os.name != "nt":
        return []
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Could not check running processes: %s", exc)
        return []
    return [{"name": line} for line in result.stdout.splitlines() if "dialux" in line.casefold()]


def is_dialux_process_running() -> bool:
    return bool(_dialux_processes())


def get_dialux_windows() -> list[tuple[int, str]]:
    if os.name != "nt":
        return []
    user32 = ctypes.windll.user32
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.EnumWindows.argtypes = (
        ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
        wintypes.LPARAM,
    )
    user32.EnumWindows.restype = wintypes.BOOL
    windows: list[tuple[int, str]] = []

    def callback(hwnd: int, _parameter: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        if "dialux" in title.value.casefold():
            windows.append((int(hwnd), title.value))
        return True

    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    callback_ref = callback_type(callback)
    user32.EnumWindows(callback_ref, 0)
    return windows


def get_dialux_connection_status() -> dict[str, Any]:
    executable = find_dialux_executable()
    running = is_dialux_process_running()
    windows = get_dialux_windows()
    connected = running and bool(windows)
    if connected:
        text = "DIALux evo is open"
    elif running:
        text = "DIALux evo is running"
    elif executable:
        text = "DIALux evo is installed"
    else:
        text = "DIALux evo not detected"
    return {
        "installed": executable is not None,
        "exe_path": executable,
        "running": running,
        "windows": windows,
        "connected": connected,
        "status_text": text,
    }


def activate_dialux() -> bool:
    windows = get_dialux_windows()
    if not windows:
        return False
    hwnd, title = windows[0]
    user32 = ctypes.windll.user32
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.ShowWindow(hwnd, SW_RESTORE)
    activated = bool(user32.SetForegroundWindow(hwnd))
    if activated:
        logger.info("Activated DIALux window: %s", title)
    return activated


def launch_dialux(exe_path: str | None = None) -> bool:
    executable = exe_path or find_dialux_executable()
    if not executable or not os.path.isfile(executable):
        return False
    try:
        subprocess.Popen([executable], shell=False)
        logger.info("Launched DIALux from %s", executable)
        return True
    except OSError as exc:
        logger.error("Could not launch DIALux: %s", exc, exc_info=True)
        return False


def copy_files_to_clipboard(file_paths: list[str]) -> bool:
    if os.name != "nt":
        raise OSError("The Windows file clipboard is available only on Windows.")
    if not file_paths:
        raise ValueError("Select at least one file to copy.")

    paths = []
    for path in file_paths:
        absolute_path = os.path.abspath(path)
        if not os.path.isfile(absolute_path):
            raise FileNotFoundError(f"Clipboard file does not exist: {absolute_path}")
        paths.append(absolute_path)

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalFree.restype = wintypes.HGLOBAL
    user32.OpenClipboard.argtypes = (wintypes.HWND,)
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL

    dropfiles = DROPFILES()
    dropfiles.pFiles = ctypes.sizeof(DROPFILES)
    dropfiles.fNC = False
    dropfiles.fWide = True
    path_data = ("\0".join(paths) + "\0\0").encode("utf-16le")
    data = bytes(dropfiles) + path_data
    memory = kernel32.GlobalAlloc(GHND, len(data))
    if not memory:
        raise OSError("Windows could not allocate clipboard memory.")
    clipboard_owns_memory = False
    try:
        pointer = kernel32.GlobalLock(memory)
        if not pointer:
            raise OSError("Windows could not lock clipboard memory.")
        try:
            ctypes.memmove(pointer, data, len(data))
        finally:
            kernel32.GlobalUnlock(memory)

        opened = False
        for attempt in range(5):
            if user32.OpenClipboard(None):
                opened = True
                break
            time.sleep(0.1 * (attempt + 1))
        if not opened:
            raise OSError("The clipboard is busy; close other clipboard tools and retry.")
        try:
            if not user32.EmptyClipboard():
                raise OSError("Windows could not clear the clipboard.")
            if not user32.SetClipboardData(CF_HDROP, memory):
                raise OSError("Windows rejected the file list on the clipboard.")
            clipboard_owns_memory = True
        finally:
            user32.CloseClipboard()
    finally:
        if not clipboard_owns_memory:
            kernel32.GlobalFree(memory)
    logger.info("Copied %d file(s) to the Windows file clipboard.", len(paths))
    return True


def reveal_in_explorer(file_path: str) -> None:
    absolute_path = os.path.abspath(file_path)
    if not os.path.exists(absolute_path):
        raise FileNotFoundError(absolute_path)
    if os.name == "nt":
        subprocess.Popen(["explorer.exe", f"/select,{absolute_path}"], shell=False)
    else:
        raise OSError("Opening Windows Explorer is available only on Windows.")


def send_to_dialux(obj_file_path: str, *, activate: bool = True) -> dict[str, Any]:
    if not os.path.isfile(obj_file_path):
        raise FileNotFoundError(obj_file_path)
    base, _ = os.path.splitext(obj_file_path)
    files = [obj_file_path]
    mtl_path = base + ".mtl"
    if os.path.isfile(mtl_path):
        files.append(mtl_path)
    copied = copy_files_to_clipboard(files)
    if not activate:
        return {
            "success": copied,
            "copied": copied,
            "dialux_activated": False,
            "dialux_launched": False,
            "message": "Files copied. Open the prepared DIALux project, then press Ctrl+V to import.",
            "file_path": obj_file_path,
        }
    activated = activate_dialux()
    launched = False
    if not activated and not is_dialux_process_running():
        launched = launch_dialux()
    if launched:
        message = "Files copied. DIALux evo is starting; press Ctrl+V in DIALux to import."
    elif activated:
        message = "Files copied. Press Ctrl+V in DIALux to import the OBJ and its MTL."
    else:
        message = "Files copied. Open DIALux evo and press Ctrl+V to import the OBJ and its MTL."
    return {
        "success": copied,
        "copied": copied,
        "dialux_activated": activated,
        "dialux_launched": launched,
        "message": message,
        "file_path": obj_file_path,
    }
