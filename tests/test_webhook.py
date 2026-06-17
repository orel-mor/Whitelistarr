import json

from fastapi.testclient import TestClient

from app.webhook import create_app, parse_plex_payload, parse_seerr_payload


class FakeSync:
    def __init__(self):
        self.calls = []
        self.rating_key_calls = []

    def sync_by_ids(self, media_type, tmdb_id=None, tvdb_id=None):
        self.calls.append((media_type, tmdb_id, tvdb_id))
        return True

    def sync_by_rating_key(self, rating_key):
        self.rating_key_calls.append(rating_key)
        return True


def _client(sync, secret=""):
    app = create_app(
        lambda: sync,
        webhook_path="/webhook/seerr",
        plex_webhook_path="/webhook/plex",
        secret=secret,
    )
    return TestClient(app)


def test_webhook_503_when_unconfigured():
    app = create_app(lambda: None, webhook_path="/webhook/seerr",
                     plex_webhook_path="/webhook/plex")
    client = TestClient(app)
    resp = client.post("/webhook/seerr",
                       json={"notification_type": "MEDIA_AVAILABLE",
                             "media": {"media_type": "movie", "tmdbId": "1"}})
    assert resp.status_code == 503


class TestParsePayload:
    def test_parses_movie_available(self):
        payload = {
            "notification_type": "MEDIA_AVAILABLE",
            "media": {"media_type": "movie", "tmdbId": "603", "tvdbId": ""},
        }
        event = parse_seerr_payload(payload)
        assert event.notification_type == "MEDIA_AVAILABLE"
        assert event.media_type == "movie"
        assert event.tmdb_id == 603
        assert event.tvdb_id is None

    def test_parses_tv_to_show_domain(self):
        payload = {
            "notification_type": "MEDIA_AVAILABLE",
            "media": {"media_type": "tv", "tmdbId": "1", "tvdbId": "121361"},
        }
        event = parse_seerr_payload(payload)
        assert event.media_type == "show"
        assert event.tvdb_id == 121361

    def test_returns_event_with_no_media(self):
        event = parse_seerr_payload({"notification_type": "TEST_NOTIFICATION"})
        assert event.notification_type == "TEST_NOTIFICATION"
        assert event.media_type is None


class TestWebhookEndpoint:
    def test_health(self):
        client = _client(FakeSync())
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "version" in body

    def test_media_available_triggers_sync(self):
        sync = FakeSync()
        client = _client(sync)
        resp = client.post(
            "/webhook/seerr",
            json={
                "notification_type": "MEDIA_AVAILABLE",
                "media": {"media_type": "movie", "tmdbId": "603"},
            },
        )
        assert resp.status_code == 200
        assert sync.calls == [("movie", 603, None)]

    def test_test_notification_does_not_sync(self):
        sync = FakeSync()
        client = _client(sync)
        resp = client.post("/webhook/seerr", json={"notification_type": "TEST_NOTIFICATION"})
        assert resp.status_code == 200
        assert sync.calls == []

    def test_non_available_event_ignored(self):
        sync = FakeSync()
        client = _client(sync)
        resp = client.post(
            "/webhook/seerr",
            json={"notification_type": "MEDIA_PENDING", "media": {"media_type": "movie", "tmdbId": "1"}},
        )
        assert resp.status_code == 200
        assert sync.calls == []

    def test_secret_required_when_configured(self):
        sync = FakeSync()
        client = _client(sync, secret="s3cret")
        resp = client.post(
            "/webhook/seerr",
            json={"notification_type": "MEDIA_AVAILABLE", "media": {"media_type": "movie", "tmdbId": "1"}},
        )
        assert resp.status_code == 401
        assert sync.calls == []

    def test_secret_accepted_via_query_token(self):
        sync = FakeSync()
        client = _client(sync, secret="s3cret")
        resp = client.post(
            "/webhook/seerr?token=s3cret",
            json={"notification_type": "MEDIA_AVAILABLE", "media": {"media_type": "movie", "tmdbId": "1"}},
        )
        assert resp.status_code == 200
        assert sync.calls == [("movie", 1, None)]


class TestParsePlexPayload:
    def test_parses_library_new(self):
        event = parse_plex_payload(
            {"event": "library.new", "Metadata": {"ratingKey": "12345", "type": "movie"}}
        )
        assert event.event == "library.new"
        assert event.rating_key == "12345"

    def test_missing_metadata(self):
        event = parse_plex_payload({"event": "media.play"})
        assert event.event == "media.play"
        assert event.rating_key is None


class TestPlexWebhookEndpoint:
    def test_library_new_triggers_rating_key_sync(self):
        sync = FakeSync()
        client = _client(sync)
        payload = {"event": "library.new", "Metadata": {"ratingKey": "12345", "type": "movie"}}
        resp = client.post("/webhook/plex", data={"payload": json.dumps(payload)})
        assert resp.status_code == 200
        assert sync.rating_key_calls == ["12345"]

    def test_non_library_new_ignored(self):
        sync = FakeSync()
        client = _client(sync)
        payload = {"event": "media.play", "Metadata": {"ratingKey": "12345"}}
        resp = client.post("/webhook/plex", data={"payload": json.dumps(payload)})
        assert resp.status_code == 200
        assert sync.rating_key_calls == []

    def test_missing_payload_is_ok(self):
        sync = FakeSync()
        client = _client(sync)
        resp = client.post("/webhook/plex", data={})
        assert resp.status_code == 200
        assert sync.rating_key_calls == []

    def test_secret_required(self):
        sync = FakeSync()
        client = _client(sync, secret="s3cret")
        payload = {"event": "library.new", "Metadata": {"ratingKey": "1", "type": "movie"}}
        resp = client.post("/webhook/plex", data={"payload": json.dumps(payload)})
        assert resp.status_code == 401
        assert sync.rating_key_calls == []

    def test_secret_accepted_via_query_token(self):
        sync = FakeSync()
        client = _client(sync, secret="s3cret")
        payload = {"event": "library.new", "Metadata": {"ratingKey": "1", "type": "movie"}}
        resp = client.post("/webhook/plex?token=s3cret", data={"payload": json.dumps(payload)})
        assert resp.status_code == 200
        assert sync.rating_key_calls == ["1"]
