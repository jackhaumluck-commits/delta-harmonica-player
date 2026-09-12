import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from harmonica_player.runtime_paths import (
    bundled_song_directory,
    resource_root,
    user_data_directory,
    user_song_directory,
)


class RuntimePathTests(unittest.TestCase):
    def test_uses_local_application_data_for_user_files(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            environment = {"LOCALAPPDATA": temporary_directory}

            self.assertEqual(
                user_data_directory(environment),
                Path(temporary_directory) / "DeltaHarmonicaPlayer",
            )
            self.assertEqual(
                user_song_directory(environment),
                Path(temporary_directory)
                / "DeltaHarmonicaPlayer"
                / "songs",
            )

    def test_uses_pyinstaller_resource_root_when_frozen(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            with patch.object(
                sys, "_MEIPASS", temporary_directory, create=True
            ):
                self.assertEqual(resource_root(), Path(temporary_directory))
                self.assertEqual(
                    bundled_song_directory(),
                    Path(temporary_directory) / "examples",
                )

    def test_falls_back_when_local_application_data_is_unavailable(self) -> None:
        self.assertEqual(
            user_data_directory({}),
            Path.home() / ".config" / "DeltaHarmonicaPlayer",
        )


if __name__ == "__main__":
    unittest.main()
