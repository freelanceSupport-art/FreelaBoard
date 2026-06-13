from __future__ import annotations

import ctypes
import sys
from pathlib import Path
from typing import Callable


IS_WINDOWS = sys.platform.startswith("win")


if IS_WINDOWS:
    from ctypes import wintypes

    DWORD = wintypes.DWORD
    UINT = wintypes.UINT
    HWND = wintypes.HWND
    HANDLE = wintypes.HANDLE
    LPARAM = wintypes.LPARAM
    WPARAM = wintypes.WPARAM
    LRESULT = ctypes.c_ssize_t
    LONG_PTR = ctypes.c_ssize_t

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", DWORD),
            ("hWnd", HWND),
            ("uID", UINT),
            ("uFlags", UINT),
            ("uCallbackMessage", UINT),
            ("hIcon", HANDLE),
            ("szTip", ctypes.c_wchar * 128),
            ("dwState", DWORD),
            ("dwStateMask", DWORD),
            ("szInfo", ctypes.c_wchar * 256),
            ("uTimeoutOrVersion", UINT),
            ("szInfoTitle", ctypes.c_wchar * 64),
            ("dwInfoFlags", DWORD),
            ("guidItem", GUID),
            ("hBalloonIcon", HANDLE),
        ]

    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)

    shell32 = ctypes.windll.shell32
    user32 = ctypes.windll.user32

    Shell_NotifyIconW = shell32.Shell_NotifyIconW
    Shell_NotifyIconW.argtypes = [DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    Shell_NotifyIconW.restype = wintypes.BOOL

    LoadImageW = user32.LoadImageW
    LoadImageW.argtypes = [HANDLE, wintypes.LPCWSTR, UINT, ctypes.c_int, ctypes.c_int, UINT]
    LoadImageW.restype = HANDLE

    LoadIconW = user32.LoadIconW
    LoadIconW.argtypes = [HANDLE, HANDLE]
    LoadIconW.restype = HANDLE

    CreatePopupMenu = user32.CreatePopupMenu
    CreatePopupMenu.argtypes = []
    CreatePopupMenu.restype = HANDLE

    AppendMenuW = user32.AppendMenuW
    AppendMenuW.argtypes = [HANDLE, UINT, ctypes.c_size_t, wintypes.LPCWSTR]
    AppendMenuW.restype = wintypes.BOOL

    TrackPopupMenu = user32.TrackPopupMenu
    TrackPopupMenu.argtypes = [
        HANDLE,
        UINT,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        HWND,
        ctypes.c_void_p,
    ]
    TrackPopupMenu.restype = UINT

    DestroyMenu = user32.DestroyMenu
    DestroyMenu.argtypes = [HANDLE]
    DestroyMenu.restype = wintypes.BOOL

    GetCursorPos = user32.GetCursorPos
    GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    GetCursorPos.restype = wintypes.BOOL

    SetForegroundWindow = user32.SetForegroundWindow
    SetForegroundWindow.argtypes = [HWND]
    SetForegroundWindow.restype = wintypes.BOOL

    PostMessageW = user32.PostMessageW
    PostMessageW.argtypes = [HWND, UINT, WPARAM, LPARAM]
    PostMessageW.restype = wintypes.BOOL

    CallWindowProcW = user32.CallWindowProcW
    CallWindowProcW.argtypes = [LONG_PTR, HWND, UINT, WPARAM, LPARAM]
    CallWindowProcW.restype = LRESULT

    if hasattr(user32, "SetWindowLongPtrW"):
        SetWindowLongPtrW = user32.SetWindowLongPtrW
    else:
        SetWindowLongPtrW = user32.SetWindowLongW
    SetWindowLongPtrW.argtypes = [HWND, ctypes.c_int, LONG_PTR]
    SetWindowLongPtrW.restype = LONG_PTR


class WindowsNotifier:
    NIM_ADD = 0x00000000
    NIM_MODIFY = 0x00000001
    NIM_DELETE = 0x00000002

    NIF_MESSAGE = 0x00000001
    NIF_ICON = 0x00000002
    NIF_TIP = 0x00000004
    NIF_INFO = 0x00000010

    NIIF_INFO = 0x00000001
    NIIF_WARNING = 0x00000002

    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x00000010
    LR_DEFAULTSIZE = 0x00000040

    WM_APP = 0x8000
    WM_LBUTTONUP = 0x0202
    WM_RBUTTONUP = 0x0205
    WM_LBUTTONDBLCLK = 0x0203
    WM_NULL = 0x0000
    GWL_WNDPROC = -4
    IDI_APPLICATION = 32512
    MF_STRING = 0x00000000
    TPM_RIGHTBUTTON = 0x00000002
    TPM_RETURNCMD = 0x00000100
    MENU_OPEN = 1001
    MENU_EXIT = 1002

    def __init__(
        self,
        hwnd: int,
        icon_path: Path,
        on_activate: Callable[[], None] | None = None,
        on_exit: Callable[[], None] | None = None,
    ) -> None:
        self.hwnd = int(hwnd)
        self.icon_path = icon_path
        self.on_activate = on_activate
        self.on_exit = on_exit
        self.icon_id = 1412
        self.callback_message = self.WM_APP + 412
        self._hicon: int | None = None
        self._added = False
        self._old_wndproc: int | None = None
        self._wndproc_ref = None

    @property
    def available(self) -> bool:
        return IS_WINDOWS and self.hwnd > 0

    def ensure_icon(self) -> bool:
        if not self.available:
            return False
        if not self._subclass_window():
            return False
        if self._added:
            return True

        data = self._new_data(self.NIF_MESSAGE | self.NIF_ICON | self.NIF_TIP)
        data.hIcon = self._load_icon()
        data.szTip = "FreelaBoard"
        self._added = bool(Shell_NotifyIconW(self.NIM_ADD, ctypes.byref(data)))
        if not self._added:
            self._added = bool(Shell_NotifyIconW(self.NIM_MODIFY, ctypes.byref(data)))
        return self._added

    def show_balloon(self, title: str, message: str, warning: bool = False) -> bool:
        if not self.ensure_icon():
            return False
        data = self._new_data(self.NIF_INFO)
        data.szInfoTitle = title[:63]
        data.szInfo = message[:255]
        data.dwInfoFlags = self.NIIF_WARNING if warning else self.NIIF_INFO
        return bool(Shell_NotifyIconW(self.NIM_MODIFY, ctypes.byref(data)))

    def close(self) -> None:
        if IS_WINDOWS and self._added:
            data = self._new_data(0)
            Shell_NotifyIconW(self.NIM_DELETE, ctypes.byref(data))
        self._added = False
        self._restore_window_proc()

    def _new_data(self, flags: int) -> "NOTIFYICONDATAW":
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = HWND(self.hwnd)
        data.uID = self.icon_id
        data.uFlags = flags
        data.uCallbackMessage = self.callback_message
        return data

    def _load_icon(self) -> int:
        if self._hicon:
            return self._hicon
        if self.icon_path.exists():
            self._hicon = LoadImageW(
                None,
                str(self.icon_path),
                self.IMAGE_ICON,
                0,
                0,
                self.LR_LOADFROMFILE | self.LR_DEFAULTSIZE,
            )
        if not self._hicon:
            self._hicon = LoadIconW(None, HANDLE(self.IDI_APPLICATION))
        return self._hicon

    def _show_context_menu(self) -> None:
        if not IS_WINDOWS:
            return

        menu = CreatePopupMenu()
        if not menu:
            return

        try:
            AppendMenuW(menu, self.MF_STRING, self.MENU_OPEN, "パネルを開く")
            AppendMenuW(menu, self.MF_STRING, self.MENU_EXIT, "終了")

            point = POINT()
            if not GetCursorPos(ctypes.byref(point)):
                return

            hwnd = HWND(self.hwnd)
            SetForegroundWindow(hwnd)
            command = TrackPopupMenu(
                menu,
                self.TPM_RIGHTBUTTON | self.TPM_RETURNCMD,
                point.x,
                point.y,
                0,
                hwnd,
                None,
            )
            PostMessageW(hwnd, self.WM_NULL, 0, 0)

            if command == self.MENU_OPEN and self.on_activate:
                self.on_activate()
            elif command == self.MENU_EXIT and self.on_exit:
                self.on_exit()
        finally:
            DestroyMenu(menu)

    def _subclass_window(self) -> bool:
        if self._old_wndproc is not None:
            return True

        @WNDPROC
        def wndproc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
            if msg == self.callback_message and int(wparam) == self.icon_id:
                if int(lparam) == self.WM_RBUTTONUP:
                    self._show_context_menu()
                    return 0
                if int(lparam) in (self.WM_LBUTTONUP, self.WM_LBUTTONDBLCLK):
                    if self.on_activate:
                        self.on_activate()
                    return 0
            return int(CallWindowProcW(self._old_wndproc, hwnd, msg, wparam, lparam))

        self._wndproc_ref = wndproc
        proc_ptr = ctypes.cast(wndproc, ctypes.c_void_p).value
        if proc_ptr is None:
            return False
        old_proc = SetWindowLongPtrW(HWND(self.hwnd), self.GWL_WNDPROC, LONG_PTR(proc_ptr))
        if not old_proc:
            self._wndproc_ref = None
            return False
        self._old_wndproc = int(old_proc)
        return True

    def _restore_window_proc(self) -> None:
        if not IS_WINDOWS or self._old_wndproc is None:
            return
        SetWindowLongPtrW(HWND(self.hwnd), self.GWL_WNDPROC, LONG_PTR(self._old_wndproc))
        self._old_wndproc = None
        self._wndproc_ref = None
