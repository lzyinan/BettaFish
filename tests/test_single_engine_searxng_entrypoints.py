from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_query_streamlit_entrypoint_does_not_require_tavily_for_searxng_default():
    source = (PROJECT_ROOT / "SingleEngineApp" / "query_engine_streamlit_app.py").read_text(encoding="utf-8")

    assert 'SEARCH_TOOL_TYPE=getattr(settings, "SEARCH_TOOL_TYPE", "SearXNGAPI")' in source
    assert "SEARXNG_BASE_URL=settings.SEARXNG_BASE_URL" in source
    assert "请在您的环境变量中设置TAVILY_API_KEY" not in source


def test_media_streamlit_entrypoint_supports_searxng_default():
    source = (PROJECT_ROOT / "SingleEngineApp" / "media_engine_streamlit_app.py").read_text(encoding="utf-8")

    assert 'SEARCH_TOOL_TYPE="SearXNGAPI"' in source
    assert "SearXNGSearchAgent" in source
