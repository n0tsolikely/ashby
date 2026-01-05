#!/usr/bin/env python3
import logging

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("ashby_lights_tuya").setLevel(logging.WARNING)

import sys
from ashby.core.router import handle_text

USER_ID = "local_terminal"   # this can be anything stable

print("🔥 ASHBY INTERACTIVE — type 'exit' to quit.")
print("Talk to Ashby like normal. Lights + cold + chat all handled.\n")

while True:
    try:
        user_input = input("You: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nExiting test…")
        break

    if user_input.lower() in ["exit", "quit"]:
        print("Goodbye brother.")
        break

    reply = handle_text(USER_ID, user_input)
    print(f"Ashby: {reply}\n")
