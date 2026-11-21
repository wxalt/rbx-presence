from __future__ import annotations

import sys


def _enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _already_running() -> bool:
    """Une seule instance à la fois (mutex nommé Windows)."""
    if sys.platform != "win32":
        return False
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW(None, False, "Local\\RBXPresenceSingleInstance")
    return kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def main() -> None:
    if _already_running():
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None, "RBX Presence is already running.", "RBX Presence", 0x40
            )
        return

    _enable_dpi_awareness()
    from src.ui import App

    App(start_minimized="--minimized" in sys.argv).mainloop()


if __name__ == "__main__":
    main()
