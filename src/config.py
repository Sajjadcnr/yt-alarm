"""Configuration loaded from environment variables / GitHub Secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


class ConfigError(Exception):
    pass


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Config:
    youtube_api_key: str
    youtube_channel_id: str
    telegram_bot_token: str
    telegram_chat_id: str
    max_videos_in_report: int
    timezone: str
    stats_file: str

    @classmethod
    def load(cls) -> "Config":
        return cls(
            youtube_api_key=_require("YOUTUBE_API_KEY"),
            youtube_channel_id=_require("YOUTUBE_CHANNEL_ID"),
            telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=_require("TELEGRAM_CHAT_ID"),
            max_videos_in_report=int(os.environ.get("MAX_VIDEOS_IN_REPORT", "20")),
            timezone=os.environ.get("TIMEZONE", "Asia/Tehran"),
            stats_file=os.environ.get("STATS_FILE", "data/stats.json"),
        )
