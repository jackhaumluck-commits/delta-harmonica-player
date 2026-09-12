"""Resolve packaged resources and per-user application data paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping


APPLICATION_DIRECTORY_NAME = "DeltaHarmonicaPlayer"
PROJECT_DIRECTORY = Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    """Return the source root or the temporary root created by PyInstaller."""

    frozen_root = getattr(sys, "_MEIPASS", None)
    return Path(frozen_root) if frozen_root is not None else PROJECT_DIRECTORY


def bundled_song_directory() -> Path:
    """Return the directory containing the bundled example scores."""

    return resource_root() / "examples"


def user_data_directory(
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Return a stable application data directory for the current user."""

    variables = os.environ if environment is None else environment
    local_app_data = variables.get("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / ".config"
    return root / APPLICATION_DIRECTORY_NAME


def user_song_directory(
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Return the directory used for imported user scores."""

    return user_data_directory(environment) / "songs"


def legacy_user_song_directory() -> Path:
    """Return the pre-v1.0 user-library directory for migration."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "songs"
    return PROJECT_DIRECTORY / "songs"
