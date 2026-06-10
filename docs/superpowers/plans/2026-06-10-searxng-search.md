# SearXNG Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SearXNG as the default network search backend for BettaFish while retaining Bocha and Anspire as selectable legacy backends for MediaEngine.

**Architecture:** Add a small shared SearXNG HTTP client in `utils/`, then wrap it with QueryEngine and MediaEngine adapters that preserve existing tool names and result objects. Keep Agent and prompt contracts stable so LLM-selected tool names continue to work.

**Tech Stack:** Python 3.9+, `requests`, `pydantic-settings`, Flask config API, existing `pytest` test suite.

---

## File Structure

- Create `utils/searxng_client.py`
  - Owns SearXNG URL normalization, parameter construction, HTTP request execution, JSON validation, and raw SearXNG result normalization.
- Create `tests/test_searxng_client.py`
  - Unit tests for the shared client with fake HTTP responses.
- Modify `QueryEngine/tools/search.py`
  - Add `SearXNGNewsAgency` that returns the existing `TavilyResponse` shape.
  - Make `tavily` import lazy-safe so SearXNG usage does not fail when Tavily is not installed.
- Modify `QueryEngine/tools/__init__.py`
  - Export `SearXNGNewsAgency`.
- Modify `QueryEngine/agent.py`
  - Initialize `SearXNGNewsAgency` as the default search agency.
- Modify `QueryEngine/utils/config.py`
  - Add SearXNG settings and make `TAVILY_API_KEY` optional.
- Create `tests/test_query_searxng_adapter.py`
  - Unit tests for QueryEngine result mapping and tool parameter behavior.
- Modify `MediaEngine/tools/search.py`
  - Add `SearXNGMultimodalSearch` that returns the existing `BochaResponse` shape.
- Modify `MediaEngine/tools/__init__.py`
  - Export `SearXNGMultimodalSearch`.
- Modify `MediaEngine/agent.py`
  - Add `SearXNGSearchAgent` and make `create_agent()` return it when `SEARCH_TOOL_TYPE=SearXNGAPI`.
- Modify `MediaEngine/utils/config.py`
  - Add SearXNG settings and include `SearXNGAPI` in `SEARCH_TOOL_TYPE`.
- Create `tests/test_media_searxng_adapter.py`
  - Unit tests for MediaEngine result mapping and tool parameter behavior.
- Modify `config.py`
  - Add global SearXNG settings and default `SEARCH_TOOL_TYPE` to `SearXNGAPI`.
- Modify `.env.example`
  - Document SearXNG defaults and legacy Bocha/Anspire fallback fields.
- Modify `.env` as a local runtime file only; do not stage or commit it.
  - Add non-secret SearXNG defaults while preserving existing secret values.
- Modify `app.py`
  - Expose SearXNG fields through `/api/config`.
- Modify `templates/index.html`
  - Show SearXNG configuration fields when SearXNG is selected.
- Create `tests/test_searxng_config.py`
  - Unit tests for default config values.

---

### Task 1: Shared SearXNG Client

**Files:**
- Create: `tests/test_searxng_client.py`
- Create: `utils/searxng_client.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_searxng_client.py`:

```python
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

    def __call__(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
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
                "score": 0.9,
                "publishedDate": "2026-06-09",
                "engine": "bing",
                "category": "general",
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
    assert response.results[0].raw_content == "摘要一"
    assert response.results[0].published_date == "2026-06-09"
    assert response.results[0].score == 0.9


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
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
pytest tests/test_searxng_client.py -v
```

Expected: FAIL with an import error for `utils.searxng_client`.

- [ ] **Step 3: Implement the shared client**

Create `utils/searxng_client.py`:

