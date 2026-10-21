from kivy.app import App
from kivy.metrics import dp
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget

from components.theme import ACCENT, MUTED, SUCCESS
from components.ui import AppButton, AppLabel, Card
from screens.common import add_heading, dispatch_to_ui, error_message, page_layout


def _enabled_permission_count(permissions: dict) -> int:
    return sum(
        bool(permissions[field])
        for field in (
            "share_location",
            "share_app_usage",
            "share_restriction_alerts",
        )
    )


class DashboardScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._refresh_generation = 0
        self.root_layout, self.content = page_layout()
        self.add_widget(self.root_layout)

    def on_pre_enter(self, *_args) -> None:
        if getattr(App.get_running_app(), "current_user", None):
            self.refresh()

    def refresh(self) -> None:
        app = App.get_running_app()
        user = app.current_user
        if not isinstance(user, dict):
            app.shell.screens.current = "auth"
            return
        self._refresh_generation += 1
        generation = self._refresh_generation
        user_id = user.get("id")
        api = app.api
        self.content.clear_widgets()
        username = user.get("username", "there")
        add_heading(self.content, f"Hello, {username}", "Your privacy dashboard")
        self.status = AppLabel(
            "Refreshing your account…",
            color=MUTED,
            size=13,
            height=dp(38),
        )
        self.content.add_widget(self.status)
        self.content.add_widget(Widget(size_hint_y=None, height=dp(2)))
        self.cards_box = self.content
        app.api.run_async(
            lambda: self._load_summary(api),
            lambda result, error: self._summary_loaded(
                result, error, user_id, generation
            ),
        )

    @staticmethod
    def _load_summary(api):
        connections = api.get_connections()
        permission_rows = []
        for connection in connections:
            permission_rows.append(
                (connection, api.get_permissions(connection["id"]))
            )
        return connections, permission_rows

    def _summary_loaded(self, result, error, user_id, generation) -> None:
        dispatch_to_ui(
            lambda: self._render_summary(result, error, user_id, generation)
        )

    def _render_summary(self, result, error, user_id, generation) -> None:
        app = App.get_running_app()
        user = getattr(app, "current_user", None)
        if (
            generation != self._refresh_generation
            or not isinstance(user, dict)
            or user.get("id") != user_id
        ):
            if not isinstance(user, dict) and app.shell.screens.current == self.name:
                app.shell.screens.current = "auth"
            return

        self.content.clear_widgets()
        add_heading(
            self.content,
            f"Hello, {user.get('username', 'there')}",
            "Your privacy dashboard",
        )
        if error:
            card = Card(size_hint_y=None, height=dp(125))
            card.add_widget(AppLabel("Could not load your dashboard", bold=True))
            card.add_widget(AppLabel(error_message(error), size=13, color=MUTED))
            card.add_widget(
                AppButton("Retry", self.refresh, primary=True, height=dp(42))
            )
            self.content.add_widget(card)
            return

        connections, permission_rows = result
        total_enabled = sum(
            _enabled_permission_count(permissions)
            for _connection, permissions in permission_rows
            if not permissions["paused"]
        )
        paused_connections = sum(
            permissions["paused"] and _enabled_permission_count(permissions) > 0
            for _connection, permissions in permission_rows
        )
        stats = Card(
            size_hint_y=None,
            height=dp(122),
            padding=dp(18),
            fill_color=(0.10, 0.12, 0.23, 1),
        )
        stats.add_widget(
            AppLabel(
                f"{len(connections)}",
                size=30,
                color=ACCENT,
                bold=True,
                height=dp(42),
            )
        )
        stats.add_widget(
            AppLabel(
                f"accepted connection{'s' if len(connections) != 1 else ''}",
                size=14,
                color=MUTED,
            )
        )
        self.content.add_widget(stats)

        sharing = Card(size_hint_y=None, height=dp(122))
        sharing.add_widget(
            AppLabel("Your sharing status", size=16, bold=True, height=dp(30))
        )
        sharing.add_widget(
            AppLabel(
                "Sharing is paused"
                if total_enabled == 0 and paused_connections
                else "All sharing is off"
                if total_enabled == 0
                else f"{total_enabled} sharing permission(s) enabled",
                color=SUCCESS if total_enabled else MUTED,
            )
        )
        sharing.add_widget(
            AppLabel(
                "These are server-side consents for data you choose to record or "
                "sync from this device.",
                size=12,
                color=MUTED,
            )
        )
        self.content.add_widget(sharing)

        self._feature_card(
            "Location",
            "Record a one-time location only after tapping the capture button and "
            "granting Android permission.",
            "locations",
        )
        self._feature_card(
            "App activity",
            "Manually sync Android app foreground/background events after enabling "
            "Usage Access.",
            "activity",
        )
        self._feature_card(
            "Restricted apps",
            "Select apps on this device. Blocking requires separately enabling "
            "the Accessibility service in Android Settings.",
            "restricted",
        )
        self.content.add_widget(
            AppButton(
                "Manage connections and sharing",
                lambda: app.shell.navigate("connections"),
                primary=True,
                height=dp(52),
            )
        )
        self.content.add_widget(
            AppButton(
                "Restricted apps setup",
                lambda: app.shell.navigate("restricted"),
                height=dp(48),
            )
        )

    def _feature_card(self, title: str, detail: str, screen_name: str) -> None:
        card = Card(size_hint_y=None, height=dp(116))
        card.add_widget(AppLabel(title, size=16, bold=True, height=dp(30)))
        card.add_widget(AppLabel(detail, size=12, color=MUTED, height=dp(50)))
        card.add_widget(
            AppButton(
                "View details",
                lambda: App.get_running_app().shell.navigate(screen_name),
                compact=True,
                height=dp(40),
            )
        )
        self.content.add_widget(card)
