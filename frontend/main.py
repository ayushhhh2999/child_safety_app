from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import ScreenManager

from screens.auth import AuthScreen
from screens.connections import ConnectionsScreen
from screens.dashboard import DashboardScreen
from screens.data import ActivitiesScreen, LocationsScreen, RestrictedAppsScreen
from screens.settings import SettingsScreen
from screens.splash import SplashScreen
from components.theme import apply_window_theme
from components.ui import AppButton
from services.api import ApiClient


class AppShell(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.screens = ScreenManager()
        self.screens.add_widget(SplashScreen(name="splash"))
        self.screens.add_widget(AuthScreen(name="auth"))
        self.screens.add_widget(DashboardScreen(name="home"))
        self.screens.add_widget(LocationsScreen(name="locations"))
        self.screens.add_widget(ActivitiesScreen(name="activity"))
        self.screens.add_widget(ConnectionsScreen(name="connections"))
        self.screens.add_widget(RestrictedAppsScreen(name="restricted"))
        self.screens.add_widget(SettingsScreen(name="settings"))
        self.add_widget(self.screens)

        self.navigation = BoxLayout(
            size_hint_y=None,
            height=dp(68),
            padding=(dp(6), dp(7)),
            spacing=dp(3),
        )
        self.navigation_buttons = {}
        for screen_name, label in (
            ("home", "Home"),
            ("locations", "Location"),
            ("activity", "Activity"),
            ("connections", "People"),
            ("settings", "Settings"),
        ):
            button = AppButton(
                label,
                lambda target=screen_name: self.navigate(target),
                compact=True,
                font_size=12,
                size_hint_x=1,
            )
            self.navigation_buttons[screen_name] = button
            self.navigation.add_widget(button)
        self.add_widget(self.navigation)
        self.screens.bind(current=self._navigation_state)
        self._navigation_state(self.screens, "splash")

    def navigate(self, screen_name: str) -> None:
        if not getattr(App.get_running_app(), "current_user", None):
            self.screens.current = "auth"
            return
        self.screens.current = screen_name

    def _navigation_state(self, _manager, current: str) -> None:
        authenticated = bool(
            getattr(App.get_running_app(), "current_user", None)
        )
        self.navigation.opacity = 1 if authenticated else 0
        self.navigation.height = dp(68) if authenticated else 0
        for name, button in self.navigation_buttons.items():
            button.set_fill(
                (0.19, 0.23, 0.43, 1)
                if name == current
                else (0.10, 0.12, 0.19, 1)
            )


class MobileTrackerApp(App):
    title = "Mobile Tracker"

    def build(self) -> AppShell:
        apply_window_theme()
        self.api = ApiClient()
        self.current_user = None
        self.api.on_unauthorized = self._handle_unauthorized
        self.shell = AppShell()
        return self.shell

    def _handle_unauthorized(self) -> None:
        from kivy.clock import Clock

        def return_to_login(_dt) -> None:
            self.current_user = None
            if hasattr(self, "shell"):
                self.shell.screens.current = "auth"
                self.shell._navigation_state(self.shell.screens, "auth")

        Clock.schedule_once(return_to_login, 0)

    def on_stop(self) -> None:
        self.api.close()


if __name__ == "__main__":
    MobileTrackerApp().run()
