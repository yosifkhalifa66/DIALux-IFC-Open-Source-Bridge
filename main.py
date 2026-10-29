"""DIALux IFC Bridge entry point with global error hooks."""

from __future__ import annotations

import sys
import threading
import traceback
from tkinter import messagebox

from src.app import main
from src.utils import get_log_path, logger


def handle_unhandled_exception(exc_type, exc_value, exc_traceback) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
    formatted = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    try:
        messagebox.showerror(
            "Unexpected Application Error",
            f"DIALux IFC Bridge encountered an unexpected error:\n\n{exc_value}\n\n"
            f"Log details saved to:\n{get_log_path()}\n\n"
            f"Details:\n{formatted[:600]}",
        )
    except Exception:
        pass


def handle_thread_exception(args: threading.ExceptHookArgs) -> None:
    logger.critical("Unhandled thread exception in %s", args.thread.name, exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


sys.excepthook = handle_unhandled_exception
if hasattr(threading, "excepthook"):
    threading.excepthook = handle_thread_exception

if __name__ == "__main__":
    main()
