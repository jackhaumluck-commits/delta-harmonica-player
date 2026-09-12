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

from . import __version__
from .hotkeys import Hotkey, HotkeyBindings, WindowsHotkeyListener
from .library import SongSummary, import_song, list_songs
from .midi_import import (
    MidiImportError,
    import_midi_with_details,
    list_midi_tracks,
)
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


_COLORS = {
    "background": "#0B1017",
    "surface": "#121A24",
    "surface_high": "#182332",
    "border": "#263447",
    "text": "#F4F7FB",
    "muted": "#92A3B7",
    "accent": "#41D69A",
    "accent_hover": "#62E5B1",
    "accent_dark": "#123D33",
    "danger": "#F06C75",
    "danger_hover": "#FF8790",
    "danger_dark": "#412128",
    "warning": "#F2C66D",
}


_TUTORIAL_SECTIONS = (
    (
        "1. 导入文本曲谱",
        "点击“导入曲谱”，选择 UTF-8 编码的 .song 或 .txt 文件。"
        "曲谱会先经过格式检查，成功后自动加入左侧曲库。",
    ),
    (
        "2. 导入 MIDI",
        "点击“导入 MIDI”，选择 .mid 或 .midi 文件。"
        "如果文件包含多个可演奏轨道，程序会请你选择其中一个；"
        "相近起奏的和弦音会合并成一组并保留每组最高音，"
        "过低的伴奏音和音域外音符会移动到更合适的八度。"
        "过密音符会自动精简，并为按键松开留出短暂空隙。",
    ),
    (
        "3. 选择模式并开始",
        "先在曲库中选择歌曲。安全预演可以直接点击“开始播放”；"
        "真实输入需要管理员权限，请切换到游戏的口琴界面后按开始热键。",
    ),
    (
        "4. 播放快捷键",
        "默认使用 F8 开始、F9 停止、F10 暂停或继续。"
        "快捷键和开始前倒计时可以在主界面中修改。",
    ),
)


