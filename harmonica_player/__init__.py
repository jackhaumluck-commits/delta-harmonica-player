"""Core models and parser for the harmonica player."""

from .song import NoteEvent, Song, SongFormatError, parse_song

__version__ = "1.0.0"

__all__ = ["NoteEvent", "Song", "SongFormatError", "parse_song", "__version__"]
