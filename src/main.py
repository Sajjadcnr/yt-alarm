"""Entry point for a single monitoring run.

Executed once per GitHub Actions run:

    read previous stats -> call YouTube API -> compute growth ->
    send Telegram report -> answer pending Telegram commands ->
    save stats.json (workflow commits it)

No loops, no sleeping, no long-running process.
"""

from __future__ import annotations

import sys

from config import Config, ConfigError
from formatter import (
    build_error_report,
    build_report_messages,
    build_stats_text_from_saved,
    build_videos_text_from_saved,
)
from storage import compare_and_build, load_stats, save_stats
from telegram import TelegramAPIError, TelegramClient, process_pending_commands
from youtube import YouTubeAPIError, YouTubeClient, YouTubeQuotaExceededError


def run() -> int:
    try:
        config = Config.load()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    telegram = TelegramClient(config.telegram_bot_token)
    previous_stats = load_stats(config.stats_file)

    try:
        youtube = YouTubeClient(config.youtube_api_key)
        channel, videos = youtube.fetch_full_snapshot(config.youtube_channel_id)
    except YouTubeQuotaExceededError as exc:
        print(f"YouTube API quota exceeded: {exc}", file=sys.stderr)
        _try_notify_error(telegram, config.telegram_chat_id, "YouTube API quota exceeded")
        return 1
    except YouTubeAPIError as exc:
        print(f"YouTube API error: {exc}", file=sys.stderr)
        _try_notify_error(telegram, config.telegram_chat_id, f"YouTube API error: {exc}")
        return 1

    comparison, new_stats = compare_and_build(previous_stats, channel, videos)
    new_stats["telegram"] = previous_stats.get("telegram", {})

    report_messages = build_report_messages(
        comparison, tz_name=config.timezone, max_videos=config.max_videos_in_report
    )

    try:
        telegram.send_report(config.telegram_chat_id, report_messages)
    except TelegramAPIError as exc:
        print(f"Telegram send error: {exc}", file=sys.stderr)
        return 1

    try:
        last_update_id = new_stats["telegram"].get("last_update_id")
        new_last_update_id = process_pending_commands(
            telegram,
            config.telegram_chat_id,
            last_update_id,
            lambda: build_stats_text_from_saved(new_stats),
            lambda: build_videos_text_from_saved(new_stats, config.max_videos_in_report),
        )
        new_stats["telegram"] = {"last_update_id": new_last_update_id}
    except TelegramAPIError as exc:
        print(f"Telegram command handling error (non-fatal): {exc}", file=sys.stderr)

    save_stats(config.stats_file, new_stats)
    print("Run completed successfully.")
    return 0


def _try_notify_error(telegram: TelegramClient, chat_id: str, message: str) -> None:
    try:
        telegram.send_message(chat_id, build_error_report(message))
    except TelegramAPIError:
        pass


if __name__ == "__main__":
    sys.exit(run())
