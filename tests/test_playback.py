import threading
import unittest

from harmonica_player.playback import (
    PauseToggleResult,
    PlaybackResult,
    PreviewController,
    play_song,
)
from harmonica_player.song import NoteEvent, Song


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeStopEvent:
    def __init__(self, clock: FakeClock, *, cancel_on_wait: int | None = None) -> None:
        self.clock = clock
        self.cancel_on_wait = cancel_on_wait
        self.wait_calls: list[float] = []
        self._set = False

    def is_set(self) -> bool:
        return self._set

    def wait(self, timeout: float) -> bool:
        self.wait_calls.append(timeout)
        if self.cancel_on_wait == len(self.wait_calls):
            self._set = True
            return True
        self.clock.now += timeout
        return False


class RecordingOutput:
    def __init__(self) -> None:
        self.records: list[tuple[object, ...]] = []
        self.event_started_signal = threading.Event()
        self.paused_signal = threading.Event()
        self.resumed_signal = threading.Event()

    def countdown(self, seconds: int) -> None:
        self.records.append(("countdown", seconds))

    def event_started(
        self, index: int, event: NoteEvent, duration: float
    ) -> None:
        self.records.append(("start", index, event.note, duration))
        self.event_started_signal.set()

    def event_finished(
        self, index: int, event: NoteEvent, *, cancelled: bool
    ) -> None:
        self.records.append(("finish", index, event.note, cancelled))

    def playback_paused(self) -> None:
        self.records.append(("paused",))
        self.paused_signal.set()

    def playback_resumed(self) -> None:
        self.records.append(("resumed",))
        self.resumed_signal.set()

    def playback_finished(self, result: PlaybackResult) -> None:
        self.records.append(("result", result))


class PlaybackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.song = Song(
            bpm=120,
            events=(
                NoteEvent("1", 1, "normal"),
                NoteEvent("5", 2, "down"),
            ),
        )

    def test_plays_countdown_and_events_at_their_durations(self) -> None:
        clock = FakeClock()
        stop_event = FakeStopEvent(clock)
        output = RecordingOutput()

        result = play_song(
            self.song,
            stop_event,  # type: ignore[arg-type]
            output,
            countdown_seconds=2,
            clock=clock,
        )

        self.assertIs(result, PlaybackResult.COMPLETED)
        self.assertEqual(stop_event.wait_calls, [1.0, 1.0, 0.5, 1.0])
        self.assertEqual(
            output.records,
            [
                ("countdown", 2),
                ("countdown", 1),
                ("start", 1, "1", 0.5),
                ("finish", 1, "1", False),
                ("start", 2, "5", 1.0),
                ("finish", 2, "5", False),
                ("result", PlaybackResult.COMPLETED),
            ],
        )

    def test_can_cancel_during_countdown(self) -> None:
        clock = FakeClock()
        stop_event = FakeStopEvent(clock, cancel_on_wait=1)
        output = RecordingOutput()

        result = play_song(
            self.song,
            stop_event,  # type: ignore[arg-type]
            output,
            countdown_seconds=3,
            clock=clock,
        )

        self.assertIs(result, PlaybackResult.CANCELLED)
        self.assertEqual(
            output.records,
            [("countdown", 3), ("result", PlaybackResult.CANCELLED)],
        )

    def test_cancellation_finishes_active_event_and_skips_later_events(self) -> None:
        clock = FakeClock()
        stop_event = FakeStopEvent(clock, cancel_on_wait=1)
        output = RecordingOutput()

        result = play_song(
            self.song,
            stop_event,  # type: ignore[arg-type]
            output,
            countdown_seconds=0,
            clock=clock,
        )

        self.assertIs(result, PlaybackResult.CANCELLED)
        self.assertEqual(
            output.records,
            [
                ("start", 1, "1", 0.5),
                ("finish", 1, "1", True),
                ("result", PlaybackResult.CANCELLED),
            ],
        )

    def test_controller_ignores_duplicate_start_and_stops_promptly(self) -> None:
        long_song = Song(
            bpm=60,
            events=(NoteEvent("1", 60, "normal"),),
        )
        output = RecordingOutput()
        controller = PreviewController(
            long_song,
            countdown_seconds=0,
            output_factory=lambda: output,
        )

        self.assertTrue(controller.start())
        self.assertTrue(output.event_started_signal.wait(1))
        self.assertFalse(controller.start())
        self.assertTrue(controller.stop())
        controller.join(1)

        self.assertFalse(controller.is_playing)
        self.assertIn(("finish", 1, "1", True), output.records)
        self.assertIn(("result", PlaybackResult.CANCELLED), output.records)

    def test_controller_freezes_time_while_paused_and_then_resumes(self) -> None:
        short_song = Song(
            bpm=60,
            events=(NoteEvent("1", 0.5, "normal"),),
        )
        output = RecordingOutput()
        controller = PreviewController(
            short_song,
            countdown_seconds=0,
            output_factory=lambda: output,
        )

        self.assertTrue(controller.start())
        self.assertTrue(output.event_started_signal.wait(1))
        self.assertIs(controller.toggle_pause(), PauseToggleResult.PAUSED)
        self.assertTrue(output.paused_signal.wait(1))

        threading.Event().wait(0.3)
        self.assertTrue(controller.is_playing)
        self.assertTrue(controller.is_paused)

        self.assertIs(controller.toggle_pause(), PauseToggleResult.RESUMED)
        self.assertTrue(output.resumed_signal.wait(1))
        controller.join(2)

        self.assertFalse(controller.is_playing)
        self.assertIn(("result", PlaybackResult.COMPLETED), output.records)

    def test_controller_can_stop_while_paused(self) -> None:
        long_song = Song(
            bpm=60,
            events=(NoteEvent("1", 60, "normal"),),
        )
        output = RecordingOutput()
        controller = PreviewController(
            long_song,
            countdown_seconds=0,
            output_factory=lambda: output,
        )

        self.assertTrue(controller.start())
        self.assertTrue(output.event_started_signal.wait(1))
        self.assertIs(controller.toggle_pause(), PauseToggleResult.PAUSED)
        self.assertTrue(output.paused_signal.wait(1))
        self.assertTrue(controller.stop())
        controller.join(1)

        self.assertFalse(controller.is_playing)
        self.assertIn(("finish", 1, "1", True), output.records)
        self.assertIn(("result", PlaybackResult.CANCELLED), output.records)


if __name__ == "__main__":
    unittest.main()
