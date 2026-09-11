"""Convert a monophonic Standard MIDI File into the project's score format."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from mido import MidiFile, merge_tracks

from .library import (
    DEFAULT_SONG_DIRECTORY,
    DEFAULT_USER_SONG_DIRECTORY,
    SongSummary,
    save_user_song,
)
from .song import NoteEvent, Song


DEFAULT_TEMPO = 500_000
SUPPORTED_MIDI_SUFFIXES = {".mid", ".midi"}
_NATURAL_OFFSETS = (0, 2, 4, 5, 7, 9, 11)
_SHARP_DEGREES = {1: 1, 3: 2, 6: 4, 8: 5, 10: 6}
_PITCH_NAMES = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
)


class MidiImportError(ValueError):
    """Raised when a MIDI file cannot be converted safely."""


@dataclass(frozen=True, slots=True)
class MidiConversion:
    song: Song
    track_index: int
    track_name: str | None


@dataclass(frozen=True, slots=True)
class MidiTrackSummary:
    """Small, display-friendly description of one MIDI track."""

    index: int
    name: str | None
    note_count: int

    @property
    def display_name(self) -> str:
        return self.name or f"轨道 {self.index}"


@dataclass(frozen=True, slots=True)
class _ActiveNote:
    pitch: int
    channel: int
    start_tick: int


def convert_midi(
    source_path: Path, *, track_index: int | None = None
) -> MidiConversion:
    """Read a MIDI file and convert one monophonic track into a :class:`Song`."""

    source_path = Path(source_path)
    midi = _load_midi(source_path)

    if midi.type == 2:
        raise MidiImportError("暂不支持异步多序列的 Type 2 MIDI 文件")
    if midi.ticks_per_beat <= 0:
        raise MidiImportError("MIDI 的每拍 tick 数必须大于零")

    selected_index = _select_track(midi, track_index)
    tempo = _constant_tempo(midi)
    events = _convert_track(midi.tracks[selected_index], midi.ticks_per_beat)
    title = source_path.stem.replace("#", "＃").strip() or "MIDI 导入曲目"
    track_name = midi.tracks[selected_index].name.strip() or None
    return MidiConversion(
        song=Song(
            bpm=60_000_000 / tempo,
            events=events,
            title=title,
        ),
        track_index=selected_index,
        track_name=track_name,
    )


def list_midi_tracks(source_path: Path) -> tuple[MidiTrackSummary, ...]:
    """Return every MIDI track so a graphical importer can offer a choice."""

    midi = _load_midi(Path(source_path))
    return tuple(
        MidiTrackSummary(
            index=index,
            name=track.name.strip() or None,
            note_count=sum(1 for message in track if _is_note_start(message)),
        )
        for index, track in enumerate(midi.tracks)
    )


def import_midi(
    source_path: Path,
    *,
    track_index: int | None = None,
    bundled_directory: Path = DEFAULT_SONG_DIRECTORY,
    user_directory: Path = DEFAULT_USER_SONG_DIRECTORY,
) -> SongSummary:
    """Convert a MIDI file and store the result in the user song library."""

    source_path = Path(source_path)
    conversion = convert_midi(source_path, track_index=track_index)
    text = format_midi_song(conversion)
    return save_user_song(
        text,
        source_path.stem,
        bundled_directory=bundled_directory,
        user_directory=user_directory,
    )


def format_midi_song(conversion: MidiConversion) -> str:
    """Serialize a MIDI conversion as editable project score text."""

    track_description = str(conversion.track_index)
    if conversion.track_name is not None:
        track_description += f"（{conversion.track_name}）"
    lines = [
        "# 由 MIDI 导入生成，可按需要手动修改",
        f"# MIDI 轨道：{track_description}",
        f"bpm {_format_number(conversion.song.bpm)}",
        f"title {conversion.song.title}",
        "",
    ]
    lines.extend(
        f"{event.note} {_format_number(event.beats)} {event.modifier}"
        for event in conversion.song.events
    )
    return "\n".join(lines) + "\n"


def midi_pitch_to_event(pitch: int, beats: float) -> NoteEvent:
    """Map a MIDI pitch to one playable key and mouse modifier."""

    mapping = _pitch_mapping()
    try:
        note, modifier = mapping[pitch]
    except KeyError as error:
        raise MidiImportError(
            f"MIDI 音符 {_pitch_name(pitch)}（{pitch}）超出当前可演奏映射；"
            "支持 C3 到 C6 的自然音，以及 C4 到 B4 的升半音"
        ) from error
    return NoteEvent(note=note, beats=beats, modifier=modifier)


def _select_track(midi: MidiFile, requested_index: int | None) -> int:
    note_tracks = [
        index
        for index, track in enumerate(midi.tracks)
        if any(_is_note_start(message) for message in track)
    ]
    if requested_index is not None:
        if not 0 <= requested_index < len(midi.tracks):
            raise MidiImportError(
                f"MIDI 轨道编号必须在 0 到 {len(midi.tracks) - 1} 之间"
            )
        if requested_index not in note_tracks:
            raise MidiImportError(f"MIDI 轨道 {requested_index} 中没有音符")
        return requested_index

    if not note_tracks:
        raise MidiImportError("MIDI 文件中没有音符")
    if len(note_tracks) > 1:
        choices = ", ".join(_describe_track(midi, index) for index in note_tracks)
        raise MidiImportError(
            f"MIDI 包含多个有音符的轨道：{choices}；"
            "请使用 --midi-track 指定一个轨道"
        )
    return note_tracks[0]


def _load_midi(source_path: Path) -> MidiFile:
    if not source_path.is_file():
        raise MidiImportError(f"找不到 MIDI 文件：{source_path}")
    if source_path.suffix.casefold() not in SUPPORTED_MIDI_SUFFIXES:
        raise MidiImportError("只支持导入 .mid 或 .midi 文件")
    try:
        return MidiFile(source_path)
    except (EOFError, OSError, ValueError) as error:
        raise MidiImportError(f"无法读取 MIDI 文件：{error}") from error


def _constant_tempo(midi: MidiFile) -> int:
    tempo_events: dict[int, set[int]] = defaultdict(set)
    absolute_tick = 0
    for message in merge_tracks(midi.tracks):
        absolute_tick += message.time
        if message.type == "set_tempo":
            tempo_events[absolute_tick].add(message.tempo)

    tempo = DEFAULT_TEMPO
    for tick in sorted(tempo_events):
        values = tempo_events[tick]
        if len(values) > 1:
            raise MidiImportError(f"MIDI 在 tick {tick} 同时设置了多个不同 BPM")
        new_tempo = next(iter(values))
        if tick > 0 and new_tempo != tempo:
            raise MidiImportError("首版 MIDI 导入暂不支持播放过程中改变 BPM")
        tempo = new_tempo
    return tempo


def _convert_track(track: object, ticks_per_beat: int) -> tuple[NoteEvent, ...]:
    messages_by_tick: dict[int, list[object]] = defaultdict(list)
    absolute_tick = 0
    for message in track:
        absolute_tick += message.time
        if _is_note_start(message) or _is_note_end(message):
            messages_by_tick[absolute_tick].append(message)

    events: list[NoteEvent] = []
    active: _ActiveNote | None = None
    last_end_tick = 0
    for tick in sorted(messages_by_tick):
        messages = messages_by_tick[tick]
        ending = [message for message in messages if _is_note_end(message)]
        starting = [message for message in messages if _is_note_start(message)]

        for message in ending:
            if active is None:
                raise MidiImportError(
                    f"tick {tick} 的 {_pitch_name(message.note)} 缺少对应的开始事件"
                )
            if (message.note, message.channel) != (active.pitch, active.channel):
                raise MidiImportError("首版 MIDI 导入只支持一次演奏一个音符，不支持和弦")
            duration_ticks = tick - active.start_tick
            if duration_ticks <= 0:
                raise MidiImportError(
                    f"MIDI 音符 {_pitch_name(active.pitch)} 的持续时间必须大于零"
                )
            if active.start_tick > last_end_tick:
                events.append(
                    NoteEvent(
                        note="0",
                        beats=(active.start_tick - last_end_tick) / ticks_per_beat,
                        modifier="rest",
                    )
                )
            events.append(
                midi_pitch_to_event(
                    active.pitch,
                    duration_ticks / ticks_per_beat,
                )
            )
            last_end_tick = tick
            active = None

        for message in starting:
            if active is not None:
                raise MidiImportError("首版 MIDI 导入只支持一次演奏一个音符，不支持和弦")
            active = _ActiveNote(
                pitch=message.note,
                channel=message.channel,
                start_tick=tick,
            )

    if active is not None:
        raise MidiImportError(
            f"MIDI 音符 {_pitch_name(active.pitch)} 缺少对应的结束事件"
        )
    if not events:
        raise MidiImportError("所选 MIDI 轨道中没有可转换的完整音符")
    return tuple(events)


def _pitch_mapping() -> dict[int, tuple[str, str]]:
    mapping: dict[int, tuple[str, str]] = {}

    for pitch, note in _natural_notes(60):
        mapping[pitch] = (note, "normal")
    for offset, note_number in _SHARP_DEGREES.items():
        mapping[60 + offset] = (str(note_number), "semitone")
    for pitch, note in _natural_notes(48):
        mapping.setdefault(pitch, (note, "down"))
    for pitch, note in _natural_notes(72):
        mapping.setdefault(pitch, (note, "up"))
    return mapping


def _natural_notes(root_pitch: int) -> tuple[tuple[int, str], ...]:
    notes = [
        (root_pitch + offset, str(index))
        for index, offset in enumerate(_NATURAL_OFFSETS, start=1)
    ]
    notes.append((root_pitch + 12, "8"))
    return tuple(notes)


def _is_note_start(message: object) -> bool:
    return message.type == "note_on" and message.velocity > 0


def _is_note_end(message: object) -> bool:
    return message.type == "note_off" or (
        message.type == "note_on" and message.velocity == 0
    )


def _describe_track(midi: MidiFile, index: int) -> str:
    name = midi.tracks[index].name.strip()
    return str(index) if not name else f"{index}（{name}）"


def _pitch_name(pitch: int) -> str:
    return f"{_PITCH_NAMES[pitch % 12]}{pitch // 12 - 1}"


def _format_number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")
