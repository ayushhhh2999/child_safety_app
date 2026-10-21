from datetime import datetime, timezone
import webbrowser

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.checkbox import CheckBox
from kivy.uix.screenmanager import Screen

from android_native.device import (
    NativeFeatureUnavailable,
    accessibility_service_enabled,
    acknowledge_restriction_alerts,
    get_pending_restriction_alerts,
    has_usage_access,
    list_launchable_apps,
    open_accessibility_settings,
    open_usage_access_settings,
    read_recent_usage_events,
    request_current_location,
    set_restricted_packages,
    vibrate_once,
)
from components.theme import ACCENT, MUTED, SUCCESS
from components.ui import AppButton, AppLabel, Card
from screens.common import (
    add_heading,
    confirm_action,
    dispatch_to_ui,
    error_message,
    page_layout,
    show_message,
)


def _display_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%b %d, %Y · %H:%M:%S %Z")
    except (ValueError, TypeError):
        return "Time unavailable"


class ApiDataScreen(Screen):
    title = "Data"
    subtitle = ""
    empty_message = "No records yet."

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._generation = 0
        self.root_layout, self.content = page_layout()
        self.add_widget(self.root_layout)

    def on_pre_enter(self, *_args) -> None:
        if getattr(App.get_running_app(), "current_user", None):
            self.refresh()

    def load(self, api):
        raise NotImplementedError

    def render(self, records) -> None:
        raise NotImplementedError

    def add_controls(self) -> None:
        return

    def add_shared_feed_controls(self, loader, renderer) -> None:
        app = App.get_running_app()
        generation = self._generation
        user_id = app.current_user["id"]
        self.content.add_widget(
            AppLabel("Shared with you", size=17, bold=True, height=dp(34))
        )
        self.content.add_widget(
            AppLabel(
                "A feed is available only when that connection enabled the matching "
                "sharing permission and has not paused sharing.",
                size=12,
                color=MUTED,
                height=dp(42),
            )
        )
        self.shared_connections = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(6),
        )
        self.shared_connections.bind(
            minimum_height=self.shared_connections.setter("height")
        )
        self.content.add_widget(self.shared_connections)
        self.shared_results = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(6),
        )
        self.shared_results.bind(minimum_height=self.shared_results.setter("height"))
        self.content.add_widget(self.shared_results)
        app.api.run_async(
            app.api.get_connections,
            lambda connections, error: self._shared_connections_loaded(
                connections,
                error,
                loader,
                renderer,
                generation,
                user_id,
            ),
        )

    def _shared_connections_loaded(
        self, connections, error, loader, renderer, generation, user_id
    ) -> None:
        def update() -> None:
            app = App.get_running_app()
            user = getattr(app, "current_user", None)
            if (
                generation != self._generation
                or not isinstance(user, dict)
                or user.get("id") != user_id
            ):
                return
            self.shared_connections.clear_widgets()
            if error:
                self.shared_connections.add_widget(
                    AppLabel(error_message(error), size=12, color=MUTED)
                )
                return
            if not connections:
                self.shared_connections.add_widget(
                    AppLabel("No accepted connections to load.", size=12, color=MUTED)
                )
                return
            for connection in connections:
                card = Card(size_hint_y=None, height=dp(82))
                card.add_widget(
                    AppLabel(
                        f"@{connection['username']}",
                        size=14,
                        bold=True,
                        height=dp(28),
                    )
                )
                card.add_widget(
                    AppButton(
                        "Load shared data",
                        lambda connection_id=connection["id"],
                        username=connection["username"]: self.load_shared_feed(
                            connection_id,
                            username,
                            loader,
                            renderer,
                            generation,
                            user_id,
                        ),
                        compact=True,
                        height=dp(40),
                    )
                )
                self.shared_connections.add_widget(card)

        dispatch_to_ui(update)

    def load_shared_feed(
        self, connection_id, username, loader, renderer, generation, user_id
    ) -> None:
        self.shared_results.clear_widgets()
        self.shared_results.add_widget(
            AppLabel(f"Loading data shared by @{username}…", size=12, color=MUTED)
        )
        api = App.get_running_app().api
        api.run_async(
            lambda: loader(api, connection_id),
            lambda records, error: self._shared_feed_loaded(
                records,
                error,
                username,
                renderer,
                generation,
                user_id,
            ),
        )

    def _shared_feed_loaded(
        self, records, error, username, renderer, generation, user_id
    ) -> None:
        def update() -> None:
            app = App.get_running_app()
            user = getattr(app, "current_user", None)
            if (
                generation != self._generation
                or not isinstance(user, dict)
                or user.get("id") != user_id
            ):
                return
            self.shared_results.clear_widgets()
            if error:
                self.shared_results.add_widget(
                    AppLabel(
                        f"Data from @{username} is unavailable: "
                        f"{error_message(error)}",
                        size=12,
                        color=MUTED,
                    )
                )
                return
            renderer(self.shared_results, username, records)

        dispatch_to_ui(update)

    def refresh(self) -> None:
        app = App.get_running_app()
        if not getattr(app, "current_user", None):
            app.shell.screens.current = "auth"
            return
        self._generation += 1
        generation = self._generation
        user_id = app.current_user["id"]
        self.content.clear_widgets()
        add_heading(self.content, self.title, self.subtitle)
        self.status = AppLabel("Loading…", size=13, color=MUTED)
        self.content.add_widget(self.status)
        self.content.add_widget(
            AppButton("Refresh", self.refresh, compact=True, height=dp(42))
        )
        app.api.run_async(
            lambda: self.load(app.api),
            lambda result, error: self._loaded(result, error, generation, user_id),
        )

    def _loaded(self, records, error, generation: int, user_id: int) -> None:
        dispatch_to_ui(
            lambda: self._render_result(records, error, generation, user_id)
        )

    def _render_result(self, records, error, generation: int, user_id: int) -> None:
        app = App.get_running_app()
        user = getattr(app, "current_user", None)
        if (
            generation != self._generation
            or not isinstance(user, dict)
            or user.get("id") != user_id
        ):
            return
        self.content.clear_widgets()
        add_heading(self.content, self.title, self.subtitle)
        self.content.add_widget(
            AppButton("Refresh", self.refresh, compact=True, height=dp(42))
        )
        self.add_controls()
        if error:
            self.content.add_widget(
                AppLabel(error_message(error), size=13, color=MUTED)
            )
            self.content.add_widget(
                AppButton("Retry", self.refresh, primary=True, height=dp(46))
            )
            return
        self.render(records)

    def add_empty_state(self, message: str | None = None) -> None:
        card = Card(size_hint_y=None, height=dp(105))
        card.add_widget(
            AppLabel(
                message or self.empty_message,
                size=14,
                color=MUTED,
            )
        )
        self.content.add_widget(card)


