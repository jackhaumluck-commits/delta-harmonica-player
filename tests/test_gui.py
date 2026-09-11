import queue
import unittest

from harmonica_player.gui import (
    GlobalHotkeyMonitor,
    QueuePlaybackOutput,
)
from harmonica_player.hotkeys import Hotkey, HotkeyBindings
from harmonica_player.playback import PlaybackResult
from harmonica_player.song import NoteEvent


class QueuePlaybackOutputTests(unittest.TestCase):
    def test_reports_progress_and_completion_through_queue(self) -> None:
        events = queue.Queue()
        output = QueuePlaybackOutput(events, total_events=2)
        note = NoteEvent("1", 1, "normal")

        output.countdown(1)
        output.event_started(1, note, 0.5)
        output.event_finished(1, note, cancelled=False)
        output.playback_finished(PlaybackResult.COMPLETED)

        received = [events.get_nowait() for _ in range(4)]
        self.assertEqual(
            [event.kind for event in received],
            ["countdown", "event_started", "event_finished", "finished"],
        )
        self.assertEqual((received[1].index, received[1].total), (1, 2))
        self.assertIs(received[-1].data, PlaybackResult.COMPLETED)


class FakeHotkeyListener:
    def __init__(self, bindings: HotkeyBindings) -> None:
        self.bindings = bindings

    def __enter__(self) -> "FakeHotkeyListener":
        return self

    def __exit__(self, *args: object) -> None:
        return

    def events(self, stop_event: object):
        yield Hotkey.START


class GlobalHotkeyMonitorTests(unittest.TestCase):
    def test_forwards_ready_and_hotkey_events(self) -> None:
        events = queue.Queue()
        bindings = HotkeyBindings("F5", "F6", "F7")
        monitor = GlobalHotkeyMonitor(
            bindings,
            events,
            listener_factory=FakeHotkeyListener,  # type: ignore[arg-type]
        )

        monitor.start()
        ready = events.get(timeout=1)
        hotkey = events.get(timeout=1)
        monitor.stop()

        self.assertEqual(ready.kind, "hotkeys_ready")
        self.assertEqual(ready.data, bindings)
        self.assertEqual(hotkey.data, Hotkey.START)


if __name__ == "__main__":
    unittest.main()
