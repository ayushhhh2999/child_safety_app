import json
from datetime import datetime, timezone


class NativeFeatureUnavailable(RuntimeError):
    pass


def _android_context():
    try:
        from jnius import autoclass
        from kivy.utils import platform
    except ImportError as error:
        raise NativeFeatureUnavailable(
            "This device feature is available only in the Android APK."
        ) from error
    if platform != "android":
        raise NativeFeatureUnavailable(
            "This device feature is available only in the Android APK."
        )
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    return autoclass, activity


def vibrate_once(milliseconds: int = 120) -> None:
    try:
        from jnius import autoclass
    except ImportError as error:
        raise NativeFeatureUnavailable(
            "Vibration testing is available only in the Android APK."
        ) from error

    try:
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Context = autoclass("android.content.Context")
        activity = PythonActivity.mActivity
        vibrator = activity.getSystemService(Context.VIBRATOR_SERVICE)
        if vibrator is None or not vibrator.hasVibrator():
            raise NativeFeatureUnavailable(
                "This device does not provide a vibration motor."
            )
        vibrator.vibrate(milliseconds)
    except NativeFeatureUnavailable:
        raise
    except Exception as error:
        raise NativeFeatureUnavailable(
            f"Could not access the device vibrator: {error}"
        ) from error


def has_usage_access() -> bool:
    autoclass, activity = _android_context()
    app_ops = activity.getSystemService("appops")
    process = autoclass("android.os.Process")
    app_ops_class = autoclass("android.app.AppOpsManager")
    try:
        operation = app_ops_class.OPSTR_GET_USAGE_STATS
        mode = app_ops.checkOpNoThrow(
            operation,
            process.myUid(),
            activity.getPackageName(),
        )
        return mode == app_ops_class.MODE_ALLOWED
    except Exception as error:
        raise NativeFeatureUnavailable(
            f"Could not check Usage Access: {error}"
        ) from error


def open_usage_access_settings() -> None:
    autoclass, activity = _android_context()
    intent = autoclass("android.content.Intent")(
        autoclass("android.provider.Settings").ACTION_USAGE_ACCESS_SETTINGS
    )
    activity.startActivity(intent)


def read_recent_usage_events(start_time_ms: int, end_time_ms: int) -> list[dict]:
    autoclass, activity = _android_context()
    if not has_usage_access():
        raise NativeFeatureUnavailable(
            "Enable Usage Access for Mobile Tracker in Android Settings first."
        )
    usage_manager = activity.getSystemService("usagestats")
    usage_events = usage_manager.queryEvents(start_time_ms, end_time_ms)
    event_class = autoclass("android.app.usage.UsageEvents$Event")
    build_version = autoclass("android.os.Build$VERSION")
    if build_version.SDK_INT >= 29:
        foreground_types = {
            event_class.ACTIVITY_RESUMED,
            event_class.MOVE_TO_FOREGROUND,
        }
        background_types = {
            event_class.ACTIVITY_PAUSED,
            event_class.MOVE_TO_BACKGROUND,
        }
    else:
        foreground_types = {event_class.MOVE_TO_FOREGROUND}
        background_types = {event_class.MOVE_TO_BACKGROUND}
    package_manager = activity.getPackageManager()
    own_package = activity.getPackageName()
    event = event_class()
    results = []
    while usage_events.hasNextEvent():
        usage_events.getNextEvent(event)
        package_name = event.getPackageName()
        if not package_name or package_name == own_package:
            continue
        event_type = event.getEventType()
        if event_type in foreground_types:
            kind = "opened"
        elif event_type in background_types:
            kind = "closed"
        else:
            continue
        try:
            app_info = package_manager.getApplicationInfo(package_name, 0)
            app_name = str(package_manager.getApplicationLabel(app_info))
        except Exception:
            app_name = package_name
        results.append(
            {
                "package_name": package_name,
                "app_name": app_name,
                "event_type": kind,
                "recorded_at": event.getTimeStamp(),
            }
        )
    return results


def list_launchable_apps() -> list[dict[str, str]]:
    autoclass, activity = _android_context()
    intent_class = autoclass("android.content.Intent")
    intent = intent_class(intent_class.ACTION_MAIN)
    intent.addCategory(intent_class.CATEGORY_LAUNCHER)
    package_manager = activity.getPackageManager()
    own_package = activity.getPackageName()
    apps = {}
    for resolve_info in package_manager.queryIntentActivities(intent, 0):
        app_info = resolve_info.activityInfo.applicationInfo
        package_name = str(app_info.packageName)
        if package_name == own_package or package_name in apps:
            continue
        apps[package_name] = {
            "package_name": package_name,
            "app_name": str(package_manager.getApplicationLabel(app_info)),
        }
    return sorted(apps.values(), key=lambda item: item["app_name"].casefold())


def accessibility_service_enabled() -> bool:
    autoclass, activity = _android_context()
    secure_settings = autoclass("android.provider.Settings$Secure")
    component_class = autoclass("android.content.ComponentName")
    service_class = autoclass(
        "org.mobiletracker.mobiletracker.RestrictionAccessibilityService"
    )
    component = component_class(activity, service_class)
    enabled_services = secure_settings.getString(
        activity.getContentResolver(),
        secure_settings.ENABLED_ACCESSIBILITY_SERVICES,
    )
    return bool(
        enabled_services
        and component.flattenToString() in str(enabled_services).split(":")
    )


def open_accessibility_settings() -> None:
    autoclass, activity = _android_context()
    intent = autoclass("android.content.Intent")(
        autoclass("android.provider.Settings").ACTION_ACCESSIBILITY_SETTINGS
    )
    activity.startActivity(intent)