class LocationsScreen(ApiDataScreen):
    title = "Location"
    subtitle = "Your device's location history. Sharing is controlled separately."
    empty_message = "No location updates have been recorded."

    @staticmethod
    def load(api):
        return api.get_locations(limit=50)

    def add_controls(self) -> None:
        self.location_button = AppButton(
            "Record my current location",
            self.capture_location,
            primary=True,
            height=dp(48),
        )
        self.content.add_widget(self.location_button)
        self.location_status = AppLabel(
            "One-time capture only; it runs after you tap the button.",
            size=12,
            color=MUTED,
            height=dp(42),
        )
        self.content.add_widget(self.location_status)
        self.add_shared_feed_controls(
            lambda api, connection_id: api.get_shared_locations(
                connection_id, limit=50
            ),
            self._render_shared_locations,
        )

    @staticmethod
    def _render_shared_locations(container, username, records) -> None:
        container.add_widget(
            AppLabel(f"Location shared by @{username}", size=14, bold=True)
        )
        if not records:
            container.add_widget(
                AppLabel("No shared location updates.", size=12, color=MUTED)
            )
            return
        for location in records:
            container.add_widget(
                AppLabel(
                    f"{float(location['latitude']):.6f}, "
                    f"{float(location['longitude']):.6f} · "
                    f"{_display_time(location['recorded_at'])}",
                    size=12,
                    color=MUTED,
                    height=dp(32),
                )
            )

    def capture_location(self) -> None:
        if getattr(self, "_capture_busy", False):
            return
        self._capture_busy = True
        self._capture_user_id = App.get_running_app().current_user["id"]
        self.location_button.set_busy(True, "Requesting location…")
        self.location_status.text = (
            "Android may ask you to grant location permission."
        )
        try:
            request_current_location(self._location_captured)
        except NativeFeatureUnavailable as error:
            self._location_captured(None, error)

    def _location_captured(self, location, error) -> None:
        dispatch_to_ui(lambda: self._finish_location_capture(location, error))

    def _finish_location_capture(self, location, error) -> None:
        app = App.get_running_app()
        user = getattr(app, "current_user", None)
        if not isinstance(user, dict) or user.get("id") != self._capture_user_id:
            self._capture_busy = False
            return
        if error or location is None:
            self._capture_busy = False
            self.location_button.set_busy(False)
            self.location_status.text = error_message(error)
            return

        self.location_status.text = "Location captured. Uploading securely…"
        user_id = self._capture_user_id
        app.api.run_async(
            lambda: app.api.create_location(
                latitude=location["latitude"],
                longitude=location["longitude"],
                accuracy_meters=location["accuracy_meters"],
                recorded_at=location["recorded_at"],
            ),
            lambda result, upload_error: self._location_uploaded(
                result, upload_error, user_id
            ),
        )

    def _location_uploaded(self, result, error, user_id) -> None:
        dispatch_to_ui(lambda: self._finish_location_upload(result, error, user_id))

    def _finish_location_upload(self, _result, error, user_id) -> None:
        self._capture_busy = False
        self.location_button.set_busy(False)
        app = App.get_running_app()
        user = getattr(app, "current_user", None)
        if not isinstance(user, dict) or user.get("id") != user_id:
            return
        if error:
            self.location_status.text = (
                "Location was captured on this device but could not be uploaded: "
                f"{error_message(error)}"
            )
            return
        self.location_status.text = "Location uploaded to your account."
        self.refresh()

    def render(self, records) -> None:
        if not records:
            self.add_empty_state()
            self.content.add_widget(
                AppLabel(
                    "No background location tracking is performed. Each update is "
                    "collected only after you tap the button above.",
                    size=12,
                    color=MUTED,
                    height=dp(58),
                )
            )
            return
        self.content.add_widget(
            AppLabel(
                f"{len(records)} recent update(s)",
                size=13,
                color=SUCCESS,
                height=dp(30),
            )
        )
        for location in records:
            latitude = float(location["latitude"])
            longitude = float(location["longitude"])
            card = Card(size_hint_y=None, height=dp(166))
            card.add_widget(
                AppLabel(
                    f"{latitude:.6f}, {longitude:.6f}",
                    size=17,
                    bold=True,
                    color=ACCENT,
                    height=dp(30),
                )
            )
            accuracy = location.get("accuracy_meters")
            card.add_widget(
                AppLabel(
                    f"Accuracy ±{float(accuracy):.0f} m"
                    if accuracy is not None
                    else "Accuracy not reported",
                    size=12,
                    color=MUTED,
                    height=dp(25),
                )
            )
            card.add_widget(
                AppLabel(
                    _display_time(location["recorded_at"]),
                    size=12,
                    color=MUTED,
                    height=dp(24),
                )
            )
            card.add_widget(
                AppButton(
                    "Open in map",
                    lambda lat=latitude, lon=longitude: webbrowser.open(
                        f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
                    ),
                    compact=True,
                    height=dp(38),
                )
            )
            self.content.add_widget(card)


