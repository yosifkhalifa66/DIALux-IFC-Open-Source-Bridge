import ctypes
from ctypes import wintypes
import os

CF_HDROP = 15
GHND = 0x0042

class DROPFILES(ctypes.Structure):
    _fields_ = [
        ("pFiles", wintypes.DWORD),
        ("pt", wintypes.POINT),
        ("fNC", wintypes.BOOL),
        ("fWide", wintypes.BOOL),
    ]

def copy_files_to_clipboard(file_paths: list[str]) -> bool:
    try:
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
        
        # Build null-terminated wide string buffer ending with double null
        # e.g.: "C:\file1.obj\0C:\file2.mtl\0\0"
        file_buffer = "\0".join(os.path.abspath(p) for p in file_paths) + "\0\0"
        encoded = file_buffer.encode("utf-16le")
        
        df = DROPFILES()
        df.pFiles = ctypes.sizeof(DROPFILES)
        df.pt.x = 0
        df.pt.y = 0
        df.fNC = False
        df.fWide = True
        
        df_bytes = bytes(df)
        total_data = df_bytes + encoded
        
        h_mem = kernel32.GlobalAlloc(GHND, len(total_data))
        if not h_mem:
            print("GlobalAlloc failed")
            return False
            
        p_mem = kernel32.GlobalLock(h_mem)
        if not p_mem:
            print("GlobalLock failed")
            kernel32.GlobalFree(h_mem)
            return False
            
        ctypes.memmove(p_mem, total_data, len(total_data))
        kernel32.GlobalUnlock(h_mem)
        
        if not user32.OpenClipboard(None):
            print("OpenClipboard failed, err:", ctypes.GetLastError())
            kernel32.GlobalFree(h_mem)
            return False
            
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_HDROP, h_mem)
        user32.CloseClipboard()
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error copying to clipboard: {e}")
        return False

if __name__ == "__main__":
    sample = r"D:\dialux ifc drag-drop\tests\sample_office.obj"
    success = copy_files_to_clipboard([sample])
    print("Clipboard copy success:", success)
