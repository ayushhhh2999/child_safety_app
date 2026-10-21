[app]
title = Mobile Tracker
package.name = mobiletracker
package.domain = org.mobiletracker
source.dir = .
source.include_exts = py,kv,png,jpg,atlas,txt
source.exclude_dirs = .venv,.buildozer,bin,tests
version = 0.1.0
requirements = python3,kivy==2.3.1,pyjnius
orientation = portrait
fullscreen = 0

android.permissions = INTERNET,VIBRATE
android.api = 35
android.minapi = 23
android.archs = arm64-v8a
android.allow_backup = False

[buildozer]
log_level = 2
warn_on_root = 1
