from app.core.matching import extract_guids, guid_key, guid_keys, parse_guid


def test_parse_guid():
    assert parse_guid("tmdb://603") == ("tmdb", "603")
    assert parse_guid("imdb://tt0133093") == ("imdb", "tt0133093")


def test_parse_guid_invalid_returns_none():
    assert parse_guid("garbage") is None
    assert parse_guid("") is None


def test_extract_guids_builds_source_map():
    guids = ["tmdb://603", "imdb://tt0133093", "tvdb://12345"]
    assert extract_guids(guids) == {
        "tmdb": "603",
        "imdb": "tt0133093",
        "tvdb": "12345",
    }


def test_extract_guids_ignores_unparseable():
    assert extract_guids(["tmdb://1", "junk", "local://abc"]) == {"tmdb": "1", "local": "abc"}


def test_guid_key_normalizes():
    assert guid_key("tmdb", 603) == "tmdb:603"
    assert guid_key("tvdb", "12345") == "tvdb:12345"


def test_guid_keys_from_guid_list():
    keys = guid_keys(["tmdb://603", "imdb://tt1"])
    assert keys == {"tmdb:603", "imdb:tt1"}