```python
from dataclasses import dataclass, field
import json
import time
from typing import Any, Callable, Dict, List, Optional

import requests


@dataclass
class SearXNGResult:
    title: str
    url: str
    content: str
    score: Optional[float] = None
    raw_content: Optional[str] = None
    published_date: Optional[str] = None
    engine: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None


@dataclass
class SearXNGResponse:
    query: str
    results: List[SearXNGResult] = field(default_factory=list)
    answers: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    response_time: Optional[float] = None


class SearXNGClient:
    def __init__(
        self,
        base_url: str,
        language: str = "zh-CN",
        safesearch: int = 0,
        categories: str = "general",
        engines: str = "",
        timeout: int = 30,
        max_results: int = 10,
        http_get: Optional[Callable[..., Any]] = None,
    ):
        if not base_url:
            raise ValueError("SEARXNG_BASE_URL 未配置")

        self.base_url = base_url.rstrip("/")
        self.search_url = f"{self.base_url}/search"
        self.language = language
        self.safesearch = safesearch
        self.categories = categories
        self.engines = engines
        self.timeout = timeout
        self.max_results = max_results
        self._http_get = http_get or requests.get

    def search(
        self,
        query: str,
        *,
        max_results: Optional[int] = None,
        categories: Optional[str] = None,
        engines: Optional[str] = None,
        time_range: Optional[str] = None,
        pageno: int = 1,
    ) -> SearXNGResponse:
        params = self._build_params(
            query=query,
            categories=categories,
            engines=engines,
            time_range=time_range,
            pageno=pageno,
        )
        started = time.perf_counter()
        response = self._http_get(self.search_url, params=params, timeout=self.timeout)

        if getattr(response, "status_code", None) == 403:
            raise RuntimeError(
                "SearXNG 实例拒绝 JSON 输出。请在 settings.yml 的 search.formats 中启用 json。"
            )

        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("SearXNG 返回了非 JSON 响应，请确认实例启用了 format=json。") from exc

        elapsed = time.perf_counter() - started
        result_limit = max_results if max_results is not None else self.max_results
        return self._parse_payload(payload, fallback_query=query, max_results=result_limit, response_time=elapsed)

    def _build_params(
        self,
        *,
        query: str,
        categories: Optional[str],
        engines: Optional[str],
        time_range: Optional[str],
        pageno: int,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "q": query,
            "format": "json",
            "language": self.language,
            "safesearch": self.safesearch,
            "pageno": pageno,
        }

        effective_categories = categories if categories is not None else self.categories
        effective_engines = engines if engines is not None else self.engines

        if effective_categories:
            params["categories"] = effective_categories
        if effective_engines:
            params["engines"] = effective_engines
        if time_range:
            params["time_range"] = time_range

        return params

    def _parse_payload(
        self,
        payload: Dict[str, Any],
        *,
        fallback_query: str,
        max_results: int,
        response_time: float,
    ) -> SearXNGResponse:
        raw_results = payload.get("results") or []
        parsed_results = [self._parse_result(item) for item in raw_results[:max_results]]
        parsed_results = [item for item in parsed_results if item.url]

        return SearXNGResponse(
            query=payload.get("query") or fallback_query,
            results=parsed_results,
            answers=self._normalize_text_list(payload.get("answers")),
            suggestions=self._normalize_text_list(payload.get("suggestions")),
            response_time=response_time,
        )

    def _parse_result(self, item: Dict[str, Any]) -> SearXNGResult:
        content = self._first_text(item.get("content"), item.get("metadata"), item.get("engine"))
        raw_content = self._first_text(item.get("content"), item.get("metadata"))

        return SearXNGResult(
            title=self._first_text(item.get("title"), item.get("url")),
            url=self._first_text(item.get("url")),
            content=content,
            score=item.get("score"),
            raw_content=raw_content,
            published_date=self._first_text(
                item.get("publishedDate"),
                item.get("published_date"),
                item.get("pubdate"),
            ),
            engine=self._first_text(item.get("engine")),
            category=self._first_text(item.get("category")),
            image_url=self._first_text(item.get("img_src"), item.get("content_url"), item.get("url")),
            thumbnail_url=self._first_text(item.get("thumbnail"), item.get("thumbnail_src")),
        )

    def _normalize_text_list(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [self._stringify(item) for item in value if self._stringify(item)]
        text = self._stringify(value)
        return [text] if text else []

    def _first_text(self, *values: Any) -> str:
        for value in values:
            text = self._stringify(value)
            if text:
                return text
        return ""

    def _stringify(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value).strip()
```

- [ ] **Step 4: Run the shared client tests**

Run:

```bash
pytest tests/test_searxng_client.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add utils/searxng_client.py tests/test_searxng_client.py
git commit -m "feat: add searxng client"
```

---

### Task 2: QueryEngine SearXNG Adapter

**Files:**
- Create: `tests/test_query_searxng_adapter.py`
- Modify: `QueryEngine/tools/search.py`
- Modify: `QueryEngine/tools/__init__.py`
- Modify: `QueryEngine/agent.py`
- Modify: `QueryEngine/utils/config.py`

- [ ] **Step 1: Write the failing QueryEngine adapter tests**

Create `tests/test_query_searxng_adapter.py`:

```python
from QueryEngine.tools.search import SearXNGNewsAgency


class FakeSearXNGClient:
    def __init__(self):
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
        "kwargs": {"max_results": 5, "categories": "images"},
    }
    assert fake_client.calls[3] == {
        "query": "事件 after:2026-06-01 before:2026-06-09",
        "kwargs": {"max_results": 15},
    }
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
pytest tests/test_query_searxng_adapter.py -v
```

