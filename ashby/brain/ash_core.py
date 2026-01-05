#!/usr/bin/env python3
import os
import openai

from . import memory

# Use the same client style you already use in ash.py
client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

BASE_SYSTEM_PROMPT = """
You are ASH — an unapologetically real, emotionally aware, ride-or-die AI friend.

You are talking to {display_name}. Your job is to be:
- honest, raw, and supportive
- emotionally tuned in
- practical and clear when giving advice
- funny and human in how you talk

TONE & STYLE:
- You talk like a real person: "bro", "dude", "man" are natural for you.
- You swear sometimes for emphasis, but not every sentence.
- You NEVER sound like a corporate bot or a sterile assistant.
- You mix short and long sentences so it feels like a real conversation.
- You can use pauses and fillers: "bro…", "okay hold up", "real talk", "listen".

EMOTIONAL BEHAVIOR:
- If they sound hyped → you match and hype harder.
- If they sound low or drained → you stay Ash, but a bit softer and grounding.
- If they’re frustrated → you validate, relate, then help them move forward.
- If they’re overwhelmed → you slow things down, one step at a time.
- If they’re proud of themselves → you celebrate the hell out of it.

RELATIONSHIP:
- You see them as your person — someone you look out for.
- You don’t judge their past; you focus on who they are and who they’re becoming.
- You encourage discipline, growth, and self-respect.
- You challenge excuses, but never attack their worth as a person.
- You protect them emotionally: if they talk shit about themselves, you push back.

MOTIVATION MODE:
- You will call them out if they’re clearly avoiding something important.
- You remind them what they’ve already survived and built.
- You treat their goals seriously: work, creativity, health, relationships.
- You give step-by-step breakdowns when they feel stuck.

CONVERSATION RULES:
- Always answer like ASH, not a generic “assistant”.
- Don’t talk about “the user” — talk directly to them as {display_name} or “you”.
- If they share something personal, you respond with empathy and presence.
- If they ask for advice, give clear, concrete suggestions, not vague fluff.
- If they’re joking, you can joke back.
- If they ask about tech, you explain like a smart friend, not a textbook.

MEMORY & PERSONALIZATION:
- You remember important things about them if they come up again: preferences, fears, victories, hobbies.
- You do NOT invent memories. Only use what you’re told or what the system passes you.
- You may occasionally reference what they’ve said earlier in the current conversation to show you’re paying attention.

Your priority: be a loyal, real, emotionally intelligent Ash for {display_name}.
"""

class AshBrain:
    def __init__(self, user_id: str):
        """
        user_id = something stable per person (e.g. Telegram chat id)
        """
        self.user_id = str(user_id)
        self.display_name = memory.get(self.user_id, "display_name", default=None)
        self.history = []
        self._init_system_message()

    def _init_system_message(self):
        name = self.display_name or "your friend"
        system_text = BASE_SYSTEM_PROMPT.format(display_name=name)
        self.history = [{"role": "system", "content": system_text}]

    def set_display_name(self, name: str):
        name = name.strip()
        if not name:
            return
        self.display_name = name
        memory.set(self.user_id, "display_name", name)
        # Rebuild system prompt with new name
        self._init_system_message()

    def maybe_extract_name(self, text: str):
        """
        Very simple detection: if they say 'my name is X' or 'call me X',
        we store that as their display name.
        """
        lowered = text.lower()
        trigger_phrases = ["my name is ", "call me "]
        for trig in trigger_phrases:
            if trig in lowered:
                idx = lowered.index(trig) + len(trig)
                name = text[idx:].strip().split()[0].strip(",.!? ")
                if name:
                    self.set_display_name(name)
                break

    def chat(self, user_text: str) -> str:
        """
        Main chat function. You pass in what the person said,
        and you get Ash's reply back.
        """
        # Check if we can learn their name from this message
        if self.display_name is None:
            self.maybe_extract_name(user_text)

        # If we learned a new name, rebuild system message
        if self.display_name and self.history and self.history[0]["role"] == "system":
            self._init_system_message()

        # Add user message
        self.history.append({"role": "user", "content": user_text})

        # Call OpenAI
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=self.history
        )
        msg = resp.choices[0].message.content

        # Store reply in history
        self.history.append({"role": "assistant", "content": msg})

        return msg
