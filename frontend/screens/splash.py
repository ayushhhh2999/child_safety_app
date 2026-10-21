from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from components.theme import ACCENT, MUTED
from components.ui import AppLabel


class SplashScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation="vertical", padding=dp(32), spacing=dp(12))
        layout.add_widget(Widget())
        layout.add_widget(
            AppLabel("MT", size=50, bold=True, color=ACCENT, halign="center", height=dp(75))
        )
        layout.add_widget(
            AppLabel(
                "Mobile Tracker",
                size=28,
                bold=True,
                halign="center",
                height=dp(45),
            )
        )
        layout.add_widget(
            AppLabel(
                "Private by design. Shared by consent.\nLoading your app…",
                size=14,
                color=MUTED,
                halign="center",
                height=dp(56),
            )
        )
        layout.add_widget(Widget())
        self.add_widget(layout)
        Clock.schedule_once(self._continue, 0.8)

    def _continue(self, _dt) -> None:
        app = App.get_running_app()
        if app is not None:
            app.shell.navigate("auth")
