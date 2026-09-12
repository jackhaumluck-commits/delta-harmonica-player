import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from harmonica_player.settings import (
    GuiSettings,
    default_settings_path,
    load_gui_settings,
    save_gui_settings,
)


class GuiSettingsTests(unittest.TestCase):
    def test_round_trips_normal_preferences(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.json"
            settings = GuiSettings("f5", "F6", "f7", 8)

            saved_path = save_gui_settings(settings, path)

            self.assertEqual(saved_path, path)
            self.assertEqual(load_gui_settings(path), settings)

    def test_real_input_consent_is_not_loaded_or_saved(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.json"
            path.write_text(
                json.dumps({"start_key": "F8", "real_input": True}),
                encoding="utf-8",
            )

            settings = load_gui_settings(path)
            save_gui_settings(settings, path)

            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("real_input", saved)

    def test_invalid_file_falls_back_to_safe_defaults(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.json"
            path.write_text('{"start_key": "F99"}', encoding="utf-8")

            self.assertEqual(load_gui_settings(path), GuiSettings())

            path.write_text('{"start_key": null}', encoding="utf-8")
            self.assertEqual(load_gui_settings(path), GuiSettings())

    def test_rejects_invalid_countdown(self) -> None:
        for value in (-1, 31, True):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "0 到 30"):
                    GuiSettings(countdown_seconds=value)  # type: ignore[arg-type]

    def test_default_path_uses_local_application_data(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            with patch.dict(
                os.environ, {"LOCALAPPDATA": temporary_directory}
            ):
                self.assertEqual(
                    default_settings_path(),
                    Path(temporary_directory)
                    / "DeltaHarmonicaPlayer"
                    / "settings.json",
                )


if __name__ == "__main__":
    unittest.main()
