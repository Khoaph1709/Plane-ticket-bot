"""Print the most recent Telegram chat ID for the configured bot.

Usage:
    TELEGRAM_BOT_TOKEN='new-token' python bot.py
"""
from __future__ import annotations

import os
import requests


def get_chat_id() -> int | None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN before running this utility")
    response = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    results = data.get("result", [])
    if not data.get("ok") or not results:
        print("No Telegram messages found. Send /start to the bot and run again.")
        return None
    message = results[-1].get("message", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    print(f"Chat ID: {chat_id}")
    print(f"Name: {chat.get('first_name', 'User')}")
    return chat_id


if __name__ == "__main__":
    get_chat_id()
