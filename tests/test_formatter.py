from formatter import (
    MAX_MESSAGE_LENGTH,
    build_report_messages,
    build_stats_text_from_saved,
    build_videos_text_from_saved,
    escape_markdown,
    top_growth_videos,
    total_positive_growth,
    new_videos,
    _fmt_growth,
    _fmt_number,
    _fmt_signed_number,
    _pack_messages,
)
from storage import ChannelComparison, ComparisonResult, VideoComparison


def make_channel(
    subscribers=1000,
    views=50000,
    video_count=1,
    subscriber_growth=None,
    view_growth=None,
    is_first_run=False,
):
    return ChannelComparison(
        subscribers=subscribers,
        views=views,
        video_count=video_count,
        subscriber_growth=subscriber_growth,
        view_growth=view_growth,
        is_first_run=is_first_run,
    )


def make_video(video_id, views=100, view_growth=None, is_new=False, title=None, published_at="2026-01-01T00:00:00Z"):
    return VideoComparison(
        video_id=video_id,
        title=title or f"Video {video_id}",
        published_at=published_at,
        views=views,
        likes=0,
        comments=0,
        view_growth=view_growth,
        is_new=is_new,
    )


# --- number / growth formatting -------------------------------------------------


def test_fmt_number_adds_thousands_separators():
    assert _fmt_number(1284521) == "1,284,521"


def test_fmt_number_negative():
    assert _fmt_number(-240) == "-240"


def test_fmt_growth_positive_video():
    assert _fmt_growth(1240) == "📈 +1,240"


def test_fmt_growth_zero_video():
    assert _fmt_growth(0) == "➖ 0"


def test_fmt_growth_negative_video():
    assert _fmt_growth(-240) == "📉 -240"


def test_fmt_growth_positive_subscribers():
    assert _fmt_growth(7) == "📈 +7"


def test_fmt_growth_zero_subscribers():
    assert _fmt_growth(0) == "➖ 0"


def test_fmt_growth_negative_subscribers():
    assert _fmt_growth(-2) == "📉 -2"


def test_fmt_growth_none_is_na():
    assert _fmt_growth(None) == "N/A"


def test_fmt_signed_number_positive():
    assert _fmt_signed_number(4821) == "+4,821"


def test_fmt_signed_number_zero():
    assert _fmt_signed_number(0) == "0"


def test_fmt_signed_number_negative():
    assert _fmt_signed_number(-5) == "-5"


def test_escape_markdown_escapes_special_chars():
    assert escape_markdown("video_test*name`[x]") == "video\\_test\\*name\\`\\[x]"


# --- ranking / aggregation --------------------------------------------------------


def test_top_growth_videos_sorts_descending_and_caps_at_five():
    videos = [
        make_video("v1", view_growth=100),
        make_video("v2", view_growth=900),
        make_video("v3", view_growth=500),
        make_video("v4", view_growth=300),
        make_video("v5", view_growth=200),
        make_video("v6", view_growth=700),
        make_video("v7", view_growth=1),
    ]
    top = top_growth_videos(videos)

    assert [v.video_id for v in top] == ["v2", "v6", "v3", "v4", "v5"]
    assert len(top) == 5


def test_top_growth_videos_excludes_zero_negative_and_unknown():
    videos = [
        make_video("v1", view_growth=0),
        make_video("v2", view_growth=-50),
        make_video("v3", view_growth=None),
        make_video("v4", view_growth=10),
    ]
    top = top_growth_videos(videos)

    assert [v.video_id for v in top] == ["v4"]


def test_total_positive_growth_ignores_zero_negative_and_none():
    videos = [
        make_video("v1", view_growth=1240),
        make_video("v2", view_growth=-300),
        make_video("v3", view_growth=0),
        make_video("v4", view_growth=None),
        make_video("v5", view_growth=3581),
    ]
    assert total_positive_growth(videos) == 4821


def test_total_positive_growth_all_non_positive_is_zero():
    videos = [make_video("v1", view_growth=-10), make_video("v2", view_growth=0)]
    assert total_positive_growth(videos) == 0


def test_new_videos_detects_is_new_flag():
    videos = [make_video("v1", is_new=False), make_video("v2", is_new=True)]
    result = new_videos(videos)
    assert [v.video_id for v in result] == ["v2"]


# --- full report building ---------------------------------------------------------


def test_report_first_run_shows_no_comparison_note():
    comparison = ComparisonResult(
        channel=make_channel(subscriber_growth=None, view_growth=None, is_first_run=True),
        videos=[make_video("v1", views=100, is_new=True)],
    )
    messages = build_report_messages(comparison)
    report = "\n".join(messages)

    assert "N/A" in report
    assert "اولین بررسی" in report