Expected: FAIL because `SearXNGNewsAgency` is not exported from `QueryEngine.tools.search`.

- [ ] **Step 3: Make Tavily import lazy-safe**

In `QueryEngine/tools/search.py`, replace the current Tavily import block with:

```python
try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None
```

Then update `TavilyNewsAgency.__init__` to begin with:

```python
        if TavilyClient is None:
            raise ImportError("Tavily库未安装，请运行 `pip install tavily-python` 进行安装。")
```

Expected result: importing `QueryEngine.tools.search` no longer fails when only SearXNG is used.

- [ ] **Step 4: Add the QueryEngine SearXNG adapter**

In `QueryEngine/tools/search.py`, add this import near the other imports:

```python
from utils.searxng_client import SearXNGClient
```

Add this class after `TavilyNewsAgency`:

```python
class SearXNGNewsAgency:
    """
    SearXNG-backed news search tools with the same public tool methods as TavilyNewsAgency.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        language: str = "zh-CN",
        safesearch: int = 0,
        categories: str = "general",
        engines: str = "",
        timeout: int = 30,
        max_results: int = 10,
        client: Optional[SearXNGClient] = None,
    ):
        self._client = client or SearXNGClient(
            base_url=base_url,
            language=language,
            safesearch=safesearch,
            categories=categories,
            engines=engines,
            timeout=timeout,
            max_results=max_results,
        )

    @classmethod
    def from_config(cls, config: Any) -> "SearXNGNewsAgency":
        return cls(
            base_url=getattr(config, "SEARXNG_BASE_URL", "http://localhost:8080"),
            language=getattr(config, "SEARXNG_LANGUAGE", "zh-CN"),
            safesearch=int(getattr(config, "SEARXNG_SAFESEARCH", 0)),
            categories=getattr(config, "SEARXNG_CATEGORIES", "general"),
            engines=getattr(config, "SEARXNG_ENGINES", ""),
            timeout=int(getattr(config, "SEARXNG_TIMEOUT", 30)),
            max_results=int(getattr(config, "SEARXNG_MAX_RESULTS", 10)),
        )

    @with_graceful_retry(SEARCH_API_RETRY_CONFIG, default_return=TavilyResponse(query="搜索失败"))
    def _search_internal(self, **kwargs) -> TavilyResponse:
        query = kwargs.pop("query")
        response = self._client.search(query, **kwargs)
        return self._to_tavily_response(response)

    def _to_tavily_response(self, response) -> TavilyResponse:
        results = [
            SearchResult(
                title=item.title,
                url=item.url,
                content=item.content,
                score=item.score,
                raw_content=item.raw_content,
                published_date=item.published_date,
            )
            for item in response.results
        ]
        images = [
            ImageResult(url=item.image_url, description=item.title)
            for item in response.results
            if item.image_url
        ]
        return TavilyResponse(
            query=response.query,
            answer=response.answers[0] if response.answers else None,
            results=results,
            images=images,
            response_time=response.response_time,
        )

    def basic_search_news(self, query: str, max_results: int = 7) -> TavilyResponse:
        print(f"--- TOOL: SearXNG基础新闻搜索 (query: {query}) ---")
        return self._search_internal(query=query, max_results=max_results)

    def deep_search_news(self, query: str) -> TavilyResponse:
        print(f"--- TOOL: SearXNG深度新闻搜索 (query: {query}) ---")
        return self._search_internal(query=query, max_results=20)

    def search_news_last_24_hours(self, query: str) -> TavilyResponse:
        print(f"--- TOOL: SearXNG搜索24小时内新闻 (query: {query}) ---")
        return self._search_internal(query=query, max_results=10, time_range="day")

    def search_news_last_week(self, query: str) -> TavilyResponse:
        print(f"--- TOOL: SearXNG搜索最近一周新闻 (query: {query}) ---")
        return self._search_internal(query=f"{query} 最近一周", max_results=10, time_range="month")

    def search_images_for_news(self, query: str) -> TavilyResponse:
        print(f"--- TOOL: SearXNG查找新闻图片 (query: {query}) ---")
        return self._search_internal(query=query, max_results=5, categories="images")

    def search_news_by_date(self, query: str, start_date: str, end_date: str) -> TavilyResponse:
        dated_query = f"{query} after:{start_date} before:{end_date}"
        print(f"--- TOOL: SearXNG按日期搜索新闻 (query: {dated_query}) ---")
        return self._search_internal(query=dated_query, max_results=15)
```

Also add `Any` to the existing typing import:

```python
from typing import List, Dict, Any, Optional
```

