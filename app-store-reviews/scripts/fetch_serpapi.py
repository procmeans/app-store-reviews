#!/usr/bin/env python3
"""Deep / historical App Store reviews via SerpApi (paid backend).

Unlike the official RSS (capped at ~500 most-recent per country), SerpApi
paginates through Apple's full review history — for one app this can be
thousands of reviews going back to launch. It's a PAID service: each page
fetched = one SerpApi search credit, so depth costs money/quota. Use this only
when the user explicitly needs history the RSS path can't reach.

Auth: reads the key from the SERPAPI_KEY environment variable (do NOT hardcode
keys in files). Get/rotate it at https://serpapi.com/manage-api-key.

Output matches fetch_reviews.py's schema (review_id/country/author/rating/title/
content/app_version/updated/...), so analyze_reviews.py works on the result, and
--merge accumulates into the same master JSON the RSS path uses.

Usage:
  export SERPAPI_KEY=xxxx
  python fetch_serpapi.py --app-id 1600837891 --country cn --max-pages 40 --merge data/naolao_master.json
  python fetch_serpapi.py --app-id 1600837891 --country cn --all   # full history (costs total_page_count credits)
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ENDPOINT = "https://serpapi.com/search.json"


def iso_date(s):
    """'2026年06月07日' -> '2026-06-07' (best effort; pass through otherwise)."""
    m = re.match(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", s or "")
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return s or ""


def parse_version(s):
    m = re.search(r"(\d+(?:\.\d+)+)", s or "")
    return m.group(1) if m else ""


def map_review(r, country):
    author = r.get("author") or {}
    return {
        "review_id": str(r.get("id", "")),
        "country": country,
        "author": author.get("name", ""),
        "rating": str(r.get("rating", "")),
        "title": r.get("title", ""),
        "content": r.get("text", ""),
        "app_version": parse_version(r.get("reviewed_version", "")),
        "updated": iso_date(r.get("review_date", "")),
        "vote_sum": "",
        "vote_count": "",
    }


def fetch_page(app_id, country, sort, page, key, retries=4):
    """Fetch one page, retrying transient network errors (SerpApi's TLS handshake
    times out intermittently). A failed page costs no credit, so retrying is free."""
    params = {
        "engine": "apple_reviews",
        "product_id": str(app_id),
        "country": country,
        "sort": sort,
        "page": page,
        "api_key": key,
    }
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return json.load(resp)
        except Exception as e:
            last = e
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))  # backoff: 2s,4s,6s
    raise last


def main():
    ap = argparse.ArgumentParser(description="Deep App Store reviews via SerpApi")
    ap.add_argument("--app-id", required=True, help="Numeric App Store app id")
    ap.add_argument("--country", default="cn", help="Single country code. Default: cn")
    ap.add_argument("--sort", default="mostrecent",
                    choices=["mostrecent", "mosthelpful"], help="Sort order")
    ap.add_argument("--max-pages", type=int, default=40,
                    help="Max pages to fetch (25 reviews/page). Each page = 1 "
                         "SerpApi credit. Default: 40 (~1000 reviews)")
    ap.add_argument("--all", action="store_true",
                    help="Fetch the full history (overrides --max-pages, uses "
                         "total_page_count credits — can be hundreds)")
    ap.add_argument("--merge", metavar="MASTER.json",
                    help="Accumulate into this master JSON (de-dup by review_id)")
    ap.add_argument("--out", default="serpapi_reviews",
                    help="Output prefix when not using --merge")
    ap.add_argument("--format", default="both", choices=["json", "csv", "both"])
    ap.add_argument("--delay", type=float, default=0.5,
                    help="Seconds between page requests. Default: 0.5")
    ap.add_argument("--start-page", type=int, default=2,
                    help="Resume from this page (skip already-fetched earlier "
                         "pages to save credits after an interruption). Default: 2")
    args = ap.parse_args()

    key = os.environ.get("SERPAPI_KEY")
    if not key:
        print("ERROR: set the SERPAPI_KEY environment variable first "
              "(export SERPAPI_KEY=xxxx).", file=sys.stderr)
        sys.exit(2)

    country = args.country.lower()
    all_reviews = []
    seen = set()

    existing_count = 0
    app_title = ""
    prev_store_stats = {}
    if args.merge and os.path.exists(args.merge):
        try:
            prev = json.load(open(args.merge, encoding="utf-8"))
            app_title = prev.get("app_title", "")
            prev_store_stats = prev.get("store_stats", {}) or {}
            for r in prev.get("reviews", []):
                rid = r.get("review_id")
                if rid and rid not in seen:
                    seen.add(rid)
                    all_reviews.append(r)
            existing_count = len(all_reviews)
            print(f"Accumulate: loaded {existing_count} existing reviews from {args.merge}")
        except (ValueError, OSError) as e:
            print(f"Warning: could not read master: {e}", file=sys.stderr)

    # First page tells us the real total page count.
    try:
        first = fetch_page(args.app_id, country, args.sort, 1, key)
    except Exception as e:
        print(f"ERROR: first request failed: {e}", file=sys.stderr)
        sys.exit(1)
    if first.get("error"):
        print(f"ERROR from SerpApi: {first['error']}", file=sys.stderr)
        sys.exit(1)

    # App title isn't in the SerpApi payload — grab it from the free iTunes
    # lookup so reports have a real name (skip silently on failure).
    if not app_title:
        try:
            lu = ("https://itunes.apple.com/lookup?"
                  + urllib.parse.urlencode({"id": args.app_id, "country": country}))
            res = json.load(urllib.request.urlopen(lu, timeout=20)).get("results", [])
            if res:
                app_title = res[0].get("trackName", "")
        except Exception:
            pass

    info = first.get("search_information", {})
    total_pages = info.get("total_page_count") or 1
    target_pages = total_pages if args.all else min(args.max_pages, total_pages)
    print(f"SerpApi 报告共 {total_pages} 页(约 {total_pages*25} 条历史)。"
          f"本次抓 {target_pages} 页 = 约 {target_pages} 次 API 额度。")

    def ingest(payload):
        added = 0
        for raw in payload.get("reviews", []):
            rv = map_review(raw, country)
            rid = rv["review_id"]
            if rid and rid not in seen:
                seen.add(rid)
                all_reviews.append(rv)
                added += 1
        return added

    new_added = ingest(first)
    pages_done = 1
    start = max(2, args.start_page)
    if start > 2:
        print(f"  从第 {start} 页续传(跳过已抓的 2-{start-1} 页)")
    for page in range(start, target_pages + 1):
        if args.delay:
            time.sleep(args.delay)
        try:
            payload = fetch_page(args.app_id, country, args.sort, page, key)
        except Exception as e:
            print(f"  page {page} 失败,停止(可用 --start-page {page} 续传): {e}", file=sys.stderr)
            break
        if payload.get("error"):
            print(f"  page {page} SerpApi error,停止: {payload['error']}", file=sys.stderr)
            break
        got = ingest(payload)
        pages_done += 1
        new_added += got
        if page % 10 == 0 or page == target_pages:
            print(f"  ...{page}/{target_pages} 页,累计新增 {new_added}")
        if not payload.get("reviews"):
            print(f"  page {page} 无评论,提前到底")
            break

    all_reviews.sort(key=lambda r: r["updated"], reverse=True)
    payload = {
        "app_id": str(args.app_id),
        "app_title": app_title,
        "countries": [country],
        "sort": args.sort,
        "source": "serpapi(apple_reviews,付费深度历史)",
        "count": len(all_reviews),
        "store_stats": prev_store_stats,
        "reviews": all_reviews,
    }

    if args.merge:
        json_path = args.merge
        prefix = args.merge[:-5] if args.merge.endswith(".json") else args.merge
    else:
        json_path = f"{args.out}.json"
        prefix = args.out

    written = []
    if args.format in ("json", "both"):
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        written.append(json_path)
    if args.format in ("csv", "both"):
        path = f"{prefix}.csv"
        fields = ["review_id", "country", "author", "rating", "title", "content",
                  "app_version", "updated", "vote_sum", "vote_count"]
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(all_reviews)
        written.append(path)

    dates = [r["updated"] for r in all_reviews if r["updated"]]
    print(f"\n抓取 {pages_done} 页,本次新增 {new_added} 条,总表 {len(all_reviews)} 条"
          + (f"(日期 {min(dates)} ~ {max(dates)})" if dates else "") + "。")
    print(f"已用约 {pages_done} 次 SerpApi 额度。Saved: " + ", ".join(written))


if __name__ == "__main__":
    main()
