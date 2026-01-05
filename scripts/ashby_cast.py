import time
import threading
import http.server
import socketserver
import pychromecast
from openai import OpenAI

# -------------------------
# CONFIG
# -------------------------
CAST_NAME = "Family room speaker 2"   # Your Google Home Mini name
PORT = 8000                           # Local webserver port
AUDIO_FILE = "ash_cast.mp3"           # TTS output file name

client = OpenAI()   # Uses OPENAI_API_KEY from environment


# -------------------------
# Generate TTS with OpenAI
# -------------------------
def generate_tts(text):
    print("Generating TTS audio...")
    response = client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="verse",     # <<<<<< ARBOR-LIKE VOICE
        input=text
    )

    with open(AUDIO_FILE, "wb") as f:
        f.write(response.read())

    print("Saved:", AUDIO_FILE)


# -------------------------
# Start temporary web server
# -------------------------
def start_web_server():
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Serving local audio on port {PORT}")
        httpd.serve_forever()


# -------------------------
# Cast to Google Home Mini
# -------------------------
def cast_audio():
    print("Discovering Chromecast device...")

    chromecasts, browser = pychromecast.get_listed_chromecasts(
        friendly_names=[CAST_NAME]
    )

    if not chromecasts:
        print("ERROR: Could not find Google Home Mini.")
        browser.stop_discovery()
        return

    cast = chromecasts[0]
    cast.wait()

    # Serve file from local Pi over HTTP
    url = f"http://192.168.229.101:{PORT}/{AUDIO_FILE}"
    print("Casting URL:", url)

    mc = cast.media_controller
    mc.play_media(url, "audio/mp3")
    mc.block_until_active()
    mc.play()

    print("Audio sent!")
    time.sleep(8)
    browser.stop_discovery()


# -------------------------
# MAIN ENTRY
# -------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 ashby_cast.py \"something for ash to say\"")
        sys.exit(1)

    text = sys.argv[1]

    # 1. Create TTS audio file
    generate_tts(text)

    # 2. Launch the local web server in a background thread
    t = threading.Thread(target=start_web_server, daemon=True)
    t.start()

    time.sleep(1)  # small delay to let the server start

    # 3. Cast to Google Home Mini
    cast_audio()