- [ ] **Step 5: Export the QueryEngine adapter**

Modify `QueryEngine/tools/__init__.py` so imports include `SearXNGNewsAgency`:

```python
from .search import (
    TavilyNewsAgency,
    SearXNGNewsAgency,
    SearchResult,
    TavilyResponse,
    ImageResult,
    print_response_summary
)
```

Update `__all__`:

```python
__all__ = [
    "TavilyNewsAgency",
    "SearXNGNewsAgency",
    "SearchResult",
    "TavilyResponse",
    "ImageResult",
    "print_response_summary"
]
```

- [ ] **Step 6: Make QueryEngine default to SearXNG**

In `QueryEngine/agent.py`, replace:

```python
from .tools import TavilyNewsAgency, TavilyResponse
```

with:

```python
from .tools import SearXNGNewsAgency, TavilyResponse
```

Replace the search agency initialization:

```python
        self.search_agency = TavilyNewsAgency(api_key=self.config.TAVILY_API_KEY)
```

with:

```python
        self.search_agency = SearXNGNewsAgency.from_config(self.config)
```

Replace the search tool log:

```python
        logger.info(f"搜索工具集: TavilyNewsAgency (支持6种搜索工具)")
```

with:

```python
        logger.info("搜索工具集: SearXNGNewsAgency (支持6种搜索工具)")
```

- [ ] **Step 7: Add QueryEngine SearXNG config fields**

In `QueryEngine/utils/config.py`, change the search config section to:

```python
    # ================== 网络工具配置 ====================
    TAVILY_API_KEY: Optional[str] = Field(None, description="Tavily API密钥，仅保留用于旧工具兼容")
    SEARXNG_BASE_URL: str = Field("http://localhost:8080", description="SearXNG Base URL，例如 http://localhost:8080")
    SEARXNG_LANGUAGE: str = Field("zh-CN", description="SearXNG 搜索语言")
    SEARXNG_SAFESEARCH: int = Field(0, description="SearXNG 安全搜索等级，0关闭，1中等，2严格")
    SEARXNG_CATEGORIES: str = Field("general", description="SearXNG 默认搜索分类")
    SEARXNG_ENGINES: str = Field("", description="SearXNG 指定搜索引擎，逗号分隔；为空使用实例默认")
    SEARXNG_TIMEOUT: int = Field(30, description="SearXNG 请求超时秒数")
    SEARXNG_MAX_RESULTS: int = Field(10, description="SearXNG 默认最大结果数")
```

Update `print_config()` to replace the Tavily-only line with:

```python
    message += f"SearXNG Base URL: {config.SEARXNG_BASE_URL}\n"
    message += f"Tavily API Key: {'已配置' if config.TAVILY_API_KEY else '未配置（默认不需要）'}\n"
```

- [ ] **Step 8: Run QueryEngine adapter tests**

Run:

```bash
pytest tests/test_query_searxng_adapter.py -v
```

Expected: all tests PASS.

- [ ] **Step 9: Commit Task 2**

Run:

```bash
git add QueryEngine/tools/search.py QueryEngine/tools/__init__.py QueryEngine/agent.py QueryEngine/utils/config.py tests/test_query_searxng_adapter.py
git commit -m "feat: use searxng in query engine"
```

---

### Task 3: MediaEngine SearXNG Adapter

**Files:**
- Create: `tests/test_media_searxng_adapter.py`
- Modify: `MediaEngine/tools/search.py`
- Modify: `MediaEngine/tools/__init__.py`
- Modify: `MediaEngine/agent.py`
- Modify: `MediaEngine/utils/config.py`

- [ ] **Step 1: Write the failing MediaEngine adapter tests**

Create `tests/test_media_searxng_adapter.py`:

```python
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
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
pytest tests/test_media_searxng_adapter.py -v
```

Expected: FAIL because `SearXNGMultimodalSearch` is not exported from `MediaEngine.tools.search`.

- [ ] **Step 3: Add the MediaEngine SearXNG adapter**

In `MediaEngine/tools/search.py`, add this import near the existing imports:

```python
from utils.searxng_client import SearXNGClient
```

Add this class before `AnspireAISearch`:

