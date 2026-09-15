import pytest

from youtube import (
    YouTubeAPIError,
    YouTubeClient,
    YouTubeQuotaExceededError,
)


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text or str(json_data)
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._json_data


class FakeSession:
    def __init__(self, responses):
        # responses: list of FakeResponse, consumed in order per .get() call
        self._responses = list(responses)
        self.requests_made = []

    def get(self, url, params=None, timeout=None):
        self.requests_made.append((url, params))
        if not self._responses:
            raise AssertionError("No more fake responses queued")
        return self._responses.pop(0)


def test_get_channel_stats_success():
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "items": [
                        {
                            "snippet": {"title": "My Channel"},
                            "statistics": {
                                "subscriberCount": "1000",
                                "viewCount": "50000",
                                "videoCount": "42",
                            },
                            "contentDetails": {
                                "relatedPlaylists": {"uploads": "UUxxxx"}
                            },
                        }
                    ]
                },
            )
        ]
    )
    client = YouTubeClient(api_key="fake", session=session)
    stats = client.get_channel_stats("UCxxxx")

    assert stats.subscribers == 1000
    assert stats.views == 50000
    assert stats.video_count == 42
    assert stats.uploads_playlist_id == "UUxxxx"
    assert stats.title == "My Channel"


def test_get_channel_stats_not_found():
    session = FakeSession([FakeResponse(200, {"items": []})])
    client = YouTubeClient(api_key="fake", session=session)

    with pytest.raises(YouTubeAPIError):
        client.get_channel_stats("UCmissing")


def test_get_all_video_ids_paginates():
    page1 = FakeResponse(
        200,
        {
            "items": [{"contentDetails": {"videoId": "v1"}}, {"contentDetails": {"videoId": "v2"}}],
            "nextPageToken": "TOKEN2",
        },
    )
    page2 = FakeResponse(
        200,
        {"items": [{"contentDetails": {"videoId": "v3"}}]},
    )
    session = FakeSession([page1, page2])
    client = YouTubeClient(api_key="fake", session=session)

    video_ids = client.get_all_video_ids("UUxxxx")

    assert video_ids == ["v1", "v2", "v3"]
    assert len(session.requests_made) == 2
    assert "pageToken" not in session.requests_made[0][1]
    assert session.requests_made[1][1]["pageToken"] == "TOKEN2"


def test_get_videos_stats_batches_requests():
    video_ids = [f"v{i}" for i in range(120)]  # forces 3 batches of <=50

    def make_response(batch_size):
        return FakeResponse(
            200,
            {
                "items": [
                    {
                        "id": f"v{i}",
                        "snippet": {"title": f"Video {i}", "publishedAt": "2026-01-01T00:00:00Z"},
                        "statistics": {"viewCount": str(i), "likeCount": "1", "commentCount": "2"},
                    }
                    for i in range(batch_size)
                ]
            },
        )

    session = FakeSession([make_response(50), make_response(50), make_response(20)])
    client = YouTubeClient(api_key="fake", session=session)

    results = client.get_videos_stats(video_ids)

    assert len(session.requests_made) == 3
    for _, params in session.requests_made:
        assert len(params["id"].split(",")) <= 50
    assert len(results) == 120


def test_quota_exceeded_raises_specific_error():
    session = FakeSession(
        [FakeResponse(403, json_data={"error": {"errors": [{"reason": "quotaExceeded"}]}}, text="quotaExceeded")]
    )
    client = YouTubeClient(api_key="fake", session=session)

    with pytest.raises(YouTubeQuotaExceededError):
        client.get_channel_stats("UCxxxx")


def test_generic_api_error_raises():
    session = FakeSession([FakeResponse(500, text="server error")])
    client = YouTubeClient(api_key="fake", session=session)

    with pytest.raises(YouTubeAPIError):
        client.get_channel_stats("UCxxxx")
