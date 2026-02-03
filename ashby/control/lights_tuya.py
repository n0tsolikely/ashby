import logging
from typing import List, Union

from tuya_iot import TuyaOpenAPI, TUYA_LOGGER
from secrets_store.env import ENDPOINT, ACCESS_ID, ACCESS_KEY, USERNAME, PASSWORD
from ashby.devices.ashby_devices import DEVICES

# ---------- Logging ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
TUYA_LOGGER.setLevel(logging.INFO)
logger = logging.getLogger("ashby_lights_tuya")

# ---------- Tuya client ----------
openapi = TuyaOpenAPI(ENDPOINT, ACCESS_ID, ACCESS_KEY)
openapi.connect(USERNAME, PASSWORD, "1", "smartlife")

# ---------- Local brightness cache ----------
# name -> 0–1000
BRIGHTNESS_STATE: dict[str, int] = {}

DEFAULT_STEP = 100
DEFAULT_BRIGHTNESS = 500  # used if we don't know current brightness yet


def _normalize_names(target: Union[str, List[str]]) -> List[str]:
    if isinstance(target, str):
        return [target]
    return list(target)


def _ensure_bulb(name: str):
    """
    Make sure the device exists and looks like a Tuya bulb.
    """
    if name not in DEVICES:
        raise ValueError(f"Unknown device: {name}")
    dev_type = DEVICES[name].get("type")
    allowed_bulb_types = {
        "bulb",
        "tuya_bulb",
        "light",
        "tuya_light",
        "A19_800lm",  # your Globe bulbs
    }
    if dev_type not in allowed_bulb_types:
        raise ValueError(f"Device {name} is not a Tuya bulb (type={dev_type})")


def _get_bulb_ids(target: Union[str, List[str]]):
    """
    Normalize 'target' into a list of (name, device_id) tuples.
    """
    names = _normalize_names(target)
    bulbs = []
    for n in names:
        _ensure_bulb(n)
        bulbs.append((n, DEVICES[n]["id"]))
    return bulbs


def _clamp(value: int, min_v: int = 0, max_v: int = 1000) -> int:
    return max(min_v, min(max_v, int(value)))


def _ok(res: dict) -> bool:
    """
    Tuya responses usually look like:
      {"success": true, "result": ...}
    If it's not clearly success=True, treat as failure.
    """
    try:
        return bool(res.get("success")) is True
    except Exception:
        return False


# ---------- Core actions ----------

def set_brightness(target: Union[str, List[str]], value: int) -> int:
    """
    Set brightness (0–1000) for one or many Tuya bulbs.

    If value == 0:
        - only send switch_led = False (OFF)
    If value > 0:
        - ensure switch_led = True
        - then send bright_value_v2 in a separate call
    """
    bulbs = _get_bulb_ids(target)
    value = _clamp(value)

    for name, dev_id in bulbs:
        BRIGHTNESS_STATE[name] = value

        # OFF path: just switch_led = False
        if value == 0:
            commands = {
                "commands": [
                    {"code": "switch_led", "value": False},
                ]
            }
            res = openapi.post(f"/v1.0/devices/{dev_id}/commands", commands)
            logger.info("turn_off %s -> 0 | %s", name, res)
            continue

        # ON path: first turn on LED
        on_cmd = {
            "commands": [
                {"code": "switch_led", "value": True},
            ]
        }
        res_on = openapi.post(f"/v1.0/devices/{dev_id}/commands", on_cmd)
        logger.info("switch_led ON %s | %s", name, res_on)

        # Then set brightness
        bright_cmd = {
            "commands": [
                {"code": "bright_value_v2", "value": value},
            ]
        }
        res_bright = openapi.post(f"/v1.0/devices/{dev_id}/commands", bright_cmd)
        logger.info("set_brightness %s -> %s | %s", name, value, res_bright)

    return value


def set_brightness(target: Union[str, List[str]], value: int) -> dict:
    """
    Set brightness (0–1000) for one or many Tuya bulbs.

    Returns a structured result:
      {
        "ok": bool,
        "attempted": [name...],
        "succeeded": [name...],
        "failed": [{"name": str, "stage": str, "res": any}],
        "value": int
      }
    """
    bulbs = _get_bulb_ids(target)
    value = _clamp(value)

    attempted: list[str] = []
    succeeded: list[str] = []
    failed: list[dict] = []

    for name, dev_id in bulbs:
        attempted.append(name)

        # OFF path
        if value == 0:
            commands = {"commands": [{"code": "switch_led", "value": False}]}
            res = openapi.post(f"/v1.0/devices/{dev_id}/commands", commands)

            if _ok(res):
                BRIGHTNESS_STATE[name] = 0
                succeeded.append(name)
            else:
                failed.append({"name": name, "stage": "off:switch_led", "res": res})
            continue

        # ON path: switch_led True
        on_cmd = {"commands": [{"code": "switch_led", "value": True}]}
        res_on = openapi.post(f"/v1.0/devices/{dev_id}/commands", on_cmd)
        if not _ok(res_on):
            failed.append({"name": name, "stage": "on:switch_led", "res": res_on})
            continue

        # Then brightness
        bright_cmd = {"commands": [{"code": "bright_value_v2", "value": value}]}
        res_bright = openapi.post(f"/v1.0/devices/{dev_id}/commands", bright_cmd)
        if not _ok(res_bright):
            failed.append({"name": name, "stage": "on:bright_value_v2", "res": res_bright})
            continue

        BRIGHTNESS_STATE[name] = value
        succeeded.append(name)

    ok = (len(failed) == 0)
    return {
        "ok": ok,
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
        "value": value,
    }


def turn_on(target: Union[str, List[str]], value: int | None = None) -> None:
    """
    Turn bulb(s) on. If value is None, use cached brightness or DEFAULT_BRIGHTNESS.
    """
    if isinstance(target, str) and value is None:
        value = BRIGHTNESS_STATE.get(target, DEFAULT_BRIGHTNESS)
    if value is None:
        value = DEFAULT_BRIGHTNESS

    set_brightness(target, value)


def turn_off(target: Union[str, List[str]]) -> None:
    """
    Turn bulb(s) off (switch_led = False, brightness cached as 0).
    """
    set_brightness(target, 0)


def get_cached_brightness(name: str) -> int:
    """
    Return last cached brightness for a bulb, or DEFAULT_BRIGHTNESS if unknown.
    """
    _ensure_bulb(name)
    return BRIGHTNESS_STATE.get(name, DEFAULT_BRIGHTNESS)
