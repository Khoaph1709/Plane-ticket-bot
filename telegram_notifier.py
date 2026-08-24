from __future__ import annotations

import os
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


MAX_MESSAGE_LENGTH = 4000


def _session() -> requests.Session:
    retry_strategy = Retry(
        total=4,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    return session


def send_message(token: str, chat_id: str, message: str) -> None:
    if not token or not chat_id:
        raise ValueError("Telegram token and chat ID are required")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    session = _session()
    parts = [message[i : i + MAX_MESSAGE_LENGTH] for i in range(0, len(message), MAX_MESSAGE_LENGTH)] or [""]
    for part in parts:
        response = session.post(
            url,
            json={"chat_id": chat_id, "text": part},
            timeout=30,
        )
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        if not body.get("ok"):
            raise RuntimeError(f"Telegram API error: {body.get('description', body)}")
        if len(parts) > 1:
            time.sleep(1)


def send_from_environment(token_env: str, chat_id_env: str, message: str) -> None:
    send_message(os.getenv(token_env, ""), os.getenv(chat_id_env, ""), message)
