"""Command-line preview for a harmonica score."""

from __future__ import annotations

import argparse
from pathlib import Path

from .library import (
    SongImportError,
    SongSelectionError,
    SongSummary,
    import_song,
    list_songs,
    select_song_path,
)
from .playback import describe_event
from .song import SongFormatError, load_song


def main() -> int:
    parser = argparse.ArgumentParser(description="预览或播放口琴曲谱的按键动作")
    parser.add_argument("score", type=Path, nargs="?", help="曲谱文件路径")
    parser.add_argument(
        "--gui",
        action="store_true",
        help="打开桌面界面",
    )
    parser.add_argument(
        "--song",
        metavar="NAME",
        help="按文件名或标题选择曲库中的曲目；使用 --list-songs 查看名称",
    )
    parser.add_argument(
        "--list-songs",
        action="store_true",
        help="列出内置曲目和用户曲目并退出",
    )
    parser.add_argument(
        "--import-song",
        type=Path,
        metavar="PATH",
        help="将 .song 或 .txt 曲谱导入用户曲库并退出",
    )
    parser.add_argument(
        "--import-midi",
        type=Path,
        metavar="PATH",
        help="将单旋律 .mid 或 .midi 文件转换并导入用户曲库",
    )
    parser.add_argument(
        "--midi-track",
        type=_non_negative_integer,
        metavar="INDEX",
        help="MIDI 中存在多个音符轨道时，指定要转换的轨道编号",
    )
    parser.add_argument(
        "--timed",
        action="store_true",
        help="按 BPM 计时预演，使用 F8/F9/F10 控制（仅 Windows）",
    )
    parser.add_argument(
        "--real-input",
        action="store_true",
        help="实际发送 Windows 键鼠输入，必须和 --timed 一起使用",
    )
    parser.add_argument(
        "--input-test-window",
        action="store_true",
        help="打开独立的键鼠输入测试窗口并退出",
    )
    parser.add_argument(
        "--countdown",
        type=_non_negative_integer,
        default=3,
        metavar="SECONDS",
        help="计时预演开始前的倒计时秒数（默认：3）",
    )
    parser.add_argument(
        "--start-key",
        type=_function_key,
        default="F8",
        metavar="F1-F24",
        help="开始播放快捷键（默认：F8）",
    )
    parser.add_argument(
        "--stop-key",
        type=_function_key,
        default="F9",
        metavar="F1-F24",
        help="停止播放快捷键（默认：F9）",
    )
    parser.add_argument(
        "--pause-key",
        type=_function_key,
        default="F10",
        metavar="F1-F24",
        help="暂停或继续快捷键（默认：F10）",
    )
    args = parser.parse_args()

    if args.gui:
        if (
            args.score is not None
            or args.song is not None
            or args.list_songs
            or args.import_song is not None
            or args.import_midi is not None
            or args.midi_track is not None
            or args.timed
            or args.real_input
            or args.input_test_window
        ):
            parser.error("--gui 不能和命令行曲谱、导入或播放选项同时使用")
        from .gui import run_gui

        try:
            return run_gui()
        except RuntimeError as error:
            parser.error(str(error))

    if args.input_test_window:
        if (
            args.score is not None
            or args.song is not None
            or args.list_songs
            or args.import_song is not None
            or args.import_midi is not None
            or args.midi_track is not None
            or args.timed
            or args.real_input
        ):
            parser.error("--input-test-window 不能和曲谱或播放选项同时使用")
        from .input_test_window import run_input_test_window

        try:
            return run_input_test_window()
        except RuntimeError as error:
            parser.error(str(error))

    if args.real_input and not args.timed:
        parser.error("--real-input 必须和 --timed 一起使用")

    if args.midi_track is not None and args.import_midi is None:
        parser.error("--midi-track 必须和 --import-midi 一起使用")

    if args.import_song is not None and args.import_midi is not None:
        parser.error("--import-song 和 --import-midi 只能选择一种")

    if args.import_song is not None:
        if (
            args.score is not None
            or args.song is not None
            or args.list_songs
            or args.timed
            or args.real_input
        ):
            parser.error("--import-song 不能和曲谱或播放选项同时使用")
        try:
            imported = import_song(args.import_song)
        except (OSError, SongFormatError, SongImportError) as error:
            parser.error(f"无法导入曲谱：{error}")
        print(
            f"已导入用户曲目：{imported.display_name} "
            f"({imported.path.name})"
        )
        return 0

    if args.import_midi is not None:
        if (
            args.score is not None
            or args.song is not None
            or args.list_songs
            or args.timed
            or args.real_input
        ):
            parser.error("--import-midi 不能和曲谱或播放选项同时使用")
        from .midi_import import MidiImportError, import_midi

        try:
            imported = import_midi(
                args.import_midi,
                track_index=args.midi_track,
            )
        except (OSError, SongFormatError, SongImportError, MidiImportError) as error:
            parser.error(f"无法导入 MIDI：{error}")
        print(
            f"已将 MIDI 转换为用户曲目：{imported.display_name} "
            f"({imported.path.name})"
        )
        return 0

    if args.list_songs:
        if args.score is not None or args.song is not None or args.timed:
            parser.error("--list-songs 不能和曲谱路径或 --song 同时使用")
        try:
            _print_song_list(list_songs())
        except (OSError, SongFormatError) as error:
            parser.error(f"无法读取曲库：{error}")
        return 0

    if args.score is not None and args.song is not None:
        parser.error("曲谱路径和 --song 只能选择一种")
    if args.score is None and args.song is None:
        parser.error("请提供曲谱路径，或使用 --song NAME 选择曲库中的曲目")

    bindings = None
    if args.timed:
        from .hotkeys import HotkeyBindings

        try:
            bindings = HotkeyBindings(
                start=args.start_key,
                stop=args.stop_key,
                pause=args.pause_key,
            )
        except ValueError as error:
            parser.error(str(error))

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
            return run_hotkey_preview(
                song,
                countdown_seconds=args.countdown,
                real_input=args.real_input,
                bindings=bindings,
            )
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


def _function_key(value: str) -> str:
    from .hotkeys import normalize_function_key

    try:
        return normalize_function_key(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _print_song_list(songs: tuple[SongSummary, ...]) -> None:
    if not songs:
        print("曲库中没有找到曲目。")
        return

    print("可用曲目：")
    for song in songs:
        print(
            f"  [{song.source.value}] {song.name:<20} "
            f"{song.display_name} | BPM {song.bpm:g}, "
            f"{song.event_count} 个事件, {song.duration_seconds:.3f} 秒"
        )


if __name__ == "__main__":
    raise SystemExit(main())
