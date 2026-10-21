from functools import partial

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.switch import Switch

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

_PERMISSIONS = (
    (
        "Location",
        "share_location",
        "Allows this connection to access your shared location when a "
        "location feature is implemented.",
    ),
    (
        "App activity",
        "share_app_usage",
        "Allows this connection to access shared app-usage events when available.",
    ),
    (
        "Restricted-app alerts",
        "share_restriction_alerts",
        "Allows this connection to receive restriction alerts when supported.",
    ),
    ("Pause sharing", "paused", "Temporarily disables all sharing for this connection."),
)


class ConnectionsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.root_layout, self.content = page_layout()
        self.add_widget(self.root_layout)

    def on_pre_enter(self, *_args) -> None:
        if getattr(App.get_running_app(), "current_user", None):
            self.refresh()

    def refresh(self) -> None:
        self.content.clear_widgets()
        add_heading(
            self.content,
            "Your people",
            "Connect only with people you trust. Sharing is always your choice.",
        )
        form = Card(size_hint_y=None, height=dp(135))
        self.search_input = text_field("Search exact username")
        form.add_widget(self.search_input)
        form.add_widget(
            AppButton("Search", self.search, primary=True, height=dp(44))
        )
        self.content.add_widget(form)
        self.search_result = None
        self.content.add_widget(
            AppLabel("Connection requests", size=18, bold=True, height=dp(36))
        )
        self.request_status = AppLabel("Loading requests…", size=13, color=MUTED)
        self.content.add_widget(self.request_status)
        self.request_list = BoxLayout(
            orientation="vertical",
            spacing=dp(9),
            size_hint_y=None,
        )
        self.request_list.bind(minimum_height=self.request_list.setter("height"))
        self.content.add_widget(self.request_list)
        self.content.add_widget(
            AppLabel("Accepted connections", size=18, bold=True, height=dp(36))
        )
        self.connections_status = AppLabel(
            "Loading connections…", size=13, color=MUTED
        )
        self.content.add_widget(self.connections_status)
        self.connections_list = BoxLayout(
            orientation="vertical",
            spacing=dp(11),
            size_hint_y=None,
        )
        self.connections_list.bind(
            minimum_height=self.connections_list.setter("height")
        )
        self.content.add_widget(self.connections_list)
        App.get_running_app().api.run_async(self._load, self._loaded)

    @staticmethod
    def _load():
        api = App.get_running_app().api
        return api.get_requests(), api.get_connections()

    def _loaded(self, result, error) -> None:
        dispatch_to_ui(lambda: self._render_lists(result, error))

    def _render_lists(self, result, error) -> None:
        self.request_list.clear_widgets()
        self.connections_list.clear_widgets()
        if error:
            message = error_message(error)
            self.request_status.text = message
            self.connections_status.text = message
            self.request_list.add_widget(
                AppButton("Retry", self.refresh, primary=True, height=dp(44))
            )
            return
        requests, connections = result
        self.request_status.text = (
            f"{len(requests)} pending request(s)"
            if requests
            else "No pending requests."
        )
        self.connections_status.text = (
            f"{len(connections)} accepted connection(s)"
            if connections
            else "No accepted connections yet."
        )
        for request in requests:
            self._render_request(request)
        for connection in connections:
            self._render_connection(connection)

    def _render_request(self, request: dict) -> None:
        card = Card(size_hint_y=None, height=dp(120))
        card.add_widget(
            AppLabel(
                f"@{request['username']}",
                size=16,
                bold=True,
                height=dp(28),
            )
        )
        incoming = request["direction"] == "incoming"
        card.add_widget(
            AppLabel(
                "Wants to connect with you"
                if incoming
                else "Request sent · waiting for response",
                size=12,
                color=MUTED,
            )
        )
        if incoming:
            buttons = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
            buttons.add_widget(
                AppButton(
                    "Accept",
                    partial(self.resolve_request, request["id"], True),
                    primary=True,
                    compact=True,
                    size_hint_x=1,
                )
            )
            buttons.add_widget(
                AppButton(
                    "Decline",
                    partial(self.resolve_request, request["id"], False),
                    compact=True,
                    size_hint_x=1,
                )
            )
            card.add_widget(buttons)
        self.request_list.add_widget(card)

    def _render_connection(self, connection: dict) -> None:
        card = Card(
            size_hint_y=None,
            padding=dp(16),
            spacing=dp(8),
        )
        card.add_widget(
            AppLabel(f"@{connection['username']}", size=17, bold=True, height=dp(30))
        )
        card.add_widget(
            AppLabel(
                "Accepted · only your own settings below control what you share.",
                size=12,
                color=SUCCESS,
            )
        )
        load_label = AppLabel("Loading your consent settings…", size=12, color=MUTED)
        card.add_widget(load_label)
        card.height = dp(116)
        self.connections_list.add_widget(card)
        api = App.get_running_app().api
        api.run_async(
            lambda: api.get_permissions(connection["id"]),
            lambda result, error: dispatch_to_ui(
                lambda: self._render_permission_settings(
                    card, connection, load_label, result, error
                )
            ),
        )

    def _render_permission_settings(
        self,
        card: Card,
        connection: dict,
        status: AppLabel,
        permissions,
        error,
    ) -> None:
        if error:
            status.text = f"Consent unavailable: {error_message(error)}"
            card.height = dp(166)
            card.add_widget(
                AppButton(
                    "Retry",
                    self.refresh,
                    primary=True,
                    compact=True,
                    height=dp(42),
                )
            )
            return
        card.remove_widget(status)
        for label, field, detail in _PERMISSIONS:
            row = BoxLayout(
                size_hint_y=None,
                height=dp(54),
                spacing=dp(7),
            )
            row.add_widget(
                AppLabel(
                    f"[b]{label}[/b]\n{detail}",
                    size=11,
                    markup=True,
                    color=MUTED,
                    height=dp(48),
                )
            )
            toggle = Switch(active=bool(permissions[field]))
            toggle.bind(
                active=partial(
                    self._permission_changed,
                    connection["id"],
                    field,
                    toggle,
                )
            )
            row.add_widget(toggle)
            card.add_widget(row)
        card.height = dp(126 + len(_PERMISSIONS) * 58 + 54)
        card.add_widget(
            AppButton(
                "Disconnect",
                lambda: self.confirm_disconnect(connection["id"]),
                compact=True,
                height=dp(44),
            )
        )

    def search(self) -> None:
        username = self.search_input.text.strip()
        if len(username) < 3:
            show_message("Check username", "Enter at least 3 characters.")
            return
        self.search_result = None
        self.search_card = Card(size_hint_y=None, height=dp(90))
        self.search_card.add_widget(AppLabel("Searching…", size=13, color=MUTED))
        self.content.add_widget(self.search_card, index=2)
        api = App.get_running_app().api
        api.run_async(
            lambda: api.search_user(username),
            lambda result, error: dispatch_to_ui(
                lambda: self._show_search_result(result, error)
            ),
        )

    def _show_search_result(self, result, error) -> None:
        if not self.search_card.parent:
            return
        self.search_card.clear_widgets()
        if error:
            self.search_card.height = dp(82)
            self.search_card.add_widget(
                AppLabel(error_message(error), size=13, color=MUTED)
            )
        elif result is None:
            self.search_card.height = dp(82)
            self.search_card.add_widget(
                AppLabel("No matching username found.", size=13, color=MUTED)
            )
        else:
            self.search_card.height = dp(112)
            self.search_card.add_widget(
                AppLabel(f"Connect with @{result['username']}?", bold=True)
            )
            self.search_card.add_widget(
                AppButton(
                    "Send request",
                    partial(self.send_request, result["username"]),
                    primary=True,
                    height=dp(44),
                )
            )

    def send_request(self, username: str) -> None:
        api = App.get_running_app().api
        api.run_async(
            lambda: api.send_connection_request(username),
            lambda _result, error: dispatch_to_ui(
                lambda: self._request_sent(error)
            ),
        )

    def _request_sent(self, error) -> None:
        if error:
            show_message("Request not sent", error_message(error))
        else:
            show_message(
                "Request sent",
                "The other person must accept. Your sharing permissions remain off.",
            )
            self.refresh()

    def resolve_request(self, connection_id: int, accept: bool) -> None:
        api = App.get_running_app().api
        resolve = api.accept_request if accept else api.reject_request
        api.run_async(
            lambda: resolve(connection_id),
            lambda _result, error: dispatch_to_ui(
                lambda: self._request_resolved(error)
            ),
        )

    def _request_resolved(self, error) -> None:
        if error:
            show_message("Request update failed", error_message(error))
        else:
            self.refresh()

    def _permission_changed(
        self, connection_id: int, field: str, toggle: Switch, _switch, value: bool
    ) -> None:
        toggle.disabled = True
        api = App.get_running_app().api
        api.run_async(
            lambda: api.update_permissions(connection_id, **{field: bool(value)}),
            lambda _result, error: dispatch_to_ui(
                lambda: self._permission_updated(error, toggle)
            ),
        )

    def _permission_updated(self, error, toggle: Switch) -> None:
        if error:
            toggle.disabled = True
            show_message("Consent not updated", error_message(error))
            self.refresh()
            return
        self.refresh()

    def confirm_disconnect(self, connection_id: int) -> None:
        confirm_action(
            "Disconnect?",
            "This immediately revokes this connection's access to your shared data.",
            partial(self._disconnect, connection_id),
        )

    def _disconnect(self, connection_id: int) -> None:
        api = App.get_running_app().api
        api.run_async(
            lambda: api.disconnect(connection_id),
            lambda _result, error: dispatch_to_ui(
                lambda: self._disconnected(error)
            ),
        )

    def _disconnected(self, error) -> None:
        if error:
            show_message("Disconnect failed", error_message(error))
        else:
            self.refresh()
