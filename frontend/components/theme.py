from kivy.core.window import Window
from kivy.metrics import dp

BACKGROUND = (0.035, 0.047, 0.09, 1)
SURFACE = (0.075, 0.09, 0.15, 1)
SURFACE_ALT = (0.10, 0.12, 0.19, 1)
ACCENT = (0.38, 0.45, 0.98, 1)
ACCENT_VIOLET = (0.58, 0.38, 0.93, 1)
TEXT = (0.93, 0.95, 1, 1)
MUTED = (0.62, 0.67, 0.77, 1)
SUCCESS = (0.38, 0.82, 0.65, 1)
DANGER = (0.95, 0.43, 0.48, 1)
OUTLINE = (0.18, 0.21, 0.31, 1)


def apply_window_theme() -> None:
    Window.clearcolor = BACKGROUND
