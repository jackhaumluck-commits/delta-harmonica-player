import unittest
from unittest.mock import patch

from harmonica_player.hotkeys import (
    HotkeyBindings,
    HotkeyRegistrationError,
    normalize_function_key,
    run_hotkey_preview,
)
from harmonica_player.song import NoteEvent, Song


class RealInputAdministratorTests(unittest.TestCase):
    def test_real_input_requires_administrator_privileges(self) -> None:
        song = Song(bpm=120, events=(NoteEvent("1", 1, "normal"),))

        with patch("harmonica_player.hotkeys.sys.platform", "win32"), patch(
            "harmonica_player.windows_input.is_running_as_administrator",
            return_value=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "需要管理员权限"):
                run_hotkey_preview(song, real_input=True)


class HotkeyBindingsTests(unittest.TestCase):
    def test_normalizes_function_key_names(self) -> None:
        bindings = HotkeyBindings(start="f5", stop="F06", pause="f24")

        self.assertEqual(bindings, HotkeyBindings("F5", "F6", "F24"))
        self.assertEqual(bindings.virtual_key("F5"), 0x74)

    def test_rejects_keys_outside_f1_to_f24(self) -> None:
        for value in ("A", "F0", "F25"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "F1 到 F24"):
                    normalize_function_key(value)

    def test_rejects_duplicate_bindings(self) -> None:
        with self.assertRaisesRegex(ValueError, "必须互不相同"):
            HotkeyBindings(start="F8", stop="f08", pause="F10")

    def test_registration_error_identifies_the_busy_key(self) -> None:
        error = HotkeyRegistrationError("F8", 1409)

        self.assertIn("F8", str(error))
        self.assertIn("1409", str(error))


if __name__ == "__main__":
    unittest.main()
