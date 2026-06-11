import pytest

from utils.searxng_client import SearXNGClient


class FakeResponse:
    def __init__(self, payload=None, status_code=200, json_error=None):
        self._payload = payload or {}
        self.status_code = status_code
        self._json_error = json_error
        self.text = "fake response text"

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._payload


class FakeGet:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "params": params,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return self.response


def test_search_normalizes_base_url_and_builds_params():
    fake_get = FakeGet(FakeResponse({"query": "测试", "results": []}))
    client = SearXNGClient(
        base_url="http://localhost:8080/",
        language="zh-CN",
        safesearch=1,
        categories="general",
        engines="bing,google",
        timeout=12,
        max_results=8,
        http_get=fake_get,
    )

    client.search("测试", categories="images", time_range="day", max_results=3)

    assert fake_get.calls == [
        {
            "url": "http://localhost:8080/search",
            "params": {
                "q": "测试",
                "format": "json",
                "language": "zh-CN",
                "safesearch": 1,
                "pageno": 1,
                "categories": "images",
                "engines": "bing,google",
                "time_range": "day",
            },
            "headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"
                ),
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            "timeout": 12,
        }
    ]


def test_search_maps_result_fields_and_limits_results():
    payload = {
        "query": "新能源",
        "answers": ["answer text"],
        "suggestions": ["suggested query"],
        "results": [
            {
                "title": "标题一",
                "url": "https://example.com/a",
                "content": "摘要一",
                "raw_content": "原始摘要一",
                "score": 0.9,
                "publishedDate": "2026-06-09",
                "engine": "bing",
                "category": "general",
                "img_src": "https://example.com/image.jpg",
                "thumbnail": "https://example.com/thumb.jpg",
            },
            {
                "title": "标题二",
                "url": "https://example.com/b",
                "metadata": "摘要二",
                "pubdate": "2026-06-08",
                "img_src": "https://example.com/image.jpg",
                "thumbnail": "https://example.com/thumb.jpg",
            },
        ],
    }
    fake_get = FakeGet(FakeResponse(payload))
    client = SearXNGClient(base_url="http://localhost:8080", http_get=fake_get)

    response = client.search("新能源", max_results=1)

    assert response.query == "新能源"
    assert response.answers == ["answer text"]
    assert response.suggestions == ["suggested query"]
    assert len(response.results) == 1
    assert response.results[0].title == "标题一"
    assert response.results[0].url == "https://example.com/a"
    assert response.results[0].content == "摘要一"
    assert response.results[0].raw_content == "原始摘要一"
    assert response.results[0].published_date == "2026-06-09"
    assert response.results[0].score == 0.9
    assert response.results[0].engine == "bing"
    assert response.results[0].category == "general"
    assert response.results[0].image_url == "https://example.com/image.jpg"
    assert response.results[0].thumbnail_url == "https://example.com/thumb.jpg"


def test_search_filters_url_less_results_before_limiting():
    payload = {
        "query": "新能源",
        "results": [
            {"title": "无链接结果", "content": "不应占用结果槽位"},
            {"title": "有效结果", "url": "https://example.com/valid", "content": "摘要"},
        ],
    }
    fake_get = FakeGet(FakeResponse(payload))
    client = SearXNGClient(base_url="http://localhost:8080", http_get=fake_get)

    response = client.search("新能源", max_results=1)

    assert len(response.results) == 1
    assert response.results[0].title == "有效结果"
    assert response.results[0].url == "https://example.com/valid"


def test_search_does_not_use_page_url_as_image_url():
    payload = {
        "query": "新能源",
        "results": [
            {
                "title": "普通网页",
                "url": "https://example.com/page",
                "content": "普通网页摘要",
            },
        ],
    }
    fake_get = FakeGet(FakeResponse(payload))
    client = SearXNGClient(base_url="http://localhost:8080", http_get=fake_get)

    response = client.search("新能源")

    assert response.results[0].url == "https://example.com/page"
    assert not response.results[0].image_url


def test_search_raises_clear_error_for_disabled_json_format():
    fake_get = FakeGet(FakeResponse({"results": []}, status_code=403))
    client = SearXNGClient(base_url="http://localhost:8080", http_get=fake_get)

    with pytest.raises(RuntimeError, match="search.formats"):
        client.search("测试")


def test_search_raises_clear_error_for_non_json_response():
    fake_get = FakeGet(FakeResponse(json_error=ValueError("not json")))
    client = SearXNGClient(base_url="http://localhost:8080", http_get=fake_get)

    with pytest.raises(RuntimeError, match="JSON"):
        client.search("测试")
