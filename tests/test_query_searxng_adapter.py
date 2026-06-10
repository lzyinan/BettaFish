import QueryEngine.tools.search as search_module
from QueryEngine.tools.search import SearXNGNewsAgency


class FakeSearXNGClient:
    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.calls = []

    def search(self, query, **kwargs):
        from utils.searxng_client import SearXNGResponse, SearXNGResult

        self.calls.append({"query": query, "kwargs": kwargs})
        return SearXNGResponse(
            query=query,
            answers=["综合摘要"],
            response_time=0.5,
            results=[
                SearXNGResult(
                    title="新闻标题",
                    url="https://example.com/news",
                    content="新闻摘要",
                    score=0.8,
                    raw_content="新闻摘要",
                    published_date="2026-06-09",
                )
            ],
        )


def test_basic_search_news_returns_tavily_compatible_response():
    fake_client = FakeSearXNGClient()
    agency = SearXNGNewsAgency(client=fake_client)

    response = agency.basic_search_news("新能源 舆情", max_results=7)

    assert fake_client.calls == [
        {"query": "新能源 舆情", "kwargs": {"max_results": 7}}
    ]
    assert response.query == "新能源 舆情"
    assert response.answer == "综合摘要"
    assert response.response_time == 0.5
    assert len(response.results) == 1
    assert response.results[0].title == "新闻标题"
    assert response.results[0].url == "https://example.com/news"
    assert response.results[0].content == "新闻摘要"
    assert response.results[0].score == 0.8
    assert response.results[0].published_date == "2026-06-09"


def test_query_tools_map_to_searxng_parameters():
    fake_client = FakeSearXNGClient()
    agency = SearXNGNewsAgency(client=fake_client)

    agency.search_news_last_24_hours("事件")
    agency.search_news_last_week("事件")
    agency.deep_search_news("事件")
    agency.search_images_for_news("事件")
    agency.search_news_by_date("事件", "2026-06-01", "2026-06-09")

    assert fake_client.calls[0] == {
        "query": "事件",
        "kwargs": {"max_results": 10, "time_range": "day"},
    }
    assert fake_client.calls[1] == {
        "query": "事件 最近一周",
        "kwargs": {"max_results": 10, "time_range": "month"},
    }
    assert fake_client.calls[2] == {
        "query": "事件",
        "kwargs": {"max_results": 20},
    }
    assert fake_client.calls[3] == {
        "query": "事件",
        "kwargs": {"max_results": 5, "categories": "images"},
    }
    assert fake_client.calls[4] == {
        "query": "事件 after:2026-06-01 before:2026-06-09",
        "kwargs": {"max_results": 15},
    }


def test_from_config_uses_defaults_for_legacy_config(monkeypatch):
    created_clients = []

    def fake_client_factory(**kwargs):
        client = FakeSearXNGClient(**kwargs)
        created_clients.append(client)
        return client

    class LegacyConfig:
        pass

    monkeypatch.setattr(search_module, "SearXNGClient", fake_client_factory)

    agency = SearXNGNewsAgency.from_config(LegacyConfig())
    response = agency.basic_search_news("事件")

    assert created_clients[0].init_kwargs == {
        "base_url": "http://localhost:8080",
        "language": "zh-CN",
        "safesearch": 0,
        "categories": "general",
        "engines": "",
        "timeout": 30,
        "max_results": 10,
    }
    assert created_clients[0].calls == [
        {"query": "事件", "kwargs": {"max_results": 7}}
    ]
    assert response.query == "事件"
