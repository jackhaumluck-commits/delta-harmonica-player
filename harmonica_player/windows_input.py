"""Safe Windows keyboard and mouse output built on ``SendInput``."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Callable, Protocol

from .playback import ConsolePreviewOutput, PlaybackOutput, PlaybackResult
from .song import NoteEvent


_INPUT_MOUSE = 0
_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_SCANCODE = 0x0008

_MOUSE_DOWN_FLAGS = {
    "left": 0x0002,
    "right": 0x0008,
    "middle": 0x0020,
}
_MOUSE_UP_FLAGS = {
    "left": 0x0004,
    "right": 0x0010,
    "middle": 0x0040,
}

# Set 1 scan codes for Z X C V B N M and comma.
_KEY_SCAN_CODES = {
    "Z": 0x2C,
    "X": 0x2D,
    "C": 0x2E,
    "V": 0x2F,
    "B": 0x30,
    "N": 0x31,
    "M": 0x32,
    ",": 0x33,
}


def is_running_as_administrator(
    *, check: Callable[[], int] | None = None
) -> bool:
    """Return whether this process has an elevated Windows token."""

    if check is None:
        if sys.platform != "win32":
            return False
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.IsUserAnAdmin.argtypes = ()
        shell32.IsUserAnAdmin.restype = wintypes.BOOL
        check = shell32.IsUserAnAdmin
    return bool(check())


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [
        ("mi", _MOUSEINPUT),
        ("ki", _KEYBDINPUT),
        ("hi", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", wintypes.DWORD), ("data", _INPUTUNION)]


class InputSender(Protocol):
    def foreground_window(self) -> int | None: ...

    def key_down(self, key: str) -> None: ...

    def key_up(self, key: str) -> None: ...

    def mouse_down(self, button: str) -> None: ...

    def mouse_up(self, button: str) -> None: ...


class WindowsInputSender:
    """Translate named keys and mouse buttons into Win32 input events."""

    def __init__(self, *, user32: object | None = None) -> None:
        if user32 is None:
            if sys.platform != "win32":
                raise RuntimeError("真实键鼠输入目前只支持 Windows")

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.SendInput.argtypes = (
                wintypes.UINT,
                ctypes.POINTER(_INPUT),
                ctypes.c_int,
            )
            user32.SendInput.restype = wintypes.UINT
            user32.GetForegroundWindow.argtypes = ()
            user32.GetForegroundWindow.restype = wintypes.HWND
        self._user32 = user32

    def foreground_window(self) -> int | None:
        window = self._user32.GetForegroundWindow()
        return int(window) if window else None

    def key_down(self, key: str) -> None:
        self._send_keyboard(key, released=False)

    def key_up(self, key: str) -> None:
        self._send_keyboard(key, released=True)

    def mouse_down(self, button: str) -> None:
        self._send_mouse(_MOUSE_DOWN_FLAGS, button)

    def mouse_up(self, button: str) -> None:
        self._send_mouse(_MOUSE_UP_FLAGS, button)

    def _send_keyboard(self, key: str, *, released: bool) -> None:
        try:
            scan_code = _KEY_SCAN_CODES[key]
        except KeyError as error:
            raise ValueError(f"不支持的键盘按键：{key}") from error

        flags = _KEYEVENTF_SCANCODE
        if released:
            flags |= _KEYEVENTF_KEYUP
        event = _INPUT(
            type=_INPUT_KEYBOARD,
            data=_INPUTUNION(
                ki=_KEYBDINPUT(
                    wVk=0,
                    wScan=scan_code,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )
        self._send(event)

    def _send_mouse(self, flags_by_button: dict[str, int], button: str) -> None:
        try:
            flags = flags_by_button[button]
        except KeyError as error:
            raise ValueError(f"不支持的鼠标按键：{button}") from error

        event = _INPUT(
            type=_INPUT_MOUSE,
            data=_INPUTUNION(
                mi=_MOUSEINPUT(
                    dx=0,
                    dy=0,
                    mouseData=0,
                    dwFlags=flags,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )
        self._send(event)

    def _send(self, event: _INPUT) -> None:
        events = (_INPUT * 1)(event)
        set_last_error = getattr(ctypes, "set_last_error", None)
        if set_last_error is not None:
            set_last_error(0)
        sent = self._user32.SendInput(1, events, ctypes.sizeof(_INPUT))
        if sent == 1:
            return

        get_last_error = getattr(ctypes, "get_last_error", None)
        error_code = get_last_error() if get_last_error is not None else 0
        if error_code:
            raise ctypes.WinError(error_code)
        raise OSError("SendInput 未能发送输入；目标程序可能具有更高权限")


class WindowsInputOutput:
    """Perform song events while guarding the F8 target window."""

    def __init__(
        self,
        *,
        sender: InputSender | None = None,
        console: PlaybackOutput | None = None,
        notice: Callable[[str], None] = print,
    ) -> None:
        self._sender = sender or WindowsInputSender()
        self._console = console or ConsolePreviewOutput()
        self._notice = notice
        self._target_window = self._sender.foreground_window()
        if self._target_window is None:
            raise RuntimeError("无法确定当前前台窗口，请切换到测试窗口后重试")

        self._current_event: NoteEvent | None = None
        self._active_key: str | None = None
        self._active_mouse_button: str | None = None
        self._focus_lost = False

    @property
    def target_window(self) -> int:
        return self._target_window

    def countdown(self, seconds: int) -> None:
        self._console.countdown(seconds)

    def event_started(self, index: int, event: NoteEvent, duration: float) -> None:
        self._current_event = event
        self._press_event(event)
        self._console.event_started(index, event, duration)

    def event_finished(
        self, index: int, event: NoteEvent, *, cancelled: bool
    ) -> None:
        try:
            self._release_active()
        finally:
            self._current_event = None
        self._console.event_finished(index, event, cancelled=cancelled)

    def playback_paused(self) -> None:
        self._release_active()
        self._console.playback_paused()

    def playback_resumed(self) -> None:
        if self._current_event is not None:
            self._press_event(self._current_event)
        self._console.playback_resumed()

    def playback_finished(self, result: PlaybackResult) -> None:
        self._current_event = None
        self._console.playback_finished(result)

    def playback_failed(self, error: Exception) -> None:
        self._current_event = None
        self._console.playback_failed(error)

    def cancel_requested(self) -> bool:
        if self._focus_lost:
            return True
        if self._sender.foreground_window() == self._target_window:
            return False

        self._focus_lost = True
        self._notice("检测到前台窗口变化，正在紧急停止并释放全部输入。")
        self.release_all()
        return True

    def release_all(self) -> None:
        self._release_active()

    def _press_event(self, event: NoteEvent) -> None:
        if event.is_rest:
            return
        if self._active_key is not None or self._active_mouse_button is not None:
            raise RuntimeError("检测到尚未释放的输入，已拒绝按下新音符")

        try:
            if event.mouse_button is not None:
                self._sender.mouse_down(event.mouse_button)
                self._active_mouse_button = event.mouse_button
            assert event.key is not None
            self._sender.key_down(event.key)
            self._active_key = event.key
        except BaseException as error:
            try:
                self._release_active()
            except BaseException as cleanup_error:
                raise cleanup_error from error
            raise

    def _release_active(self) -> None:
        key = self._active_key
        mouse_button = self._active_mouse_button
        self._active_key = None
        self._active_mouse_button = None

        errors: list[BaseException] = []
        if key is not None:
            try:
                self._sender.key_up(key)
            except BaseException as error:
                errors.append(error)
        if mouse_button is not None:
            try:
                self._sender.mouse_up(mouse_button)
            except BaseException as error:
                errors.append(error)
        if errors:
            raise errors[0]
