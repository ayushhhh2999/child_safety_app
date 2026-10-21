# Mobile Tracker Android frontend

This Kivy client is a separate application from `backend/`. It provides a dark,
mobile-first shell with splash, authentication, dashboard, location, activity,
connections/privacy, restricted-app and profile/settings screens. It calls the
existing FastAPI authentication and connection/consent endpoints directly.

## Implemented against the current backend

- Signup (`POST /api/auth/signup`), login (`POST /api/auth/login`), and profile
  lookup (`GET /api/auth/me`).
- Username search and request creation/listing, accept/reject, accepted
  connections, per-owner sharing preferences, and disconnect under
  `/api/connections`.
- Dashboard accepted-connection count and the current account's server-side
  sharing consent, fetched from the backend.
- API health probe (`GET /health`), API address configuration, logout, and a
  user-triggered vibration test on Android.

Sharing controls apply to the signed-in person's own data only; each consent
setting is read from and written to that user's permission row. Permission
switches are reloaded from the server after updates. No sample location,
activity, alerts, or connection statistics are fabricated.

## Backend dependencies / unavailable features

The inspected backend currently does not define these API endpoints or related
models:

- `POST /api/locations`, `GET /api/locations/me`, or
  `GET /api/connections/{connection_id}/locations`.
- `POST /api/activities`, `GET /api/activities/me`, or
  `GET /api/connections/{connection_id}/activities`.
- Restricted-app, restriction-alert, device, account-deletion, or historical
  data deletion endpoints.

Consequently, the location and activity screens explain why data is unavailable;
they do not show made-up coordinates or events. The restricted-app screen can
explain that Usage Access and Accessibility are not requested because this
version has no consumer for those permissions, and supports a manual vibration
test. App discovery, collection, alerts, accessibility monitoring, and blocking
are not implemented. There is no map because no authorized location feed
exists. The frontend does not register a foreground service or Accessibility
Service.

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
  "$HOME/mobile_tracker_frontend"
cd "$HOME/mobile_tracker_frontend"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install buildozer cython==0.29.36
buildozer android debug
```

Buildozer downloads and configures Android SDK/NDK components on the first
build. The debug APK is written to `bin/`. Install it on a connected device
using Android platform tools:

```bash
adb install -r bin/mobiletracker-0.1.0-arm64-v8a-debug.apk
```

Open **Configure API server** on first launch and provide a reachable HTTPS API
URL. Test login, consent changes, and revoked access on a physical device. A
successful Python test run is not evidence that the APK built or that Android
background/device integrations work. Buildozer/APK compilation and physical
device testing have not been performed as part of this change.

## Session and token security

JWTs are kept in process memory only and are cleared on logout, an authenticated
401 response, or app restart. This frontend intentionally does not persist a
token in plaintext preferences; Android Keystore-backed token persistence is
not included. Session restoration is therefore unavailable. Passwords are
never persisted, and the server remains responsible for password hashing and
JWT signing.
