"""
DIALux evo Bridge: process detection, window activation, clipboard transfer,
and seamless desktop automation.
"""
import os
import sys
import ctypes
from ctypes import wintypes
import subprocess
import winreg
from typing import Optional, List, Tuple
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

# Setup Windows API calls with explicit 64-bit types
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int


def find_dialux_executable() -> Optional[str]:
    """Search for installed DIALux evo executable."""
    candidates = [
        r"C:\Program Files\DIAL GmbH\DIALux\DIALux.exe",
        r"C:\Program Files\DIAL GmbH\DIALux\DIALux_x64.exe",
        r"C:\Program Files (x86)\DIAL GmbH\DIALux\DIALux.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
            
    # Try reading from registry
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Dial.Dialux.Document\shell\open\command") as key:
            val, _ = winreg.QueryValueEx(key, "")
            if val:
                # Value is typically "C:\Program Files\...\DIALux.exe" "%1"
                parts = val.split('"')
                if len(parts) >= 2 and os.path.exists(parts[1]):
                    return parts[1]
    except Exception:
        pass
        
    return None


def get_dialux_windows() -> List[Tuple[int, str]]:
    """Enumerate all open top-level DIALux windows."""
    results = []
    
    def enum_cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value
                if "DIALux" in title:
                    results.append((hwnd, title))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    cb = WNDENUMPROC(enum_cb)
    user32.EnumWindows(cb, 0)
    return results


def activate_dialux() -> bool:
    """Bring the active DIALux window to the foreground."""
    windows = get_dialux_windows()
    if windows:
        hwnd, title = windows[0]
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        logger.info(f"Activated DIALux window: '{title}'")
        return True
    return False


def launch_dialux(exe_path: Optional[str] = None) -> bool:
    """Launch DIALux evo if it is not currently open."""
    path = exe_path or find_dialux_executable()
    if path and os.path.exists(path):
        subprocess.Popen([path], shell=False)
        logger.info(f"Launched DIALux from: {path}")
        return True
    logger.warning("DIALux executable not found.")
    return False


def copy_files_to_clipboard(file_paths: List[str]) -> bool:
    """
    Place file path(s) onto the Windows clipboard in CF_HDROP format.
    This enables direct pasting (Ctrl+V) into DIALux evo and Windows Explorer.
    """
    valid_paths = [os.path.abspath(p) for p in file_paths if os.path.exists(p)]
    if not valid_paths:
        logger.warning("No existing files to copy to clipboard.")
        return False
        
    try:
        # Buffer: Path1\0Path2\0\0 in UTF-16LE
        file_buffer = "\0".join(valid_paths) + "\0\0"
        encoded = file_buffer.encode("utf-16le")
        
        df = DROPFILES()
        df.pFiles = ctypes.sizeof(DROPFILES)
        df.pt.x = 0
        df.pt.y = 0
        df.fNC = False
        df.fWide = True
        
        total_data = bytes(df) + encoded
        
        h_mem = kernel32.GlobalAlloc(GHND, len(total_data))
        if not h_mem:
            return False
            
        p_mem = kernel32.GlobalLock(h_mem)
        if not p_mem:
            kernel32.GlobalFree(h_mem)
            return False
            
        ctypes.memmove(p_mem, total_data, len(total_data))
        kernel32.GlobalUnlock(h_mem)
        
        if not user32.OpenClipboard(None):
            kernel32.GlobalFree(h_mem)
            return False
            
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_HDROP, h_mem)
        user32.CloseClipboard()
        logger.info(f"Copied {len(valid_paths)} file(s) to Windows CF_HDROP clipboard.")
        return True
    except Exception as e:
        logger.error(f"Failed to copy to clipboard: {e}")
        return False


def reveal_in_explorer(file_path: str):
    """Open Windows Explorer with the specific file selected."""
    abs_path = os.path.abspath(file_path)
    if os.path.exists(abs_path):
        subprocess.run(["explorer.exe", f"/select,{abs_path}"], shell=False)


def send_to_dialux(obj_file_path: str) -> dict:
    """
    Execute full 'Send to DIALux' pipeline:
    1. Verify file exists
    2. Copy OBJ + MTL to clipboard
    3. Bring DIALux window to front or launch DIALux
    4. Return status info
    """
    if not os.path.exists(obj_file_path):
        return {"success": False, "message": f"File does not exist: {obj_file_path}"}
        
    # Accompanying MTL if present
    base, _ = os.path.splitext(obj_file_path)
    mtl_path = base + ".mtl"
    files = [obj_file_path]
    if os.path.exists(mtl_path):
        files.append(mtl_path)
        
    # Copy to clipboard
    copied = copy_files_to_clipboard(files)
    
    # Window management
    dialux_was_running = activate_dialux()
    if not dialux_was_running:
        launched = launch_dialux()
        status_msg = "DIALux evo launched. File copied to clipboard (Ctrl+V / Drag into 3D view)." if launched else "File copied to clipboard. Please open DIALux evo manually."
    else:
        status_msg = "DIALux evo activated! File copied to clipboard: Press Ctrl+V or drag directly into DIALux."
        
    return {
        "success": True,
        "copied": copied,
        "dialux_running": dialux_was_running,
        "message": status_msg,
        "file_path": obj_file_path
    }
