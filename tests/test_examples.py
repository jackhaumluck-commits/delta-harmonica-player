import unittest
from pathlib import Path

from harmonica_player.song import load_song


EXAMPLES_DIRECTORY = Path(__file__).parent.parent / "examples"


class ExampleScoreTests(unittest.TestCase):
    def test_all_example_scores_can_be_loaded(self) -> None:
        score_paths = sorted(EXAMPLES_DIRECTORY.glob("*.song"))
        self.assertTrue(score_paths, "examples 文件夹中至少应该有一份曲谱")

        for score_path in score_paths:
            with self.subTest(score=score_path.name):
                song = load_song(score_path)
                self.assertGreater(len(song.events), 0)

    def test_twinkle_twinkle_has_expected_length(self) -> None:
        song = load_song(EXAMPLES_DIRECTORY / "twinkle_twinkle.song")

        self.assertEqual(len(song.events), 14)
        self.assertAlmostEqual(song.duration_seconds, 12.0)

    def test_modifier_exercise_covers_all_mouse_modifiers(self) -> None:
        song = load_song(EXAMPLES_DIRECTORY / "modifier_exercise.song")

        modifiers = {event.modifier for event in song.events if not event.is_rest}
        self.assertEqual(modifiers, {"normal", "down", "semitone", "up"})

    def test_user_song_import_template_can_be_loaded(self) -> None:
        song = load_song(EXAMPLES_DIRECTORY / "user_song_template.txt")

        self.assertEqual(song.title, "用户曲谱示例")
        self.assertGreater(len(song.events), 0)


if __name__ == "__main__":
    unittest.main()
