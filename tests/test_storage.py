import os

from storage import compare_and_build, load_stats, save_stats
from youtube import ChannelStats, VideoStats


def make_channel(subscribers=1000, views=50000, video_count=2):
    return ChannelStats(
        channel_id="UCxxxx",
        title="My Channel",
        subscribers=subscribers,
        views=views,
        video_count=video_count,
        uploads_playlist_id="UUxxxx",
    )


def make_video(video_id, views, likes=10, comments=1, title="Video", published="2026-01-01T00:00:00Z"):
    return VideoStats(
        video_id=video_id,
        title=title,
        published_at=published,
        views=views,
        likes=likes,
        comments=comments,
    )


def test_load_stats_missing_file_returns_empty(tmp_path):
    path = os.path.join(tmp_path, "stats.json")
    assert load_stats(path) == {}


def test_load_stats_empty_file_returns_empty(tmp_path):
    path = os.path.join(tmp_path, "stats.json")
    with open(path, "w") as f:
        f.write("")
    assert load_stats(path) == {}


def test_save_and_load_roundtrip(tmp_path):
    path = os.path.join(tmp_path, "nested", "stats.json")
    save_stats(path, {"channel": {"subscribers": 5}})
    loaded = load_stats(path)
    assert loaded == {"channel": {"subscribers": 5}}


def test_first_run_has_no_growth():
    channel = make_channel()
    videos = [make_video("v1", 100)]

    comparison, new_stats = compare_and_build({}, channel, videos)

    assert comparison.channel.is_first_run is True
    assert comparison.channel.subscriber_growth is None
    assert comparison.channel.view_growth is None
    assert comparison.videos[0].is_new is True
    assert comparison.videos[0].view_growth is None
    assert new_stats["channel"]["subscribers"] == 1000
    assert new_stats["videos"]["v1"]["views"] == 100


def test_growth_calculated_on_second_run():
    previous = {
        "channel": {"subscribers": 1000, "views": 50000, "video_count": 1},
        "videos": {"v1": {"title": "Video", "views": 100, "likes": 10, "comments": 1, "published_at": "x"}},
    }
    channel = make_channel(subscribers=1037, views=62450, video_count=1)
    videos = [make_video("v1", 1340)]

    comparison, new_stats = compare_and_build(previous, channel, videos)

    assert comparison.channel.is_first_run is False
    assert comparison.channel.subscriber_growth == 37
    assert comparison.channel.view_growth == 12450
    assert comparison.videos[0].view_growth == 1240
    assert comparison.videos[0].is_new is False


def test_new_video_detected():
    previous = {
        "channel": {"subscribers": 1000, "views": 50000, "video_count": 1},
        "videos": {"v1": {"title": "Old", "views": 100, "likes": 1, "comments": 0, "published_at": "x"}},
    }
    channel = make_channel(video_count=2)
    videos = [make_video("v1", 150), make_video("v2", 0, title="New Video")]

    comparison, new_stats = compare_and_build(previous, channel, videos)

    new_video = next(v for v in comparison.videos if v.video_id == "v2")
    assert new_video.is_new is True
    assert new_video.view_growth is None
    assert "v2" in new_stats["videos"]


def test_missing_video_marked_but_not_deleted():
    previous = {
        "channel": {"subscribers": 1000, "views": 50000, "video_count": 1},
        "videos": {
            "v1": {"title": "Gone", "views": 100, "likes": 1, "comments": 0, "published_at": "x", "status": "active", "missing_runs": 0}
        },
    }
    channel = make_channel(video_count=0)
    videos = []

    comparison, new_stats = compare_and_build(previous, channel, videos)

    assert "v1" in new_stats["videos"]
    assert new_stats["videos"]["v1"]["status"] == "missing"
    assert new_stats["videos"]["v1"]["missing_runs"] == 1
    assert "v1" in comparison.missing_video_ids


def test_video_archived_after_repeated_missing_runs():
    previous = {
        "channel": {"subscribers": 1000, "views": 50000, "video_count": 1},
        "videos": {
            "v1": {
                "title": "Gone",
                "views": 100,
                "likes": 1,
                "comments": 0,
                "published_at": "x",
                "status": "missing",
                "missing_runs": 2,
            }
        },
    }
    channel = make_channel(video_count=0)
    videos = []

    comparison, new_stats = compare_and_build(previous, channel, videos)

    assert new_stats["videos"]["v1"]["status"] == "archived"
    assert "v1" in comparison.archived_video_ids


def test_archived_video_stays_archived_and_is_not_reported_missing_again():
    previous = {
        "channel": {"subscribers": 1000, "views": 50000, "video_count": 1},
        "videos": {
            "v1": {
                "title": "Gone",
                "views": 100,
                "likes": 1,
                "comments": 0,
                "published_at": "x",
                "status": "archived",
                "missing_runs": 3,
            }
        },
    }
    channel = make_channel(video_count=0)
    videos = []

    comparison, new_stats = compare_and_build(previous, channel, videos)

    assert new_stats["videos"]["v1"]["status"] == "archived"
    assert "v1" not in comparison.missing_video_ids
    assert "v1" not in comparison.archived_video_ids
