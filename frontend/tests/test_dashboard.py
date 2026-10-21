import unittest
from types import SimpleNamespace
from unittest.mock import patch

from kivy.uix.screenmanager import ScreenManager

from screens.dashboard import DashboardScreen


class DashboardSessionTests(unittest.TestCase):
    def test_stale_summary_callback_after_logout_returns_to_auth(self) -> None:
        manager = ScreenManager()
        dashboard = DashboardScreen(name="home")
        from kivy.uix.screenmanager import Screen

        manager.add_widget(dashboard)
        manager.add_widget(Screen(name="auth"))
        manager.current = "home"
        app = SimpleNamespace(
            current_user=None,
            shell=SimpleNamespace(screens=manager),
        )

        with patch("screens.dashboard.App.get_running_app", return_value=app):
            dashboard._render_summary(
                result=([], []),
                error=None,
                user_id=1,
                generation=0,
            )

        self.assertEqual(manager.current, "auth")


if __name__ == "__main__":
    unittest.main()
