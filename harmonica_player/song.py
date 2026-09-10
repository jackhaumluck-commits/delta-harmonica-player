"""Parse a small numbered-score format into timed input actions."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path


NOTE_TO_KEY = {
    "1": "Z",
    "2": "X",
    "3": "C",
    "4": "V",
    "5": "B",
    "6": "N",
    "7": "M",
    "8": ",",
}

MODIFIER_TO_MOUSE_BUTTON = {
    "normal": None,
    "down": "left",
    "semitone": "middle",
    "up": "right",
}


class SongFormatError(ValueError):
    """Raised when a score contains an invalid instruction."""


@dataclass(frozen=True, slots=True)
class NoteEvent:
    note: str
    beats: float
    modifier: str

    @property
    def is_rest(self) -> bool:
        return self.note == "0"

    @property
    def key(self) -> str | None:
        return None if self.is_rest else NOTE_TO_KEY[self.note]

    @property
    def mouse_button(self) -> str | None:
        return None if self.is_rest else MODIFIER_TO_MOUSE_BUTTON[self.modifier]

    def duration_seconds(self, bpm: float) -> float:
        return self.beats * 60 / bpm


@dataclass(frozen=True, slots=True)
class Song:
    bpm: float
    events: tuple[NoteEvent, ...]

    @property
    def duration_seconds(self) -> float:
        return sum(event.duration_seconds(self.bpm) for event in self.events)


def parse_song(text: str) -> Song:
    """Parse score text and return an immutable :class:`Song`."""

    bpm: float | None = None
    events: list[NoteEvent] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.split("#", maxsplit=1)[0].strip()
        if not line:
            continue

        parts = line.split()
        if parts[0].lower() == "bpm":
            if bpm is not None:
                raise SongFormatError(f"第 {line_number} 行：BPM 只能设置一次")
            if len(parts) != 2:
                raise SongFormatError(f"第 {line_number} 行：BPM 格式应为 'bpm 120'")
            bpm = _parse_positive_number(parts[1], line_number, "BPM")
            continue

        if bpm is None:
            raise SongFormatError(f"第 {line_number} 行：请先设置 BPM")
        if len(parts) != 3:
            raise SongFormatError(
                f"第 {line_number} 行：音符格式应为 '音符 拍数 修饰词'"
            )

        note, beats_text, modifier = parts
        modifier = modifier.lower()
        beats = _parse_positive_number(beats_text, line_number, "拍数")

        if note == "0":
            if modifier != "rest":
                raise SongFormatError(f"第 {line_number} 行：休止符必须写成 '0 拍数 rest'")
        else:
            if note not in NOTE_TO_KEY:
                raise SongFormatError(f"第 {line_number} 行：音符必须是 0 到 8")
            if modifier not in MODIFIER_TO_MOUSE_BUTTON:
                allowed = ", ".join(MODIFIER_TO_MOUSE_BUTTON)
                raise SongFormatError(
                    f"第 {line_number} 行：修饰词必须是 {allowed} 或 rest"
                )

        events.append(NoteEvent(note=note, beats=beats, modifier=modifier))

    if bpm is None:
        raise SongFormatError("曲谱缺少 BPM 设置")
    if not events:
        raise SongFormatError("曲谱中没有音符")

    return Song(bpm=bpm, events=tuple(events))


def load_song(path: Path) -> Song:
    return parse_song(path.read_text(encoding="utf-8"))


def _parse_positive_number(value: str, line_number: int, field_name: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise SongFormatError(f"第 {line_number} 行：{field_name}必须是数字") from error

    if not isfinite(number) or number <= 0:
        raise SongFormatError(f"第 {line_number} 行：{field_name}必须大于零")
    return number
