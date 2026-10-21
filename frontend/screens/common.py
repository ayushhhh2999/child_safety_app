from collections.abc import Callable

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.popup import Popup

from components.theme import MUTED, SURFACE, TEXT
from components.ui import AppButton, AppLabel


def show_message(title: str, message: str) -> None:
    Popup(
        title=title,
        content=AppLabel(
            text=message,
            size=14,
            color=MUTED,
            padding=(dp(16), dp(12)),
        ),
        size_hint=(0.88, None),
        height=230,
        separator_color=(0.18, 0.21, 0.31, 1),
        title_color=TEXT,
        background_color=SURFACE,
    ).open()


def confirm_action(title: str, message: str, confirm: Callable[[], None]) -> None:
    from kivy.uix.boxlayout import BoxLayout

    body = BoxLayout(orientation="vertical", padding=16, spacing=12)
    body.add_widget(AppLabel(message, size=14, color=MUTED))
    buttons = BoxLayout(size_hint_y=None, height=48, spacing=10)
    popup = Popup(
        title=title,
        content=body,
        size_hint=(0.9, None),
        height=250,
        separator_color=(0.18, 0.21, 0.31, 1),
        title_color=TEXT,
        background_color=SURFACE,
    )
    buttons.add_widget(
        AppButton("Cancel", popup.dismiss, compact=True, size_hint_x=1)
    )
    buttons.add_widget(
        AppButton(
            "Continue",
            lambda: (popup.dismiss(), confirm()),
            primary=True,
            compact=True,
            size_hint_x=1,
        )
    )
    body.add_widget(buttons)
    popup.open()


def make_button(text: str, callback: Callable[[], None], height: int = 48):
    return AppButton(text, callback, height=height)


def page_layout():
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.scrollview import ScrollView

    root = BoxLayout(orientation="vertical", padding=(16, 14, 16, 10))
    scroll = ScrollView(do_scroll_x=False, bar_width=dp(3))
    content = BoxLayout(
        orientation="vertical",
        spacing=dp(12),
        size_hint_y=None,
        padding=(0, 0, 0, dp(18)),
    )
    content.bind(minimum_height=content.setter("height"))
    scroll.add_widget(content)
    root.add_widget(scroll)
    return root, content


def add_heading(container, title: str, subtitle: str | None = None) -> None:
    from kivy.uix.boxlayout import BoxLayout

    header = BoxLayout(
        orientation="vertical",
        size_hint_y=None,
        height=dp(82 if subtitle else 48),
        spacing=dp(2),
    )
    header.add_widget(AppLabel(title, size=25, bold=True, height=dp(40)))
    if subtitle:
        header.add_widget(
            AppLabel(subtitle, size=13, color=MUTED, height=dp(34))
        )
    container.add_widget(header)


def add_card(container, title: str, detail: str, accent=None):
    from kivy.uix.boxlayout import BoxLayout

    card = Card(
        size_hint_y=None,
        padding=dp(17),
        spacing=dp(8),
        fill_color=SURFACE,
    )
    card.add_widget(AppLabel(title, size=16, bold=True, height=dp(28)))
    card.add_widget(
        AppLabel(detail, size=13, color=accent or MUTED, height=dp(48))
    )
    container.add_widget(card)
    return card


def error_message(error: Exception | None) -> str:
    return str(error) if error else "The request did not complete."


def dispatch_to_ui(callback: Callable[[], None]) -> None:
    Clock.schedule_once(lambda _dt: callback(), 0)