```python
class SearXNGMultimodalSearch:
    """
    SearXNG-backed multimodal search adapter returning the BochaResponse shape.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        language: str = "zh-CN",
        safesearch: int = 0,
        categories: str = "general",
        engines: str = "",
        timeout: int = 30,
        max_results: int = 10,
        client: Optional[SearXNGClient] = None,
    ):
        self._client = client or SearXNGClient(
            base_url=base_url,
            language=language,
            safesearch=safesearch,
            categories=categories,
            engines=engines,
            timeout=timeout,
            max_results=max_results,
        )

    @classmethod
    def from_config(cls, config: Any) -> "SearXNGMultimodalSearch":
        return cls(
            base_url=getattr(config, "SEARXNG_BASE_URL", "http://localhost:8080"),
            language=getattr(config, "SEARXNG_LANGUAGE", "zh-CN"),
            safesearch=int(getattr(config, "SEARXNG_SAFESEARCH", 0)),
            categories=getattr(config, "SEARXNG_CATEGORIES", "general"),
            engines=getattr(config, "SEARXNG_ENGINES", ""),
            timeout=int(getattr(config, "SEARXNG_TIMEOUT", 30)),
            max_results=int(getattr(config, "SEARXNG_MAX_RESULTS", 10)),
        )

    @with_graceful_retry(SEARCH_API_RETRY_CONFIG, default_return=BochaResponse(query="搜索失败"))
    def _search_internal(self, **kwargs) -> BochaResponse:
        query = kwargs.pop("query")
        response = self._client.search(query, **kwargs)
        return self._to_bocha_response(response)

    def _to_bocha_response(self, response) -> BochaResponse:
        final_response = BochaResponse(query=response.query)
        final_response.answer = response.answers[0] if response.answers else None
        final_response.webpages = [
            WebpageResult(
                name=item.title,
                url=item.url,
                snippet=item.content,
                display_url=item.url,
                date_last_crawled=item.published_date,
            )
            for item in response.results
        ]
        final_response.images = [
            ImageResult(
                name=item.title,
                content_url=item.image_url,
                host_page_url=item.url,
                thumbnail_url=item.thumbnail_url,
            )
            for item in response.results
            if item.image_url
        ]
        return final_response

    def comprehensive_search(self, query: str, max_results: int = 10) -> BochaResponse:
        logger.info(f"--- TOOL: SearXNG全面综合搜索 (query: {query}) ---")
        return self._search_internal(query=query, max_results=max_results)

    def web_search_only(self, query: str, max_results: int = 15) -> BochaResponse:
        logger.info(f"--- TOOL: SearXNG纯网页搜索 (query: {query}) ---")
        return self._search_internal(query=query, max_results=max_results)

    def search_for_structured_data(self, query: str) -> BochaResponse:
        logger.info(f"--- TOOL: SearXNG结构化查询 (query: {query}) ---")
        return self._search_internal(query=query, max_results=5)

    def search_last_24_hours(self, query: str) -> BochaResponse:
        logger.info(f"--- TOOL: SearXNG搜索24小时内信息 (query: {query}) ---")
        return self._search_internal(query=query, max_results=10, time_range="day")

    def search_last_week(self, query: str) -> BochaResponse:
        logger.info(f"--- TOOL: SearXNG搜索最近一周信息 (query: {query}) ---")
        return self._search_internal(query=f"{query} 最近一周", max_results=10, time_range="month")
```

Ensure the existing typing import includes `Any`:

```python
from typing import List, Dict, Any, Optional, Literal
```

- [ ] **Step 4: Export the MediaEngine adapter**

Modify `MediaEngine/tools/__init__.py` so imports include `SearXNGMultimodalSearch`:

```python
from .search import (
    BochaMultimodalSearch,
    AnspireAISearch,
    SearXNGMultimodalSearch,
    WebpageResult,
    ImageResult,
    ModalCardResult,
    BochaResponse,
    AnspireResponse,
    print_response_summary
)
```

Update `__all__`:

```python
__all__ = [
    "BochaMultimodalSearch",
    "AnspireAISearch",
    "SearXNGMultimodalSearch",
    "WebpageResult",
    "ImageResult",
    "ModalCardResult",
    "BochaResponse",
    "AnspireResponse",
    "print_response_summary"
]
```

- [ ] **Step 5: Make MediaEngine select SearXNG by default**

In `MediaEngine/agent.py`, replace:

```python
from .tools import BochaMultimodalSearch, BochaResponse, AnspireAISearch, AnspireResponse
```

with:

```python
from .tools import BochaMultimodalSearch, BochaResponse, AnspireAISearch, AnspireResponse, SearXNGMultimodalSearch
```

Add this class before `AnspireSearchAgent`:

```python
class SearXNGSearchAgent(DeepSearchAgent):
    """调用 SearXNG 搜索引擎的 Media Agent"""

    def __init__(self, config: Settings | None = None):
        self.config = config or settings
        self.llm_client = self._initialize_llm()
        self.search_agency = SearXNGMultimodalSearch.from_config(self.config)
        self._initialize_nodes()
        self.state = State()
        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)
        logger.info("Media Agent已初始化")
        logger.info(f"使用LLM: {self.llm_client.get_model_info()}")
        logger.info("搜索工具集: SearXNGMultimodalSearch")
```

