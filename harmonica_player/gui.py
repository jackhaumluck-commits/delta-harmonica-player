"""Tk desktop interface for the song library and playback controller."""

from __future__ import annotations

import ctypes
import os
import queue
import sys
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Event, Thread
from typing import Any, Callable

from .hotkeys import Hotkey, HotkeyBindings, WindowsHotkeyListener
from .library import SongSummary, import_song, list_songs
from .midi_import import MidiImportError, import_midi, list_midi_tracks
from .playback import (
    PauseToggleResult,
    PlaybackOutput,
    PlaybackResult,
    PreviewController,
    describe_event,
)
from .settings import GuiSettings, load_gui_settings, save_gui_settings
from .song import NoteEvent, load_song
from .windows_input import WindowsInputOutput, is_running_as_administrator


@dataclass(frozen=True, slots=True)
class UiEvent:
    """One thread-safe notification consumed by the Tk event loop."""

    kind: str
    message: str = ""
    index: int = 0
    total: int = 0
    data: object | None = None


class QueuePlaybackOutput:
    """Translate playback callbacks into events without touching Tk off-thread."""

    def __init__(self, events: queue.Queue[UiEvent], total_events: int) -> None:
        self._events = events
        self._total_events = total_events

    def countdown(self, seconds: int) -> None:
        self._events.put(UiEvent("countdown", f"{seconds}..."))

    def event_started(
        self, index: int, event: NoteEvent, duration: float
    ) -> None:
        self._events.put(
            UiEvent(
                "event_started",
                f"{describe_event(event)}，持续 {duration:.3f} 秒",
                index=index,
                total=self._total_events,
            )
        )

    def event_finished(
        self, index: int, event: NoteEvent, *, cancelled: bool
    ) -> None:
        self._events.put(
            UiEvent(
                "event_finished",
                index=index,
                total=self._total_events,
                data=cancelled,
            )
        )

    def playback_paused(self) -> None:
        self._events.put(UiEvent("paused", "播放已暂停"))

    def playback_resumed(self) -> None:
        self._events.put(UiEvent("resumed", "播放继续"))

    def playback_finished(self, result: PlaybackResult) -> None:
        self._events.put(UiEvent("finished", data=result))

    def playback_failed(self, error: Exception) -> None:
        self._events.put(UiEvent("failed", str(error), data=error))

    def cancel_requested(self) -> bool:
        return False

    def release_all(self) -> None:
        return


