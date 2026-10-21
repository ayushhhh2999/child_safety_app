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

android.permissions = INTERNET,VIBRATE,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,PACKAGE_USAGE_STATS
android.api = 35
android.minapi = 24
android.archs = arm64-v8a
android.allow_backup = False
android.add_src = android_src
android.add_resources = android_res
android.extra_manifest_xml = android_manifest.xml

[buildozer]
log_level = 2
warn_on_root = 1
