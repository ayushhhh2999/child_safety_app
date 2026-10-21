from kivy.app import App
from kivy.metrics import dp
from kivy.uix.screenmanager import Screen

from components.theme import MUTED, SUCCESS
from components.ui import AppButton, AppLabel, Card, text_field
from screens.common import (
    add_heading,
    confirm_action,
    dispatch_to_ui,
    error_message,
    page_layout,
    show_message,
)


class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.root_layout, self.content = page_layout()
        self.add_widget(self.root_layout)

    def on_pre_enter(self, *_args) -> None:
        self.refresh()

    def refresh(self) -> None:
        app = App.get_running_app()
        self.content.clear_widgets()
        signed_in = bool(app.current_user)
        add_heading(
            self.content,
            "Profile & settings" if signed_in else "Connect to your API",
            "Account and connection details"
            if signed_in
            else "Configure the backend address before signing in.",
        )
        if signed_in:
            user = app.current_user
            profile = Card(size_hint_y=None, height=dp(116))
            profile.add_widget(
                AppLabel(
                    f"@{user.get('username', 'Unavailable')}",
                    size=17,
                    bold=True,
                )
            )
            profile.add_widget(
                AppLabel(user.get("email", "Email unavailable"), size=13, color=MUTED)
            )
            self.content.add_widget(profile)

        api_card = Card(size_hint_y=None, height=dp(190))
        api_card.add_widget(AppLabel("API connection", size=16, bold=True))
        self.api_url = text_field("https://your-api.example.com")
        self.api_url.text = app.api.base_url
        api_card.add_widget(self.api_url)
        self.api_status = AppLabel("Not checked", size=12, color=MUTED)
        api_card.add_widget(self.api_status)
        api_card.add_widget(
            AppButton("Save & test connection", self.save_and_test, primary=True)
        )
        self.content.add_widget(api_card)

        privacy = Card(size_hint_y=None, height=dp(150))
        privacy.add_widget(AppLabel("Privacy", size=16, bold=True))
        privacy.add_widget(
            AppLabel(
                "Your access token stays in memory and is removed when you log out "
                "or close the app. It is not stored in plaintext preferences. "
                "Keep the API secret and database credentials on the server.",
                size=12,
                color=MUTED,
                height=dp(76),
            )
        )
        self.content.add_widget(privacy)

        account = Card(size_hint_y=None, height=dp(138))
        account.add_widget(AppLabel("Account deletion", size=16, bold=True))
        account.add_widget(
            AppLabel(
                "The backend does not provide an account or historical-data deletion "
                "endpoint. Contact the service administrator to request deletion.",
                size=12,
                color=MUTED,
                height=dp(62),
            )
        )
        self.content.add_widget(account)
        if signed_in:
            self.content.add_widget(
                AppButton(
                    "Log out",
                    lambda: confirm_action(
                        "Log out?",
                        "Your in-memory session token will be discarded.",
                        self.logout,
                    ),
                    height=dp(50),
                )
            )
        else:
            self.content.add_widget(
                AppButton(
                    "Back to sign in",
                    lambda: setattr(app.shell.screens, "current", "auth"),
                    height=dp(50),
                )
            )
        self.content.add_widget(
            AppLabel(
                "Mobile Tracker · Android client 0.1.0 · Location capture and app "
                "usage sync are manual; app blocking requires Android opt-in.",
                size=11,
                color=MUTED,
                height=dp(46),
            )
        )

    def save_and_test(self) -> None:
        app = App.get_running_app()
        api = app.api
        previous_url = api.base_url
        try:
            api.set_base_url(self.api_url.text)
        except (OSError, ValueError) as error:
            self.api_status.text = str(error)
            return
        if previous_url != api.base_url and app.current_user:
            app.current_user = None
            app.shell._navigation_state(app.shell.screens, "settings")
            self.refresh()
        self.api_status.text = "Checking /health…"

        def complete(result, error) -> None:
            def update_ui() -> None:
                if error:
                    self.api_status.text = error_message(error)
                elif result.get("status") == "healthy":
                    self.api_status.text = "Connected · API health check passed"
                    self.api_status.color = SUCCESS
                else:
                    self.api_status.text = "API responded with an unexpected health status."
                    self.api_status.color = MUTED

            dispatch_to_ui(update_ui)

        api.run_async(api.health, complete)

    def logout(self) -> None:
        app = App.get_running_app()
        app.api.logout()
        app.current_user = None
        app.shell.screens.current = "auth"
