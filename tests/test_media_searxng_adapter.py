import MediaEngine.tools.search as search_module
from MediaEngine.tools.search import SearXNGMultimodalSearch


class FakeSearXNGClient:
    def __init__(self):
        self.calls = []

    def search(self, query, **kwargs):
        from utils.searxng_client import SearXNGResponse, SearXNGResult

        self.calls.append({"query": query, "kwargs": kwargs})
        return SearXNGResponse(
            query=query,
            answers=["摘要"],
            results=[
                SearXNGResult(
                    title="页面标题",
                    url="https://example.com/page",
                    content="页面摘要",
                    raw_content="页面摘要",
                    published_date="2026-06-09",
                    image_url="https://example.com/image.jpg",
                    thumbnail_url="https://example.com/thumb.jpg",
                )
            ],
        )


def test_comprehensive_search_returns_bocha_compatible_response():
    fake_client = FakeSearXNGClient()
    search = SearXNGMultimodalSearch(client=fake_client)

    response = search.comprehensive_search("品牌 舆情", max_results=10)

    assert fake_client.calls == [
        {"query": "品牌 舆情", "kwargs": {"max_results": 10}}
    ]
    assert response.query == "品牌 舆情"
    assert response.answer == "摘要"
    assert response.follow_ups == []
    assert response.modal_cards == []
    assert len(response.webpages) == 1
    assert response.webpages[0].name == "页面标题"
    assert response.webpages[0].url == "https://example.com/page"
    assert response.webpages[0].snippet == "页面摘要"
    assert response.webpages[0].date_last_crawled == "2026-06-09"
    assert len(response.images) == 1
    assert response.images[0].content_url == "https://example.com/image.jpg"
    assert response.images[0].thumbnail_url == "https://example.com/thumb.jpg"


def test_media_tools_map_to_searxng_parameters():
    fake_client = FakeSearXNGClient()
    search = SearXNGMultimodalSearch(client=fake_client)

    search.web_search_only("事件", max_results=15)
    search.search_for_structured_data("汇率")
    search.search_last_24_hours("事件")
    search.search_last_week("事件")

    assert fake_client.calls[0] == {
        "query": "事件",
        "kwargs": {"max_results": 15},
    }
    assert fake_client.calls[1] == {
        "query": "汇率",
        "kwargs": {"max_results": 5},
    }
    assert fake_client.calls[2] == {
        "query": "事件",
        "kwargs": {"max_results": 10, "time_range": "day"},
    }
    assert fake_client.calls[3] == {
        "query": "事件 最近一周",
        "kwargs": {"max_results": 10, "time_range": "month"},
    }


def test_from_config_uses_defaults_for_legacy_config(monkeypatch):
    constructed = []

    class LegacyConfig:
        pass

    class FakeConstructedSearXNGClient(FakeSearXNGClient):
        def __init__(self, **kwargs):
            super().__init__()
            constructed.append(kwargs)

    monkeypatch.setattr(
        search_module,
        "SearXNGClient",
        FakeConstructedSearXNGClient,
    )

    search = SearXNGMultimodalSearch.from_config(LegacyConfig())
    response = search.comprehensive_search("品牌 舆情")

    assert constructed == [
        {
            "base_url": "http://localhost:8080",
            "language": "zh-CN",
            "safesearch": 0,
            "categories": "general",
            "engines": "",
            "timeout": 30,
            "max_results": 10,
        }
    ]
    assert response.query == "品牌 舆情"
    assert response.answer == "摘要"


def test_create_agent_selects_searxng_agent(monkeypatch):
    import MediaEngine.agent as agent_module

    monkeypatch.setattr(
        agent_module.SearXNGSearchAgent,
        "__init__",
        lambda self, config=None: None,
    )
    monkeypatch.setattr(agent_module.settings, "SEARCH_TOOL_TYPE", "SearXNGAPI")

    result = agent_module.create_agent()

    assert result.__class__ is agent_module.SearXNGSearchAgent
