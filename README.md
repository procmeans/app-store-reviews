# App Store Reviews Scraper

抓取 Apple App Store 用户评论的小工具，基于苹果**官方** iTunes RSS feed —— 无需 API key / token，返回干净的 JSON。脚本处理分页、多国家、去重，并输出 CSV/JSON。

> Collect customer reviews for an iOS app from Apple's official iTunes RSS feed. No API key required.

## 功能

- **`fetch_reviews.py`** —— 主工具。从官方 RSS feed 抓取评论，支持多国家（`us,cn,hk,jp`...）、分页、去重，输出 CSV/JSON。
- **`analyze_reviews.py`** —— 对抓取结果做评分分布、关键词、正负面样本等分析。
- **`fetch_serpapi.py`** —— 可选的 SerpAPI 兜底，用于超过 RSS ~500 条历史上限的单国家深抓（需自备 `SERPAPI_KEY`）。
- **`accumulate.sh`** —— 配合 launchd/cron 定时增量抓取，把新评论持续合并进 `data/<别名>_master.json`，只增不重。

## 快速开始

```bash
# 安装依赖
pip3 install requests

# 抓取微信美区 + 国区评论，导出 CSV+JSON
python3 app-store-reviews/scripts/fetch_reviews.py \
  --app-id 414478124 --country us,cn --format both --out reviews

# 也可以直接用应用名搜索
python3 app-store-reviews/scripts/fetch_reviews.py \
  --app-name "Telegram" --country us --format both --out telegram

# 分析抓取结果
python3 app-store-reviews/scripts/analyze_reviews.py reviews.json --neg 4 --pos 2
```

### 可选：SerpAPI 深抓

```bash
export SERPAPI_KEY=你的key   # 不要硬编码进文件
python3 app-store-reviews/scripts/fetch_serpapi.py --app-id <ID> --country us
```

### 定时增量抓取

编辑 `accumulate.sh` 里的 `APPS` 列表（格式：`别名 app_id 国家列表`），然后用 launchd（见 `com.rainwe.appstore-reviews.plist`）或 cron 定时运行。

## 说明

- RSS feed 是苹果官方接口，单国家最多约返回 10 页 / ~500 条最新评论。
- 本仓库只包含代码；抓取的数据集（`data/`）和分析报告（`output/`）未公开。

## License

MIT
