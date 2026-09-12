import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from harmonica_player.library import (
    SongImportError,
    SongSelectionError,
    SongSource,
    import_song,
    list_songs,
    migrate_legacy_user_songs,
    select_song_path,
)
from harmonica_player.song import SongFormatError


EXAMPLES_DIRECTORY = Path(__file__).parent.parent / "examples"


class SongLibraryTests(unittest.TestCase):
    def test_lists_bundled_songs_in_name_order(self) -> None:
        songs = list_songs(EXAMPLES_DIRECTORY, None)

        self.assertEqual(
            [song.name for song in songs],
            ["demo", "modifier_exercise", "twinkle_twinkle"],
        )
        self.assertEqual(
            [song.title for song in songs],
            ["按键与变调演示", "变调按键练习", "小星星（第一段）"],
        )
        self.assertEqual(songs[2].event_count, 14)
        self.assertAlmostEqual(songs[2].duration_seconds, 12.0)
        self.assertTrue(all(song.source is SongSource.BUNDLED for song in songs))

    def test_selects_song_by_stem_or_filename(self) -> None:
        by_stem = select_song_path("twinkle_twinkle", EXAMPLES_DIRECTORY, None)
        by_filename = select_song_path(
            "twinkle_twinkle.song", EXAMPLES_DIRECTORY, None
        )

        self.assertEqual(by_stem, by_filename)
        self.assertEqual(by_stem.name, "twinkle_twinkle.song")

    def test_selects_song_by_chinese_title(self) -> None:
        path = select_song_path("小星星（第一段）", EXAMPLES_DIRECTORY, None)

        self.assertEqual(path.name, "twinkle_twinkle.song")

    def test_unknown_song_reports_available_names(self) -> None:
        with self.assertRaisesRegex(
            SongSelectionError, "可用曲目：.*modifier_exercise"
        ):
            select_song_path("missing", EXAMPLES_DIRECTORY, None)

    def test_imports_txt_score_and_selects_it_by_title(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "my_song.txt"
            user_directory = root / "songs"
            source.write_text(
                "bpm 90\ntitle 我的曲子\n1 1 normal\n",
                encoding="utf-8",
            )

            summary = import_song(
                source,
                bundled_directory=EXAMPLES_DIRECTORY,
                user_directory=user_directory,
            )

            self.assertEqual(summary.path, user_directory / "my_song.song")
            self.assertEqual(summary.source, SongSource.USER)
            self.assertEqual(
                select_song_path(
                    "我的曲子", EXAMPLES_DIRECTORY, user_directory
                ),
                summary.path,
            )

    def test_rejects_duplicate_import(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "my_song.song"
            user_directory = root / "songs"
            source.write_text("bpm 90\n1 1 normal\n", encoding="utf-8")
            import_song(
                source,
                bundled_directory=EXAMPLES_DIRECTORY,
                user_directory=user_directory,
            )

            with self.assertRaisesRegex(SongImportError, "已存在"):
                import_song(
                    source,
                    bundled_directory=EXAMPLES_DIRECTORY,
                    user_directory=user_directory,
                )

    def test_rejects_import_that_conflicts_with_bundled_title(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "another.song"
            source.write_text(
                "bpm 80\ntitle 小星星（第一段）\n1 1 normal\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(SongImportError, "冲突"):
                import_song(
                    source,
                    bundled_directory=EXAMPLES_DIRECTORY,
                    user_directory=root / "songs",
                )

    def test_rejects_unsupported_import_extension(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "my_song.md"
            source.write_text("bpm 90\n1 1 normal\n", encoding="utf-8")

            with self.assertRaisesRegex(SongImportError, "只支持导入"):
                import_song(source, user_directory=source.parent / "songs")

    def test_rejects_non_utf8_import(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "my_song.song"
            source.write_bytes(b"\xff\xfe")

            with self.assertRaisesRegex(SongImportError, "UTF-8"):
                import_song(source, user_directory=source.parent / "songs")

    def test_reports_invalid_user_score_filename(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            user_directory = Path(temporary_directory)
            (user_directory / "broken.song").write_text(
                "1 1 normal\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(SongFormatError, "broken.song"):
                list_songs(EXAMPLES_DIRECTORY, user_directory)

    def test_migrates_legacy_user_scores_without_overwriting(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            legacy_directory = root / "legacy"
            user_directory = root / "current"
            legacy_directory.mkdir()
            user_directory.mkdir()
            (legacy_directory / "old.song").write_text(
                "bpm 90\n1 1 normal\n", encoding="utf-8"
            )
            (legacy_directory / "existing.song").write_text(
                "bpm 80\n1 1 normal\n", encoding="utf-8"
            )
            existing = user_directory / "existing.song"
            existing.write_text("bpm 120\n2 1 normal\n", encoding="utf-8")

            migrated = migrate_legacy_user_songs(
                legacy_directory, user_directory
            )

            self.assertEqual(migrated, (user_directory / "old.song",))
            self.assertEqual(
                (user_directory / "old.song").read_text(encoding="utf-8"),
                "bpm 90\n1 1 normal\n",
            )
            self.assertEqual(
                existing.read_text(encoding="utf-8"),
                "bpm 120\n2 1 normal\n",
            )
            (user_directory / "old.song").unlink()
            self.assertEqual(
                migrate_legacy_user_songs(legacy_directory, user_directory), ()
            )
            self.assertFalse((user_directory / "old.song").exists())


if __name__ == "__main__":
    unittest.main()
