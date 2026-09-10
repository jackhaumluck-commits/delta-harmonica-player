"""Timed terminal preview that never sends keyboard or mouse input."""

from __future__ import annotations

from enum import Enum
from threading import Event, Lock, Thread
from time import monotonic
from typing import Callable, Protocol

from .song import NoteEvent, Song


class PlaybackResult(Enum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PreviewOutput(Protocol):
    """Receive playback events without knowing how they are displayed."""

    def countdown(self, seconds: int) -> None: ...

    def event_started(
        self, index: int, event: NoteEvent, duration: float
    ) -> None: ...

    def event_finished(
        self, index: int, event: NoteEvent, *, cancelled: bool
    ) -> None: ...

    def playback_finished(self, result: PlaybackResult) -> None: ...


class ConsolePreviewOutput:
    """Print the actions that a future real-input output would perform."""

    def countdown(self, seconds: int) -> None:
        print(f"{seconds}...", flush=True)

    def event_started(self, index: int, event: NoteEvent, duration: float) -> None:
        print(
            f"{index:>3}. 开始 {describe_event(event):<28} {duration:.3f}s",
            flush=True,
        )

    def event_finished(
        self, index: int, event: NoteEvent, *, cancelled: bool
    ) -> None:
        if event.is_rest:
            return
        suffix = "（停止）" if cancelled else ""
        print(f"     释放 {describe_event(event)}{suffix}", flush=True)

    def playback_finished(self, result: PlaybackResult) -> None:
        if result is PlaybackResult.COMPLETED:
            message = "预演完成，等待 F8 再次开始。"
        else:
            message = "预演已停止，等待 F8 再次开始。"
        print(message, flush=True)


def describe_event(event: NoteEvent) -> str:
    if event.is_rest:
        return "休止"
    if event.mouse_button is None:
        return f"键盘 {event.key}"
    return f"鼠标 {event.mouse_button} + 键盘 {event.key}"


def play_song(
    song: Song,
    stop_event: Event,
    output: PreviewOutput,
    *,
    countdown_seconds: int = 3,
    clock: Callable[[], float] = monotonic,
) -> PlaybackResult:
    """Preview one song at its configured BPM, with prompt cancellation."""

    if countdown_seconds < 0:
        raise ValueError("倒计时不能小于零")

    deadline = clock()
    for remaining in range(countdown_seconds, 0, -1):
        if stop_event.is_set():
            return _finish(output, PlaybackResult.CANCELLED)
        output.countdown(remaining)
        deadline += 1.0
        if _wait_until(stop_event, deadline, clock):
            return _finish(output, PlaybackResult.CANCELLED)

    # Fixed deadlines keep small scheduling delays from accumulating as drift.
    deadline = clock()
    for index, event in enumerate(song.events, start=1):
        if stop_event.is_set():
            return _finish(output, PlaybackResult.CANCELLED)

        duration = event.duration_seconds(song.bpm)
        output.event_started(index, event, duration)
        deadline += duration
        cancelled = _wait_until(stop_event, deadline, clock)
        output.event_finished(index, event, cancelled=cancelled)

        if cancelled:
            return _finish(output, PlaybackResult.CANCELLED)

    return _finish(output, PlaybackResult.COMPLETED)


def _wait_until(
    stop_event: Event, deadline: float, clock: Callable[[], float]
) -> bool:
    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            return stop_event.is_set()
        if stop_event.wait(remaining):
            return True


def _finish(output: PreviewOutput, result: PlaybackResult) -> PlaybackResult:
    output.playback_finished(result)
    return result


class PreviewController:
    """Start and stop a single background preview safely."""

    def __init__(
        self,
        song: Song,
        *,
        countdown_seconds: int = 3,
        output_factory: Callable[[], PreviewOutput] = ConsolePreviewOutput,
    ) -> None:
        self._song = song
        self._countdown_seconds = countdown_seconds
        self._output_factory = output_factory
        self._lock = Lock()
        self._thread: Thread | None = None
        self._stop_event: Event | None = None

    def start(self) -> bool:
        """Start a preview; return False when one is already running."""

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False

            stop_event = Event()
            thread = Thread(
                target=play_song,
                args=(self._song, stop_event, self._output_factory()),
                kwargs={"countdown_seconds": self._countdown_seconds},
                name="harmonica-preview",
                daemon=True,
            )
            self._stop_event = stop_event
            self._thread = thread
            thread.start()
            return True

    def stop(self) -> bool:
        """Request cancellation; return False when nothing is running."""

        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                return False
            assert self._stop_event is not None
            self._stop_event.set()
            return True

    def join(self, timeout: float | None = None) -> None:
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join(timeout)

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()
