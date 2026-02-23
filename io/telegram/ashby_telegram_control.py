from secrets_store.env import (
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

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---------- Ashby brain ----------
from ashby.core.router import handle_text as ashby_handle_text

# ---------- Stuart (meetings) Telegram door ----------
from ashby.interfaces.telegram.stuart_door_core import (
    DoorState,
    DoorPrompt,
    parse_callback_data,
    start_from_upload,
    apply_mode,
    apply_speakers,
)
from ashby.interfaces.telegram.stuart_runner import run_default_pipeline

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
with open("secrets_store/ashby_nest.env") as f:
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



# ---------- Stuart door helpers ----------
def _prompt_to_markup(prompt: DoorPrompt) -> InlineKeyboardMarkup:
    rows = []
    for b in prompt.buttons:
        rows.append([InlineKeyboardButton(b.label, callback_data=b.data)])
    return InlineKeyboardMarkup(rows)


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Accept audio/video/voice/document and start a Stuart flow.
    msg = update.message
    if msg is None:
        return
    chat_id = str(update.effective_chat.id)
    att = msg.audio or msg.video or msg.voice or msg.document
    if att is None:
        await msg.reply_text("No attachment found.")
        return

    file_id = getattr(att, "file_id", None)
    filename = getattr(att, "file_name", None) or "upload.bin"
    # Best-effort kind
    if msg.video:
        kind = "video"
    else:
        kind = "audio"

    # Where to stash the incoming file
    import os
    from pathlib import Path
    # Runtime storage must stay outside repo by default.
    # Priority:
    # 1) STUART_ROOT (explicit operator override)
    # 2) ASHBY_TELEGRAM_RUNTIME_ROOT (telegram-specific override)
    # 3) ~/ashby_runtime/ashby (canonical default for telegram control runtime)
    stuart_root = (
        os.environ.get("STUART_ROOT")
        or os.environ.get("ASHBY_TELEGRAM_RUNTIME_ROOT")
        or str(Path("~/ashby_runtime/ashby").expanduser())
    )
    inbox = Path(stuart_root) / "inbox" / "telegram" / chat_id
    inbox.mkdir(parents=True, exist_ok=True)
    dest = inbox / filename

    tg_file = await context.bot.get_file(file_id)
    await tg_file.download_to_drive(custom_path=str(dest))

    st, prompt = start_from_upload(local_path=str(dest), source_kind=kind)
    context.user_data["stuart_door_state"] = st.__dict__
    await msg.reply_text(prompt.text, reply_markup=_prompt_to_markup(prompt))


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q is None:
        return
    await q.answer()

    parsed = parse_callback_data(q.data or "")
    if parsed is None:
        return

    state_d = context.user_data.get("stuart_door_state")
    if not isinstance(state_d, dict):
        await q.message.reply_text("Stuart: no active flow. Send a file first.")
        return

    st = DoorState(**state_d)
    kind, value = parsed

    if kind == "mode":
        mode = "meeting" if value == "meeting" else "journal"
        st, prompt = apply_mode(st, mode)  # type: ignore[arg-type]
        context.user_data["stuart_door_state"] = st.__dict__
        await q.message.reply_text(prompt.text, reply_markup=_prompt_to_markup(prompt))
        return

    if kind == "spk":
        # Capture speakers, then require an explicit confirm before running.
        st, prompt = apply_speakers(st, value if value in ("auto", "1", "2", "3+") else "auto")  # type: ignore[arg-type]
        context.user_data["stuart_door_state"] = st.__dict__
        await q.message.reply_text(prompt.text, reply_markup=_prompt_to_markup(prompt))
        return

    if kind == "go":
        if value == "cancel":
            context.user_data.pop("stuart_door_state", None)
            await q.message.reply_text("Stuart: cancelled.")
            return

        if value != "run":
            return

        rr = st.to_run_request()
        await q.message.reply_text("Stuart: running...")
        try:
            out = run_default_pipeline(
                local_path=st.local_path,
                source_kind="audio" if st.source_kind != "video" else "video",
                run_request=rr,
            )

            pdf_path = out.get("pdf_path")
            if isinstance(pdf_path, str) and pdf_path:
                from pathlib import Path

                p = Path(pdf_path)
                if p.exists():
                    await q.message.reply_document(document=p.read_bytes(), filename=p.name)
                else:
                    await q.message.reply_text(f"Stuart: ran, but PDF missing: {pdf_path}")
            else:
                await q.message.reply_text("Stuart: ran, but no PDF path returned.")
        except Exception as e:
            import traceback

            print("\n========== STUART ERROR ==========")
            traceback.print_exc()
            print("========== /STUART ERROR ==========\n")
            await q.message.reply_text(f"Stuart error: {e}")
        finally:
            context.user_data.pop("stuart_door_state", None)
        return


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
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.ATTACHMENT, handle_media))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    logger.info("ASHBY Telegram gateway online (text-only)")
    app.run_polling()


if __name__ == "__main__":
    main()
