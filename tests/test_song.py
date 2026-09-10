import unittest

from harmonica_player.song import SongFormatError, parse_song


class ParseSongTests(unittest.TestCase):
    def test_parses_notes_modifiers_and_rest(self) -> None:
        song = parse_song(
            """
            # comment
            bpm 120
            1 1 normal
            5 0.5 down
            3 2 semitone
            8 1 up
            0 0.5 rest
            """
        )

        self.assertEqual(song.bpm, 120)
        self.assertEqual(len(song.events), 5)
        self.assertEqual(song.events[0].key, "Z")
        self.assertEqual(song.events[1].mouse_button, "left")
        self.assertEqual(song.events[2].mouse_button, "middle")
        self.assertEqual(song.events[3].key, ",")
        self.assertEqual(song.events[3].mouse_button, "right")
        self.assertTrue(song.events[4].is_rest)
        self.assertAlmostEqual(song.duration_seconds, 2.5)

    def test_requires_bpm_before_notes(self) -> None:
        with self.assertRaisesRegex(SongFormatError, "请先设置 BPM"):
            parse_song("1 1 normal")

    def test_rejects_unknown_note(self) -> None:
        with self.assertRaisesRegex(SongFormatError, "音符必须是 0 到 8"):
            parse_song("bpm 120\n9 1 normal")

    def test_rejects_non_positive_duration(self) -> None:
        with self.assertRaisesRegex(SongFormatError, "拍数必须大于零"):
            parse_song("bpm 120\n1 0 normal")

    def test_rest_requires_rest_modifier(self) -> None:
        with self.assertRaisesRegex(SongFormatError, "休止符必须"):
            parse_song("bpm 120\n0 1 normal")


if __name__ == "__main__":
    unittest.main()