def _song_kind_label(song: SongSummary) -> str:
    """Return the compact source label shown beneath a library title."""

    if "midi" in song.name.casefold():
        return "MIDI 导入"
    if song.name == "twinkle_twinkle":
        return "内置示例曲"
    if song.name == "modifier_exercise":
        return "内置练习曲"
    return f"{song.source.value}曲谱"


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
        self._tutorial_window: Any | None = None
        self._log_messages: list[str] = []
        self._closing = False
        self._settings = load_gui_settings()
        self._administrator = is_running_as_administrator()

        self._build_window()
        self._refresh_songs()
        self._restart_hotkeys()
        self._root.protocol("WM_DELETE_WINDOW", self._close)
        self._root.after(50, self._poll_events)

    def _configure_styles(self) -> None:
        style = self._ttk.Style(self._root)
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 10))
        style.configure("App.TFrame", background=_COLORS["background"])
        style.configure("Card.TFrame", background=_COLORS["surface"])
        style.configure(
            "CardTitle.TLabel",
            background=_COLORS["surface"],
            foreground=_COLORS["text"],
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        style.configure(
            "Muted.TLabel",
            background=_COLORS["surface"],
            foreground=_COLORS["muted"],
        )
        style.configure(
            "Hero.TLabel",
            background=_COLORS["surface"],
            foreground=_COLORS["text"],
            font=("Microsoft YaHei UI", 32, "bold"),
        )
        style.configure(
            "Event.TLabel",
            background=_COLORS["surface"],
            foreground=_COLORS["text"],
            font=("Microsoft YaHei UI", 22, "bold"),
        )
        style.configure(
            "Accent.TButton",
            background=_COLORS["accent"],
            foreground="#07130F",
            borderwidth=0,
            padding=(18, 15),
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("active", _COLORS["accent_hover"])],
        )
        style.configure(
            "Secondary.TButton",
            background=_COLORS["surface_high"],
            foreground=_COLORS["text"],
            bordercolor=_COLORS["border"],
            padding=(14, 12),
        )
        style.map(
            "Secondary.TButton",
            background=[("active", _COLORS["border"])],
        )
        style.configure(
            "Danger.TButton",
            background=_COLORS["danger"],
            foreground="#FFFFFF",
            borderwidth=0,
            padding=(14, 12),
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        style.map(
            "Danger.TButton",
            background=[("active", _COLORS["danger_hover"])],
            foreground=[("active", "#FFFFFF")],
        )
        style.configure(
            "Library.Treeview",
            background=_COLORS["surface"],
            fieldbackground=_COLORS["surface"],
            foreground=_COLORS["text"],
            borderwidth=0,
            rowheight=54,
        )
        style.map(
            "Library.Treeview",
            background=[("selected", _COLORS["accent_dark"])],
            foreground=[("selected", _COLORS["accent_hover"])],
        )
        style.configure(
            "Library.Treeview.Heading",
            background=_COLORS["surface_high"],
            foreground=_COLORS["muted"],
            borderwidth=0,
            padding=(6, 8),
        )
        style.map(
            "Library.Treeview.Heading",
            background=[("active", _COLORS["surface_high"])],
        )
        style.configure(
            "Dark.TCombobox",
            fieldbackground=_COLORS["surface_high"],
            background=_COLORS["surface_high"],
            foreground=_COLORS["text"],
            arrowcolor=_COLORS["muted"],
            bordercolor=_COLORS["border"],
            padding=6,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", _COLORS["surface_high"])],
            foreground=[("readonly", _COLORS["text"])],
        )
        style.configure(
            "Dark.TSpinbox",
            fieldbackground=_COLORS["surface_high"],
            background=_COLORS["surface_high"],
            foreground=_COLORS["text"],
            arrowcolor=_COLORS["muted"],
            bordercolor=_COLORS["border"],
            padding=6,
        )
        style.configure(
            "Mode.TRadiobutton",
            background=_COLORS["surface"],
            foreground=_COLORS["text"],
            indicatorcolor=_COLORS["surface_high"],
            padding=(0, 4),
        )
        style.map(
            "Mode.TRadiobutton",
            indicatorcolor=[("selected", _COLORS["accent"])],
            background=[("active", _COLORS["surface"])],
            foreground=[("disabled", _COLORS["muted"])],
        )
        style.configure(
            "Player.Horizontal.TProgressbar",
            background=_COLORS["accent"],
            troughcolor=_COLORS["surface_high"],
            borderwidth=0,
            thickness=9,
        )

    def _build_window(self) -> None:
        root = self._root
        ttk = self._ttk
        tk = self._tk
        self._configure_styles()

        version_label = f"v{__version__.split('.dev', 1)[0]}"
        if ".dev" in __version__:
            version_label += " 开发版"
        root.title(f"口琴自动演奏器 {version_label}")
        root.geometry("1180x840")
        root.minsize(1000, 740)
        root.configure(background=_COLORS["background"])
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        header = ttk.Frame(root, style="App.TFrame", padding=(24, 17, 24, 13))
        header.grid(row=0, column=0, sticky="ew")
        brand = ttk.Frame(header, style="App.TFrame")
        brand.pack(side="left")
        tk.Label(
            brand,
            text="口琴自动演奏器",
            background=_COLORS["background"],
            foreground=_COLORS["text"],
            font=("Microsoft YaHei UI", 19, "bold"),
        ).pack(anchor="w")
        tk.Label(
            brand,
            text="三角洲行动 · 游戏内口琴演奏工具",
            background=_COLORS["background"],
            foreground=_COLORS["muted"],
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(2, 0))
        status_area = ttk.Frame(header, style="App.TFrame")
        status_area.pack(side="right")
        tk.Label(
            status_area,
            text=version_label,
            background=_COLORS["surface_high"],
            foreground=_COLORS["muted"],
            padx=10,
            pady=5,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 10))
        administrator_text = (
            "管理员权限：已开启"
            if self._administrator
            else "管理员权限：未开启"
        )
        administrator_color = (
            _COLORS["accent"] if self._administrator else _COLORS["warning"]
        )
        tk.Label(
            status_area,
            text=administrator_text,
            background=_COLORS["surface"],
            foreground=administrator_color,
            padx=12,
            pady=5,
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(side="left")

        main = ttk.Frame(root, style="App.TFrame", padding=(24, 0, 24, 22))
        main.grid(row=1, column=0, sticky="nsew")
        main.columnconfigure(0, minsize=310)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        library_frame = ttk.Frame(main, style="Card.TFrame", padding=18)
        library_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        library_frame.columnconfigure(0, weight=1)
        library_frame.rowconfigure(2, weight=1)
        library_header = ttk.Frame(library_frame, style="Card.TFrame")
        library_header.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            library_header, text="曲目库", style="CardTitle.TLabel"
        ).pack(side="left")
        self._song_count_var = tk.StringVar(value="0 首")
        ttk.Label(
            library_header,
            textvariable=self._song_count_var,
            style="Muted.TLabel",
        ).pack(side="right")
        ttk.Label(
            library_frame,
            text="选择一首曲目开始演奏",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 13))

        tree_area = ttk.Frame(library_frame, style="Card.TFrame")
        tree_area.grid(row=2, column=0, sticky="nsew")
        tree_area.columnconfigure(0, weight=1)
        tree_area.rowconfigure(0, weight=1)
        self._song_tree = ttk.Treeview(
            tree_area,
            columns=(),
            show="tree",
            selectmode="browse",
            style="Library.Treeview",
        )
        self._song_tree.column("#0", width=255, minwidth=190)
        scrollbar = ttk.Scrollbar(
            tree_area, orient="vertical", command=self._song_tree.yview
        )
        self._song_tree.configure(yscrollcommand=scrollbar.set)
        self._song_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._song_tree.bind("<<TreeviewSelect>>", self._show_song_details)

        import_buttons = ttk.Frame(library_frame, style="Card.TFrame")
        import_buttons.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        import_buttons.columnconfigure((0, 1), weight=1)
        ttk.Button(
            import_buttons,
            text="导入曲谱",
            command=self._import_score,
            style="Secondary.TButton",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(
            import_buttons,
            text="导入和使用教程",
            command=self._show_tutorial,
            style="Secondary.TButton",
        ).grid(row=0, column=1, sticky="ew", padx=(5, 0))
        ttk.Button(
            import_buttons,
            text="导入 MIDI",
            command=self._import_midi,
            style="Secondary.TButton",
        ).grid(row=1, column=0, sticky="ew", padx=(0, 5), pady=(9, 0))
        ttk.Button(
            import_buttons,
            text="刷新曲库",
            command=self._refresh_songs,
            style="Secondary.TButton",
        ).grid(row=1, column=1, sticky="ew", padx=(5, 0), pady=(9, 0))
        ttk.Label(
            library_frame,
            text="用于游戏内口琴演奏",
            style="Muted.TLabel",
        ).grid(row=4, column=0, sticky="w", pady=(18, 0))

        control_frame = ttk.Frame(main, style="App.TFrame")
        control_frame.grid(row=0, column=1, sticky="nsew")
        control_frame.columnconfigure(0, weight=1)
        control_frame.rowconfigure(4, weight=1)

        details = ttk.Frame(control_frame, style="Card.TFrame", padding=18)
        details.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            details, text="当前曲目", style="Muted.TLabel"
        ).pack(anchor="center")
        self._song_title_var = tk.StringVar(value="尚未选择曲目")
        ttk.Label(
            details,
            textvariable=self._song_title_var,
            style="Hero.TLabel",
        ).pack(anchor="center", pady=(4, 8))
        self._song_meta_var = tk.StringVar(value="从左侧曲目库中选择")
        ttk.Label(
            details,
            textvariable=self._song_meta_var,
            style="Muted.TLabel",
        ).pack(anchor="center")
        self._song_file_var = tk.StringVar(value="")
        ttk.Label(
            details,
            textvariable=self._song_file_var,
            style="Muted.TLabel",
        ).pack(anchor="center", pady=(3, 0))

        middle = ttk.Frame(control_frame, style="App.TFrame")
        middle.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        middle.columnconfigure(0, weight=2)
        middle.columnconfigure(1, weight=3)

        settings_frame = ttk.Frame(middle, style="Card.TFrame", padding=16)
        settings_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ttk.Label(
            settings_frame, text="快捷控制", style="CardTitle.TLabel"
        ).grid(row=0, column=0, columnspan=5, sticky="w")
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
            ("暂停", self._pause_key_var),
        )
        for column, (label, variable) in enumerate(variables):
            ttk.Label(
                settings_frame, text=label, style="Muted.TLabel"
            ).grid(row=1, column=column, sticky="w", pady=(10, 4))
            ttk.Combobox(
                settings_frame,
                values=keys,
                textvariable=variable,
                width=6,
                state="readonly",
                style="Dark.TCombobox",
            ).grid(row=2, column=column, sticky="ew", padx=(0, 7))
            settings_frame.columnconfigure(column, weight=1)
        ttk.Label(
            settings_frame, text="倒计时", style="Muted.TLabel"
        ).grid(row=1, column=3, sticky="w", pady=(10, 4))
        ttk.Spinbox(
            settings_frame,
            from_=0,
            to=30,
            width=6,
            textvariable=self._countdown_var,
            style="Dark.TSpinbox",
        ).grid(row=2, column=3, sticky="ew", padx=(0, 7))
        ttk.Button(
            settings_frame,
            text="应用",
            command=self._apply_settings,
            style="Secondary.TButton",
        ).grid(row=2, column=4, sticky="ew")
        self._hotkey_status_var = tk.StringVar(value="正在注册全局热键……")
        ttk.Label(
            settings_frame,
            textvariable=self._hotkey_status_var,
            style="Muted.TLabel",
            wraplength=470,
        ).grid(row=3, column=0, columnspan=5, sticky="w", pady=(9, 0))

        mode_frame = ttk.Frame(middle, style="Card.TFrame", padding=16)
        mode_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ttk.Label(
            mode_frame, text="输出模式", style="CardTitle.TLabel"
        ).pack(anchor="w")
        self._real_input_var = tk.BooleanVar(value=False)
        ttk.Radiobutton(
            mode_frame,
            text="安全预演",
            variable=self._real_input_var,
            value=False,
            style="Mode.TRadiobutton",
        ).pack(anchor="w", pady=(8, 0))
        self._real_mode_button = ttk.Radiobutton(
            mode_frame,
            text="Windows 真实输入",
            variable=self._real_input_var,
            value=True,
            style="Mode.TRadiobutton",
        )
        self._real_mode_button.pack(anchor="w")
        if sys.platform != "win32" or not self._administrator:
            self._real_mode_button.configure(state="disabled")
        mode_note = (
            "已取得管理员权限"
            if self._administrator
            else "需以管理员身份重新启动"
        )
        ttk.Label(
            mode_frame,
            text=mode_note,
            style="Muted.TLabel",
            wraplength=220,
        ).pack(anchor="w", pady=(7, 0))

        progress_frame = ttk.Frame(
            control_frame, style="Card.TFrame", padding=18
        )
        progress_frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        progress_header = ttk.Frame(progress_frame, style="Card.TFrame")
        progress_header.pack(fill="x")
        self._playback_status_var = tk.StringVar(value="准备就绪")
        ttk.Label(
            progress_header,
            textvariable=self._playback_status_var,
            style="CardTitle.TLabel",
        ).pack(side="left")
        self._progress_text_var = tk.StringVar(value="0%")
        tk.Label(
            progress_header,
            textvariable=self._progress_text_var,
            background=_COLORS["surface"],
            foreground=_COLORS["accent"],
            font=("Segoe UI", 15, "bold"),
        ).pack(side="right")
        self._progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(
            progress_frame,
            variable=self._progress_var,
            maximum=100,
            style="Player.Horizontal.TProgressbar",
        ).pack(fill="x", pady=(11, 12))
        event_summary = ttk.Frame(progress_frame, style="Card.TFrame")
        event_summary.pack(fill="x", pady=(0, 14))
        self._current_event_var = tk.StringVar(value="尚未开始")
        ttk.Label(
            event_summary,
            text="当前音符 / 动作",
            style="Muted.TLabel",
        ).pack(anchor="center")
        ttk.Label(
            event_summary,
            textvariable=self._current_event_var,
            style="Event.TLabel",
        ).pack(anchor="center", pady=(2, 1))
        self._event_counter_var = tk.StringVar(value="事件 0 / 0")
        ttk.Label(
            event_summary,
            textvariable=self._event_counter_var,
            style="Muted.TLabel",
        ).pack(anchor="center")
        buttons = ttk.Frame(progress_frame, style="Card.TFrame")
        buttons.pack(fill="x")
        buttons.columnconfigure((0, 1, 2), weight=1)
        ttk.Button(
            buttons,
            text="开始播放",
            command=self._start_from_button,
            style="Accent.TButton",
        ).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            buttons,
            text="暂停 / 继续",
            command=self._toggle_pause,
            style="Secondary.TButton",
        ).grid(row=0, column=1, sticky="ew", padx=9)
        ttk.Button(
            buttons,
            text="停止",
            command=self._stop_playback,
            style="Danger.TButton",
        ).grid(row=0, column=2, sticky="ew")

        ttk.Label(
            control_frame,
            text="真实输入时：切换到目标窗口后按开始热键，切换窗口会自动停止。",
            style="Muted.TLabel",
        ).grid(row=3, column=0, sticky="w", pady=(9, 0))

        status_strip = ttk.Frame(control_frame, style="Card.TFrame", padding=12)
        status_strip.grid(row=4, column=0, sticky="sew", pady=(12, 0))
        status_strip.columnconfigure(1, weight=1)
        ttk.Label(
            status_strip,
            text="状态",
            style="CardTitle.TLabel",
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))
        self._last_log_var = tk.StringVar(value="准备就绪")
        ttk.Label(
            status_strip,
            textvariable=self._last_log_var,
            style="Muted.TLabel",
        ).grid(row=0, column=1, sticky="w")

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

        self._song_count_var.set(f"{len(songs)} 首")
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
                text=f"{song.display_name}\n{_song_kind_label(song)}",
            )
            if current is not None and song.path == current:
                selected_id = item_id
        if selected_id is None and songs:
            selected_id = next(
                (
                    item_id
                    for item_id, song in self._song_by_id.items()
                    if song.name == "twinkle_twinkle"
                ),
                "song-0",
            )
        if selected_id is not None:
            self._song_tree.selection_set(selected_id)
            self._song_tree.focus(selected_id)
            self._song_tree.see(selected_id)
            self._show_song_details()
        else:
            self._song_title_var.set("曲库中还没有曲目")
            self._song_meta_var.set("请使用左侧按钮导入曲谱或 MIDI")
            self._song_file_var.set("")

    def _selected_song(self) -> SongSummary | None:
        selection = self._song_tree.selection()
        return self._song_by_id.get(selection[0]) if selection else None

    def _show_song_details(self, _event: object | None = None) -> None:
        song = self._selected_song()
        if song is None:
            self._song_title_var.set("尚未选择曲目")
            self._song_meta_var.set("从左侧曲目库中选择")
            self._song_file_var.set("")
            return
        self._song_title_var.set(song.display_name)
        self._song_meta_var.set(
            f"BPM  {song.bpm:g}　·　{song.event_count} 个事件　·　"
            f"时长：{song.duration_seconds:.3f} 秒"
        )
        self._song_file_var.set(
            f"{song.source.value}曲目　/　{song.path.name}"
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
            result = import_midi_with_details(path, track_index=track_index)
        except Exception as error:
            self._messagebox.showerror(
                "MIDI 导入失败", str(error), parent=self._root
            )
            self._append_log(f"MIDI 导入失败：{error}")
            return
        details: list[str] = []
        if result.conversion.polyphony_detected:
            details.append(
                "检测到和弦，已按相近起奏时间分组并保留每组最高音。"
            )
        if result.conversion.octave_folding_detected:
            details.append(
                "检测到音域外音符，已按音名移动到最近的可演奏八度。"
            )
        if result.conversion.low_register_adjustment_detected:
            details.append(
                "已将多声部中的部分过低伴奏音上移八度，以突出主旋律。"
            )
        if result.conversion.timing_adjustment_detected:
            details.append(
                "已限制相邻音至少间隔 0.10 秒，并预留 0.02 秒松键空隙。"
            )
        self._finish_import(
            result.summary,
            detail="\n".join(details) if details else None,
        )

    def _show_tutorial(self) -> None:
        """Open a concise guide for importing songs and starting playback."""

        if (
            self._tutorial_window is not None
            and self._tutorial_window.winfo_exists()
        ):
            self._tutorial_window.lift()
            self._tutorial_window.focus_force()
            return

        tk = self._tk
        ttk = self._ttk
        window = tk.Toplevel(self._root)
        self._tutorial_window = window
        window.title("导入和使用教程")
        window.geometry("660x590")
        window.minsize(620, 540)
        window.configure(background=_COLORS["background"])
        window.transient(self._root)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)

        container = ttk.Frame(window, style="Card.TFrame", padding=24)
        container.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        container.columnconfigure(0, weight=1)

        ttk.Label(
            container,
            text="导入和使用教程",
            style="Hero.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            container,
            text="按照下面的顺序，即可把曲目加入曲库并开始演奏。",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 16))

        for index, (title, description) in enumerate(_TUTORIAL_SECTIONS):
            row = 2 + index * 2
            ttk.Label(
                container,
                text=title,
                style="CardTitle.TLabel",
            ).grid(row=row, column=0, sticky="w", pady=(0 if index == 0 else 12, 3))
            ttk.Label(
                container,
                text=description,
                style="Muted.TLabel",
                wraplength=570,
                justify="left",
            ).grid(row=row + 1, column=0, sticky="ew")

        note = tk.Label(
            container,
            text=(
                "真实输入提示：程序必须以管理员身份运行。按 F8 前先切换到"
                "三角洲行动的口琴演奏界面；切换到其他窗口会自动停止。"
            ),
            background=_COLORS["accent_dark"],
            foreground=_COLORS["accent_hover"],
            font=("Microsoft YaHei UI", 9),
            justify="left",
            wraplength=550,
            padx=14,
            pady=11,
        )
        note.grid(row=10, column=0, sticky="ew", pady=(18, 14))

        def close_tutorial() -> None:
            window.destroy()
            self._tutorial_window = None

        ttk.Button(
            container,
            text="知道了",
            command=close_tutorial,
            style="Accent.TButton",
        ).grid(row=11, column=0, sticky="e")
        window.protocol("WM_DELETE_WINDOW", close_tutorial)
        window.grab_set()
        window.focus_force()

    def _finish_import(
        self, imported: SongSummary, *, detail: str | None = None
    ) -> None:
        self._refresh_songs(imported.path)
        self._append_log(f"已导入：{imported.display_name}")
        message = f"已加入用户曲库：{imported.display_name}"
        if detail is not None:
            self._append_log(detail)
            message += f"\n\n{detail}"
        self._messagebox.showinfo(
            "导入成功",
            message,
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
        self._progress_text_var.set("0%")
        self._current_event_var.set("等待开始")
        self._event_counter_var.set(f"事件 0 / {len(song.events)}")
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
            self._progress_text_var.set(f"{percentage:.0f}%")
            self._current_event_var.set(event.message)
            self._event_counter_var.set(
                f"事件 {event.index} / {event.total}"
            )
            self._playback_status_var.set(
                f"{event.index}/{event.total}　{event.message}"
            )
            self._append_log(f"{event.index}/{event.total} {event.message}")
        elif event.kind == "event_finished":
            if event.total:
                percentage = event.index / event.total * 100
                self._progress_var.set(percentage)
                self._progress_text_var.set(f"{percentage:.0f}%")
        elif event.kind == "paused":
            self._playback_status_var.set(event.message)
            self._append_log(event.message)
        elif event.kind == "resumed":
            self._playback_status_var.set(event.message)
            self._append_log(event.message)
        elif event.kind == "finished":
            if event.data is PlaybackResult.COMPLETED:
                self._progress_var.set(100)
                self._progress_text_var.set("100%")
                message = "播放完成"
            else:
                message = "播放已停止"
            self._current_event_var.set(message)
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
        entry = f"[{timestamp}] {message}"
        self._log_messages.append(entry)
        if len(self._log_messages) > 200:
            del self._log_messages[:-200]
        self._last_log_var.set(entry)

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

