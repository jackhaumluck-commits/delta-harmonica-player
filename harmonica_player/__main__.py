"""Command-line preview for a harmonica score."""

from __future__ import annotations

import argparse
from pathlib import Path

from .playback import describe_event
from .song import SongFormatError, load_song


def main() -> int:
    parser = argparse.ArgumentParser(description="预览口琴曲谱的按键动作")
    parser.add_argument("score", type=Path, help="曲谱文件路径")
    parser.add_argument(
        "--timed",
        action="store_true",
        help="按 BPM 计时预演，并使用 F8 开始、F9 停止（仅 Windows）",
    )
    parser.add_argument(
        "--countdown",
        type=_non_negative_integer,
        default=3,
        metavar="SECONDS",
        help="计时预演开始前的倒计时秒数（默认：3）",
    )
    args = parser.parse_args()

    try:
        song = load_song(args.score)
    except (OSError, SongFormatError) as error:
        parser.error(str(error))

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


if __name__ == "__main__":
    raise SystemExit(main())
