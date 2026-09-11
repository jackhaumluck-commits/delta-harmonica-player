import unittest
from unittest.mock import patch

from harmonica_player.hotkeys import run_hotkey_preview
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


if __name__ == "__main__":
    unittest.main()
