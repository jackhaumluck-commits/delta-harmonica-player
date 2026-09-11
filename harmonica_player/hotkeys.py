"""Windows global hotkeys for controlling the safe timed preview."""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Iterator
from ctypes import wintypes
from dataclasses import dataclass
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
_VK_F1 = 0x70
_WM_HOTKEY = 0x0312
_PM_REMOVE = 0x0001


def normalize_function_key(value: str) -> str:
    """Normalize an F1-F24 key name or raise a friendly error."""

    normalized = value.strip().upper()
    if not normalized.startswith("F") or not normalized[1:].isdigit():
        raise ValueError("快捷键必须是 F1 到 F24")
    number = int(normalized[1:])
    if not 1 <= number <= 24:
        raise ValueError("快捷键必须是 F1 到 F24")
    return f"F{number}"


@dataclass(frozen=True, slots=True)
class HotkeyBindings:
    start: str = "F8"
    stop: str = "F9"
    pause: str = "F10"

    def __post_init__(self) -> None:
        normalized = (
            normalize_function_key(self.start),
            normalize_function_key(self.stop),
            normalize_function_key(self.pause),
        )
        if len(set(normalized)) != len(normalized):
            raise ValueError("开始、停止和暂停快捷键必须互不相同")
        object.__setattr__(self, "start", normalized[0])
        object.__setattr__(self, "stop", normalized[1])
        object.__setattr__(self, "pause", normalized[2])

    def virtual_key(self, key: str) -> int:
        return _VK_F1 + int(normalize_function_key(key)[1:]) - 1


class WindowsHotkeyListener:
    """Register playback hotkeys and yield events from the Windows message loop."""

    def __init__(self, bindings: HotkeyBindings | None = None) -> None:
        self._bindings = bindings or HotkeyBindings()
        self._registered_ids: list[int] = []

    def __enter__(self) -> WindowsHotkeyListener:
        if sys.platform != "win32":
            raise RuntimeError("全局播放热键目前只支持 Windows")

        try:
            self._register(_START_ID, self._bindings.start)
            self._register(_STOP_ID, self._bindings.stop)
            self._register(_PAUSE_ID, self._bindings.pause)
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

    def _register(self, hotkey_id: int, key: str) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        virtual_key = self._bindings.virtual_key(key)
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
    bindings: HotkeyBindings | None = None,
) -> int:
    """Wait for global hotkeys and run repeatable timed playback."""

    bindings = bindings or HotkeyBindings()
    output = ConsolePreviewOutput(
        total_events=len(song.events),
        start_key=bindings.start,
        stop_key=bindings.stop,
        pause_key=bindings.pause,
    )
    if real_input:
        if sys.platform != "win32":
            raise RuntimeError("真实键鼠输入目前只支持 Windows")

        from .windows_input import (
            WindowsInputOutput,
            is_running_as_administrator,
        )

        if not is_running_as_administrator():
            raise RuntimeError(
                "真实输入模式需要管理员权限。请关闭当前终端，右键 "
                "PowerShell 或 Windows Terminal，选择“以管理员身份运行”，"
                "然后重新执行命令。"
            )

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
            f"真实输入模式已就绪：切换到目标窗口后按 {bindings.start}；"
            f"{bindings.stop} 紧急停止，{bindings.pause} 暂停/继续，"
            "Ctrl+C 退出。",
            flush=True,
        )
        print("播放中切换前台窗口会自动停止并释放全部输入。", flush=True)
    else:
        print(
            f"计时预演已就绪：{bindings.start} 开始，"
            f"{bindings.stop} 紧急停止，{bindings.pause} 暂停/继续，"
            "Ctrl+C 退出。",
            flush=True,
        )
    try:
        with WindowsHotkeyListener(bindings) as listener:
            for hotkey in listener.events():
                if hotkey is Hotkey.START:
                    if controller.is_playing:
                        print(
                            f"播放正在进行中，已忽略重复的 {bindings.start}。",
                            flush=True,
                        )
                    else:
                        print(f"收到 {bindings.start}，开始倒计时。", flush=True)
                        controller.start()
                elif hotkey is Hotkey.STOP:
                    if controller.stop():
                        print(f"收到 {bindings.stop}，正在停止。", flush=True)
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
