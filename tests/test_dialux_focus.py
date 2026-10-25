import ctypes
from ctypes import wintypes
import subprocess
import os

user32 = ctypes.windll.user32

def find_dialux_hwnd():
    dialux_hwnds = []
    
    def enum_cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value
                if "DIALux" in title:
                    dialux_hwnds.append((hwnd, title))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    cb = WNDENUMPROC(enum_cb)
    user32.EnumWindows(cb, 0)
    return dialux_hwnds

def activate_or_launch_dialux(dialux_exe_path: str = r"C:\Program Files\DIAL GmbH\DIALux\DIALux.exe"):
    hwnds = find_dialux_hwnd()
    if hwnds:
        hwnd, title = hwnds[0]
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        return True, f"Activated running DIALux window: '{title}'"
    else:
        if os.path.exists(dialux_exe_path):
            subprocess.Popen([dialux_exe_path])
            return True, "Launched DIALux evo successfully."
        return False, f"DIALux executable not found at: {dialux_exe_path}"

if __name__ == "__main__":
    print("Found DIALux windows:", find_dialux_hwnd())
