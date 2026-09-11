import unittest
from pathlib import Path

from harmonica_player.library import (
    SongSelectionError,
    list_songs,
    select_song_path,
)


EXAMPLES_DIRECTORY = Path(__file__).parent.parent / "examples"


class SongLibraryTests(unittest.TestCase):
    def test_lists_bundled_songs_in_name_order(self) -> None:
        songs = list_songs(EXAMPLES_DIRECTORY)

        self.assertEqual(
            [song.name for song in songs],
            ["demo", "twinkle_twinkle"],
        )
        self.assertEqual(songs[1].event_count, 14)
        self.assertAlmostEqual(songs[1].duration_seconds, 12.0)

    def test_selects_song_by_stem_or_filename(self) -> None:
        by_stem = select_song_path("twinkle_twinkle", EXAMPLES_DIRECTORY)
        by_filename = select_song_path("twinkle_twinkle.song", EXAMPLES_DIRECTORY)

        self.assertEqual(by_stem, by_filename)
        self.assertEqual(by_stem.name, "twinkle_twinkle.song")

    def test_unknown_song_reports_available_names(self) -> None:
        with self.assertRaisesRegex(
            SongSelectionError, "可用曲目：demo, twinkle_twinkle"
        ):
            select_song_path("missing", EXAMPLES_DIRECTORY)


if __name__ == "__main__":
    unittest.main()
