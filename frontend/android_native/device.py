class NativeFeatureUnavailable(RuntimeError):
    pass


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

