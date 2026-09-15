"""Reading/writing data/stats.json and computing growth between runs.

The file is committed back to the repository by the GitHub Actions workflow,
so it doubles as persistent storage across otherwise-stateless runs.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from youtube import ChannelStats, VideoStats

MISSING_RUNS_BEFORE_ARCHIVE = 3


@dataclass
class ChannelComparison:
    subscribers: int
    views: int
    video_count: int
    subscriber_growth: int | None
    view_growth: int | None
    is_first_run: bool


@dataclass
class VideoComparison:
    video_id: str
    title: str
    published_at: str
    views: int
    likes: int
    comments: int
    view_growth: int | None
    is_new: bool


@dataclass
class ComparisonResult:
    channel: ChannelComparison
    videos: list[VideoComparison] = field(default_factory=list)
    missing_video_ids: list[str] = field(default_factory=list)
    archived_video_ids: list[str] = field(default_factory=list)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_stats(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    if not content:
        return {}
    return json.loads(content)


def save_stats(path: str, stats: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def compare_and_build(
    previous: dict[str, Any],
    channel: ChannelStats,
    videos: list[VideoStats],
) -> tuple[ComparisonResult, dict[str, Any]]:
    """Compare new YouTube data against the previous snapshot.

    Returns (comparison_result, new_stats_dict). new_stats_dict is what
    should be written back to stats.json.
    """
    prev_channel = previous.get("channel") or {}
    prev_videos: dict[str, Any] = previous.get("videos") or {}
    is_first_run = not prev_channel

    channel_comparison = ChannelComparison(
        subscribers=channel.subscribers,
        views=channel.views,
        video_count=channel.video_count,
        subscriber_growth=(
            None
            if is_first_run or "subscribers" not in prev_channel
            else channel.subscribers - int(prev_channel["subscribers"])
        ),
        view_growth=(
            None
            if is_first_run or "views" not in prev_channel
            else channel.views - int(prev_channel["views"])
        ),
        is_first_run=is_first_run,
    )

    current_video_ids = {v.video_id for v in videos}
    video_comparisons: list[VideoComparison] = []
    new_videos_dict: dict[str, Any] = {}

    for video in videos:
        prev_video = prev_videos.get(video.video_id)
        is_new = prev_video is None
        view_growth: int | None
        if is_new or "views" not in (prev_video or {}):
            view_growth = None
        else:
            view_growth = video.views - int(prev_video["views"])

        video_comparisons.append(
            VideoComparison(
                video_id=video.video_id,
                title=video.title,
                published_at=video.published_at,
                views=video.views,
                likes=video.likes,
                comments=video.comments,
                view_growth=view_growth,
                is_new=is_new,
            )
        )

        new_videos_dict[video.video_id] = {
            "title": video.title,
            "views": video.views,
            "likes": video.likes,
            "comments": video.comments,
            "published_at": video.published_at,
            "status": "active",
            "missing_runs": 0,
        }

    missing_video_ids: list[str] = []
    archived_video_ids: list[str] = []

    for video_id, prev_video in prev_videos.items():
        if video_id in current_video_ids:
            continue

        status = prev_video.get("status", "active")
        missing_runs = int(prev_video.get("missing_runs", 0)) + 1

        if status == "archived":
            new_videos_dict[video_id] = prev_video
            continue

        if missing_runs >= MISSING_RUNS_BEFORE_ARCHIVE:
            archived = dict(prev_video)
            archived["status"] = "archived"
            archived["missing_runs"] = missing_runs
            new_videos_dict[video_id] = archived
            archived_video_ids.append(video_id)
        else:
            missing = dict(prev_video)
            missing["status"] = "missing"
            missing["missing_runs"] = missing_runs
            new_videos_dict[video_id] = missing
            missing_video_ids.append(video_id)

    comparison = ComparisonResult(
        channel=channel_comparison,
        videos=video_comparisons,
        missing_video_ids=missing_video_ids,
        archived_video_ids=archived_video_ids,
    )

    new_stats = {
        "channel": {
            "subscribers": channel.subscribers,
            "views": channel.views,
            "video_count": channel.video_count,
            "updated_at": _now_iso(),
        },
        "videos": new_videos_dict,
    }

    return comparison, new_stats
