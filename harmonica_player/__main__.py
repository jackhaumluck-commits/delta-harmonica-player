"""Command-line preview for a harmonica score."""

from __future__ import annotations

import argparse
from pathlib import Path

from .song import SongFormatError, load_song


def main() -> int:
    parser = argparse.ArgumentParser(description="预览口琴曲谱的按键动作")
    parser.add_argument("score", type=Path, help="曲谱文件路径")
    args = parser.parse_args()

    try:
        song = load_song(args.score)
    except (OSError, SongFormatError) as error:
        parser.error(str(error))

    print(f"BPM: {song.bpm:g}")
    print(f"事件数: {len(song.events)}")
    print(f"总时长: {song.duration_seconds:.3f} 秒")
    print()

    elapsed = 0.0
    for index, event in enumerate(song.events, start=1):
        duration = event.duration_seconds(song.bpm)
        if event.is_rest:
            action = "休止"
        elif event.mouse_button is None:
            action = f"按住键盘 {event.key}"
        else:
            action = f"按住鼠标 {event.mouse_button} + 键盘 {event.key}"
        print(f"{index:>3}. {elapsed:>7.3f}s  {action:<28} {duration:.3f}s")
        elapsed += duration

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