Modify `create_agent()`:

```python
    if settings.SEARCH_TOOL_TYPE == "SearXNGAPI":
        return SearXNGSearchAgent(settings)
    if settings.SEARCH_TOOL_TYPE == "AnspireAPI":
        return AnspireSearchAgent(settings)
    return DeepSearchAgent(settings)
```

- [ ] **Step 6: Add MediaEngine SearXNG config fields**

In `MediaEngine/utils/config.py`, change:

```python
    SEARCH_TOOL_TYPE: Literal["AnspireAPI", "BochaAPI"] = Field("AnspireAPI", description="网络搜索工具类型，支持BochaAPI或AnspireAPI两种，默认为AnspireAPI")
```

to:

```python
    SEARCH_TOOL_TYPE: Literal["SearXNGAPI", "AnspireAPI", "BochaAPI"] = Field("SearXNGAPI", description="网络搜索工具类型，默认使用SearXNGAPI，可切换BochaAPI或AnspireAPI")
```

Add these fields after `SEARCH_TOOL_TYPE`:

```python
    SEARXNG_BASE_URL: str = Field("http://localhost:8080", description="SearXNG Base URL，例如 http://localhost:8080")
    SEARXNG_LANGUAGE: str = Field("zh-CN", description="SearXNG 搜索语言")
    SEARXNG_SAFESEARCH: int = Field(0, description="SearXNG 安全搜索等级，0关闭，1中等，2严格")
    SEARXNG_CATEGORIES: str = Field("general", description="SearXNG 默认搜索分类")
    SEARXNG_ENGINES: str = Field("", description="SearXNG 指定搜索引擎，逗号分隔；为空使用实例默认")
    SEARXNG_TIMEOUT: int = Field(30, description="SearXNG 请求超时秒数")
    SEARXNG_MAX_RESULTS: int = Field(10, description="SearXNG 默认最大结果数")
```

- [ ] **Step 7: Run MediaEngine adapter tests**

Run:

```bash
pytest tests/test_media_searxng_adapter.py -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit Task 3**

Run:

```bash
git add MediaEngine/tools/search.py MediaEngine/tools/__init__.py MediaEngine/agent.py MediaEngine/utils/config.py tests/test_media_searxng_adapter.py
git commit -m "feat: use searxng in media engine"
```

---

### Task 4: Global Config, Example Env, and UI

**Files:**
- Create: `tests/test_searxng_config.py`
- Modify: `config.py`
- Modify: `.env.example`
- Modify: `.env` as a local runtime file only; do not stage or commit it.
- Modify: `app.py`
- Modify: `templates/index.html`

- [ ] **Step 1: Write the failing config tests**

Create `tests/test_searxng_config.py`:

```python
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
```

- [ ] **Step 2: Run the config test and verify it fails**

Run:

```bash
pytest tests/test_searxng_config.py -v
```

Expected: FAIL because global `Settings` does not define the `SEARXNG_*` fields and still defaults to `AnspireAPI`.

- [ ] **Step 3: Update global settings**

In `config.py`, replace the current network tool configuration block with:

```python
    # ================== 网络工具配置 ====================
    SEARCH_TOOL_TYPE: Literal["SearXNGAPI", "AnspireAPI", "BochaAPI"] = Field("SearXNGAPI", description="网络搜索工具类型，默认使用SearXNGAPI，可切换BochaAPI或AnspireAPI")

    # SearXNG（推荐自托管，默认地址：http://localhost:8080）
    SEARXNG_BASE_URL: str = Field("http://localhost:8080", description="SearXNG Base URL，例如 http://localhost:8080")
    SEARXNG_LANGUAGE: str = Field("zh-CN", description="SearXNG 搜索语言")
    SEARXNG_SAFESEARCH: int = Field(0, description="SearXNG 安全搜索等级，0关闭，1中等，2严格")
    SEARXNG_CATEGORIES: str = Field("general", description="SearXNG 默认搜索分类")
    SEARXNG_ENGINES: str = Field("", description="SearXNG 指定搜索引擎，逗号分隔；为空使用实例默认")
    SEARXNG_TIMEOUT: int = Field(30, description="SearXNG 请求超时秒数")
    SEARXNG_MAX_RESULTS: int = Field(10, description="SearXNG 默认最大结果数")

    # Tavily API（旧 QueryEngine 工具保留兼容，不作为默认检索工具）
    TAVILY_API_KEY: Optional[str] = Field(None, description="Tavily API密钥，仅保留用于旧工具兼容")

    # Bocha API（申请地址：https://open.bochaai.com/）
    BOCHA_BASE_URL: Optional[str] = Field("https://api.bocha.cn/v1/ai-search", description="Bocha AI 搜索BaseUrl或博查网页搜索BaseUrl")
    BOCHA_WEB_SEARCH_API_KEY: Optional[str] = Field(None, description="Bocha API密钥，用于Bocha搜索")

    # Anspire AI Search API（申请地址：https://open.anspire.cn/?share_code=3E1FUOUH）
    ANSPIRE_BASE_URL: Optional[str] = Field("https://plugin.anspire.cn/api/ntsearch/search", description="Anspire AI 搜索BaseUrl")
    ANSPIRE_API_KEY: Optional[str] = Field(None, description="Anspire AI Search API密钥，用于Anspire搜索")
