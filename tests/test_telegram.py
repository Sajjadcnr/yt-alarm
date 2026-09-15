from telegram import TelegramClient


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text or str(json_data)
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._json_data


class FakeSession:
    def __init__(self):
        self.posts = []

    def post(self, url, data=None, timeout=None):
        self.posts.append({"url": url, "data": data})
        return FakeResponse(200)


def test_send_message_includes_parse_mode_when_given():
    session = FakeSession()
    client = TelegramClient(bot_token="fake", session=session)

    client.send_message("123", "hello", parse_mode="Markdown")

    assert len(session.posts) == 1
    assert session.posts[0]["data"]["chat_id"] == "123"
    assert session.posts[0]["data"]["text"] == "hello"
    assert session.posts[0]["data"]["parse_mode"] == "Markdown"


def test_send_message_omits_parse_mode_when_not_given():
    session = FakeSession()
    client = TelegramClient(bot_token="fake", session=session)

    client.send_message("123", "hello")

    assert "parse_mode" not in session.posts[0]["data"]


def test_send_report_sends_one_request_per_message_in_order():
    session = FakeSession()
    client = TelegramClient(bot_token="fake", session=session)

    client.send_report("123", ["message one", "message two", "message three"])

    assert len(session.posts) == 3
    assert [p["data"]["text"] for p in session.posts] == ["message one", "message two", "message three"]
    for post in session.posts:
        assert post["data"]["chat_id"] == "123"
        assert post["data"]["parse_mode"] == "Markdown"
