# SearXNG 搜索适配设计

日期：2026-06-10

状态：已与用户确认设计，等待用户审阅规格文档后进入实现计划。

## 背景

当前 BettaFish 的网络搜索分散在两个外部检索路径：

- `QueryEngine` 默认直接依赖 `TavilyNewsAgency`，需要 `TAVILY_API_KEY`。
- `MediaEngine` 通过 `SEARCH_TOOL_TYPE` 在 `BochaAPI` 和 `AnspireAPI` 之间切换。

用户希望新增 SearXNG 支持，并把 SearXNG 设为默认搜索工具，同时保留旧工具作为可选后备。

## 调研结论

SearXNG 官方 Search API 支持 `GET /search` 和 `POST /search`，请求参数包括：

- `q`：搜索查询，必填。
- `format`：输出格式，可取 `json`、`csv`、`rss`。
- `categories`：逗号分隔的搜索分类。
- `engines`：逗号分隔的搜索引擎。
- `language`：搜索语言。
- `pageno`：页码。
- `time_range`：可取 `day`、`month`、`year`。
- `safesearch`：可取 `0`、`1`、`2`。

SearXNG 实例必须在 `settings.yml` 的 `search.formats` 中启用 `json`，否则请求 `format=json` 会返回 403。公共实例可能禁用 JSON 输出或有严格限流，因此默认推荐自托管实例。

参考资料：

- https://docs.searxng.org/dev/search_api.html
- https://docs.searxng.org/admin/settings/settings_search.html
- https://docs.searxng.org/dev/result_types/main/mainresult.html
- https://docs.searxng.org/dev/result_types/main/image.html

Context7 当前未在本 Codex 会话中暴露可用 MCP 工具或可安装插件；SearXNG 用法以官方文档和网络检索结果为准。

## 决策

采用“最小侵入适配层”方案：

1. 新增 SearXNG 搜索客户端。
2. 将 SearXNG 设为默认 `SEARCH_TOOL_TYPE`。
3. 保持 Agent 层现有工具名和返回字段契约不变。
4. 保留 Tavily、Bocha、Anspire 作为可选后备，避免一次性移除导致不可逆回归。

不在本轮做大型 `SearchProvider` 抽象重构。该重构长期更干净，但会扩大改动面，不是当前目标的必要条件。

## 配置设计

新增 `.env` 配置项：

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

配置更新范围：

- `config.py`
  - `SEARCH_TOOL_TYPE` 支持 `SearXNGAPI | AnspireAPI | BochaAPI`。
  - 默认值改为 `SearXNGAPI`。
  - 增加全部 `SEARXNG_*` 字段。
- `QueryEngine/utils/config.py`
  - 增加全部 `SEARXNG_*` 字段。
  - `TAVILY_API_KEY` 不再作为默认必填搜索前置条件。
- `MediaEngine/utils/config.py`
  - 增加全部 `SEARXNG_*` 字段。
  - `SEARCH_TOOL_TYPE` 支持 `SearXNGAPI`。
- `.env.example`
  - 新增 SearXNG 默认配置。
  - 将 Tavily、Bocha、Anspire 标注为旧工具或可选后备。
- `app.py`
  - `CONFIG_KEYS` 纳入全部 `SEARXNG_*` 字段。
  - `/api/config` 继续读写 `.env`。
- `templates/index.html`
  - 外部检索工具下拉新增 `SearXNGAPI`。
  - 选择 SearXNG 时显示 Base URL、语言、安全搜索、分类、引擎、超时和最大结果数。
  - 旧工具密钥字段按所选工具条件显示。

## QueryEngine 设计

新增 SearXNG 新闻搜索适配器，保持 QueryEngine 已有工具名：

- `basic_search_news(query, max_results=7)`
- `deep_search_news(query)`
- `search_news_last_24_hours(query)`
- `search_news_last_week(query)`
- `search_images_for_news(query)`
- `search_news_by_date(query, start_date, end_date)`

返回对象兼容现有 `TavilyResponse` 消费逻辑：

- `query`
- `answer`
- `results`
- `images`
- `response_time`

`results` 中每项保持：