class GlobalHotkeyMonitor:
    """Own the Win32 hotkey message loop on a stoppable worker thread."""

    def __init__(
        self,
        bindings: HotkeyBindings,
        events: queue.Queue[UiEvent],
        *,
        listener_factory: Callable[[HotkeyBindings], WindowsHotkeyListener]
        = WindowsHotkeyListener,
    ) -> None:
        self._bindings = bindings
        self._events = events
        self._listener_factory = listener_factory
        self._stop_event = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = Thread(
            target=self._run,
            name="harmonica-hotkeys",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(1)

    def _run(self) -> None:
        try:
            with self._listener_factory(self._bindings) as listener:
                self._events.put(UiEvent("hotkeys_ready", data=self._bindings))
                for hotkey in listener.events(self._stop_event):
                    self._events.put(UiEvent("hotkey", data=hotkey))
        except Exception as error:
            if not self._stop_event.is_set():
                self._events.put(UiEvent("hotkeys_failed", str(error), data=error))


class HarmonicaPlayerApp:
    """Build and coordinate the desktop interface without subclassing Tk."""

    def __init__(
        self,
        root: Any,
        *,
        tk: Any,
        ttk: Any,
        filedialog: Any,
        messagebox: Any,
        simpledialog: Any,
        scrolled_text: type,
    ) -> None:
        self._root = root
        self._tk = tk
        self._ttk = ttk
        self._filedialog = filedialog
        self._messagebox = messagebox
        self._simpledialog = simpledialog
        self._scrolled_text = scrolled_text
        self._events: queue.Queue[UiEvent] = queue.Queue()
        self._song_by_id: dict[str, SongSummary] = {}
        self._controller: PreviewController | None = None
        self._hotkey_monitor: GlobalHotkeyMonitor | None = None
        self._closing = False
        self._settings = load_gui_settings()
        self._administrator = is_running_as_administrator()

        self._build_window()
        self._refresh_songs()
        self._restart_hotkeys()
        self._root.protocol("WM_DELETE_WINDOW", self._close)
        self._root.after(50, self._poll_events)

    def _build_window(self) -> None:
        root = self._root
        ttk = self._ttk
        tk = self._tk

        root.title("三角洲口琴播放器 v0.9")
        root.geometry("980x680")
        root.minsize(860, 600)

        header = ttk.Frame(root, padding=(12, 10))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="三角洲口琴播放器",
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(side="left")
        administrator_text = (
            "管理员权限：是"
            if self._administrator
            else "管理员权限：否（真实输入不可用）"
        )
        self._administrator_label = ttk.Label(header, text=administrator_text)
        self._administrator_label.pack(side="right")

        body = ttk.Panedwindow(root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        library_frame = ttk.LabelFrame(body, text="曲库", padding=8)
        control_frame = ttk.Frame(body, padding=(10, 0, 0, 0))
        body.add(library_frame, weight=2)
        body.add(control_frame, weight=3)

        tree_area = ttk.Frame(library_frame)
        tree_area.pack(fill="both", expand=True)
        self._song_tree = ttk.Treeview(
            tree_area,
            columns=("source", "bpm", "duration"),
            show="tree headings",
            selectmode="browse",
        )
        self._song_tree.heading("#0", text="曲名")
        self._song_tree.heading("source", text="来源")
        self._song_tree.heading("bpm", text="BPM")
        self._song_tree.heading("duration", text="时长")
        self._song_tree.column("#0", width=190, minwidth=130)
        self._song_tree.column("source", width=55, anchor="center")
        self._song_tree.column("bpm", width=55, anchor="center")
        self._song_tree.column("duration", width=70, anchor="e")
        scrollbar = ttk.Scrollbar(
            tree_area, orient="vertical", command=self._song_tree.yview
        )
        self._song_tree.configure(yscrollcommand=scrollbar.set)
        self._song_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._song_tree.bind("<<TreeviewSelect>>", self._show_song_details)

        import_buttons = ttk.Frame(library_frame)
        import_buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(
            import_buttons, text="导入曲谱", command=self._import_score
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(
            import_buttons, text="导入 MIDI", command=self._import_midi
        ).pack(side="left", expand=True, fill="x", padx=(4, 4))
        ttk.Button(
            import_buttons, text="刷新", command=self._refresh_songs
        ).pack(side="left", padx=(4, 0))

        details = ttk.LabelFrame(control_frame, text="所选曲目", padding=10)
        details.pack(fill="x")
        self._details_var = tk.StringVar(value="尚未选择曲目")
        ttk.Label(
            details,
            textvariable=self._details_var,
            justify="left",
        ).pack(anchor="w")

        settings_frame = ttk.LabelFrame(
            control_frame, text="播放设置", padding=10
        )
        settings_frame.pack(fill="x", pady=(10, 0))
        keys = tuple(f"F{number}" for number in range(1, 25))
        self._start_key_var = tk.StringVar(value=self._settings.start_key)
        self._stop_key_var = tk.StringVar(value=self._settings.stop_key)
        self._pause_key_var = tk.StringVar(value=self._settings.pause_key)
        self._countdown_var = tk.StringVar(
            value=str(self._settings.countdown_seconds)
        )
        variables = (
            ("开始", self._start_key_var),
            ("停止", self._stop_key_var),
            ("暂停 / 继续", self._pause_key_var),
        )
        for column, (label, variable) in enumerate(variables):
            ttk.Label(settings_frame, text=label).grid(
                row=0, column=column, sticky="w", padx=(0, 8)
            )
            ttk.Combobox(
                settings_frame,
                values=keys,
                textvariable=variable,
                width=8,
                state="readonly",
            ).grid(row=1, column=column, sticky="ew", padx=(0, 8))
            settings_frame.columnconfigure(column, weight=1)
        ttk.Label(settings_frame, text="倒计时（秒）").grid(
            row=0, column=3, sticky="w", padx=(0, 8)
        )
        ttk.Spinbox(
            settings_frame,
            from_=0,
            to=30,
            width=8,
            textvariable=self._countdown_var,
        ).grid(row=1, column=3, sticky="ew", padx=(0, 8))
        ttk.Button(
            settings_frame, text="应用", command=self._apply_settings
        ).grid(row=1, column=4, sticky="ew")
        self._hotkey_status_var = tk.StringVar(value="正在注册全局热键……")
        ttk.Label(
            settings_frame, textvariable=self._hotkey_status_var
        ).grid(row=2, column=0, columnspan=5, sticky="w", pady=(8, 0))

        mode_frame = ttk.LabelFrame(control_frame, text="输出模式", padding=10)
        mode_frame.pack(fill="x", pady=(10, 0))
        self._real_input_var = tk.BooleanVar(value=False)
        self._real_input_check = ttk.Checkbutton(
            mode_frame,
            text="启用 Windows 真实键鼠输入（每次启动都默认关闭）",
            variable=self._real_input_var,
        )
        self._real_input_check.pack(anchor="w")
        if sys.platform != "win32":
            self._real_input_check.configure(state="disabled")
        ttk.Label(
            mode_frame,
            text="安全预演可点击开始；真实输入请先切到目标窗口，再按开始热键。",
            foreground="#666666",
        ).pack(anchor="w", pady=(4, 0))

        buttons = ttk.Frame(control_frame)
        buttons.pack(fill="x", pady=(10, 0))
        self._start_button = ttk.Button(
            buttons, text="开始", command=self._start_from_button
        )
        self._start_button.pack(side="left", expand=True, fill="x")
        self._pause_button = ttk.Button(
            buttons, text="暂停 / 继续", command=self._toggle_pause
        )
        self._pause_button.pack(
            side="left", expand=True, fill="x", padx=(8, 8)
        )
        ttk.Button(buttons, text="停止", command=self._stop_playback).pack(
            side="left", expand=True, fill="x"
        )

        progress_frame = ttk.LabelFrame(
            control_frame, text="播放进度", padding=10
        )
        progress_frame.pack(fill="x", pady=(10, 0))
        self._progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(
            progress_frame,
            variable=self._progress_var,
            maximum=100,
        ).pack(fill="x")
        self._playback_status_var = tk.StringVar(value="等待开始")
        ttk.Label(
            progress_frame, textvariable=self._playback_status_var
        ).pack(anchor="w", pady=(6, 0))

        log_frame = ttk.LabelFrame(control_frame, text="运行记录", padding=8)
        log_frame.pack(fill="both", expand=True, pady=(10, 0))
        self._log_widget = self._scrolled_text(
            log_frame,
            height=8,
            wrap="word",
            state="disabled",
            font=("Consolas", 9),
        )
        self._log_widget.pack(fill="both", expand=True)

    def _refresh_songs(self, select_path: Path | None = None) -> None:
        current = select_path
        if current is None:
            selected = self._selected_song()
            current = None if selected is None else selected.path
        try:
            songs = list_songs()
        except Exception as error:
            self._messagebox.showerror("无法读取曲库", str(error), parent=self._root)
            return

        for item_id in self._song_tree.get_children():
            self._song_tree.delete(item_id)
        self._song_by_id.clear()
        selected_id: str | None = None
        for index, song in enumerate(songs):
            item_id = f"song-{index}"
            self._song_by_id[item_id] = song
            self._song_tree.insert(
                "",
                "end",
                iid=item_id,
                text=song.display_name,
                values=(
                    song.source.value,
                    f"{song.bpm:g}",
                    f"{song.duration_seconds:.1f} 秒",
                ),
            )
            if current is not None and song.path == current:
                selected_id = item_id
        if selected_id is None and songs:
            selected_id = "song-0"
        if selected_id is not None:
            self._song_tree.selection_set(selected_id)
            self._song_tree.focus(selected_id)
            self._song_tree.see(selected_id)
            self._show_song_details()
        else:
            self._details_var.set("曲库中还没有曲目")

    def _selected_song(self) -> SongSummary | None:
        selection = self._song_tree.selection()
        return self._song_by_id.get(selection[0]) if selection else None

    def _show_song_details(self, _event: object | None = None) -> None:
        song = self._selected_song()
        if song is None:
            self._details_var.set("尚未选择曲目")
            return
        title = song.title or "（未设置标题）"
        self._details_var.set(
            f"标题：{title}\n"
            f"文件：{song.path.name}　来源：{song.source.value}\n"
            f"BPM：{song.bpm:g}　事件：{song.event_count}　"
            f"时长：{song.duration_seconds:.3f} 秒"
        )

    def _import_score(self) -> None:
        filename = self._filedialog.askopenfilename(
            parent=self._root,
            title="导入文本曲谱",
            filetypes=(
                ("口琴曲谱", "*.song *.txt"),
                ("所有文件", "*.*"),
            ),
        )
        if not filename:
            return
        try:
            imported = import_song(Path(filename))
        except Exception as error:
            self._messagebox.showerror("导入失败", str(error), parent=self._root)
            self._append_log(f"曲谱导入失败：{error}")
            return
        self._finish_import(imported)

    def _import_midi(self) -> None:
        filename = self._filedialog.askopenfilename(
            parent=self._root,
            title="导入 MIDI",
            filetypes=(("MIDI 文件", "*.mid *.midi"), ("所有文件", "*.*")),
        )
        if not filename:
            return
        path = Path(filename)
        try:
            playable_tracks = [
                track for track in list_midi_tracks(path) if track.note_count > 0
            ]
            if not playable_tracks:
                raise MidiImportError("MIDI 文件中没有音符")
            track_index = playable_tracks[0].index
            if len(playable_tracks) > 1:
                choices = "\n".join(
                    f"{track.index}：{track.display_name}（{track.note_count} 个音符）"
                    for track in playable_tracks
                )
                selected = self._simpledialog.askinteger(
                    "选择 MIDI 轨道",
                    f"这个 MIDI 有多个可用轨道：\n\n{choices}\n\n请输入轨道编号：",
                    parent=self._root,
                    minvalue=0,
                    maxvalue=max(track.index for track in playable_tracks),
                )
                if selected is None:
                    return
                valid_indexes = {track.index for track in playable_tracks}
                if selected not in valid_indexes:
                    raise MidiImportError(f"MIDI 轨道 {selected} 中没有音符")
                track_index = selected
            imported = import_midi(path, track_index=track_index)
        except Exception as error:
            self._messagebox.showerror(
                "MIDI 导入失败", str(error), parent=self._root
            )
            self._append_log(f"MIDI 导入失败：{error}")
            return
        self._finish_import(imported)

    def _finish_import(self, imported: SongSummary) -> None:
        self._refresh_songs(imported.path)
        self._append_log(f"已导入：{imported.display_name}")
        self._messagebox.showinfo(
            "导入成功",
            f"已加入用户曲库：{imported.display_name}",
            parent=self._root,
        )

    def _apply_settings(self) -> None:
        try:
            settings = GuiSettings(
                start_key=self._start_key_var.get(),
                stop_key=self._stop_key_var.get(),
                pause_key=self._pause_key_var.get(),
                countdown_seconds=int(self._countdown_var.get()),
            )
        except (TypeError, ValueError) as error:
            self._messagebox.showerror(
                "设置无效", str(error), parent=self._root
            )
            return
        self._settings = settings
        try:
            save_gui_settings(settings)
        except OSError as error:
            self._messagebox.showwarning(
                "设置未保存",
                f"本次运行已应用，但无法保存到磁盘：{error}",
                parent=self._root,
            )
        self._restart_hotkeys()
        self._append_log("播放设置已应用")

    def _restart_hotkeys(self) -> None:
        if self._hotkey_monitor is not None:
            self._hotkey_monitor.stop()
            self._hotkey_monitor = None
        if sys.platform != "win32":
            self._hotkey_status_var.set("当前系统不支持 Windows 全局热键")
            return
        self._hotkey_status_var.set("正在注册全局热键……")
        self._hotkey_monitor = GlobalHotkeyMonitor(
            self._settings.bindings,
            self._events,
        )
        self._hotkey_monitor.start()

    def _start_from_button(self) -> None:
        if self._real_input_var.get():
            message = (
                f"真实输入已准备。请切换到目标窗口，再按 "
                f"{self._settings.start_key} 开始。"
            )
            self._playback_status_var.set(message)
            self._append_log(message)
            self._messagebox.showinfo("请使用开始热键", message, parent=self._root)
            return
        self._start_playback()

    def _start_playback(self) -> None:
        if self._controller is not None and self._controller.is_playing:
            self._append_log("播放正在进行，已忽略重复开始")
            return
        summary = self._selected_song()
        if summary is None:
            self._messagebox.showwarning(
                "没有曲目", "请先在左侧选择一首曲目。", parent=self._root
            )
            return
        real_input = bool(self._real_input_var.get())
        if real_input:
            if not self._administrator:
                self._messagebox.showerror(
                    "需要管理员权限",
                    "真实输入需要以管理员身份运行本程序。",
                    parent=self._root,
                )
                return
            if _foreground_window_is_this_process():
                self._playback_status_var.set(
                    f"请先切到目标窗口，再按 {self._settings.start_key}"
                )
                self._append_log("已阻止向播放器窗口发送真实输入")
                return
        try:
            song = load_song(summary.path)
        except Exception as error:
            self._messagebox.showerror("无法读取曲目", str(error), parent=self._root)
            return

        output = QueuePlaybackOutput(self._events, len(song.events))

        def output_factory() -> PlaybackOutput:
            if real_input:
                return WindowsInputOutput(
                    console=output,
                    notice=lambda message: self._events.put(
                        UiEvent("notice", message)
                    ),
                )
            return output

        controller = PreviewController(
            song,
            countdown_seconds=self._settings.countdown_seconds,
            output_factory=output_factory,
        )
        try:
            started = controller.start()
        except Exception as error:
            self._messagebox.showerror("无法开始播放", str(error), parent=self._root)
            self._append_log(f"无法开始播放：{error}")
            return
        if not started:
            return
        self._controller = controller
        self._progress_var.set(0)
        mode = "真实输入" if real_input else "安全预演"
        self._playback_status_var.set(f"{mode}：{summary.display_name}")
        self._append_log(f"开始{mode}：{summary.display_name}")

    def _toggle_pause(self) -> None:
        if self._controller is None:
            result = PauseToggleResult.NOT_PLAYING
        else:
            result = self._controller.toggle_pause()
        if result is PauseToggleResult.NOT_PLAYING:
            self._append_log("当前没有可以暂停的播放")

    def _stop_playback(self) -> None:
        if self._controller is not None and self._controller.stop():
            self._append_log("正在停止播放……")
        else:
            self._append_log("当前没有正在进行的播放")

    def _poll_events(self) -> None:
        if self._closing:
            return
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            self._handle_event(event)
        self._root.after(50, self._poll_events)

    def _handle_event(self, event: UiEvent) -> None:
        if event.kind == "hotkey":
            if event.data is Hotkey.START:
                self._start_playback()
            elif event.data is Hotkey.STOP:
                self._stop_playback()
            elif event.data is Hotkey.PAUSE_TOGGLE:
                self._toggle_pause()
        elif event.kind == "hotkeys_ready":
            bindings = event.data
            assert isinstance(bindings, HotkeyBindings)
            self._hotkey_status_var.set(
                f"全局热键：{bindings.start} 开始，{bindings.stop} 停止，"
                f"{bindings.pause} 暂停 / 继续"
            )
            self._append_log("全局热键注册成功")
        elif event.kind == "hotkeys_failed":
            self._hotkey_status_var.set(f"全局热键不可用：{event.message}")
            self._append_log(f"全局热键注册失败：{event.message}")
        elif event.kind == "countdown":
            self._playback_status_var.set(f"倒计时：{event.message}")
        elif event.kind == "event_started":
            percentage = (
                (event.index - 1) / event.total * 100 if event.total else 0
            )
            self._progress_var.set(percentage)
            self._playback_status_var.set(
                f"{event.index}/{event.total}　{event.message}"
            )
            self._append_log(f"{event.index}/{event.total} {event.message}")
        elif event.kind == "event_finished":
            if event.total:
                self._progress_var.set(event.index / event.total * 100)
        elif event.kind == "paused":
            self._playback_status_var.set(event.message)
            self._append_log(event.message)
        elif event.kind == "resumed":
            self._playback_status_var.set(event.message)
            self._append_log(event.message)
        elif event.kind == "finished":
            if event.data is PlaybackResult.COMPLETED:
                self._progress_var.set(100)
                message = "播放完成"
            else:
                message = "播放已停止"
            self._playback_status_var.set(message)
            self._append_log(message)
        elif event.kind == "failed":
            self._playback_status_var.set(f"播放失败：{event.message}")
            self._append_log(f"播放失败：{event.message}")
        elif event.kind == "notice":
            self._playback_status_var.set(event.message)
            self._append_log(event.message)

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log_widget.configure(state="normal")
        self._log_widget.insert("end", f"[{timestamp}] {message}\n")
        self._log_widget.see("end")
        self._log_widget.configure(state="disabled")

    def _close(self) -> None:
        self._closing = True
        if self._hotkey_monitor is not None:
            self._hotkey_monitor.stop()
        if self._controller is not None:
            self._controller.stop()
            self._controller.join(1)
        self._root.destroy()


def _foreground_window_is_this_process() -> bool:
    if sys.platform != "win32":
        return False
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.argtypes = ()
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    )
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    window = user32.GetForegroundWindow()
    if not window:
        return False
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
    return process_id.value == os.getpid()


def run_gui() -> int:
    """Open the desktop interface and block until its main window closes."""

    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, simpledialog, ttk
        from tkinter.scrolledtext import ScrolledText
    except ImportError as error:
        raise RuntimeError("当前 Python 环境没有安装 tkinter，无法打开桌面界面") from error

    try:
        root = tk.Tk()
    except tk.TclError as error:
        raise RuntimeError(f"无法打开桌面界面：{error}") from error
    HarmonicaPlayerApp(
        root,
        tk=tk,
        ttk=ttk,
        filedialog=filedialog,
        messagebox=messagebox,
        simpledialog=simpledialog,
        scrolled_text=ScrolledText,
    )
    root.mainloop()
    return 0
