"""Timed playback with replaceable preview or real-input outputs."""

from __future__ import annotations

from enum import Enum
from threading import Event, Lock, Thread
from time import monotonic
from typing import Callable, Protocol

from .song import NoteEvent, Song


class PlaybackResult(Enum):
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PauseToggleResult(Enum):
    PAUSED = "paused"
    RESUMED = "resumed"
    NOT_PLAYING = "not_playing"


class PlaybackOutput(Protocol):
    """Receive playback events without knowing how they are performed."""

    def countdown(self, seconds: int) -> None: ...

    def event_started(
        self, index: int, event: NoteEvent, duration: float
    ) -> None: ...

    def event_finished(
        self, index: int, event: NoteEvent, *, cancelled: bool
    ) -> None: ...

    def playback_paused(self) -> None: ...

    def playback_resumed(self) -> None: ...

    def playback_finished(self, result: PlaybackResult) -> None: ...

    def playback_failed(self, error: Exception) -> None: ...

    def cancel_requested(self) -> bool: ...

    def release_all(self) -> None: ...


class ConsolePreviewOutput:
    """Print the actions that a future real-input output would perform."""

    def __init__(
        self,
        *,
        total_events: int | None = None,
        start_key: str = "F8",
        stop_key: str = "F9",
        pause_key: str = "F10",
    ) -> None:
        self._total_events = total_events
        self._start_key = start_key
        self._stop_key = stop_key
        self._pause_key = pause_key

    def countdown(self, seconds: int) -> None:
        print(f"{seconds}...", flush=True)

    def event_started(self, index: int, event: NoteEvent, duration: float) -> None:
        progress = f"{index:>3}."
        if self._total_events is not None:
            percentage = (index - 1) / self._total_events
            progress = (
                f"[{index:>{len(str(self._total_events))}}/{self._total_events} "
                f"已完成 {percentage:>6.1%}]"
            )
        print(
            f"{progress} 开始 {describe_event(event):<28} {duration:.3f}s",
            flush=True,
        )

    def event_finished(
        self, index: int, event: NoteEvent, *, cancelled: bool
    ) -> None:
        if event.is_rest:
            return
        suffix = "（停止）" if cancelled else ""
        print(f"     释放 {describe_event(event)}{suffix}", flush=True)

    def playback_paused(self) -> None:
        print(
            f"预演已暂停，按 {self._pause_key} 继续，"
            f"按 {self._stop_key} 停止。",
            flush=True,
        )

    def playback_resumed(self) -> None:
        print("预演继续。", flush=True)

    def playback_finished(self, result: PlaybackResult) -> None:
        if result is PlaybackResult.COMPLETED:
            message = f"预演完成，等待 {self._start_key} 再次开始。"
        else:
            message = f"预演已停止，等待 {self._start_key} 再次开始。"
        print(message, flush=True)

    def playback_failed(self, error: Exception) -> None:
        print(f"播放失败：{error}", flush=True)

    def cancel_requested(self) -> bool:
        return False

    def release_all(self) -> None:
        return


def describe_event(event: NoteEvent) -> str:
    if event.is_rest:
        return "休止"
    if event.mouse_button is None:
        return f"键盘 {event.key}"
    return f"鼠标 {event.mouse_button} + 键盘 {event.key}"


def play_song(
    song: Song,
    stop_event: Event,
    output: PlaybackOutput,
    *,
    countdown_seconds: int = 3,
    pause_event: Event | None = None,
    clock: Callable[[], float] = monotonic,
) -> PlaybackResult:
    """Play one song at its configured BPM, with prompt cancellation."""

    if countdown_seconds < 0:
        raise ValueError("倒计时不能小于零")

    try:
        return _play_song(
            song,
            stop_event,
            output,
            countdown_seconds=countdown_seconds,
            pause_event=pause_event,
            clock=clock,
        )
    except BaseException as error:
        try:
            output.release_all()
        except BaseException as cleanup_error:
            raise cleanup_error from error
        raise


