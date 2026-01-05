from env import ENDPOINT, ACCESS_ID, ACCESS_KEY, USERNAME, PASSWORD
from tuya_iot import TuyaOpenAPI, TUYA_LOGGER
from ashby.devices.ashby_devices import DEVICES
import logging
import sys

# Basic logging so we can see what Tuya is doing
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
TUYA_LOGGER.setLevel(logging.INFO)

# Initialize Tuya OpenAPI client
openapi = TuyaOpenAPI(ENDPOINT, ACCESS_ID, ACCESS_KEY)

# Country code "1" = US/CA, "smartlife" = app schema
openapi.connect(USERNAME, PASSWORD, "1", "smartlife")


def get_device_id(device_name: str) -> str:
    """Look up a device ID from the DEVICES registry."""
    if device_name not in DEVICES:
        raise ValueError(f"Unknown device name: {device_name}")
    return DEVICES[device_name]["id"]


def set_plug(device_name: str, on: bool):
    """Turn the named Tuya plug on or off."""
    device_id = get_device_id(device_name)
    commands = {"commands": [{"code": "switch_1", "value": on}]}
    res = openapi.post(f"/v1.0/devices/{device_id}/commands", commands)
    print(f"[{device_name}] -> {'ON' if on else 'OFF'} | Response: {res}")
    return res


def main():
    # Usage: python3 ashby_tuya_test.py bed_lamp on
    if len(sys.argv) >= 3:
        device_name = sys.argv[1]
        state_arg = sys.argv[2].lower()

        if state_arg in ["on", "1", "true", "yes"]:
            turn_on = True
        elif state_arg in ["off", "0", "false", "no"]:
            turn_on = False
        else:
            print("Use 'on' or 'off' as the second argument.")
            sys.exit(1)

        set_plug(device_name, turn_on)
        return

    # If no args, show an interactive helper
    print("Available devices:")
    for name, info in DEVICES.items():
        desc = info.get("description", "")
        print(f"- {name}: {desc}")

    device_name = input("Enter device name (e.g. bed_lamp, birdcage_light): ").strip()
    print("Press Enter to turn it ON...")
    input()
    set_plug(device_name, True)

    print("Press Enter to turn it OFF...")
    input()
    set_plug(device_name, False)


if __name__ == "__main__":
    main()
