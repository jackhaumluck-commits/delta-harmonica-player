"""Create a small monophonic MIDI file for testing the v0.8 importer."""

from pathlib import Path

from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo


OUTPUT_PATH = Path(__file__).with_name("generated_midi_scale.mid")


def main() -> None:
    midi = MidiFile(ticks_per_beat=480)
    track = MidiTrack()
    track.append(MetaMessage("track_name", name="C major scale", time=0))
    track.append(MetaMessage("set_tempo", tempo=bpm2tempo(100), time=0))

    for index, pitch in enumerate((60, 62, 64, 65, 67, 69, 71, 72)):
        rest_before_note = 240 if index == 4 else 0
        track.append(
            Message(
                "note_on",
                note=pitch,
                velocity=64,
                time=rest_before_note,
            )
        )
        track.append(Message("note_off", note=pitch, velocity=0, time=240))

    midi.tracks.append(track)
    midi.save(OUTPUT_PATH)
    print(f"已生成 MIDI 示例：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()