def _play_song(
    song: Song,
    stop_event: Event,
    output: PlaybackOutput,
    *,
    countdown_seconds: int,
    pause_event: Event | None,
    clock: Callable[[], float],
) -> PlaybackResult:

    deadline = clock()
    for remaining in range(countdown_seconds, 0, -1):
        if _cancellation_requested(stop_event, output):
            return _finish(output, PlaybackResult.CANCELLED)
        output.countdown(remaining)
        deadline += 1.0
        cancelled, deadline = _wait_until(
            stop_event,
            deadline,
            clock,
            pause_event=pause_event,
            output=output,
        )
        if cancelled:
            return _finish(output, PlaybackResult.CANCELLED)

    # Fixed deadlines keep small scheduling delays from accumulating as drift.
    deadline = clock()
    for index, event in enumerate(song.events, start=1):
        if _cancellation_requested(stop_event, output):
            return _finish(output, PlaybackResult.CANCELLED)

        duration = event.duration_seconds(song.bpm)
        output.event_started(index, event, duration)
        deadline += duration
        cancelled, deadline = _wait_until(
            stop_event,
            deadline,
            clock,
            pause_event=pause_event,
            output=output,
        )
        output.event_finished(index, event, cancelled=cancelled)

        if cancelled:
            return _finish(output, PlaybackResult.CANCELLED)

    return _finish(output, PlaybackResult.COMPLETED)


def _wait_until(
    stop_event: Event,
    deadline: float,
    clock: Callable[[], float],
    *,
    pause_event: Event | None,
    output: PlaybackOutput,
) -> tuple[bool, float]:
    while True:
        if _cancellation_requested(stop_event, output):
            return True, deadline

        if pause_event is not None and pause_event.is_set():
            paused_at = clock()
            output.playback_paused()
            while pause_event.is_set():
                if stop_event.wait(0.05):
                    return True, deadline
                if output.cancel_requested():
                    return True, deadline
            deadline += clock() - paused_at
            if _cancellation_requested(stop_event, output):
                return True, deadline
            output.playback_resumed()

        remaining = deadline - clock()
        if remaining <= 0:
            return stop_event.is_set(), deadline

        wait_time = remaining if pause_event is None else min(remaining, 0.05)
        if stop_event.wait(wait_time):
            return True, deadline


def _cancellation_requested(stop_event: Event, output: PlaybackOutput) -> bool:
    return stop_event.is_set() or output.cancel_requested()


def _finish(output: PlaybackOutput, result: PlaybackResult) -> PlaybackResult:
    output.release_all()
    output.playback_finished(result)
    return result


class PreviewController:
    """Start and stop a single background preview safely."""

    def __init__(
        self,
        song: Song,
        *,
        countdown_seconds: int = 3,
        output_factory: Callable[[], PlaybackOutput] = ConsolePreviewOutput,
    ) -> None:
        self._song = song
        self._countdown_seconds = countdown_seconds
        self._output_factory = output_factory
        self._lock = Lock()
        self._thread: Thread | None = None
        self._stop_event: Event | None = None
        self._pause_event: Event | None = None

    def start(self) -> bool:
        """Start a preview; return False when one is already running."""

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False

            stop_event = Event()
            pause_event = Event()
            output = self._output_factory()
            thread = Thread(
                target=_run_playback,
                args=(
                    self._song,
                    stop_event,
                    pause_event,
                    output,
                    self._countdown_seconds,
                ),
                name="harmonica-preview",
                daemon=True,
            )
            self._stop_event = stop_event
            self._pause_event = pause_event
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

    def toggle_pause(self) -> PauseToggleResult:
        """Pause or resume the active preview."""

        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                return PauseToggleResult.NOT_PLAYING
            assert self._pause_event is not None
            if self._pause_event.is_set():
                self._pause_event.clear()
                return PauseToggleResult.RESUMED
            self._pause_event.set()
            return PauseToggleResult.PAUSED

    def join(self, timeout: float | None = None) -> None:
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join(timeout)

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return (
                self._thread is not None
                and self._thread.is_alive()
                and self._pause_event is not None
                and self._pause_event.is_set()
            )


def _run_playback(
    song: Song,
    stop_event: Event,
    pause_event: Event,
    output: PlaybackOutput,
    countdown_seconds: int,
) -> None:
    try:
        play_song(
            song,
            stop_event,
            output,
            countdown_seconds=countdown_seconds,
            pause_event=pause_event,
        )
    except Exception as error:
        output.playback_failed(error)
