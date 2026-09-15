"""Builds the human-readable Telegram report."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from storage import ComparisonResult, VideoComparison

MEDAL_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def _fmt_number(value: int) -> str:
    return f"{value:,}"


def _fmt_growth(growth: int | None) -> str:
    if growth is None:
        return "N/A"
    if growth > 0:
        return f"📈 +{_fmt_number(growth)}"
    if growth < 0:
        return f"📉 {_fmt_number(growth)}"
    return "➖ 0"


def _rank_label(index: int) -> str:
    if index < len(MEDAL_EMOJIS):
        return MEDAL_EMOJIS[index]
    return f"{index + 1}."


def _current_time_str(tz_name: str) -> str:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).strftime("%H:%M")


def _sort_videos(videos: list[VideoComparison]) -> list[VideoComparison]:
    def sort_key(v: VideoComparison) -> tuple[int, int]:
        if v.view_growth is not None and v.view_growth > 0:
            return (0, -v.view_growth)
        if v.view_growth is None or v.view_growth == 0:
            return (1, 0)
        return (2, -v.view_growth)

    return sorted(videos, key=sort_key)


def build_report(
    comparison: ComparisonResult,
    tz_name: str = "Asia/Tehran",
    max_videos: int = 20,
) -> str:
    lines: list[str] = []
    lines.append("📊 YouTube Analytics")
    lines.append("")
    lines.append(f"🕐 {_current_time_str(tz_name)}")
    lines.append("")

    ch = comparison.channel
    lines.append("👥 Subscribers")
    lines.append(_fmt_number(ch.subscribers))
    lines.append(_fmt_growth(ch.subscriber_growth))
    lines.append("")
    lines.append("👁 Channel Views")
    lines.append(_fmt_number(ch.views))
    lines.append(_fmt_growth(ch.view_growth))
    lines.append("")
    lines.append("🎬 Videos")
    lines.append(_fmt_number(ch.video_count))

    new_videos = [v for v in comparison.videos if v.is_new]
    if new_videos:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━")
        lines.append("")
        lines.append("🆕 New Videos")
        for v in new_videos:
            lines.append("")
            lines.append(f"🎥 {v.title}")
            lines.append(f"👁 {_fmt_number(v.views)} views")

    ranked = _sort_videos(comparison.videos)
    shown = ranked[:max_videos]

    growing = [v for v in shown if v.view_growth is not None and v.view_growth > 0]
    others = [v for v in shown if v not in growing]

    if growing:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━")
        lines.append("")
        lines.append("🔥 بیشترین رشد")
        for i, v in enumerate(growing):
            lines.append("")
            lines.append(f"{_rank_label(i)} {v.title}")
            lines.append(f"👁 {_fmt_number(v.views)} views")
            lines.append(_fmt_growth(v.view_growth))

    if others:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━")
        lines.append("")
        lines.append("📊 سایر ویدیوها")
        for v in others:
            lines.append("")
            lines.append(f"🎥 {v.title}")
            lines.append(f"👁 {_fmt_number(v.views)} views")
            lines.append(_fmt_growth(v.view_growth))

    if comparison.missing_video_ids:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━")
        lines.append("")
        lines.append(f"⚠️ {len(comparison.missing_video_ids)} video(s) missing from channel listing")

    if comparison.archived_video_ids:
        lines.append(f"🗑 {len(comparison.archived_video_ids)} video(s) archived (missing for {3}+ runs)")

    if ch.is_first_run:
        lines.append("")
        lines.append("━━━━━━━━━━━━━━")
        lines.append("")
        lines.append("ℹ️ اولین اجرا — Growth از اجرای بعدی محاسبه می‌شود.")

    return "\n".join(lines)


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
