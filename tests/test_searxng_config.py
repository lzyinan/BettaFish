from config import Settings


def test_global_settings_default_to_searxng_without_api_key():
    settings = Settings(_env_file=None)

    assert settings.SEARCH_TOOL_TYPE == "SearXNGAPI"
    assert settings.SEARXNG_BASE_URL == "http://localhost:8080"
    assert settings.SEARXNG_LANGUAGE == "zh-CN"
    assert settings.SEARXNG_SAFESEARCH == 0
    assert settings.SEARXNG_CATEGORIES == "general"
    assert settings.SEARXNG_ENGINES == ""
    assert settings.SEARXNG_TIMEOUT == 30
    assert settings.SEARXNG_MAX_RESULTS == 10
