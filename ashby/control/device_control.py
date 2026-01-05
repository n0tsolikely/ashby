# device_control.py
#
# Bridge between Ashby brain (router) and real Tuya hardware.
# Uses GROUPS to map logical groups -> physical device keys in DEVICES,
# then delegates to ashby.control.lights_tuya for actual control.

from ashby.devices.ashby_devices import DEVICES
from ashby.control.lights_tuya import set_brightness as tuya_set_brightness


# --- Logical group → physical devices mapping --- #

GROUPS = {
    "captain_america": ["captain_america_bulb"],
    "thor": ["thor_bulb"],
    "sky": ["sky_bulb"],
    # later: "bed_lamp": ["bed_lamp"],
}


def set_group_brightness(group: str, level: int) -> dict:
    """
    group: e.g. 'captain_america'
    level: 0–1000 internal Ashby brightness scale.

    Returns a structured result from lights_tuya.set_brightness():
      {
        "ok": bool,
        "attempted": [...],
        "succeeded": [...],
        "failed": [...],
        "value": int,
        "group": str,
        "devices": [device_key...]
      }
    """
    device_keys = GROUPS.get(group)
    if not device_keys:
        msg = f"No devices configured for group '{group}'"
        print(f"[Ashby WARNING] {msg}")
        return {
            "ok": False,
            "group": group,
            "devices": [],
            "attempted": [],
            "succeeded": [],
            "failed": [{"name": group, "stage": "group_lookup", "res": msg}],
            "value": int(level) if level is not None else 0,
        }

    # Clamp level
    try:
        level = int(level)
    except (TypeError, ValueError):
        level = 0
    level = max(0, min(1000, level))

    # Ensure devices exist
    missing = [k for k in device_keys if k not in DEVICES]
    device_keys = [k for k in device_keys if k in DEVICES]

    if missing:
        print(f"[Ashby WARNING] Missing device definitions for: {missing}")

    if not device_keys:
        msg = "All devices in group missing from DEVICES"
        print(f"[Ashby WARNING] {msg}")
        return {
            "ok": False,
            "group": group,
            "devices": [],
            "attempted": [],
            "succeeded": [],
            "failed": [{"name": group, "stage": "devices_missing", "res": msg}],
            "value": level,
        }

    print(f"[Ashby INFO] Setting group '{group}' devices {device_keys} to {level}/1000")

    # Delegate to Tuya
    res = tuya_set_brightness(device_keys, level)

    # Attach group metadata
    if not isinstance(res, dict):
        # Extremely defensive fallback
        return {
            "ok": False,
            "group": group,
            "devices": device_keys,
            "attempted": device_keys,
            "succeeded": [],
            "failed": [{"name": group, "stage": "tuya_return_type", "res": type(res).__name__}],
            "value": level,
        }

    res["group"] = group
    res["devices"] = device_keys
    return res
