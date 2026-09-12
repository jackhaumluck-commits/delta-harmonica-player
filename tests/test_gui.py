import queue
import unittest
from pathlib import Path

from harmonica_player.gui import (
    GlobalHotkeyMonitor,
    QueuePlaybackOutput,
    _song_kind_label,
    _TUTORIAL_SECTIONS,
)
from harmonica_player.hotkeys import Hotkey, HotkeyBindings
from harmonica_player.library import SongSource, SongSummary
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


class GuiContentTests(unittest.TestCase):
    def test_tutorial_covers_import_modes_and_default_hotkeys(self) -> None:
        tutorial = "\n".join(
            f"{title}\n{description}"
            for title, description in _TUTORIAL_SECTIONS
        )

        self.assertIn("导入文本曲谱", tutorial)
        self.assertIn("导入 MIDI", tutorial)
        self.assertIn("最高音", tutorial)
        self.assertIn("更合适的八度", tutorial)
        self.assertIn("过低的伴奏音", tutorial)
        self.assertIn("过密音符", tutorial)
        self.assertIn("安全预演", tutorial)
        self.assertIn("F8 开始、F9 停止、F10 暂停或继续", tutorial)

    def test_song_kind_label_uses_factual_library_categories(self) -> None:
        song = SongSummary(
            name="twinkle_twinkle",
            title="小星星（第一段）",
            path=Path("twinkle_twinkle.song"),
            bpm=80,
            event_count=14,
            duration_seconds=12,
            source=SongSource.BUNDLED,
        )

        self.assertEqual(_song_kind_label(song), "内置示例曲")


if __name__ == "__main__":
    unittest.main()