def test_report_shows_channel_growth_with_correct_sign():
    comparison = ComparisonResult(
        channel=make_channel(subscribers=12483, views=1284521, subscriber_growth=7, view_growth=3842),
        videos=[],
    )
    report = "\n".join(build_report_messages(comparison))

    assert "12,483" in report
    assert "📈 +7" in report
    assert "1,284,521" in report
    assert "📈 +3,842" in report


def test_report_growth_section_sorted_top_first():
    comparison = ComparisonResult(
        channel=make_channel(),
        videos=[
            make_video("v1", title="Video Low", view_growth=640),
            make_video("v2", title="Video High", view_growth=1842),
            make_video("v3", title="Video Mid", view_growth=921),
        ],
    )
    report = "\n".join(build_report_messages(comparison))

    assert report.index("Video High") < report.index("Video Mid") < report.index("Video Low")
    assert "🥇" in report
    assert "🥈" in report
    assert "🥉" in report


def test_report_no_positive_growth_shows_placeholder():
    comparison = ComparisonResult(
        channel=make_channel(),
        videos=[make_video("v1", view_growth=0), make_video("v2", view_growth=-10)],
    )
    report = "\n".join(build_report_messages(comparison))

    assert "در این بازه رشد ویویی ثبت نشده است" in report


def test_report_new_videos_section_listed():
    comparison = ComparisonResult(
        channel=make_channel(),
        videos=[
            make_video("v1", title="New One", views=1240, is_new=True),
            make_video("v2", title="New Two", views=530, is_new=True),
        ],
    )
    report = "\n".join(build_report_messages(comparison))

    assert "ویدیوهای جدید" in report
    assert "New One" in report
    assert "1,240 views" in report
    assert "New Two" in report
    assert "530 views" in report


def test_report_overall_status_totals():
    comparison = ComparisonResult(
        channel=make_channel(),
        videos=[
            make_video("v1", title="Video A", view_growth=1842, is_new=False),
            make_video("v2", title="Video B", view_growth=2979, is_new=False),
            make_video("v3", title="New Video", views=10, is_new=True),
        ],
    )
    report = "\n".join(build_report_messages(comparison))

    assert "وضعیت کلی" in report
    assert "بیشترین رشد: Video B" in report
    assert "مجموع رشد ویو ویدیوها: `+4,821`" in report
    assert "ویدیوی جدید: `1`" in report


# --- message splitting -------------------------------------------------------------


def test_pack_messages_single_block_fits_one_message():
    messages = _pack_messages(["short block one", "short block two"])
    assert len(messages) == 1


def test_pack_messages_splits_when_over_limit():
    big_block = "x" * 3000
    blocks = [big_block, big_block, big_block]
    messages = _pack_messages(blocks)

    assert len(messages) > 1
    for message in messages:
        assert len(message) <= MAX_MESSAGE_LENGTH


def test_pack_messages_never_splits_a_single_block_across_messages():
    blocks = [f"block-{i}: " + ("y" * 200) for i in range(30)]
    messages = _pack_messages(blocks)

    for block in blocks:
        assert sum(block in message for message in messages) == 1


def test_report_splits_into_multiple_messages_for_many_new_videos():
    videos = [
        make_video(f"v{i}", title=f"ویدیوی بسیار طولانی شماره {i} " * 5, views=i, is_new=True)
        for i in range(80)
    ]
    comparison = ComparisonResult(channel=make_channel(video_count=80), videos=videos)

    messages = build_report_messages(comparison, max_videos=80)

    assert len(messages) > 1
    for message in messages:
        assert len(message) <= MAX_MESSAGE_LENGTH

    combined = "\n".join(messages)
    for i in range(80):
        assert f"ویدیوی بسیار طولانی شماره {i} " in combined


def test_report_caps_new_videos_and_notes_remainder():
    videos = [make_video(f"v{i}", title=f"New {i}", is_new=True) for i in range(5)]
    comparison = ComparisonResult(channel=make_channel(video_count=5), videos=videos)

    report = "\n".join(build_report_messages(comparison, max_videos=3))

    assert "New 0" in report
    assert "New 1" in report
    assert "New 2" in report
    assert "و 2 ویدیوی جدید دیگر" in report


# --- saved-stats commands (unchanged behaviour) ------------------------------------


def test_build_stats_text_from_saved_handles_missing_data():
    text = build_stats_text_from_saved({})
    assert "هنوز" in text


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
