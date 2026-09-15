"""Builds the Telegram report(s) for a monitoring run.

Report layout (see README): channel stats -> top view-growth videos (top 5,
positive only) -> new videos -> an overall status recap. Telegram enforces a
4096-character limit per message, so the report is built as a list of
messages: the main summary always fits in the first message, and video
detail sections spill into additional messages if needed.
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from storage import ComparisonResult, VideoComparison

MAX_MESSAGE_LENGTH = 4096
TOP_GROWTH_LIMIT = 5
MEDALS = ["🥇", "🥈", "🥉"]
SEPARATOR = "━━━━━━━━━━━━━━"
ELLIPSIS = "…"

_MARKDOWN_SPECIAL_CHARS = re.compile(r"([_*`\[])")


def escape_markdown(text: str) -> str:
    """Escape Telegram legacy-Markdown special characters in dynamic text
    (video/channel titles) so they never break `parse_mode=Markdown` or get
    misrendered."""
    return _MARKDOWN_SPECIAL_CHARS.sub(r"\\\1", text)


def _fmt_number(value: int) -> str:
    if value < 0:
        return f"-{abs(value):,}"
    return f"{value:,}"


def _fmt_signed_number(value: int) -> str:
    if value > 0:
        return f"+{_fmt_number(value)}"
    if value < 0:
        return _fmt_number(value)
    return "0"


def _fmt_growth(growth: int | None) -> str:
    """📈 +N / ➖ 0 / 📉 -N, or N/A when there is nothing to compare against."""
    if growth is None:
        return "N/A"
    if growth > 0:
        return f"📈 +{_fmt_number(growth)}"
    if growth < 0:
        return f"📉 {_fmt_number(growth)}"
    return "➖ 0"


def _current_time_str(tz_name: str) -> str:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).strftime("%H:%M")


def _rank_label(index: int) -> str:
    if index < len(MEDALS):
        return MEDALS[index]
    return f"{index + 1}."


def _format_published_date(published_at: str) -> str | None:
    if not published_at:
        return None
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.strftime("%Y-%m-%d")


def top_growth_videos(
    videos: list[VideoComparison], limit: int = TOP_GROWTH_LIMIT
) -> list[VideoComparison]:
    """Videos with strictly positive view growth, sorted descending, capped at `limit`."""
    positive = [v for v in videos if v.view_growth is not None and v.view_growth > 0]
    return sorted(positive, key=lambda v: v.view_growth, reverse=True)[:limit]


def total_positive_growth(videos: list[VideoComparison]) -> int:
    """Sum of positive view growth only; zero/negative/unknown growth is ignored."""
    return sum(v.view_growth for v in videos if v.view_growth is not None and v.view_growth > 0)


def new_videos(videos: list[VideoComparison]) -> list[VideoComparison]:
    return [v for v in videos if v.is_new]


def _safe_truncate(block: str, limit: int) -> str:
    if len(block) <= limit:
        return block
    return block[: max(limit - len(ELLIPSIS), 0)] + ELLIPSIS


def _pack_messages(blocks: list[str]) -> list[str]:
    """Greedily pack blocks (each kept intact, never split mid-block) into
    messages no longer than MAX_MESSAGE_LENGTH."""
    messages: list[str] = []
    current: list[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current, current_len
        if current:
            messages.append("\n\n".join(current))
        current = []
        current_len = 0

    for raw_block in blocks:
        block = _safe_truncate(raw_block, MAX_MESSAGE_LENGTH)
        addition = len(block) + (2 if current else 0)

        if current and current_len + addition > MAX_MESSAGE_LENGTH:
            flush()
            addition = len(block)

        current.append(block)
        current_len += addition

    flush()
    return messages or [""]


def _build_header_block(comparison: ComparisonResult, tz_name: str) -> str:
    ch = comparison.channel
    subscriber_growth = _fmt_growth(ch.subscriber_growth)
    view_growth = _fmt_growth(ch.view_growth)

    lines = [
        "📊 *YouTube — گزارش ساعتی*",
        "",
        f"🕐 {_current_time_str(tz_name)}",
        "",
        "👥 *Subscribers*",
        f"`{_fmt_number(ch.subscribers)}`",
        subscriber_growth if ch.subscriber_growth is None else f"{subscriber_growth} از بررسی قبلی",
        "",
        "👁️ *Total Channel Views*",
        f"`{_fmt_number(ch.views)}`",
        view_growth if ch.view_growth is None else f"{view_growth} از بررسی قبلی",
        "",
        "🎬 *Total Videos*",
        f"`{_fmt_number(ch.video_count)}`",
    ]

    if ch.is_first_run:
        lines.append("")
        lines.append("ℹ️ اولین بررسی — داده‌ای برای مقایسه وجود ندارد.")

    return "\n".join(lines)


def _build_growth_section_blocks(videos: list[VideoComparison]) -> list[str]:
    top = top_growth_videos(videos)
    blocks = ["🔥 *بیشترین رشد ویو*"]

    if not top:
        blocks.append("➖ در این بازه رشد ویویی ثبت نشده است.")
        return blocks

    for i, v in enumerate(top):
        title = escape_markdown(v.title)
        blocks.append(f"{_rank_label(i)} {title}\n👁️ `+{_fmt_number(v.view_growth)} views`")

    return blocks


def _build_new_videos_section_blocks(videos: list[VideoComparison], max_items: int) -> list[str]:
    videos_new = new_videos(videos)
    if not videos_new:
        return []

    blocks = ["🆕 *ویدیوهای جدید*"]
    shown, remainder = videos_new[:max_items], videos_new[max_items:]

    for v in shown:
        title = escape_markdown(v.title)
        entry = f"• {title}\n👁️ `{_fmt_number(v.views)} views`"
        published = _format_published_date(v.published_at)
        if published:
            entry += f"\n📅 {published}"
        blocks.append(entry)

    if remainder:
        blocks.append(f"… و {_fmt_number(len(remainder))} ویدیوی جدید دیگر")

    return blocks


def _build_status_block(comparison: ComparisonResult) -> str:
    top = top_growth_videos(comparison.videos, limit=1)
    total_growth = total_positive_growth(comparison.videos)
    new_count = len(new_videos(comparison.videos))

    lines = ["📊 *وضعیت کلی*"]
    if top:
        lines.append(f"🔥 بیشترین رشد: {escape_markdown(top[0].title)}")
    else:
        lines.append("🔥 بیشترین رشد: ➖ ندارد")
    lines.append(f"📈 مجموع رشد ویو ویدیوها: `{_fmt_signed_number(total_growth)}`")
    lines.append(f"🆕 ویدیوی جدید: `{new_count}`")
    lines.append("")
    lines.append("⏱️ بررسی بعدی: حدود 1 ساعت دیگر")

    return "\n".join(lines)


def build_report_messages(
    comparison: ComparisonResult,
    tz_name: str = "Asia/Tehran",
    max_videos: int = 20,
) -> list[str]:
    """Build the full report as one or more Telegram messages.

    The channel summary always opens the first message; video detail
    sections (growth ranking, new videos) and the closing status recap are
    packed in afterwards, spilling into additional messages if the combined
    text would exceed Telegram's 4096-character limit.
    """
    header_block = _build_header_block(comparison, tz_name)
    growth_blocks = _build_growth_section_blocks(comparison.videos)
    new_video_blocks = _build_new_videos_section_blocks(comparison.videos, max_videos)
    status_block = _build_status_block(comparison)

    blocks = [header_block, SEPARATOR, *growth_blocks]
    if new_video_blocks:
        blocks += [SEPARATOR, *new_video_blocks]
    blocks += [SEPARATOR, status_block]

    return _pack_messages(blocks)


def build_error_report(message: str) -> str:
    return f"⚠️ YouTube Analytics Bot Error\n\n{message}"


def build_stats_text_from_saved(stats: dict) -> str:
    channel = stats.get("channel")
    if not channel:
        return "هنوز آماری ذخیره نشده است. لطفاً منتظر اجرای بعدی بمانید."

    lines = [
        "📊 Latest Channel Stats",
        "",
        "👥 Subscribers",
        _fmt_number(int(channel.get("subscribers", 0))),
        "",
        "👁 Channel Views",
        _fmt_number(int(channel.get("views", 0))),
        "",
        "🎬 Videos",
        _fmt_number(int(channel.get("video_count", 0))),
        "",
        f"🕐 Updated: {channel.get('updated_at', 'N/A')}",
    ]
    return "\n".join(lines)


def build_videos_text_from_saved(stats: dict, max_videos: int = 20) -> str:
    videos = stats.get("videos") or {}
    active = [
        (video_id, data)
        for video_id, data in videos.items()
        if data.get("status", "active") != "archived"
    ]
    if not active:
        return "هنوز اطلاعات ویدیویی ذخیره نشده است."

    ranked = sorted(active, key=lambda item: int(item[1].get("views", 0)), reverse=True)[:max_videos]

    lines = ["🎥 Videos (by views)"]
    for i, (_, data) in enumerate(ranked):
        lines.append("")
        lines.append(f"{_rank_label(i)} {data.get('title', 'Untitled')}")
        lines.append(f"👁 {_fmt_number(int(data.get('views', 0)))} views")

    return "\n".join(lines)
