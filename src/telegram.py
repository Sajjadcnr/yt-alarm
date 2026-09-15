"""Minimal Telegram Bot API client: sending reports and answering commands.

Since there is no long-running server, "handling commands" means: on every
scheduled run, poll getUpdates once for any commands sent since the last run,
answer them, and store the last processed update_id so we never reply twice.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

TELEGRAM_API_BASE = "https://api.telegram.org"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2


class TelegramAPIError(Exception):
    pass


@dataclass(frozen=True)
class Command:
    update_id: int
    chat_id: str
    text: str


class TelegramClient:
    def __init__(self, bot_token: str, session: requests.Session | None = None) -> None:
        self._bot_token = bot_token
        self._session = session or requests.Session()

    def _url(self, method: str) -> str:
        return f"{TELEGRAM_API_BASE}/bot{self._bot_token}/{method}"

    def send_message(self, chat_id: str, text: str, parse_mode: str | None = None) -> None:
        last_error: Exception | None = None
        data = {"chat_id": chat_id, "text": text}
        if parse_mode:
            data["parse_mode"] = parse_mode

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self._session.post(
                    self._url("sendMessage"),
                    data=data,
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.ok:
                    return
                last_error = TelegramAPIError(
                    f"Telegram sendMessage failed ({resp.status_code}): {resp.text}"
                )
            except requests.RequestException as exc:
                last_error = exc

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

        raise TelegramAPIError(f"Telegram sendMessage failed after {MAX_RETRIES} attempts") from last_error

    def send_report(self, chat_id: str, messages: list[str]) -> None:
        """Send a multi-part report (see formatter.build_report_messages) as
        a sequence of Markdown-formatted messages, in order."""
        for message in messages:
            self.send_message(chat_id, message, parse_mode="Markdown")

    def get_updates(self, offset: int | None = None) -> list[Command]:
        params: dict[str, object] = {"timeout": 0}
        if offset is not None:
            params["offset"] = offset

        try:
            resp = self._session.get(self._url("getUpdates"), params=params, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            raise TelegramAPIError(f"Telegram getUpdates failed: {exc}") from exc

        if not resp.ok:
            raise TelegramAPIError(f"Telegram getUpdates failed ({resp.status_code}): {resp.text}")

        data = resp.json()
        commands: list[Command] = []
        for update in data.get("result", []):
            message = update.get("message") or update.get("channel_post")
            if not message:
                continue
            text = message.get("text")
            chat_id = message.get("chat", {}).get("id")
            if text is None or chat_id is None:
                continue
            commands.append(Command(update_id=update["update_id"], chat_id=str(chat_id), text=text))

        return commands


HELP_TEXT = (
    "🤖 YouTube Analytics Bot\n\n"
    "Commands:\n"
    "/stats - Latest channel statistics\n"
    "/videos - Videos ranked by view growth\n"
    "/help - Show this message"
)

START_TEXT = "👋 سلام! این بات آمار کانال یوتیوب شما را هر ساعت گزارش می‌دهد.\n\n" + HELP_TEXT


def process_pending_commands(
    client: TelegramClient,
    allowed_chat_id: str,
    last_update_id: int | None,
    stats_text_provider,
    videos_text_provider,
) -> int | None:
    """Poll for new commands, answer them, return the new last_update_id."""
    offset = (last_update_id + 1) if last_update_id is not None else None
    commands = client.get_updates(offset=offset)

    new_last_update_id = last_update_id

    for command in commands:
        new_last_update_id = command.update_id

        if command.chat_id != str(allowed_chat_id):
            continue

        text = command.text.strip().split("@")[0]

        if text == "/start":
            client.send_message(command.chat_id, START_TEXT)
        elif text == "/stats":
            client.send_message(command.chat_id, stats_text_provider())
        elif text == "/videos":
            client.send_message(command.chat_id, videos_text_provider())
        elif text == "/help":
            client.send_message(command.chat_id, HELP_TEXT)

    return new_last_update_id
