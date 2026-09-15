from formatter import (
    build_report,
    build_stats_text_from_saved,
    build_videos_text_from_saved,
    _fmt_growth,
    _fmt_number,
)
from storage import ChannelComparison, ComparisonResult, VideoComparison


def test_fmt_number_adds_thousands_separators():
    assert _fmt_number(1234567) == "1,234,567"


def test_fmt_growth_positive():
    assert _fmt_growth(37) == "📈 +37"


def test_fmt_growth_zero():
    assert _fmt_growth(0) == "➖ 0"


def test_fmt_growth_negative():
    assert _fmt_growth(-5) == "📉 -5"


def test_fmt_growth_none_is_na():
    assert _fmt_growth(None) == "N/A"


def test_build_report_first_run_shows_na_growth():
    comparison = ComparisonResult(
        channel=ChannelComparison(
            subscribers=1000,
            views=50000,
            video_count=1,
            subscriber_growth=None,
            view_growth=None,
            is_first_run=True,
        ),
        videos=[
            VideoComparison(
                video_id="v1",
                title="Video One",
                published_at="2026-01-01T00:00:00Z",
                views=100,
                likes=1,
                comments=0,
                view_growth=None,
                is_new=True,
            )
        ],
    )

    report = build_report(comparison)

    assert "N/A" in report
    assert "Subscribers" in report
    assert "1,000" in report
    assert "اولین اجرا" in report


def test_build_report_shows_positive_growth_sorted_first():
    comparison = ComparisonResult(
        channel=ChannelComparison(
            subscribers=1037,
            views=62450,
            video_count=2,
            subscriber_growth=37,
            view_growth=12450,
            is_first_run=False,
        ),
        videos=[
            VideoComparison(
                video_id="v1",
                title="Low Growth",
                published_at="x",
                views=200,
                likes=1,
                comments=0,
                view_growth=10,
                is_new=False,
            ),
            VideoComparison(
                video_id="v2",
                title="High Growth",
                published_at="x",
                views=5000,
                likes=1,
                comments=0,
                view_growth=2430,
                is_new=False,
            ),
        ],
    )

    report = build_report(comparison)

    assert report.index("High Growth") < report.index("Low Growth")
    assert "+37" in report
    assert "+12,450" in report


def test_build_stats_text_from_saved_handles_missing_data():
    text = build_stats_text_from_saved({})
    assert "هنوز" in text


def test_build_stats_text_from_saved_formats_channel():
    stats = {"channel": {"subscribers": 1000, "views": 50000, "video_count": 3, "updated_at": "2026-09-15T15:00:00Z"}}
    text = build_stats_text_from_saved(stats)
    assert "1,000" in text
    assert "50,000" in text


def test_build_videos_text_from_saved_excludes_archived():
    stats = {
        "videos": {
            "v1": {"title": "Active", "views": 100, "status": "active"},
            "v2": {"title": "Archived", "views": 999999, "status": "archived"},
        }
    }
    text = build_videos_text_from_saved(stats)
    assert "Active" in text
    assert "Archived" not in text