- `title`
- `url`
- `content`
- `score`
- `raw_content`
- `published_date`

SearXNG JSON 映射规则：

- `title` 从 `title` 读取。
- `url` 从 `url` 读取。
- `content` 优先取 `content`，否则取 `metadata`、`engine` 等可用摘要字段组合。
- `score` 从 `score` 读取，缺失则为 `None`。
- `raw_content` 使用原始摘要字段。
- `published_date` 优先取 `publishedDate`，否则取 `pubdate`。
- 图片结果优先使用 `img_src`、`thumbnail`、`thumbnail_src`、`url`。

## MediaEngine 设计

新增 SearXNG 多模态搜索适配器，保持 MediaEngine 已有工具名：

- `comprehensive_search(query, max_results=10)`
- `web_search_only(query, max_results=15)`
- `search_for_structured_data(query)`
- `search_last_24_hours(query)`
- `search_last_week(query)`

返回对象兼容现有 `BochaResponse` / `AnspireResponse` 消费逻辑：

- `query`
- `conversation_id`
- `answer`
- `follow_ups`
- `webpages`
- `images`
- `modal_cards`

`webpages` 中每项保持：

- `name`
- `url`
- `snippet`
- `display_url`
- `date_last_crawled`

SearXNG 不提供 Bocha 的 AI 总结、追问和模态卡。适配器将这些字段保持为空，不影响现有 Agent 摘要流程，因为 Agent 当前主要消费 `webpages`。

## 搜索参数映射

通用请求路径：

```text
GET {SEARXNG_BASE_URL}/search
```

通用参数：

```text
q=<query>
format=json
language=<SEARXNG_LANGUAGE>
categories=<SEARXNG_CATEGORIES>
engines=<SEARXNG_ENGINES>
safesearch=<SEARXNG_SAFESEARCH>
pageno=1
```

工具映射：

- 通用搜索：使用默认分类和引擎。
- 深度搜索：增加最大结果数量，必要时使用同一 SearXNG 查询路径。
- 24 小时：`time_range=day`。
- 最近一周：SearXNG 无 `week`，使用 `time_range=month`，并在查询中补充“最近一周”语义。
- 图片搜索：`categories=images`。
- 指定日期搜索：SearXNG 无原生 `start_date/end_date` 参数，保留工具名并把日期信息写入查询词，例如 `主题 after:YYYY-MM-DD before:YYYY-MM-DD`。这是 best-effort 行为。

## 错误处理

SearXNG 适配器需要处理以下情况：

- `SEARXNG_BASE_URL` 为空：启动时抛出明确配置错误。
- Base URL 带尾部 `/`：自动规范化。
- HTTP 403：记录“实例未启用 JSON 输出，请在 SearXNG settings.yml search.formats 增加 json”。
- 超时或连接错误：交给现有 retry/fallback 机制，并记录网络错误。
- 非 JSON 响应：记录实例返回格式不符合预期。
- 空 `results`：返回空结果对象，不中断 Agent 流程。
- 单条结果缺字段：跳过不可用字段，保留可用字段，不让单条脏数据中断整次搜索。

## 测试计划

新增单元测试覆盖：

1. SearXNG JSON 到 QueryEngine 结果结构的映射。
2. SearXNG JSON 到 MediaEngine 结果结构的映射。
3. 参数构造：
   - 通用搜索
   - 图片搜索
   - 24 小时搜索
   - 最近一周搜索
   - 指定日期搜索
4. 错误路径：
   - 403
   - 超时
   - 非 JSON 响应
   - 空结果
   - 缺失字段

验证命令：

```bash
pytest
cd tests && python run_tests.py
```

如果完整 `pytest` 受外部依赖影响不可运行，至少运行新增搜索适配测试和现有 `tests/run_tests.py`，并在交付时说明未覆盖的环境依赖。

## 非目标

本轮不做以下事项：

- 不移除 Tavily、Bocha、Anspire 旧代码。
- 不重构所有搜索工具为统一抽象接口。
- 不自动部署 SearXNG 实例。
- 不修改 InsightEngine 的数据库搜索工具。
- 不依赖公共 SearXNG 实例作为默认值。

