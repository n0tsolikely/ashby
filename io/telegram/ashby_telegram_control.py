from secrets.env import (
    ENDPOINT,
    ACCESS_ID,
    ACCESS_KEY,
    USERNAME,
    PASSWORD,
    TELEGRAM_TOKEN,
)

from ashby.devices.ashby_devices import DEVICES
from tuya_iot import TuyaOpenAPI

import logging
import json
import requests
import re

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------- Ashby brain ----------
from ashby.core.router import handle_text as ashby_handle_text

# ---------- Logging ----------
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------- Tuya (plug) setup ----------
openapi = TuyaOpenAPI(ENDPOINT, ACCESS_ID, ACCESS_KEY)
openapi.connect(USERNAME, PASSWORD, "1", "smartlife")  # US/CA


def set_plug(on: bool, plug_name: str = "bed_lamp"):
    device = DEVICES.get(plug_name)
    if not device:
        return {"success": False, "error": f"No device named '{plug_name}'"}

    device_id = device["id"]
    commands = {"commands": [{"code": "switch_1", "value": on}]}
    return openapi.post(f"/v1.0/devices/{device_id}/commands", commands)


# ---------- Nest (thermostat) ----------
nest_env = {}
with open("secrets/ashby_nest.env") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            nest_env[k] = v.strip().strip('"').strip("'")

NEST_REFRESH_TOKEN = nest_env["NEST_REFRESH_TOKEN"]
NEST_CLIENT_ID = nest_env["NEST_CLIENT_ID"]
NEST_CLIENT_SECRET = nest_env["NEST_CLIENT_SECRET"]
NEST_DEVICE = nest_env["NEST_DEVICE"]

TOKEN_URL = "https://www.googleapis.com/oauth2/v4/token"
EXECUTE_URL = f"https://smartdevicemanagement.googleapis.com/v1/{NEST_DEVICE}:executeCommand"


def get_nest_access_token():
    r = requests.post(
        TOKEN_URL,
        data={
            "client_id": NEST_CLIENT_ID,
            "client_secret": NEST_CLIENT_SECRET,
            "refresh_token": NEST_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def set_heat_celsius(temp_c: float):
    token = get_nest_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "command": "sdm.devices.commands.ThermostatTemperatureSetpoint.SetHeat",
        "params": {"heatCelsius": float(temp_c)},
    }
    return requests.post(EXECUTE_URL, headers=headers, json=payload, timeout=30)


# ---------- Telegram: PURE TEXT GATEWAY ----------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id
    lower = text.lower()

    action_hints = []

    # OPTIONAL quick device hints (can remove later)
    temp_match = re.search(r"(\d+(\.\d+)?)", lower)
    if any(w in lower for w in ["heat", "temperature", "temp"]) and temp_match:
        temp = float(temp_match.group(1))
        try:
            r = set_heat_celsius(temp)
            if 200 <= r.status_code < 300:
                action_hints.append(f"Heat set to {temp}°C.")
        except Exception as e:
            action_hints.append(f"Heat error: {e}")

    if "plug" in lower or "outlet" in lower:
        if "on" in lower:
            res = set_plug(True)
            if res.get("success"):
                action_hints.append("Plug turned ON.")
        elif "off" in lower:
            res = set_plug(False)
            if res.get("success"):
                action_hints.append("Plug turned OFF.")

    # ---- Ashby brain ----
    try:
        reply = ashby_handle_text(str(chat_id), text)
    except Exception as e:
        logger.exception("Ashby brain error")
        reply = f"Something broke in the brain: {e}"

    if action_hints:
        reply += "\n\n(" + " ".join(action_hints) + ")"

    await update.message.reply_text(reply)


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).job_queue(None).build()
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    logger.info("ASHBY Telegram gateway online (text-only)")
    app.run_polling()


if __name__ == "__main__":
    main()