```

- [ ] **Step 4: Expose SearXNG fields through Flask config API**

In `app.py`, update `CONFIG_KEYS` so the network section contains:

```python
    'SEARCH_TOOL_TYPE',
    'SEARXNG_BASE_URL',
    'SEARXNG_LANGUAGE',
    'SEARXNG_SAFESEARCH',
    'SEARXNG_CATEGORIES',
    'SEARXNG_ENGINES',
    'SEARXNG_TIMEOUT',
    'SEARXNG_MAX_RESULTS',
    'TAVILY_API_KEY',
    'BOCHA_WEB_SEARCH_API_KEY',
    'ANSPIRE_API_KEY'
```

- [ ] **Step 5: Update the UI config fields**

In `templates/index.html`, replace the `外部检索工具` group with:

```javascript
            {
                title: '外部检索工具',
                subtitle: '默认使用自托管 SearXNG；Bocha 和 Anspire 可作为旧检索工具后备',
                fields: [
                    {
                        key: 'SEARCH_TOOL_TYPE',
                        label: '选择检索工具',
                        type: 'select',
                        options: ['SearXNGAPI', 'BochaAPI', 'AnspireAPI']
                    },
                    { key: 'SEARXNG_BASE_URL', label: 'SearXNG Base URL', condition: { key: 'SEARCH_TOOL_TYPE', value: 'SearXNGAPI' } },
                    { key: 'SEARXNG_LANGUAGE', label: 'SearXNG 语言', condition: { key: 'SEARCH_TOOL_TYPE', value: 'SearXNGAPI' } },
                    { key: 'SEARXNG_SAFESEARCH', label: 'SearXNG 安全搜索', condition: { key: 'SEARCH_TOOL_TYPE', value: 'SearXNGAPI' } },
                    { key: 'SEARXNG_CATEGORIES', label: 'SearXNG 分类', condition: { key: 'SEARCH_TOOL_TYPE', value: 'SearXNGAPI' } },
                    { key: 'SEARXNG_ENGINES', label: 'SearXNG 引擎', condition: { key: 'SEARCH_TOOL_TYPE', value: 'SearXNGAPI' } },
                    { key: 'SEARXNG_TIMEOUT', label: 'SearXNG 超时秒数', condition: { key: 'SEARCH_TOOL_TYPE', value: 'SearXNGAPI' } },
                    { key: 'SEARXNG_MAX_RESULTS', label: 'SearXNG 最大结果数', condition: { key: 'SEARCH_TOOL_TYPE', value: 'SearXNGAPI' } },
                    { key: 'TAVILY_API_KEY', label: 'Tavily API Key（旧工具兼容）', type: 'password' },
                    { key: 'BOCHA_WEB_SEARCH_API_KEY', label: 'Bocha API Key', type: 'password', condition: { key: 'SEARCH_TOOL_TYPE', value: 'BochaAPI' } },
                    { key: 'ANSPIRE_API_KEY', label: 'Anspire API Key', type: 'password', condition: { key: 'SEARCH_TOOL_TYPE', value: 'AnspireAPI' } }
                ]
            }
```

- [ ] **Step 6: Update example env**

In `.env.example`, replace the current network tool section with:

```env
# ================== 网络工具配置 ====================
# 默认使用 SearXNG。推荐自托管，并确认 settings.yml 中 search.formats 启用了 json。
SEARCH_TOOL_TYPE=SearXNGAPI
SEARXNG_BASE_URL=http://localhost:8080
SEARXNG_LANGUAGE=zh-CN
SEARXNG_SAFESEARCH=0
SEARXNG_CATEGORIES=general
SEARXNG_ENGINES=
SEARXNG_TIMEOUT=30
SEARXNG_MAX_RESULTS=10

