from dataclasses import dataclass, field
import json
import time
from typing import Any, Callable, Dict, List, Optional
from urllib import error, parse, request


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


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


class _UrllibResponse:
    def __init__(self, status_code: int, headers: Any, body: bytes):
        self.status_code = status_code
        self.headers = headers
        self.text = body.decode("utf-8", errors="replace")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"SearXNG HTTP {self.status_code}: {self.text[:300]}")

    def json(self):
        return json.loads(self.text)


def _default_http_get(url: str, params=None, headers=None, timeout=None):
    query = parse.urlencode(params or {}, doseq=True)
    request_url = f"{url}?{query}" if query else url
    req = request.Request(request_url, headers=headers or {})
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return _UrllibResponse(response.status, response.headers, response.read())
    except error.HTTPError as exc:
        return _UrllibResponse(exc.code, exc.headers, exc.read())


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
        self._http_get = http_get or _default_http_get
        self._headers = DEFAULT_HEADERS.copy()

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
        response = self._http_get(
            self.search_url,
            params=params,
            headers=self._headers,
            timeout=self.timeout,
        )

        if getattr(response, "status_code", None) == 403:
            raise RuntimeError(
                "SearXNG 实例返回 403。请确认 settings.yml 的 search.formats 已启用 json，"
                "且前置网关/WAF 允许程序化访问。"
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
        parsed_results = [self._parse_result(item) for item in raw_results]
        parsed_results = [item for item in parsed_results if item.url][:max_results]

        return SearXNGResponse(
            query=payload.get("query") or fallback_query,
            results=parsed_results,
            answers=self._normalize_text_list(payload.get("answers")),
            suggestions=self._normalize_text_list(payload.get("suggestions")),
            response_time=response_time,
        )

    def _parse_result(self, item: Dict[str, Any]) -> SearXNGResult:
        content = self._first_text(item.get("content"), item.get("metadata"), item.get("engine"))
        raw_content = self._first_text(item.get("raw_content"), item.get("content"), item.get("metadata"))

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
            image_url=self._first_text(item.get("img_src"), item.get("content_url")),
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
