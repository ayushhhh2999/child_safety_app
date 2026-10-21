from kivy.metrics import dp
from kivy.uix.screenmanager import Screen

from android_native.device import (
    NativeFeatureUnavailable,
    vibrate_once,
)
from components.theme import MUTED
from components.ui import AppButton, AppLabel, Card
from screens.common import add_heading, page_layout, show_message


class UnavailableDataScreen(Screen):
    page_title = "Data"
    subtitle = ""
    missing = ()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.root_layout, self.content = page_layout()
        self.add_widget(self.root_layout)

    def on_pre_enter(self, *_args) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.content.clear_widgets()
        add_heading(self.content, self.page_title, self.subtitle)
        card = Card(size_hint_y=None, height=dp(170))
        card.add_widget(
            AppLabel(
                "Not available yet",
                size=18,
                bold=True,
                height=dp(34),
            )
        )
        card.add_widget(
            AppLabel(
                "This screen is intentionally empty until the backend and native "
                "feature are implemented. No sample or guessed records are shown.",
                size=13,
                color=MUTED,
                height=dp(80),
            )
        )
        self.content.add_widget(card)
        self.content.add_widget(
            AppLabel(
                "Backend dependency: " + "; ".join(self.missing),
                size=13,
                color=MUTED,
                height=dp(100),
            )
        )


class LocationsScreen(UnavailableDataScreen):
    page_title = "Location"
    subtitle = "Only device-owner approved location data may appear here."
    missing = (
        "POST /api/locations",
        "GET /api/locations/me",
        "GET /api/connections/{connection_id}/locations",
        "location collection, runtime permission, foreground service and map UI",
    )


class ActivitiesScreen(UnavailableDataScreen):
    page_title = "App activity"
    subtitle = "A timeline will appear only when real, authorized events exist."
    missing = (
        "POST /api/activities",
        "GET /api/activities/me",
        "GET /api/connections/{connection_id}/activities",
        "Android Usage Access integration and event deduplication",
    )


class RestrictedAppsScreen(UnavailableDataScreen):
    page_title = "Restricted apps"
    subtitle = "Android restrictions are best-effort and never hidden."
    missing = (
        "restricted-app and restriction-alert backend endpoints",
        "an installed-app discovery and user-selected restriction store",
        "an explicitly configured AccessibilityService for launch detection",
    )

    def refresh(self) -> None:
        super().refresh()
        self.content.add_widget(
            AppLabel(
                "Usage Access and Accessibility are not requested by this build. "
                "The backend and native monitoring service are not implemented, "
                "so granting these special permissions would have no purpose.",
                size=13,
                color=MUTED,
                height=dp(88),
            )
        )
        self.content.add_widget(
            AppButton(
                "Test device vibration",
                self.test_vibration,
                height=dp(48),
            )
        )

    def test_vibration(self) -> None:
        try:
            vibrate_once()
        except NativeFeatureUnavailable as error:
            show_message("Vibration unavailable", str(error))
