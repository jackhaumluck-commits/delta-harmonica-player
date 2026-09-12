"""Persistent settings used by the desktop interface."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .hotkeys import HotkeyBindings
from .runtime_paths import user_data_directory


@dataclass(frozen=True, slots=True)
class GuiSettings:
    """Normal GUI preferences that are safe to restore on the next launch."""

    start_key: str = "F8"
    stop_key: str = "F9"
    pause_key: str = "F10"
    countdown_seconds: int = 3

    def __post_init__(self) -> None:
        bindings = HotkeyBindings(
            start=self.start_key,
            stop=self.stop_key,
            pause=self.pause_key,
        )
        if (
            isinstance(self.countdown_seconds, bool)
            or not isinstance(self.countdown_seconds, int)
            or not 0 <= self.countdown_seconds <= 30
        ):
            raise ValueError("倒计时必须是 0 到 30 之间的整数")
        object.__setattr__(self, "start_key", bindings.start)
        object.__setattr__(self, "stop_key", bindings.stop)
        object.__setattr__(self, "pause_key", bindings.pause)

    @property
    def bindings(self) -> HotkeyBindings:
        return HotkeyBindings(
            start=self.start_key,
            stop=self.stop_key,
            pause=self.pause_key,
        )


def default_settings_path() -> Path:
    """Return a per-user path instead of storing preferences in the repository."""

    return user_data_directory() / "settings.json"


def load_gui_settings(path: Path | None = None) -> GuiSettings:
    """Load settings, falling back to defaults for missing or invalid files."""

    settings_path = path or default_settings_path()
    try:
        raw = json.loads(settings_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("设置文件必须包含 JSON 对象")
        return GuiSettings(
            start_key=raw.get("start_key", "F8"),
            stop_key=raw.get("stop_key", "F9"),
            pause_key=raw.get("pause_key", "F10"),
            countdown_seconds=raw.get("countdown_seconds", 3),
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        AttributeError,
        TypeError,
        ValueError,
    ):
        return GuiSettings()


def save_gui_settings(
    settings: GuiSettings, path: Path | None = None
) -> Path:
    """Atomically save normal preferences; real-input consent is never stored."""

    settings_path = path or default_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = settings_path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(settings_path)
    return settings_path