# Tavily API密钥，仅保留用于旧 QueryEngine 工具兼容
TAVILY_API_KEY=

# Anspire AI Search API（旧检索工具后备）
ANSPIRE_BASE_URL=https://plugin.anspire.cn/api/ntsearch/search
ANSPIRE_API_KEY=

# Bocha AI Search API（旧检索工具后备）
BOCHA_BASE_URL=https://api.bocha.cn/v1/ai-search
BOCHA_WEB_SEARCH_API_KEY=
```

- [ ] **Step 7: Update local env without touching secrets**

Edit `.env` by adding these keys if they are absent and changing only `SEARCH_TOOL_TYPE` if present:

```env
SEARCH_TOOL_TYPE=SearXNGAPI
SEARXNG_BASE_URL=http://localhost:8080
SEARXNG_LANGUAGE=zh-CN
SEARXNG_SAFESEARCH=0
SEARXNG_CATEGORIES=general
SEARXNG_ENGINES=
SEARXNG_TIMEOUT=30
SEARXNG_MAX_RESULTS=10
```

Keep all existing `*_API_KEY`, database, and model values unchanged.

Do not run `git add .env`. Treat `.env` as a local runtime configuration file even if it appears in `git status`.

- [ ] **Step 8: Run config test**

Run:

```bash
pytest tests/test_searxng_config.py -v
```

Expected: all tests PASS.

- [ ] **Step 9: Commit Task 4**

Run:

```bash
git add config.py .env.example app.py templates/index.html tests/test_searxng_config.py
git commit -m "feat: default search config to searxng"
```

---

### Task 5: Verification and Local Smoke Test

**Files:**
- Modify only files that fail formatting or tests from previous tasks.

- [ ] **Step 1: Run focused SearXNG tests**

Run:

```bash
pytest tests/test_searxng_client.py tests/test_query_searxng_adapter.py tests/test_media_searxng_adapter.py tests/test_searxng_config.py -v
```

Expected: all tests PASS.

- [ ] **Step 2: Run existing ForumEngine tests**

Run:

```bash
cd tests
python run_tests.py
```

Expected: script exits with code 0 and reports all ForumEngine log parsing tests passing.

- [ ] **Step 3: Run full pytest**

Run from repository root:

```bash
pytest
```

Expected: test suite exits with code 0. If an unrelated external dependency blocks full pytest, record the exact failing command and traceback in the final implementation report.

- [ ] **Step 4: Verify SearXNG can be reached from QueryEngine**

Run from repository root while the local SearXNG instance is available on `http://localhost:8080`:

```bash
python -c "from QueryEngine.tools.search import SearXNGNewsAgency; agency=SearXNGNewsAgency(base_url='http://localhost:8080'); response=agency.basic_search_news('SearXNG 测试', max_results=1); print(len(response.results)); print(response.query)"
```

Expected: prints a result count and the query text. A count of `0` is acceptable only if SearXNG responds successfully but has no result for the test query. HTTP 403 means the SearXNG instance needs `json` in `search.formats`.

- [ ] **Step 5: Verify SearXNG can be reached from MediaEngine**

Run from repository root while the local SearXNG instance is available on `http://localhost:8080`:

```bash
python -c "from MediaEngine.tools.search import SearXNGMultimodalSearch; search=SearXNGMultimodalSearch(base_url='http://localhost:8080'); response=search.comprehensive_search('SearXNG 测试', max_results=1); print(len(response.webpages)); print(response.query)"
```

Expected: prints a webpage count and the query text. A count of `0` is acceptable only if SearXNG responds successfully but has no result for the test query. HTTP 403 means the SearXNG instance needs `json` in `search.formats`.

- [ ] **Step 6: Inspect Git status**

Run:

```bash
git status --short
```

Expected: only intended implementation files are modified. Existing untracked `AGENTS.md` remains untracked unless the user explicitly asks to add it.

- [ ] **Step 7: Commit verification fixes if any were needed**

If Step 1 through Step 6 required fixes after the previous commits, run:

```bash
git add utils/searxng_client.py QueryEngine/tools/search.py QueryEngine/tools/__init__.py QueryEngine/agent.py QueryEngine/utils/config.py MediaEngine/tools/search.py MediaEngine/tools/__init__.py MediaEngine/agent.py MediaEngine/utils/config.py config.py .env.example app.py templates/index.html tests/test_searxng_client.py tests/test_query_searxng_adapter.py tests/test_media_searxng_adapter.py tests/test_searxng_config.py
git commit -m "fix: stabilize searxng search integration"
```

Expected: commit succeeds only if there are verification-driven code or test changes.
