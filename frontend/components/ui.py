from collections.abc import Callable

from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.properties import ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from components import theme


class Card(BoxLayout):
    fill_color = ListProperty(theme.SURFACE)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = kwargs.get("orientation", "vertical")
        self.padding = kwargs.get("padding", dp(18))
        self.spacing = kwargs.get("spacing", dp(10))
        self.size_hint_y = kwargs.get("size_hint_y", None)
        self.bind(pos=self._draw, size=self._draw, fill_color=self._draw)
        with self.canvas.before:
            self._fill = Color(*self.fill_color)
            self._shape = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[dp(20)],
            )

    def _draw(self, *_args) -> None:
        self._fill.rgba = self.fill_color
        self._shape.pos = self.pos
        self._shape.size = self.size


class AppLabel(Label):
    def __init__(
        self,
        text: str,
        size: float = 15,
        color=theme.TEXT,
        bold: bool = False,
        **kwargs,
    ):
        super().__init__(
            text=text,
            font_size=sp(size),
            color=color,
            bold=bold,
            halign=kwargs.pop("halign", "left"),
            valign=kwargs.pop("valign", "middle"),
            size_hint_y=kwargs.pop("size_hint_y", None),
            height=kwargs.pop("height", dp(28)),
            **kwargs,
        )
        self.bind(size=self._fit_text)
        self._fit_text()

    def _fit_text(self, *_args) -> None:
        self.text_size = (self.width, None)


class AppButton(Button):
    def __init__(
        self,
        text: str,
        callback: Callable[[], None],
        *,
        primary: bool = False,
        compact: bool = False,
        **kwargs,
    ):
        self.fill = theme.ACCENT if primary else theme.SURFACE_ALT
        self._callback = callback
        font_size = kwargs.pop("font_size", 14)
        super().__init__(
            text=text,
            color=theme.TEXT,
            font_size=sp(font_size),
            bold=primary,
            background_normal="",
            background_down="",
            background_color=(0, 0, 0, 0),
            size_hint_y=kwargs.pop("size_hint_y", None),
            height=kwargs.pop("height", dp(44 if compact else 50)),
            **kwargs,
        )
        with self.canvas.before:
            self._fill_color = Color(*self.fill)
            self._background = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[dp(15)],
            )
        self.bind(pos=self._sync_canvas, size=self._sync_canvas)
        self.bind(on_release=lambda _button: self._callback())

    def _sync_canvas(self, *_args) -> None:
        self._background.pos = self.pos
        self._background.size = self.size

    def set_busy(self, busy: bool, label: str = "Please wait…") -> None:
        if busy:
            self._normal_text = self.text
            self.text = label
        elif hasattr(self, "_normal_text"):
            self.text = self._normal_text
        self.disabled = busy

    def set_fill(self, color) -> None:
        self.fill = color
        self._fill_color.rgba = color


def text_field(hint: str, *, password: bool = False) -> TextInput:
    return TextInput(
        hint_text=hint,
        multiline=False,
        password=password,
        size_hint_y=None,
        height=dp(52),
        padding=(dp(15), dp(15)),
        background_normal="",
        background_active="",
        background_color=theme.SURFACE_ALT,
        foreground_color=theme.TEXT,
        hint_text_color=theme.MUTED,
        cursor_color=theme.ACCENT,
        font_size=sp(15),
    )
