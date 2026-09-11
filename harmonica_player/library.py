"""Discover, import, and select bundled or user-provided score files."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .song import Song, SongFormatError, load_song, parse_song


PROJECT_DIRECTORY = Path(__file__).resolve().parent.parent
DEFAULT_SONG_DIRECTORY = PROJECT_DIRECTORY / "examples"
DEFAULT_USER_SONG_DIRECTORY = PROJECT_DIRECTORY / "songs"
SUPPORTED_IMPORT_SUFFIXES = {".song", ".txt"}


class SongSelectionError(ValueError):
    """Raised when a song cannot be selected unambiguously."""


class SongImportError(ValueError):
    """Raised when a score cannot be added to the user library."""


class SongSource(Enum):
    BUNDLED = "内置"
    USER = "用户"


@dataclass(frozen=True, slots=True)
class SongSummary:
    name: str
    title: str | None
    path: Path
    bpm: float
    event_count: int
    duration_seconds: float
    source: SongSource

    @property
    def display_name(self) -> str:
        return self.title or self.name


def list_songs(
    bundled_directory: Path = DEFAULT_SONG_DIRECTORY,
    user_directory: Path | None = DEFAULT_USER_SONG_DIRECTORY,
) -> tuple[SongSummary, ...]:
    """Return the bundled and user songs in stable name order."""

    summaries = list(_list_directory(bundled_directory, SongSource.BUNDLED))
    if user_directory is not None and user_directory != bundled_directory:
        summaries.extend(_list_directory(user_directory, SongSource.USER))
    summaries.sort(key=lambda song: (song.name.casefold(), song.source.value))
    return tuple(summaries)


def select_song_path(
    name: str,
    bundled_directory: Path = DEFAULT_SONG_DIRECTORY,
    user_directory: Path | None = DEFAULT_USER_SONG_DIRECTORY,
) -> Path:
    """Resolve a song by its filename stem, filename, or title."""

    requested_name = name.strip().casefold()
    if requested_name.endswith(".song"):
        requested_name = requested_name.removesuffix(".song")

    songs = list_songs(bundled_directory, user_directory)
    matches = [song for song in songs if requested_name in _aliases(song)]
    if len(matches) == 1:
        return matches[0].path
    if len(matches) > 1:
        choices = ", ".join(_describe_song(song) for song in matches)
        raise SongSelectionError(
            f"曲目名称 '{name}' 不唯一：{choices}；请重命名其中一份曲谱"
        )

    available = ", ".join(
        _describe_song(summary) for summary in songs
    ) or "（没有曲目）"
    raise SongSelectionError(f"未知曲目 '{name}'；可用曲目：{available}")


def import_song(
    source_path: Path,
    *,
    bundled_directory: Path = DEFAULT_SONG_DIRECTORY,
    user_directory: Path = DEFAULT_USER_SONG_DIRECTORY,
) -> SongSummary:
    """Validate and copy a text score into the user song library."""

    source_path = Path(source_path)
    if not source_path.is_file():
        raise SongImportError(f"找不到曲谱文件：{source_path}")
    if source_path.suffix.casefold() not in SUPPORTED_IMPORT_SUFFIXES:
        allowed = ", ".join(sorted(SUPPORTED_IMPORT_SUFFIXES))
        raise SongImportError(f"只支持导入 {allowed} 文件")

    try:
        text = source_path.read_text(encoding="utf-8")
    except UnicodeError as error:
        raise SongImportError("曲谱必须使用 UTF-8 编码") from error
    song = parse_song(text)
    destination = user_directory / f"{source_path.stem}.song"
    imported_aliases = {source_path.stem.casefold()}
    if song.title is not None:
        imported_aliases.add(song.title.casefold())

    if destination.exists():
        raise SongImportError(f"用户曲库中已存在：{destination.name}")

    for existing in list_songs(bundled_directory, user_directory):
        if imported_aliases.intersection(_aliases(existing)):
            raise SongImportError(
                f"曲目名称或标题与现有曲目冲突：{_describe_song(existing)}"
            )

    user_directory.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8", newline="\n")
    return _summarize(destination, song, SongSource.USER)


def _list_directory(
    directory: Path, source: SongSource
) -> tuple[SongSummary, ...]:
    if not directory.exists():
        return ()

    summaries: list[SongSummary] = []
    for path in directory.glob("*.song"):
        try:
            song = load_song(path)
        except UnicodeError as error:
            raise SongFormatError(f"{path.name}：曲谱必须使用 UTF-8 编码") from error
        except SongFormatError as error:
            raise SongFormatError(f"{path.name}：{error}") from error
        summaries.append(_summarize(path, song, source))
    return tuple(summaries)


def _summarize(path: Path, song: Song, source: SongSource) -> SongSummary:
    return SongSummary(
        name=path.stem,
        title=song.title,
        path=path,
        bpm=song.bpm,
        event_count=len(song.events),
        duration_seconds=song.duration_seconds,
        source=source,
    )


def _aliases(song: SongSummary) -> set[str]:
    aliases = {song.name.casefold()}
    if song.title is not None:
        aliases.add(song.title.casefold())
    return aliases


def _describe_song(song: SongSummary) -> str:
    name = song.name if song.title is None else f"{song.name}（{song.title}）"
    return f"{name}［{song.source.value}］"
