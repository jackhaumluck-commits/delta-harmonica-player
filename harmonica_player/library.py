"""Discover and select the score files bundled with the project."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .song import load_song


DEFAULT_SONG_DIRECTORY = Path(__file__).resolve().parent.parent / "examples"


class SongSelectionError(ValueError):
    """Raised when a bundled song cannot be selected."""


@dataclass(frozen=True, slots=True)
class SongSummary:
    name: str
    path: Path
    bpm: float
    event_count: int
    duration_seconds: float


def list_songs(directory: Path = DEFAULT_SONG_DIRECTORY) -> tuple[SongSummary, ...]:
    """Return the bundled songs in stable name order."""

    summaries: list[SongSummary] = []
    for path in sorted(directory.glob("*.song")):
        song = load_song(path)
        summaries.append(
            SongSummary(
                name=path.stem,
                path=path,
                bpm=song.bpm,
                event_count=len(song.events),
                duration_seconds=song.duration_seconds,
            )
        )
    return tuple(summaries)


def select_song_path(
    name: str, directory: Path = DEFAULT_SONG_DIRECTORY
) -> Path:
    """Resolve a bundled song by its stem or filename."""

    requested_name = name.casefold()
    if requested_name.endswith(".song"):
        requested_name = requested_name.removesuffix(".song")
    songs = list_songs(directory)
    for summary in songs:
        if summary.name.casefold() == requested_name:
            return summary.path

    available = ", ".join(summary.name for summary in songs) or "（没有曲目）"
    raise SongSelectionError(f"未知曲目 '{name}'；可用曲目：{available}")