class ActivitiesScreen(ApiDataScreen):
    title = "App activity"
    subtitle = "Usage events reported by this device."
    empty_message = "No app-usage events have been recorded."

    @staticmethod
    def load(api):
        return api.get_activities(limit=50)

    def add_controls(self) -> None:
        self.usage_status = AppLabel(
            "Checking Android Usage Access…",
            size=12,
            color=MUTED,
            height=dp(38),
        )
        self.content.add_widget(self.usage_status)
        self.usage_button = AppButton(
            "Enable Usage Access",
            self.enable_usage_access,
            height=dp(46),
        )
        self.content.add_widget(self.usage_button)
        self.sync_button = AppButton(
            "Sync app activity from the last 24 hours",
            self.sync_usage_events,
            primary=True,
            height=dp(48),
        )
        self.content.add_widget(self.sync_button)
        self.add_shared_feed_controls(
            lambda api, connection_id: api.get_shared_activities(
                connection_id, limit=50
            ),
            self._render_shared_activities,
        )
        try:
            self._set_usage_status(has_usage_access())
        except NativeFeatureUnavailable:
            self.usage_status.text = (
                "Usage Access can be enabled only in the Android app."
            )
            self.usage_button.disabled = True
            self.sync_button.disabled = True

    @staticmethod
    def _render_shared_activities(container, username, records) -> None:
        container.add_widget(
            AppLabel(f"App activity shared by @{username}", size=14, bold=True)
        )
        if not records:
            container.add_widget(
                AppLabel("No shared app-usage events.", size=12, color=MUTED)
            )
            return
        for event in records:
            container.add_widget(
                AppLabel(
                    f"{event['app_name']} · {event['event_type'].capitalize()} · "
                    f"{_display_time(event['recorded_at'])}",
                    size=12,
                    color=MUTED,
                    height=dp(32),
                )
            )

    def _set_usage_status(self, enabled: bool) -> None:
        self.usage_status.text = (
            "Usage Access is enabled. Sync is manual and limited to the last 24h."
            if enabled
            else "Usage Access is off. Enable it before syncing app events."
        )
        self.usage_button.text = (
            "Usage Access enabled" if enabled else "Enable Usage Access"
        )
        self.sync_button.disabled = not enabled

    def enable_usage_access(self) -> None:
        try:
            confirm_action(
                "Enable Usage Access",
                "Android will show an operating-system settings page. Mobile "
                "Tracker can then read app foreground/background timestamps for "
                "the last 24 hours when you manually sync. It does not read screen "
                "contents. You can revoke this access in Android Settings.",
                open_usage_access_settings,
            )
        except NativeFeatureUnavailable as error:
            show_message("Usage Access unavailable", str(error))

    def sync_usage_events(self) -> None:
        if getattr(self, "_sync_busy", False):
            return
        try:
            if not has_usage_access():
                self._set_usage_status(False)
                return
        except NativeFeatureUnavailable as error:
            show_message("Usage Access unavailable", str(error))
            return
        self._sync_busy = True
        self.sync_button.set_busy(True, "Reading app activity…")
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_ms = now_ms - 24 * 60 * 60 * 1000
        api = App.get_running_app().api
        api.run_async(
            lambda: self._read_and_upload_events(api, start_ms, now_ms),
            self._usage_sync_finished,
        )

    @staticmethod
    def _read_and_upload_events(api, start_ms: int, end_ms: int) -> int:
        events = read_recent_usage_events(start_ms, end_ms)
        for event in events:
            recorded_at = datetime.fromtimestamp(
                event["recorded_at"] / 1000,
                timezone.utc,
            ).isoformat()
            api.create_activity(
                package_name=event["package_name"],
                app_name=event["app_name"],
                event_type=event["event_type"],
                recorded_at=recorded_at,
            )
        return len(events)

    def _usage_sync_finished(self, count, error) -> None:
        dispatch_to_ui(lambda: self._finish_usage_sync(count, error))

    def _finish_usage_sync(self, count, error) -> None:
        self._sync_busy = False
        if hasattr(self, "sync_button"):
            self.sync_button.set_busy(False)
        if error:
            show_message("Activity sync failed", error_message(error))
            return
        show_message(
            "Activity synced",
            f"Uploaded {count} app-usage event(s) from the last 24 hours.",
        )
        self.refresh()

    def render(self, records) -> None:
        if not records:
            self.add_empty_state()
            self.content.add_widget(
                AppLabel(
                    "Usage events are collected only when you manually sync. "
                    "No screen contents or fabricated session durations are stored.",
                    size=12,
                    color=MUTED,
                    height=dp(58),
                )
            )
            return
        for event in records:
            card = Card(size_hint_y=None, height=dp(94))
            card.add_widget(
                AppLabel(event["app_name"], size=16, bold=True, height=dp(28))
            )
            card.add_widget(
                AppLabel(
                    f"{event['event_type'].capitalize()} · "
                    f"{_display_time(event['recorded_at'])}",
                    size=12,
                    color=MUTED,
                    height=dp(24),
                )
            )
            self.content.add_widget(card)


