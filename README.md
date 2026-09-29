# App Store Reviews Scraper

**English** | [中文](#中文)

A tiny tool to scrape Apple App Store customer reviews via Apple's **official** iTunes RSS feed — no API key, no token, returns clean JSON. The scripts handle pagination, multiple countries, and de-duplication, then export to CSV/JSON.

## Features

- **`fetch_reviews.py`** — Main tool. Pulls reviews from the official RSS feed. Supports multiple countries (`us,cn,hk,jp`...), pagination, and de-duplication; exports CSV/JSON.
- **`analyze_reviews.py`** — Analyzes scraped results: rating distribution, keywords, and positive/negative sample quotes. `--dims game-en` switches the complaint tally to English casual-game dimensions (ads, paid ad removal, physics fairness, progression, crashes...).
- **`fetch_gplay.py`** — Google Play reviews via the `google-play-scraper` library (no key, no 500 cap). Same output schema (plus `store`, `dev_reply`), so `analyze_reviews.py` and `--merge` work unchanged.
- **`fetch_serpapi.py`** — Optional SerpAPI fallback for deep single-country scraping beyond the RSS ~500-review limit (requires your own `SERPAPI_KEY`).
- **`accumulate.sh`** — Scheduled incremental scraping with launchd/cron; continuously merges new reviews into `data/<alias>_master.json`, append-only with no duplicates.

## Quick Start

```bash
# Install dependency
pip3 install requests

# Scrape WeChat reviews from the US + CN stores, export CSV + JSON
python3 app-store-reviews/scripts/fetch_reviews.py \
  --app-id 414478124 --country us,cn --format both --out reviews

# Or search by app name directly
python3 app-store-reviews/scripts/fetch_reviews.py \
  --app-name "Telegram" --country us --format both --out telegram

# Analyze the results
python3 app-store-reviews/scripts/analyze_reviews.py reviews.json --neg 4 --pos 2

# Google Play (pip3 install google-play-scraper), analyzed with the English game preset
python3 app-store-reviews/scripts/fetch_gplay.py --package <com.example.game> --country us --count 2000 --out game_gp
python3 app-store-reviews/scripts/analyze_reviews.py game_gp.json --dims game-en
```

### Optional: SerpAPI deep scraping

```bash
export SERPAPI_KEY=your_key   # do NOT hardcode it in files
python3 app-store-reviews/scripts/fetch_serpapi.py --app-id <ID> --country us
```

### Scheduled incremental scraping

Edit the `APPS` list in `accumulate.sh` (format: `alias app_id country_list`), then run it on a schedule with launchd (see `com.rainwe.appstore-reviews.plist`) or cron.

## Notes

- The RSS feed is Apple's official endpoint; it returns at most ~10 pages / ~500 most-recent reviews per country.
- This repo contains code only; scraped datasets (`data/`) and analysis reports (`output/`) are not published.

## License

MIT

---

## 中文

[English](#app-store-reviews-scraper) | **中文**

抓取 Apple App Store 用户评论的小工具，基于苹果**官方** iTunes RSS feed —— 无需 API key / token，返回干净的 JSON。脚本处理分页、多国家、去重，并输出 CSV/JSON。

### 功能

- **`fetch_reviews.py`** —— 主工具。从官方 RSS feed 抓取评论，支持多国家（`us,cn,hk,jp`...）、分页、去重，输出 CSV/JSON。
- **`analyze_reviews.py`** —— 对抓取结果做评分分布、关键词、正负面样本等分析。`--dims game-en` 切换为英文休闲游戏的吐槽维度（广告、付费去广告、物理公平、进度感、崩溃等）。
- **`fetch_gplay.py`** —— 用 `google-play-scraper` 抓 Google Play 评论（无需 key、没有 500 条上限），输出字段与 RSS 一致（另加 `store`、`dev_reply`），`analyze_reviews.py` 和 `--merge` 直接可用。
- **`fetch_serpapi.py`** —— 可选的 SerpAPI 兜底，用于超过 RSS ~500 条历史上限的单国家深抓（需自备 `SERPAPI_KEY`）。
- **`accumulate.sh`** —— 配合 launchd/cron 定时增量抓取，把新评论持续合并进 `data/<别名>_master.json`，只增不重。

### 快速开始

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

# Google Play（先 pip3 install google-play-scraper），用英文游戏维度分析
python3 app-store-reviews/scripts/fetch_gplay.py --package <com.example.game> --country us --count 2000 --out game_gp
python3 app-store-reviews/scripts/analyze_reviews.py game_gp.json --dims game-en
```

#### 可选：SerpAPI 深抓

```bash
export SERPAPI_KEY=你的key   # 不要硬编码进文件
python3 app-store-reviews/scripts/fetch_serpapi.py --app-id <ID> --country us
```

#### 定时增量抓取

编辑 `accumulate.sh` 里的 `APPS` 列表（格式：`别名 app_id 国家列表`），然后用 launchd（见 `com.rainwe.appstore-reviews.plist`）或 cron 定时运行。

### 说明

- RSS feed 是苹果官方接口，单国家最多约返回 10 页 / ~500 条最新评论。
- 本仓库只包含代码；抓取的数据集（`data/`）和分析报告（`output/`）未公开。

### License

MIT
