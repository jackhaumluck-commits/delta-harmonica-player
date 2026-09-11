"""Windows global hotkeys for controlling the safe timed preview."""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Iterator
from ctypes import wintypes
from enum import Enum
from time import sleep

from .playback import ConsolePreviewOutput, PauseToggleResult, PreviewController
from .song import Song


class Hotkey(Enum):
    START = "start"
    STOP = "stop"
    PAUSE_TOGGLE = "pause_toggle"


_START_ID = 1
_STOP_ID = 2
_PAUSE_ID = 3
_MOD_NOREPEAT = 0x4000
_VK_F8 = 0x77
_VK_F9 = 0x78
_VK_F10 = 0x79
_WM_HOTKEY = 0x0312
_PM_REMOVE = 0x0001


class WindowsHotkeyListener:
    """Register playback hotkeys and yield events from the Windows message loop."""

    def __init__(self) -> None:
        self._registered_ids: list[int] = []

    def __enter__(self) -> WindowsHotkeyListener:
        if sys.platform != "win32":
            raise RuntimeError("全局 F8/F9/F10 热键目前只支持 Windows")

        try:
            self._register(_START_ID, _VK_F8)
            self._register(_STOP_ID, _VK_F9)
            self._register(_PAUSE_ID, _VK_F10)
        except BaseException:
            self._unregister_all()
            raise
        return self

    def __exit__(self, *args: object) -> None:
        self._unregister_all()

    def events(self) -> Iterator[Hotkey]:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        message = wintypes.MSG()

        while True:
            found = user32.PeekMessageW(
                ctypes.byref(message),
                None,
                _WM_HOTKEY,
                _WM_HOTKEY,
                _PM_REMOVE,
            )
            if not found:
                # Returning to Python regularly lets Ctrl+C interrupt the loop.
                sleep(0.05)
                continue
            if message.wParam == _START_ID:
                yield Hotkey.START
            elif message.wParam == _STOP_ID:
                yield Hotkey.STOP
            elif message.wParam == _PAUSE_ID:
                yield Hotkey.PAUSE_TOGGLE

    def _register(self, hotkey_id: int, virtual_key: int) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        if not user32.RegisterHotKey(None, hotkey_id, _MOD_NOREPEAT, virtual_key):
            raise ctypes.WinError(ctypes.get_last_error())
        self._registered_ids.append(hotkey_id)

    def _unregister_all(self) -> None:
        if sys.platform != "win32":
            return
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        for hotkey_id in reversed(self._registered_ids):
            user32.UnregisterHotKey(None, hotkey_id)
        self._registered_ids.clear()


def run_hotkey_preview(
    song: Song,
    *,
    countdown_seconds: int = 3,
    real_input: bool = False,
) -> int:
    """Wait for global hotkeys and run repeatable timed playback."""

    output = ConsolePreviewOutput()
    if real_input:
        from .windows_input import WindowsInputOutput

        output_factory = lambda: WindowsInputOutput(console=output)
    else:
        output_factory = lambda: output
    controller = PreviewController(
        song,
        countdown_seconds=countdown_seconds,
        output_factory=output_factory,
    )

    if real_input:
        print(
            "真实输入模式已就绪：切换到测试窗口后按 F8；"
            "F9 紧急停止，F10 暂停/继续，Ctrl+C 退出。",
            flush=True,
        )
        print("播放中切换前台窗口会自动停止并释放全部输入。", flush=True)
    else:
        print(
            "计时预演已就绪：F8 开始，F9 紧急停止，"
            "F10 暂停/继续，Ctrl+C 退出。",
            flush=True,
        )
    try:
        with WindowsHotkeyListener() as listener:
            for hotkey in listener.events():
                if hotkey is Hotkey.START:
                    if controller.is_playing:
                        print("播放正在进行中，已忽略重复的 F8。", flush=True)
                    else:
                        print("收到 F8，开始倒计时。", flush=True)
                        controller.start()
                elif hotkey is Hotkey.STOP:
                    if controller.stop():
                        print("收到 F9，正在停止。", flush=True)
                    else:
                        print("当前没有正在进行的预演。", flush=True)
                elif (
                    controller.toggle_pause() is PauseToggleResult.NOT_PLAYING
                ):
                    print("当前没有可以暂停的预演。", flush=True)
    except KeyboardInterrupt:
        print("\n正在退出……", flush=True)
    finally:
        controller.stop()
        controller.join()
    return 0
