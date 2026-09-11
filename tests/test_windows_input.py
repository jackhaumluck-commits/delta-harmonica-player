import unittest

from harmonica_player.playback import ConsolePreviewOutput
from harmonica_player.song import NoteEvent
from harmonica_player.windows_input import (
    WindowsInputOutput,
    WindowsInputSender,
    is_running_as_administrator,
)


class FakeSender:
    def __init__(self) -> None:
        self.window: int | None = 100
        self.actions: list[tuple[str, str]] = []
        self.fail_key_down = False

    def foreground_window(self) -> int | None:
        return self.window

    def key_down(self, key: str) -> None:
        self.actions.append(("key_down", key))
        if self.fail_key_down:
            raise OSError("模拟键盘失败")

    def key_up(self, key: str) -> None:
        self.actions.append(("key_up", key))

    def mouse_down(self, button: str) -> None:
        self.actions.append(("mouse_down", button))

    def mouse_up(self, button: str) -> None:
        self.actions.append(("mouse_up", button))


class FakeUser32:
    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []

    def GetForegroundWindow(self) -> int:
        return 123

    def SendInput(self, count: int, events: object, size: int) -> int:
        event = events[0]
        if event.type == 1:
            self.events.append(
                ("keyboard", event.ki.wScan, event.ki.dwFlags, size)
            )
        else:
            self.events.append(("mouse", event.mi.dwFlags, size))
        return count


class SilentConsole(ConsolePreviewOutput):
    def __init__(self) -> None:
        self.records: list[str] = []

    def countdown(self, seconds: int) -> None:
        return

    def event_started(
        self, index: int, event: NoteEvent, duration: float
    ) -> None:
        self.records.append("started")

    def event_finished(
        self, index: int, event: NoteEvent, *, cancelled: bool
    ) -> None:
        self.records.append("finished")

    def playback_paused(self) -> None:
        self.records.append("paused")

    def playback_resumed(self) -> None:
        self.records.append("resumed")


class WindowsInputOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sender = FakeSender()
        self.notices: list[str] = []
        self.output = WindowsInputOutput(
            sender=self.sender,
            console=SilentConsole(),
            notice=self.notices.append,
        )
        self.event = NoteEvent("5", 1, "down")

    def test_presses_mouse_before_key_and_releases_in_reverse_order(self) -> None:
        self.output.event_started(1, self.event, 0.5)
        self.output.event_finished(1, self.event, cancelled=False)

        self.assertEqual(
            self.sender.actions,
            [
                ("mouse_down", "left"),
                ("key_down", "B"),
                ("key_up", "B"),
                ("mouse_up", "left"),
            ],
        )

    def test_pause_releases_and_resume_presses_current_event_again(self) -> None:
        self.output.event_started(1, self.event, 1.0)
        self.output.playback_paused()
        self.output.playback_resumed()
        self.output.event_finished(1, self.event, cancelled=False)

        self.assertEqual(
            self.sender.actions,
            [
                ("mouse_down", "left"),
                ("key_down", "B"),
                ("key_up", "B"),
                ("mouse_up", "left"),
                ("mouse_down", "left"),
                ("key_down", "B"),
                ("key_up", "B"),
                ("mouse_up", "left"),
            ],
        )

    def test_focus_change_releases_input_and_requests_cancellation(self) -> None:
        self.output.event_started(1, self.event, 1.0)
        self.sender.window = 200

        self.assertTrue(self.output.cancel_requested())
        self.assertTrue(self.output.cancel_requested())
        self.assertEqual(len(self.notices), 1)
        self.assertEqual(
            self.sender.actions[-2:],
            [("key_up", "B"), ("mouse_up", "left")],
        )

    def test_key_failure_releases_mouse_modifier(self) -> None:
        self.sender.fail_key_down = True

        with self.assertRaisesRegex(OSError, "模拟键盘失败"):
            self.output.event_started(1, self.event, 1.0)

        self.assertEqual(
            self.sender.actions,
            [
                ("mouse_down", "left"),
                ("key_down", "B"),
                ("mouse_up", "left"),
            ],
        )

    def test_rest_does_not_send_input(self) -> None:
        rest = NoteEvent("0", 1, "rest")

        self.output.event_started(1, rest, 0.5)
        self.output.event_finished(1, rest, cancelled=False)

        self.assertEqual(self.sender.actions, [])

    def test_requires_a_foreground_window(self) -> None:
        self.sender.window = None

        with self.assertRaisesRegex(RuntimeError, "无法确定当前前台窗口"):
            WindowsInputOutput(sender=self.sender)


class WindowsInputSenderTests(unittest.TestCase):
    def test_builds_scan_code_and_mouse_button_events(self) -> None:
        user32 = FakeUser32()
        sender = WindowsInputSender(user32=user32)

        sender.key_down("Z")
        sender.key_up(",")
        sender.mouse_down("middle")
        sender.mouse_up("middle")

        self.assertEqual(user32.events[0][:3], ("keyboard", 0x2C, 0x0008))
        self.assertEqual(user32.events[1][:3], ("keyboard", 0x33, 0x000A))
        self.assertEqual(user32.events[2][:2], ("mouse", 0x0020))
        self.assertEqual(user32.events[3][:2], ("mouse", 0x0040))
        self.assertTrue(all(event[-1] > 0 for event in user32.events))

    def test_rejects_unknown_keys_and_mouse_buttons(self) -> None:
        sender = WindowsInputSender(user32=FakeUser32())

        with self.assertRaisesRegex(ValueError, "不支持的键盘按键"):
            sender.key_down("A")
        with self.assertRaisesRegex(ValueError, "不支持的鼠标按键"):
            sender.mouse_down("side")


class AdministratorCheckTests(unittest.TestCase):
    def test_reports_elevated_process(self) -> None:
        self.assertTrue(is_running_as_administrator(check=lambda: 1))

    def test_reports_non_elevated_process(self) -> None:
        self.assertFalse(is_running_as_administrator(check=lambda: 0))


if __name__ == "__main__":
    unittest.main()
