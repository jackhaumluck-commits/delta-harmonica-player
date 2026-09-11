"""Command-line preview for a harmonica score."""

from __future__ import annotations

import argparse
from pathlib import Path

from .library import SongSelectionError, SongSummary, list_songs, select_song_path
from .playback import describe_event
from .song import SongFormatError, load_song


def main() -> int:
    parser = argparse.ArgumentParser(description="预览口琴曲谱的按键动作")
    parser.add_argument("score", type=Path, nargs="?", help="曲谱文件路径")
    parser.add_argument(
        "--song",
        metavar="NAME",
        help="按名称选择内置曲目；使用 --list-songs 查看名称",
    )
    parser.add_argument(
        "--list-songs",
        action="store_true",
        help="列出内置曲目并退出",
    )
    parser.add_argument(
        "--timed",
        action="store_true",
        help="按 BPM 计时预演，使用 F8/F9/F10 控制（仅 Windows）",
    )
    parser.add_argument(
        "--countdown",
        type=_non_negative_integer,
        default=3,
        metavar="SECONDS",
        help="计时预演开始前的倒计时秒数（默认：3）",
    )
    args = parser.parse_args()

    if args.list_songs:
        if args.score is not None or args.song is not None:
            parser.error("--list-songs 不能和曲谱路径或 --song 同时使用")
        try:
            _print_song_list(list_songs())
        except (OSError, SongFormatError) as error:
            parser.error(f"无法读取内置曲目：{error}")
        return 0

    if args.score is not None and args.song is not None:
        parser.error("曲谱路径和 --song 只能选择一种")
    if args.score is None and args.song is None:
        parser.error("请提供曲谱路径，或使用 --song NAME 选择内置曲目")

    try:
        if args.score is not None:
            score_path = args.score
        else:
            assert args.song is not None
            score_path = select_song_path(args.song)
        song = load_song(score_path)
    except (OSError, SongFormatError, SongSelectionError) as error:
        parser.error(str(error))

    if song.title is None:
        print(f"曲目: {score_path.stem}")
    else:
        print(f"曲目: {song.title} ({score_path.stem})")
    print(f"BPM: {song.bpm:g}")
    print(f"事件数: {len(song.events)}")
    print(f"总时长: {song.duration_seconds:.3f} 秒")
    print()

    if args.timed:
        from .hotkeys import run_hotkey_preview

        try:
            return run_hotkey_preview(song, countdown_seconds=args.countdown)
        except OSError as error:
            parser.error(f"无法注册全局热键：{error}")
        except RuntimeError as error:
            parser.error(str(error))

    elapsed = 0.0
    for index, event in enumerate(song.events, start=1):
        duration = event.duration_seconds(song.bpm)
        action = describe_event(event)
        print(f"{index:>3}. {elapsed:>7.3f}s  {action:<28} {duration:.3f}s")
        elapsed += duration

    return 0


def _non_negative_integer(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("必须是整数") from error
    if number < 0:
        raise argparse.ArgumentTypeError("不能小于零")
    return number


def _print_song_list(songs: tuple[SongSummary, ...]) -> None:
    if not songs:
        print("没有找到内置曲目。")
        return

    print("可用的内置曲目：")
    for song in songs:
        print(
            f"  {song.name:<20} {song.display_name} | BPM {song.bpm:g}, "
            f"{song.event_count} 个事件, {song.duration_seconds:.3f} 秒"
        )


if __name__ == "__main__":
    raise SystemExit(main())
