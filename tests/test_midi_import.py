import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo

from harmonica_player.midi_import import (
    MidiImportError,
    convert_midi,
    format_midi_song,
    import_midi,
    list_midi_tracks,
    midi_pitch_to_event,
)
from harmonica_player.song import NoteEvent, parse_song


class MidiImportTests(unittest.TestCase):
    def test_converts_tempo_rests_octaves_and_semitones(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "练习曲.mid"
            midi = MidiFile(ticks_per_beat=480)
            track = MidiTrack()
            track.append(MetaMessage("track_name", name="Melody", time=0))
            track.append(
                MetaMessage("set_tempo", tempo=bpm2tempo(100), time=0)
            )
            track.extend(
                [
                    Message("note_on", note=48, velocity=64, time=240),
                    Message("note_off", note=48, velocity=0, time=480),
                    Message("note_on", note=60, velocity=64, time=0),
                    Message("note_off", note=60, velocity=0, time=240),
                    Message("note_on", note=61, velocity=64, time=0),
                    Message("note_on", note=61, velocity=0, time=240),
                    Message("note_on", note=84, velocity=64, time=0),
                    Message("note_off", note=84, velocity=0, time=480),
                ]
            )
            midi.tracks.append(track)
            midi.save(path)

            conversion = convert_midi(path)

            self.assertAlmostEqual(conversion.song.bpm, 100)
            self.assertEqual(conversion.song.title, "练习曲")
            self.assertEqual(conversion.track_index, 0)
            self.assertEqual(conversion.track_name, "Melody")
            self.assertFalse(conversion.polyphony_detected)
            self.assertFalse(conversion.octave_folding_detected)
            self.assertEqual(
                [
                    (event.note, event.beats, event.modifier)
                    for event in conversion.song.events
                ],
                [
                    ("0", 0.5, "rest"),
                    ("1", 1.0, "down"),
                    ("1", 0.5, "normal"),
                    ("1", 0.5, "semitone"),
                    ("8", 1.0, "up"),
                ],
            )
            reparsed = parse_song(format_midi_song(conversion))
            self.assertEqual(reparsed, conversion.song)

    def test_imports_generated_score_into_user_library(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / "simple.mid"
            self._save_notes(path, [(60, 480)])

            summary = import_midi(
                path,
                bundled_directory=root / "bundled",
                user_directory=root / "songs",
            )

            self.assertEqual(summary.path, root / "songs" / "simple.song")
            self.assertEqual(summary.title, "simple")
            self.assertIn("1 1 normal", summary.path.read_text(encoding="utf-8"))

    def test_uses_default_120_bpm_when_tempo_is_missing(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "default.mid"
            self._save_notes(path, [(60, 480)])

            conversion = convert_midi(path)

            self.assertEqual(conversion.song.bpm, 120)

    def test_rejects_missing_unsupported_and_corrupt_files(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            missing = root / "missing.mid"
            unsupported = root / "notes.txt"
            corrupt = root / "broken.mid"
            unsupported.write_text("not midi", encoding="utf-8")
            corrupt.write_bytes(b"not midi")

            with self.assertRaisesRegex(MidiImportError, "找不到 MIDI"):
                convert_midi(missing)
            with self.assertRaisesRegex(MidiImportError, "只支持导入"):
                convert_midi(unsupported)
            with self.assertRaisesRegex(MidiImportError, "无法读取 MIDI"):
                convert_midi(corrupt)

    def test_multiple_note_tracks_require_an_explicit_selection(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "tracks.mid"
            midi = MidiFile(type=1, ticks_per_beat=480)
            tempo_track = MidiTrack()
            tempo_track.append(
                MetaMessage("set_tempo", tempo=bpm2tempo(120), time=0)
            )
            midi.tracks.append(tempo_track)
            for name, pitch in (("Lead", 60), ("Bass", 48)):
                track = MidiTrack()
                track.append(MetaMessage("track_name", name=name, time=0))
                track.append(Message("note_on", note=pitch, velocity=64, time=0))
                track.append(Message("note_off", note=pitch, velocity=0, time=480))
                midi.tracks.append(track)
            midi.save(path)

            with self.assertRaisesRegex(MidiImportError, "--midi-track"):
                convert_midi(path)

            tracks = list_midi_tracks(path)
            self.assertEqual(
                [(track.index, track.name, track.note_count) for track in tracks],
                [(0, None, 0), (1, "Lead", 1), (2, "Bass", 1)],
            )

            conversion = convert_midi(path, track_index=2)
            self.assertEqual(conversion.track_name, "Bass")
            self.assertEqual(conversion.song.events[0].modifier, "down")

            with self.assertRaisesRegex(MidiImportError, "0 到 2"):
                convert_midi(path, track_index=3)
            with self.assertRaisesRegex(MidiImportError, "没有音符"):
                convert_midi(path, track_index=0)

    def test_extracts_highest_note_from_chords(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "chord.mid"
            midi = MidiFile(ticks_per_beat=480)
            track = MidiTrack(
                [
                    Message("note_on", note=60, velocity=64, time=0),
                    Message("note_on", note=64, velocity=64, time=0),
                    Message("note_off", note=60, velocity=0, time=480),
                    Message("note_off", note=64, velocity=0, time=0),
                ]
            )
            midi.tracks.append(track)
            midi.save(path)

            conversion = convert_midi(path)

            self.assertTrue(conversion.polyphony_detected)
            self.assertEqual(
                conversion.song.events,
                (NoteEvent("3", 1.0, "normal"),),
            )
            self.assertIn("和弦处理", format_midi_song(conversion))

    def test_tracks_highest_note_through_overlapping_notes(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "overlap.mid"
            midi = MidiFile(ticks_per_beat=480)
            track = MidiTrack(
                [
                    Message("note_on", note=60, velocity=64, time=0),
                    Message("note_on", note=67, velocity=64, time=240),
                    Message("note_off", note=67, velocity=0, time=240),
                    Message("note_off", note=60, velocity=0, time=240),
                ]
            )
            midi.tracks.append(track)
            midi.save(path)

            conversion = convert_midi(path)

            self.assertTrue(conversion.polyphony_detected)
            self.assertEqual(
                conversion.song.events,
                (
                    NoteEvent("1", 0.5, "normal"),
                    NoteEvent("5", 0.5, "normal"),
                    NoteEvent("1", 0.5, "normal"),
                ),
            )

    def test_keeps_repeated_notes_as_separate_events(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "repeated.mid"
            midi = MidiFile(ticks_per_beat=480)
            track = MidiTrack(
                [
                    Message("note_on", note=60, velocity=64, time=0),
                    Message("note_off", note=60, velocity=0, time=480),
                    Message("note_on", note=60, velocity=64, time=0),
                    Message("note_off", note=60, velocity=0, time=480),
                ]
            )
            midi.tracks.append(track)
            midi.save(path)

            conversion = convert_midi(path)

            self.assertFalse(conversion.polyphony_detected)
            self.assertEqual(
                conversion.song.events,
                (
                    NoteEvent("1", 1.0, "normal"),
                    NoteEvent("1", 1.0, "normal"),
                ),
            )

    def test_does_not_retrigger_held_high_note_for_lower_voice_changes(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "held_high.mid"
            midi = MidiFile(ticks_per_beat=480)
            track = MidiTrack(
                [
                    Message("note_on", note=67, velocity=64, time=0),
                    Message("note_on", note=60, velocity=64, time=240),
                    Message("note_off", note=60, velocity=0, time=240),
                    Message("note_off", note=67, velocity=0, time=240),
                ]
            )
            midi.tracks.append(track)
            midi.save(path)

            conversion = convert_midi(path)

            self.assertEqual(
                conversion.song.events,
                (NoteEvent("5", 1.5, "normal"),),
            )

    def test_rejects_tempo_changes_during_playback(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "tempo.mid"
            midi = MidiFile(ticks_per_beat=480)
            track = MidiTrack(
                [
                    MetaMessage("set_tempo", tempo=bpm2tempo(100), time=0),
                    Message("note_on", note=60, velocity=64, time=0),
                    MetaMessage("set_tempo", tempo=bpm2tempo(120), time=240),
                    Message("note_off", note=60, velocity=0, time=240),
                ]
            )
            midi.tracks.append(track)
            midi.save(path)

            with self.assertRaisesRegex(MidiImportError, "改变 BPM"):
                convert_midi(path)

    def test_folds_unplayable_pitch_into_nearest_octave(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            unplayable = root / "unplayable.mid"
            self._save_notes(unplayable, [(49, 480)])

            conversion = convert_midi(unplayable)

            self.assertTrue(conversion.octave_folding_detected)
            self.assertEqual(
                conversion.song.events,
                (NoteEvent("1", 1.0, "semitone"),),
            )
            self.assertIn("音域处理", format_midi_song(conversion))

    def test_rejects_unfinished_note(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            unfinished = Path(temporary_directory) / "unfinished.mid"
            self._save_notes(unfinished, [(60, None)])

            with self.assertRaisesRegex(MidiImportError, "缺少对应的结束事件"):
                convert_midi(unfinished)

    def test_pitch_mapping_uses_normal_notes_at_shared_octave_edges(self) -> None:
        self.assertEqual(
            midi_pitch_to_event(60, 1),
            NoteEvent("1", 1, "normal"),
        )
        self.assertEqual(midi_pitch_to_event(72, 1).modifier, "normal")
        self.assertEqual(midi_pitch_to_event(84, 1).modifier, "up")
        self.assertEqual(
            midi_pitch_to_event(49, 1),
            NoteEvent("1", 1, "semitone"),
        )
        self.assertEqual(
            midi_pitch_to_event(96, 1),
            NoteEvent("8", 1, "up"),
        )

    @staticmethod
    def _save_notes(path: Path, notes: list[tuple[int, int | None]]) -> None:
        midi = MidiFile(ticks_per_beat=480)
        track = MidiTrack()
        for pitch, duration in notes:
            track.append(Message("note_on", note=pitch, velocity=64, time=0))
            if duration is not None:
                track.append(
                    Message("note_off", note=pitch, velocity=0, time=duration)
                )
        midi.tracks.append(track)
        midi.save(path)


if __name__ == "__main__":
    unittest.main()
