package org.mobiletracker.mobiletracker;

import android.accessibilityservice.AccessibilityService;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.view.accessibility.AccessibilityEvent;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.TimeZone;
import java.util.UUID;

public final class RestrictionAccessibilityService extends AccessibilityService {
    private static final String PREFS = "mobile_tracker_restrictions";
    private static final String SELECTED_PACKAGES = "package_names";
    private static final String PENDING_ALERTS = "pending_alerts";
    private static final int MAX_PENDING_ALERTS = 100;
    private String lastBlockedPackage;

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null || event.getPackageName() == null) {
            return;
        }
        int eventType = event.getEventType();
        if (eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
                && eventType != AccessibilityEvent.TYPE_WINDOWS_CHANGED) {
            return;
        }

        String packageName = event.getPackageName().toString();
        Set<String> selected = getSharedPreferences(PREFS, MODE_PRIVATE)
                .getStringSet(SELECTED_PACKAGES, new HashSet<>());
        if (selected == null || !selected.contains(packageName)) {
            lastBlockedPackage = null;
            return;
        }
        if (packageName.equals(getPackageName())
                || packageName.equals(lastBlockedPackage)) {
            return;
        }

        if (performGlobalAction(GLOBAL_ACTION_HOME)) {
            lastBlockedPackage = packageName;
            recordAlert(packageName);
        }
    }

    @Override
    public void onInterrupt() {
        lastBlockedPackage = null;
    }

    private void recordAlert(String packageName) {
        String appName = packageName;
        try {
            ApplicationInfo info = getPackageManager().getApplicationInfo(packageName, 0);
            appName = getPackageManager().getApplicationLabel(info).toString();
        } catch (Exception ignored) {
            // Keep the package name as a useful alert label if the app was removed.
        }

        JSONArray pending = readPendingAlerts();
        JSONObject alert = new JSONObject();
        try {
            alert.put("id", UUID.randomUUID().toString());
            alert.put("package_name", packageName);
            alert.put("app_name", appName);
            alert.put("recorded_at", utcNow());
            pending.put(alert);
        } catch (JSONException ignored) {
            return;
        }
        while (pending.length() > MAX_PENDING_ALERTS) {
            pending.remove(0);
        }
        getSharedPreferences(PREFS, MODE_PRIVATE)
                .edit()
                .putString(PENDING_ALERTS, pending.toString())
                .apply();
    }

    private JSONArray readPendingAlerts() {
        String serialized = getSharedPreferences(PREFS, MODE_PRIVATE)
                .getString(PENDING_ALERTS, "[]");
        try {
            return new JSONArray(serialized);
        } catch (JSONException ignored) {
            return new JSONArray();
        }
    }

    private static String utcNow() {
        SimpleDateFormat format =
                new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US);
        format.setTimeZone(TimeZone.getTimeZone("UTC"));
        return format.format(new Date());
    }

    public static String getPendingRestrictionAlerts(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .getString(PENDING_ALERTS, "[]");
    }

    public static void acknowledgeRestrictionAlerts(Context context, String idsJson) {
        Set<String> acknowledged = new HashSet<>();
        try {
            JSONArray ids = new JSONArray(idsJson);
            for (int index = 0; index < ids.length(); index++) {
                acknowledged.add(ids.getString(index));
            }
        } catch (JSONException error) {
            throw new IllegalArgumentException("Invalid alert acknowledgement list", error);
        }

        String serialized = getPendingRestrictionAlerts(context);
        JSONArray pending;
        try {
            pending = new JSONArray(serialized);
        } catch (JSONException ignored) {
            pending = new JSONArray();
        }
        JSONArray remaining = new JSONArray();
        for (int index = 0; index < pending.length(); index++) {
            JSONObject alert = pending.optJSONObject(index);
            if (alert == null || !acknowledged.contains(alert.optString("id"))) {
                remaining.put(alert);
            }
        }
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit()
                .putString(PENDING_ALERTS, remaining.toString())
                .apply();
    }
}