def set_restricted_packages(package_names: list[str]) -> None:
    autoclass, activity = _android_context()
    hash_set = autoclass("java.util.HashSet")()
    for package_name in package_names:
        hash_set.add(package_name)
    preferences = activity.getSharedPreferences(
        "mobile_tracker_restrictions",
        autoclass("android.content.Context").MODE_PRIVATE,
    )
    preferences.edit().putStringSet("package_names", hash_set).apply()


def get_pending_restriction_alerts() -> list[dict]:
    autoclass, activity = _android_context()
    service_class = autoclass(
        "org.mobiletracker.mobiletracker.RestrictionAccessibilityService"
    )
    serialized = service_class.getPendingRestrictionAlerts(activity)
    try:
        alerts = json.loads(str(serialized))
    except (TypeError, json.JSONDecodeError) as error:
        raise NativeFeatureUnavailable(
            "The Android service returned invalid pending alerts."
        ) from error
    if not isinstance(alerts, list) or any(
        not isinstance(alert, dict)
        or not all(
            isinstance(alert.get(field), str)
            for field in ("id", "package_name", "app_name", "recorded_at")
        )
        for alert in alerts
    ):
        raise NativeFeatureUnavailable(
            "The Android service returned malformed pending alerts."
        )
    return alerts


def acknowledge_restriction_alerts(alert_ids: list[str]) -> None:
    autoclass, activity = _android_context()
    service_class = autoclass(
        "org.mobiletracker.mobiletracker.RestrictionAccessibilityService"
    )
    service_class.acknowledgeRestrictionAlerts(
        activity,
        json.dumps(alert_ids),
    )


_location_listener = None
_location_timeout = None


def request_current_location(callback) -> None:
    global _location_listener, _location_timeout

    try:
        autoclass, activity = _android_context()
        from android.permissions import (
            Permission,
            check_permission,
            request_permissions,
        )
        from jnius import PythonJavaClass, java_method
        from kivy.clock import Clock
    except ImportError as error:
        callback(None, NativeFeatureUnavailable(
            "Location capture requires the Android application."
        ))
        return

    permissions = [Permission.ACCESS_FINE_LOCATION, Permission.ACCESS_COARSE_LOCATION]
    granted = [check_permission(permission) for permission in permissions]
    if not any(granted):
        def permission_result(_permissions, grant_results) -> None:
            if not any(grant_results):
                callback(None, NativeFeatureUnavailable(
                    "Location permission was not granted."
                ))
                return
            _start_location_request(
                autoclass, activity, callback, Clock, PythonJavaClass, java_method
            )

        request_permissions(permissions, permission_result)
        return
    _start_location_request(
        autoclass, activity, callback, Clock, PythonJavaClass, java_method
    )


def _start_location_request(
    autoclass, activity, callback, Clock, PythonJavaClass, java_method
) -> None:
    global _location_listener, _location_timeout
    location_manager = activity.getSystemService("location")
    if not location_manager.isProviderEnabled("gps") and not location_manager.isProviderEnabled("network"):
        callback(None, NativeFeatureUnavailable(
            "Turn on Android Location Services and try again."
        ))
        return

    class LocationListener(PythonJavaClass):
        __javainterfaces__ = ["android/location/LocationListener"]
        __javacontext__ = "app"

        @java_method("(Landroid/location/Location;)V")
        def onLocationChanged(self, location) -> None:
            global _location_listener, _location_timeout
            location_manager.removeUpdates(self)
            Clock.schedule_once(
                lambda _dt: callback(
                    {
                        "latitude": float(location.getLatitude()),
                        "longitude": float(location.getLongitude()),
                        "accuracy_meters": (
                            float(location.getAccuracy())
                            if location.hasAccuracy()
                            else None
                        ),
                        "recorded_at": datetime.fromtimestamp(
                            location.getTime() / 1000,
                            timezone.utc,
                        ).isoformat(),
                    },
                    None,
                ),
                0,
            )
            _location_timeout = None
            _location_listener = None

        @java_method("(Ljava/lang/String;ILandroid/os/Bundle;)V")
        def onStatusChanged(self, _provider, _status, _extras) -> None:
            return

        @java_method("(Ljava/lang/String;)V")
        def onProviderEnabled(self, _provider) -> None:
            return

        @java_method("(Ljava/lang/String;)V")
        def onProviderDisabled(self, _provider) -> None:
            return

    listener = LocationListener()
    _location_listener = listener
    providers = []
    for provider in ("gps", "network"):
        if location_manager.isProviderEnabled(provider):
            providers.append(provider)

    from android.permissions import (
        Permission,
        check_permission,
        request_permissions,
    )

    permission_for_provider = {
        "gps": Permission.ACCESS_FINE_LOCATION,
        "network": Permission.ACCESS_COARSE_LOCATION,
    }
    try:
        for provider in providers:
            permission = permission_for_provider[provider]
            if check_permission(permission):
                location_manager.requestLocationUpdates(
                    provider,
                    0,
                    0,
                    listener,
                )
    except Exception as error:
        _location_listener = None
        callback(None, NativeFeatureUnavailable(
            f"Could not start location updates: {error}"
        ))
        return

    def timed_out(_dt) -> None:
        global _location_listener, _location_timeout
        if _location_listener is listener:
            location_manager.removeUpdates(listener)
            _location_listener = None
            _location_timeout = None
            callback(None, NativeFeatureUnavailable(
                "No location fix arrived. Check GPS signal and retry."
            ))

    _location_timeout = Clock.schedule_once(timed_out, 20)
