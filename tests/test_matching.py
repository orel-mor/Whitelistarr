from app.core.matching import (
    extract_guids,
    guid_key,
    guid_keys,
    parse_guid,
    parse_legacy_guid,
)


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


def test_parse_legacy_guid_maps_known_agents():
    assert parse_legacy_guid("com.plexapp.agents.thetvdb://383203?lang=en") == ("tvdb", "383203")
    assert parse_legacy_guid("com.plexapp.agents.imdb://tt29768334?lang=en") == (
        "imdb",
        "tt29768334",
    )
    assert parse_legacy_guid("com.plexapp.agents.themoviedb://603?lang=en") == ("tmdb", "603")


def test_parse_legacy_guid_without_query_suffix():
    assert parse_legacy_guid("com.plexapp.agents.thetvdb://383203") == ("tvdb", "383203")


def test_parse_legacy_guid_ignores_unknown_or_modern():
    # Unmappable legacy agent (e.g. the HAMA anime agent) -> None.
    assert parse_legacy_guid("com.plexapp.agents.hama://tvdb-121361?lang=en") is None
    # Modern source://id guids aren't "legacy" -> None (handled by extract_guids).
    assert parse_legacy_guid("tmdb://603") is None
    assert parse_legacy_guid("garbage") is None
    assert parse_legacy_guid("") is None
