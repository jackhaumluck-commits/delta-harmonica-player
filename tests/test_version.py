import unittest

import harmonica_player


class VersionTests(unittest.TestCase):
    def test_version_is_v1_release(self) -> None:
        self.assertEqual(harmonica_player.__version__, "1.0.0")


if __name__ == "__main__":
    unittest.main()
