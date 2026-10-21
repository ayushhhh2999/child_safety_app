# Mobile Tracker Android frontend

This Kivy client is a separate application from `backend/`. It provides a dark,
mobile-first shell with authentication, connections/privacy controls, manual
location capture, manual app-usage sync, opt-in restricted-app blocking, and
profile/settings screens.

## Implemented against the current backend

- Signup (`POST /api/auth/signup`), login (`POST /api/auth/login`), and profile
  lookup (`GET /api/auth/me`).
- Username search and request creation/listing, accept/reject, accepted
  connections, per-owner sharing preferences, and disconnect under
  `/api/connections`.
- Dashboard accepted-connection count and the current account's server-side
  sharing consent, fetched from the backend.
- One-time, user-triggered device location capture and owner-scoped location
  history (`/api/locations`).
- Manual 24-hour Android Usage Access event sync and owner-scoped activity
  history (`/api/activities`).
- Launcher-visible app selection, server-saved restriction rules, optional
  Android Accessibility blocking, and restriction-alert sync
  (`/api/restrictions`).
- API health probe (`GET /health`), API address configuration, logout, and a
  user-triggered vibration test on Android.

Sharing controls apply to the signed-in person's own data only; each consent
setting is read from and written to that user's permission row. Permission
switches are reloaded from the server after updates. No sample location,
activity, alerts, or connection statistics are fabricated.

## Tracking permissions and backend deployment

The backend must be deployed with the tracking router and both Alembic
migrations, through revision `0004_activity_event_dedup`, before these
screens can use the tracking endpoints. Deploying only the APK does not update
the Render service or its database schema.

- Location is captured only after the user taps **Record my current location**
  and grants Android location permission. There is no background or continuous
  location service.
- App activity is read only after the user enables Android Usage Access and
  manually syncs. The client reads foreground/background timestamps for the
  preceding 24 hours; it does not read screen contents or infer durations.
- App blocking requires the device owner to select apps and separately enable
  the app's Accessibility service in Android Settings. The service checks
  foreground package transitions and returns selected apps to Home. It does not
  read screen contents. Accessibility behavior must be verified on a physical
  Android device and may vary across Android versions and manufacturers.
- Tracking data belongs to the authenticated account. Shared reads are allowed
  only for accepted connections with that account's matching sharing permission
  enabled and not paused. The backend applies a 30-day retention window.
- Account deletion/export endpoints and Android Keystore-backed token
  persistence are not implemented. Tokens stay in memory and are cleared on
  logout, an authenticated 401 response, or app restart. Ask the service
  administrator to delete an account.

## Local Windows development

Start the backend in one PowerShell window:

```powershell
cd C:\Users\ayush\Desktop\development\mobile_tracker_app\backend
$env:JWT_SECRET_KEY = "replace-with-a-long-random-development-secret"
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

In another PowerShell window, configure and run the Kivy client:

```powershell
cd C:\Users\ayush\Desktop\development\mobile_tracker_app\frontend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:API_BASE_URL = "http://127.0.0.1:8000"
python main.py
```

Run the frontend API-client tests using the frontend virtual environment:

```powershell
cd C:\Users\ayush\Desktop\development\mobile_tracker_app\frontend
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The Android build defaults to `https://child-safety-app-6s5b.onrender.com`.
The desktop-only environment variable is a development override. The app's
**Configure API server** screen also stores the URL in the app's private data
directory. Use an HTTPS backend URL in an Android APK; this build intentionally
does not enable Android cleartext HTTP traffic. Server/JWT/database secrets must
never be placed in the app.

## Build and install a debug APK (Ubuntu / WSL2)

Buildozer and the Android SDK/NDK toolchain run on Linux. Install the system
prerequisites in Ubuntu/WSL2:

```bash
sudo apt update
sudo apt install -y git zip unzip openjdk-17-jdk python3-pip python3-venv \
  autoconf libtool pkg-config zlib1g-dev libncurses-dev cmake \
  libffi-dev libssl-dev
```

For more reliable builds, copy the frontend from the Windows-mounted project
into WSL's Linux filesystem, then build there:

```bash
cp -r /mnt/c/Users/ayush/Desktop/development/mobile_tracker_app/frontend \
  "$HOME/mobile_tracker_frontend_build"
cd "$HOME/mobile_tracker_frontend_build"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install buildozer cython==0.29.36
sed -i 's/include-system-site-packages = false/include-system-site-packages = true/' \
  .venv/pyvenv.cfg
export PATH="$PWD/.venv/bin:$PATH"
PIP_CONSTRAINT="$(pwd)/android-build-constraints.in" buildozer android debug
```

Buildozer downloads and configures Android SDK/NDK components on the first
build. This configuration targets Android API 35 and requires Android 7.0
(API 24) or newer; Python 3.14's Android build uses native APIs unavailable on
API 23. `android-build-constraints.in` pins the build environment's pip and
`charset-normalizer` to versions compatible with the current
Python-for-Android installer.

Use this command to ensure the constraints apply to Buildozer's internal pip:

```bash
export PATH="$PWD/.venv/bin:$PATH"
PIP_CONSTRAINT="$(pwd)/android-build-constraints.in" buildozer android debug
```

The debug APK is written to `bin/`. Install it on a connected device using
Android platform tools:

```bash
adb install -r bin/mobiletracker-0.1.0-arm64-v8a-debug.apk
```

The Android build defaults to
`https://child-safety-app-6s5b.onrender.com`. Open **Configure API server** to
change it. Test login, consent changes, manual capture/sync, and revoked sharing
access on a physical device. A successful Python test run does not verify Android
permission prompts or Accessibility behavior.

## Session and token security

JWTs are kept in process memory only and are cleared on logout, an authenticated
401 response, or app restart. This frontend intentionally does not persist a
token in plaintext preferences; Android Keystore-backed token persistence is
not included. Session restoration is therefore unavailable. Passwords are
never persisted, and the server remains responsible for password hashing and
JWT signing.
