import re
from collections.abc import Callable

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from components.theme import ACCENT, MUTED, TEXT
from components.ui import AppButton, AppLabel, Card, text_field
from screens.common import dispatch_to_ui


class AuthScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.signup_mode = False
        self._busy = False
        self.fields = {}
        self.content = BoxLayout(
            orientation="vertical",
            padding=(dp(24), dp(20)),
            spacing=dp(13),
            size_hint_y=None,
        )
        self.content.bind(minimum_height=self.content.setter("height"))
        scroll = ScrollView(do_scroll_x=False)
        scroll.add_widget(self.content)
        self.add_widget(scroll)
        self._render()

    def _render(self) -> None:
        self.content.clear_widgets()
        self.fields.clear()
        self.content.add_widget(Widget(size_hint_y=None, height=dp(20)))
        brand = Card(
            size_hint_y=None,
            height=dp(112),
            padding=dp(18),
            spacing=dp(5),
            fill_color=(0.10, 0.12, 0.23, 1),
        )
        brand.add_widget(
            AppLabel(
                "MT   Mobile Tracker",
                size=24,
                bold=True,
                color=TEXT,
                height=dp(42),
            )
        )
        brand.add_widget(
            AppLabel(
                "Your data. Your choice. Always.",
                size=13,
                color=MUTED,
                height=dp(34),
            )
        )
        self.content.add_widget(brand)
        self.content.add_widget(Widget(size_hint_y=None, height=dp(4)))
        self.content.add_widget(
            AppLabel(
                "Create your account" if self.signup_mode else "Welcome back",
                size=27,
                bold=True,
                height=dp(42),
            )
        )
        self.content.add_widget(
            AppLabel(
                "Sign up to connect with someone you trust."
                if self.signup_mode
                else "Sign in to manage your trusted connections.",
                size=14,
                color=MUTED,
                height=dp(34),
            )
        )

        form = Card(
            size_hint_y=None,
            padding=dp(16),
            spacing=dp(11),
            fill_color=(0.075, 0.09, 0.15, 1),
        )
        self.fields["username"] = text_field("Username")
        form.add_widget(self.fields["username"])
        if self.signup_mode:
            self.fields["email"] = text_field("Email address")
            form.add_widget(self.fields["email"])
        self.fields["password"] = text_field(
            "Password",
            password=not getattr(self, "password_visible", False),
        )
        form.add_widget(self.fields["password"])
        if self.signup_mode:
            self.fields["confirm"] = text_field(
                "Confirm password",
                password=not getattr(self, "password_visible", False),
            )
            form.add_widget(self.fields["confirm"])
        form.height = dp(16 * 2 + (52 + 11) * len(self.fields) + 8)
        self.content.add_widget(form)

        actions = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
        self.password_button = AppButton(
            "Hide password" if getattr(self, "password_visible", False) else "Show password",
            self.toggle_password_visibility,
            compact=True,
            size_hint_x=1,
        )
        actions.add_widget(self.password_button)
        self.content.add_widget(actions)
        if self.signup_mode:
            self.content.add_widget(
                AppLabel(
                    "Use 12–128 characters. Passwords are securely hashed by the server. "
                    "By creating an account you agree to use sharing only with clear "
                    "consent; sharing starts disabled.",
                    size=12,
                    color=MUTED,
                    height=dp(65),
                )
            )
        self.status = AppLabel("", size=13, color=MUTED, height=dp(35))
        self.content.add_widget(self.status)
        self.submit_button = AppButton(
            "Create account" if self.signup_mode else "Sign in",
            self.submit,
            primary=True,
            height=dp(54),
        )
        self.content.add_widget(self.submit_button)
        self.content.add_widget(
            AppButton(
                "Already have an account? Sign in"
                if self.signup_mode
                else "New to Mobile Tracker? Create account",
                self.toggle_mode,
                compact=True,
                height=dp(46),
            )
        )
        self.content.add_widget(
            AppButton(
                "Configure API server",
                self.open_api_settings,
                compact=True,
                height=dp(44),
            )
        )
        self.content.add_widget(
            AppLabel(
                "Location and activity collection are not available in this build. "
                "No monitoring starts without your explicit action.",
                size=12,
                color=MUTED,
                height=dp(55),
            )
        )

    def toggle_password_visibility(self) -> None:
        self.password_visible = not getattr(self, "password_visible", False)
        for key in ("password", "confirm"):
            if key in self.fields:
                self.fields[key].password = not self.password_visible
        self.password_button.text = (
            "Hide password" if self.password_visible else "Show password"
        )

    def toggle_mode(self) -> None:
        if self._busy:
            return
        self.signup_mode = not self.signup_mode
        self.status = None
        self._render()

    def _validate(self) -> str | None:
        username = self.fields["username"].text.strip()
        password = self.fields["password"].text
        if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username):
            return "Username must be 3–30 letters, numbers, or underscores."
        if not password:
            return "Enter your password."
        if len(password) > 128:
            return "Password must be no more than 128 characters."
        if self.signup_mode:
            email = self.fields["email"].text.strip()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                return "Enter a valid email address."
            if len(password) < 12:
                return "Use at least 12 characters for your password."
            if self.fields["confirm"].text != password:
                return "The passwords do not match."
        return None

    def submit(self) -> None:
        if self._busy:
            return
        validation_error = self._validate()
        if validation_error:
            self.status.text = validation_error
            return

        app = App.get_running_app()
        is_signup = self.signup_mode
        username = self.fields["username"].text.strip()
        password = self.fields["password"].text
        self._busy = True
        self.submit_button.set_busy(True, "Creating account…" if is_signup else "Signing in…")
        self.status.text = "Connecting securely to your API…"

        if is_signup:
            email = self.fields["email"].text.strip()
            operation: Callable = lambda: app.api.signup(username, email, password)
        else:
            operation = lambda: app.api.login(username, password)

        def complete(result, error) -> None:
            def update_ui() -> None:
                self._busy = False
                self.submit_button.set_busy(False)
                if error:
                    self.status.text = str(error)
                    return
                if is_signup:
                    self.signup_mode = False
                    self._render()
                    self.status.text = "Account created. Sign in to continue."
                    return
                app.current_user = result
                app.shell.navigate("home")

            dispatch_to_ui(update_ui)

        app.api.run_async(operation, complete)

    def open_api_settings(self) -> None:
        App.get_running_app().shell.screens.current = "settings"
