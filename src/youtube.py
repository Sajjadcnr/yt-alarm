"""YouTube Data API v3 access, kept quota-efficient.

Strategy (see project README for the full rationale):
    channels.list  -> statistics + uploads playlist id      (1 unit)
    playlistItems.list (paginated, 50/page) -> all video ids (1 unit / page)
    videos.list (batched, 50 ids/call) -> stats for all videos (1 unit / call)

We deliberately never call search.list, and we never fetch videos one at a time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
PLAYLIST_PAGE_SIZE = 50
VIDEOS_BATCH_SIZE = 50
REQUEST_TIMEOUT = 30


class YouTubeAPIError(Exception):
    """Raised for any non-recoverable YouTube API failure."""


class YouTubeQuotaExceededError(YouTubeAPIError):
    """Raised specifically when the daily quota has been exhausted."""


@dataclass(frozen=True)
class ChannelStats:
    channel_id: str
    title: str
    subscribers: int
    views: int
    video_count: int
    uploads_playlist_id: str


@dataclass(frozen=True)
class VideoStats:
    video_id: str
    title: str
    published_at: str
    views: int
    likes: int
    comments: int


def _get(session: requests.Session, path: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        resp = session.get(f"{YOUTUBE_API_BASE}/{path}", params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise YouTubeAPIError(f"Network error calling YouTube API ({path}): {exc}") from exc

    if resp.status_code == 403:
        body = resp.text
        if "quotaExceeded" in body or "quota" in body.lower():
            raise YouTubeQuotaExceededError("YouTube API quota exceeded")
        raise YouTubeAPIError(f"YouTube API 403 Forbidden on {path}: {body}")

    if not resp.ok:
        raise YouTubeAPIError(f"YouTube API error {resp.status_code} on {path}: {resp.text}")

    return resp.json()


class YouTubeClient:
    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        self._api_key = api_key
        self._session = session or requests.Session()

    def get_channel_stats(self, channel_id: str) -> ChannelStats:
        data = _get(
            self._session,
            "channels",
            {
                "part": "snippet,statistics,contentDetails",
                "id": channel_id,
                "key": self._api_key,
            },
        )
        items = data.get("items", [])
        if not items:
            raise YouTubeAPIError(f"Channel not found: {channel_id}")

        item = items[0]
        stats = item.get("statistics", {})
        content_details = item.get("contentDetails", {})
        uploads_playlist_id = content_details.get("relatedPlaylists", {}).get("uploads")
        if not uploads_playlist_id:
            raise YouTubeAPIError("Channel has no uploads playlist")

        return ChannelStats(
            channel_id=channel_id,
            title=item.get("snippet", {}).get("title", ""),
            subscribers=int(stats.get("subscriberCount", 0)),
            views=int(stats.get("viewCount", 0)),
            video_count=int(stats.get("videoCount", 0)),
            uploads_playlist_id=uploads_playlist_id,
        )

    def get_all_video_ids(self, uploads_playlist_id: str) -> list[str]:
        video_ids: list[str] = []
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {
                "part": "contentDetails",
                "playlistId": uploads_playlist_id,
                "maxResults": PLAYLIST_PAGE_SIZE,
                "key": self._api_key,
            }
            if page_token:
                params["pageToken"] = page_token

            data = _get(self._session, "playlistItems", params)

            for item in data.get("items", []):
                video_id = item.get("contentDetails", {}).get("videoId")
                if video_id:
                    video_ids.append(video_id)

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return video_ids

    def get_videos_stats(self, video_ids: list[str]) -> list[VideoStats]:
        results: list[VideoStats] = []

        for start in range(0, len(video_ids), VIDEOS_BATCH_SIZE):
            batch = video_ids[start : start + VIDEOS_BATCH_SIZE]
            data = _get(
                self._session,
                "videos",
                {
                    "part": "snippet,statistics",
                    "id": ",".join(batch),
                    "key": self._api_key,
                },
            )

            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                results.append(
                    VideoStats(
                        video_id=item["id"],
                        title=snippet.get("title", ""),
                        published_at=snippet.get("publishedAt", ""),
                        views=int(stats.get("viewCount", 0)),
                        likes=int(stats.get("likeCount", 0)),
                        comments=int(stats.get("commentCount", 0)),
                    )
                )

        return results

    def fetch_full_snapshot(self, channel_id: str) -> tuple[ChannelStats, list[VideoStats]]:
        channel = self.get_channel_stats(channel_id)
        video_ids = self.get_all_video_ids(channel.uploads_playlist_id)
        videos = self.get_videos_stats(video_ids)
        return channel, videos
