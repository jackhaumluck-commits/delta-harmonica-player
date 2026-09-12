"""Windows executable entry point for the desktop interface."""

from harmonica_player.gui import run_gui


if __name__ == "__main__":
    raise SystemExit(run_gui())