class RestrictedAppsScreen(ApiDataScreen):
    title = "Restricted apps"
    subtitle = "Restrictions only work when the device owner enables the service."
    empty_message = "No restricted apps selected."

    def __init__(self, **kwargs):
        self._available_apps = []
        self._selected_packages = set()
        super().__init__(**kwargs)

    @staticmethod
    def load(api):
        return api.get_restricted_apps(), api.get_restriction_alerts(limit=50)

    def add_controls(self) -> None:
        try:
            service_enabled = accessibility_service_enabled()
            self._service_available = True
        except NativeFeatureUnavailable:
            service_enabled = False
            self._service_available = False
        self.service_status = AppLabel(
            "Accessibility service enabled"
            if service_enabled
            else "Accessibility service is off",
            size=12,
            color=SUCCESS if service_enabled else MUTED,
            height=dp(30),
        )
        self.content.add_widget(self.service_status)
        self.content.add_widget(
            AppButton(
                "Load installed apps",
                self.load_installed_apps,
                height=dp(46),
            )
        )
        if self._service_available:
            self.content.add_widget(
                AppButton(
                    "Enable / review Accessibility service",
                    self.enable_accessibility_service,
                    height=dp(46),
                )
            )
        else:
            self.content.add_widget(
                AppLabel(
                    "App selection and blocking require the Android APK.",
                    size=12,
                    color=MUTED,
                    height=dp(34),
                )
            )
        self.app_selection = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(6),
        )
        self.app_selection.bind(minimum_height=self.app_selection.setter("height"))
        self.content.add_widget(self.app_selection)
        self.save_selection_button = AppButton(
            "Save selected apps",
            self.save_restricted_apps,
            primary=True,
            height=dp(48),
        )
        self.content.add_widget(self.save_selection_button)
        self.content.add_widget(
            AppButton(
                "Sync restriction alerts",
                self.sync_restriction_alerts,
                height=dp(44),
            )
        )
        self.add_shared_feed_controls(
            lambda api, connection_id: api.get_shared_restriction_alerts(
                connection_id, limit=50
            ),
            self._render_shared_alerts,
        )

    @staticmethod
    def _render_shared_alerts(container, username, alerts) -> None:
        container.add_widget(
            AppLabel(f"Restriction alerts shared by @{username}", size=14, bold=True)
        )
        if not alerts:
            container.add_widget(
                AppLabel("No shared restriction alerts.", size=12, color=MUTED)
            )
            return
        for alert in alerts:
            container.add_widget(
                AppLabel(
                    f"{alert['app_name']} · {_display_time(alert['recorded_at'])}",
                    size=12,
                    color=MUTED,
                    height=dp(32),
                )
            )

    def load_installed_apps(self) -> None:
        try:
            self._available_apps = list_launchable_apps()
        except NativeFeatureUnavailable as error:
            show_message("Installed apps unavailable", str(error))
            return
        self.app_selection.clear_widgets()
        for installed_app in self._available_apps:
            row = BoxLayout(
                size_hint_y=None,
                height=dp(44),
                spacing=dp(8),
            )
            checkbox = CheckBox(
                active=installed_app["package_name"] in self._selected_packages,
                size_hint_x=None,
                width=dp(46),
            )
            package_name = installed_app["package_name"]
            checkbox.bind(
                active=lambda _box, active, package=package_name:
                    self._toggle_selected_package(package, active)
            )
            row.add_widget(checkbox)
            row.add_widget(AppLabel(installed_app["app_name"], size=13))
            self.app_selection.add_widget(row)
        if not self._available_apps:
            self.app_selection.add_widget(
                AppLabel("No launchable apps were found.", size=12, color=MUTED)
            )

    def _toggle_selected_package(self, package_name: str, active: bool) -> None:
        if active:
            self._selected_packages.add(package_name)
        else:
            self._selected_packages.discard(package_name)

    def enable_accessibility_service(self) -> None:
        try:
            confirm_action(
                "Enable app blocking",
                "Android Accessibility access lets this app detect which app is "
                "foregrounded. Only apps you select will be sent back to the home "
                "screen. Screen contents are not read or uploaded. You can disable "
                "this service in Android Settings at any time.",
                open_accessibility_settings,
            )
        except NativeFeatureUnavailable as error:
            show_message("Service unavailable", str(error))

    def save_restricted_apps(self) -> None:
        if not self._available_apps:
            show_message("Load apps first", "Load installed apps before saving.")
            return
        selected = [
            installed_app for installed_app in self._available_apps
            if installed_app["package_name"] in self._selected_packages
        ]
        self.save_selection_button.set_busy(True, "Saving…")
        api = App.get_running_app().api
        api.run_async(
            lambda: api.update_restricted_apps(selected),
            lambda records, error: self._restricted_apps_saved(
                records, error, selected
            ),
        )

    def _restricted_apps_saved(self, records, error, selected) -> None:
        dispatch_to_ui(
            lambda: self._finish_restricted_apps_save(records, error, selected)
        )

    def _finish_restricted_apps_save(self, records, error, selected) -> None:
        self.save_selection_button.set_busy(False)
        if error:
            show_message("Could not save apps", error_message(error))
            return
        try:
            set_restricted_packages(
                [installed_app["package_name"] for installed_app in selected]
            )
        except NativeFeatureUnavailable as native_error:
            show_message(
                "Saved to your account",
                "The server selection was saved, but this device could not save "
                f"the local blocking rules: {native_error}",
            )
            return
        show_message(
            "Apps saved",
            f"Saved {len(records)} restricted app(s). Blocking is active only "
            "while the Accessibility service is enabled.",
        )
        self.refresh()

    def sync_restriction_alerts(self) -> None:
        try:
            pending = get_pending_restriction_alerts()
        except NativeFeatureUnavailable as error:
            show_message("Alerts unavailable", str(error))
            return
        if not pending:
            show_message("No pending alerts", "There are no new device alerts.")
            return
        api = App.get_running_app().api
        api.run_async(
            lambda: self._upload_restriction_alerts(api, pending),
            lambda uploaded, error: self._restriction_alerts_synced(
                uploaded, error, pending
            ),
        )

    @staticmethod
    def _upload_restriction_alerts(api, alerts) -> list[str]:
        uploaded_ids = []
        for alert in alerts:
            api.create_restriction_alert(
                package_name=alert["package_name"],
                app_name=alert["app_name"],
                recorded_at=alert["recorded_at"],
                details="Blocked by the device owner's selected-app rule.",
            )
            uploaded_ids.append(alert["id"])
        return uploaded_ids

    def _restriction_alerts_synced(self, uploaded, error, _pending) -> None:
        dispatch_to_ui(
            lambda: self._finish_restriction_alert_sync(uploaded, error)
        )

    def _finish_restriction_alert_sync(self, uploaded, error) -> None:
        if error:
            show_message("Alert sync failed", error_message(error))
            return
        try:
            acknowledge_restriction_alerts(uploaded)
        except NativeFeatureUnavailable as native_error:
            show_message("Alerts uploaded", str(native_error))
            return
        self.refresh()

    def render(self, result) -> None:
        apps, alerts = result
        state = Card(size_hint_y=None, height=dp(108))
        state.add_widget(
            AppLabel(
                "App blocking requires your explicit Android opt-in",
                size=16,
                bold=True,
                height=dp(32),
            )
        )
        state.add_widget(
            AppLabel(
                "Only selected apps are blocked, and only while the Accessibility "
                "service is enabled. You can disable it in Android Settings.",
                size=12,
                color=MUTED,
                height=dp(58),
            )
        )
        self.content.add_widget(state)

        self.content.add_widget(
            AppLabel("Selected apps", size=17, bold=True, height=dp(34))
        )
        self._selected_packages = {
            app["package_name"] for app in apps
        }
        if self._service_available:
            try:
                set_restricted_packages(list(self._selected_packages))
            except NativeFeatureUnavailable as error:
                self.content.add_widget(
                    AppLabel(
                        f"Could not sync local blocking rules: {error}",
                        size=12,
                        color=MUTED,
                    )
                )
        if apps:
            for app in apps:
                card = Card(size_hint_y=None, height=dp(60))
                card.add_widget(AppLabel(app["app_name"], size=14, bold=True))
                self.content.add_widget(card)
        else:
            self.add_empty_state()

        self.content.add_widget(
            AppLabel("Recent restriction alerts", size=17, bold=True, height=dp(34))
        )
        if alerts:
            for alert in alerts:
                card = Card(size_hint_y=None, height=dp(86))
                card.add_widget(
                    AppLabel(alert["app_name"], size=14, bold=True, height=dp(26))
                )
                card.add_widget(
                    AppLabel(
                        _display_time(alert["recorded_at"]),
                        size=12,
                        color=MUTED,
                        height=dp(24),
                    )
                )
                self.content.add_widget(card)
        else:
            self.add_empty_state("No restriction alerts recorded.")

        self.content.add_widget(
            AppButton(
                "Test device vibration",
                self.test_vibration,
                height=dp(48),
            )
        )

    @staticmethod
    def test_vibration() -> None:
        try:
            vibrate_once()
        except NativeFeatureUnavailable as error:
            show_message("Vibration unavailable", str(error))
