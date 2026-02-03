import json
import requests
import sys

# Load env from file
env = {}
with open("secrets_store/ashby_nest.env") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            # Strip quotes if present
            val = val.strip().strip('"').strip("'")
            env[key] = val

NEST_REFRESH_TOKEN = env["NEST_REFRESH_TOKEN"]
NEST_CLIENT_ID = env["NEST_CLIENT_ID"]
NEST_CLIENT_SECRET = env["NEST_CLIENT_SECRET"]
NEST_DEVICE = env["NEST_DEVICE"]

TOKEN_URL = "https://www.googleapis.com/oauth2/v4/token"
EXECUTE_URL = f"https://smartdevicemanagement.googleapis.com/v1/{NEST_DEVICE}:executeCommand"


def get_access_token():
    """Use the long-lived refresh token to get a fresh access token."""
    data = {
        "client_id": NEST_CLIENT_ID,
        "client_secret": NEST_CLIENT_SECRET,
        "refresh_token": NEST_REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }
    r = requests.post(TOKEN_URL, data=data)
    r.raise_for_status()
    body = r.json()
    if "access_token" not in body:
        raise RuntimeError(f"Failed to get access token: {body}")
    return body["access_token"]


def set_heat_celsius(temp_c: float):
    access_token = get_access_token()

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "command": "sdm.devices.commands.ThermostatTemperatureSetpoint.SetHeat",
        "params": {
            "heatCelsius": float(temp_c)
        },
    }

    r = requests.post(EXECUTE_URL, headers=headers, data=json.dumps(payload))
    print("Status:", r.status_code)
    print("Response:", r.text)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 ashby_nest_set.py <temp_celsius>")
        print("Example: python3 ashby_nest_set.py 24")
        sys.exit(1)

    try:
        temp = float(sys.argv[1])
    except ValueError:
        print("Bro, give me a number like: python3 ashby_nest_set.py 22")
        sys.exit(1)

    print(f"Setting heat to {temp}°C...")
    set_heat_celsius(temp)
