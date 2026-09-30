---
name: app-store-reviews
description: >-
  Scrape Apple App Store customer reviews via Apple's official iTunes RSS feed
  (token-free, returns JSON) and save them as CSV/JSON. Use this whenever the
  user wants to collect, download, pull, analyze, or monitor App Store reviews
  / ratings / user feedback for an iOS app — whether they give an app id, an
  App Store URL, or just the app's name, and whether they want one country or
  several (us, cn, jp, hk...). Trigger even if the user says "苹果商店评论",
  "app reviews", "iOS 用户评价", "抓取 App Store 评论" without naming RSS. For
  large single-country history beyond ~500 reviews, this skill also documents
  the optional app-store-scraper Python library fallback.
---

# App Store Reviews Scraper

Collect customer reviews for an iOS app from Apple's **official** iTunes RSS
feed. The feed needs no API key or token, returns clean JSON, and is the stable
way to do this. The bundled script handles pagination, multiple countries,
de-duplication, and CSV/JSON output.

## Primary tool: the RSS script

Run `scripts/fetch_reviews.py`. It already knows the official endpoint, the
10-page limit, and how to parse entries. Do not hand-roll requests unless the
script genuinely can't do what's asked.

```bash
python3 scripts/fetch_reviews.py --app-id <ID> --country us,cn --format both --out reviews
```

Key arguments:
- `--app-id <numeric>` **or** `--app-name "<name>"` (one is required). With
  `--app-name` the script looks the id up via the iTunes search API first.
- `--country` comma-separated codes, default `us`. Each country is a separate
  ~500-review pool, merged and de-duped.
- `--sort mostrecent|mosthelpful` (default `mostrecent`).
- `--pages 1-10` cap per country (default 10).
- `--format json|csv|both` (default `json`), `--out <prefix>` for filenames.

The script prints a human summary and a final `===JSON_SUMMARY===` line with
raw JSON (app id, file paths, and a 3-review sample) so you can read results
back programmatically.

## Getting the app id

If the user gives an **App Store URL** like
`https://apps.apple.com/us/app/wechat/id414478124`, the id is the number after
`id` (here `414478124`) — pass it to `--app-id` directly. If they give only a
name, use `--app-name` and the script resolves it.

## The hard limit and coverage (explain this to the user)

The official RSS feed returns at most **10 pages × 50 = ~500 reviews per
country**, and only `mostrecent` or `mosthelpful` ordering. This is Apple's
limit, not the script's. To widen coverage, pass more countries — that's the
intended, fully-official way to get more data.

To make this concrete, the script also fetches each country's official rating
stats (average rating + total rating count) from the iTunes lookup API and
prints **how much of the store the scraped reviews represent** — e.g. "抓到 500
条 / 总评分 4028 万，约每 402,980 条评分抓到 1 条文字评论". Always relay this to
the user so they understand the ~500 reviews are a recent slice, not the full
history. Important caveat to state: Apple publishes a total **rating** count
(stars), which is a superset of text reviews — there is no official "total text
review count", so coverage is reported against ratings and labeled as such.

## Deep / historical reviews via SerpApi (paid, works)

When the user needs history the RSS path can't reach (RSS caps at ~500 most
recent per country), and they have a **SerpApi key**, use
`scripts/fetch_serpapi.py`. SerpApi paginates Apple's full review history on its
backend — for one app this is often thousands of reviews back to launch
(verified: 奶酪单词 returned 210 pages ≈ 5,250 reviews back to 2021).

```bash
export SERPAPI_KEY=xxxx
python3 scripts/fetch_serpapi.py --app-id <ID> --country cn --max-pages 40 --merge data/<app>_master.json
python3 scripts/fetch_serpapi.py --app-id <ID> --country cn --all   # full history
```

It's **paid by the page**: 25 reviews/page, each page = 1 SerpApi search credit.
Always check the user's quota (`https://serpapi.com/account`) and tell them the
cost before a deep pull — a full history can be hundreds of credits. The key is
read from the `SERPAPI_KEY` env var (never hardcode it). Output matches the RSS
schema, so `analyze_reviews.py` and `--merge` work the same way.

## Optional fallback: app-store-scraper library (currently broken)

The `app-store-scraper` / token-scraping libraries also target deep history via
Apple's undocumented `amp-api.apps.apple.com` endpoint, but Apple removed the
bearer token from the app page HTML, so these are **broken as of 2026** (return
0 reviews). Prefer SerpApi above. Only revisit the library route if you confirm
the token mechanism has been restored.

```bash
pip install app-store-scraper
```

```python
from app_store_scraper import AppStore
app = AppStore(country="us", app_name="wechat", app_id=414478124)
app.review(how_many=2000)   # may take a while; can break/return fewer
reviews = app.reviews       # list of dicts: rating, title, review, date, userName...
```

After fetching with the library, save to CSV/JSON in the same shape the user
asked for (reuse the field names from the RSS output where possible:
`rating, title, content, author, app_version, updated`).

## Output shape

CSV/JSON columns from the RSS path:
`review_id, country, author, rating, title, content, app_version, updated, vote_sum, vote_count`,
sorted newest-first. JSON also wraps a top-level object with `app_id`,
`app_title`, `countries`, `sort`, `count`, and the `reviews` array.

## Analysis (when the user wants insight, not just data)

If the user asks "why are people unhappy", "common complaints", "版本回归",
"出个分析报告", etc., run the analyzer on the scraped JSON:

```bash
python3 scripts/analyze_reviews.py reviews.json --out report.md
```

For games, add `--profile game`: the complaint dimensions switch to multilingual
game keywords (ads, fake ads, difficulty/boosters, repetition, pricing, bugs,
readability, lost progress, plus a positive dimension) in en/ja/ko/zh/de/fr/es/pt/ru.

It prints (and optionally saves) a Markdown report with: overall average,
rating distribution bars, a **per-version average-rating table** to spot
regressions (a version with enough reviews but a notably lower average usually
means an update broke something), a **complaint-dimension tally** (keyword hit
counts across 价格/广告/扣费/闪退/同步/客服/内容/学习机制), and buckets of
representative negative, positive, and feature-request reviews.

Use the complaint-dimension tally as the **quantitative floor for frequencies** —
don't eyeball how common a pain point is, and address every dimension (even the
low ones). It exists because models reliably under-count or skip frequent
themes like "会员太贵" when left to pure语感.

The report ends with a "高频吐槽与亮点(由助手归纳)" placeholder. Fill that
section in yourself: read the sample buckets and the version table, then write
3-6 recurring complaint themes (each with a representative quote) and 2-3
positive highlights. This synthesis is deliberately left to you rather than to
keyword counting — judging what reviewers actually mean, especially in Chinese,
is something you do better than a frequency script.

## Competitor comparison

When the user wants competitive analysis — "竞品分析", "赛道对比", "我的 app vs
对手", or tracking a set of rival apps — don't just analyze one app. Read
`references/competitor-comparison.md` for the full workflow and report template:
resolve each rival's id, scrape each into its own master, produce per-app
insight (高频吐槽 / 高频表扬 / 新需求, by semantic grouping — not keyword
clustering), then synthesize a cross-competitor report. The real value is the
**cross-cutting patterns** (what the whole category gets wrong/right) and the
target app's **relative position + opportunity gaps**, not per-app complaint
lists. With several apps and ~500 reviews each, run the per-app insight passes
in parallel (one sub-agent per app).

## After scraping

Report back concisely: app title, total review count, per-country breakdown,
the saved file path(s), and the rating distribution. Don't dump the full review
list into chat — point at the file. Run the analyzer only when the user wants
insight beyond the raw data.
