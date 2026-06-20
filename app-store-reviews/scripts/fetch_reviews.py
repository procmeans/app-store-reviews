#!/usr/bin/env python3
"""Fetch Apple App Store customer reviews via the official iTunes RSS feed.

The RSS feed is Apple's official, token-free endpoint. It returns JSON and is
stable, but caps out at 10 pages x 50 reviews ~= 500 most-recent (or most-helpful)
reviews PER country. To get broader coverage, pass several countries and the
results are merged + de-duplicated.

Usage examples:
  # By numeric app id, US only
  python fetch_reviews.py --app-id 389801252 --country us

  # Multiple countries merged, save both CSV and JSON
  python fetch_reviews.py --app-id 414478124 --country cn,us,hk,tw --format both --out reviews

  # Look the app id up by name first
  python fetch_reviews.py --app-name "WeChat" --country cn
"""
import argparse
import csv
import json
import os
import sys
import time
from urllib.parse import quote

import requests

RSS_URL = (
    "https://itunes.apple.com/{country}/rss/customerreviews/"
    "page={page}/id={app_id}/sortby={sort}/json"
)
LOOKUP_URL = "https://itunes.apple.com/lookup?id={app_id}&country={country}"
SEARCH_URL = (
    "https://itunes.apple.com/search?term={term}&country={country}"
    "&entity=software&limit=5"
)
HEADERS = {"User-Agent": "Mozilla/5.0 (app-store-reviews skill)"}
MAX_PAGES = 10  # Apple hard limit


def coverage_str(n, total):
    """Human-readable coverage of n scraped reviews vs total store ratings.

    Avoids a useless '0.00%' for huge apps by switching to a '1 in N' framing.
    The denominator is star-rating count (a superset of text reviews), so we
    always label it as ratings, not reviews.
    """
    if not total:
        return ""
    pct = 100 * n / total
    if pct >= 0.5:
        frac = f"约占 {pct:.2f}%"
    else:
        frac = f"约每 {round(total / n):,} 条评分中抓到 1 条文字评论"
    return f"总评分数 {total:,}（{frac}；分母为打星总量，非纯文字评论）"


def resolve_app_id_by_name(name, country):
    """Search the iTunes store and return (app_id, app_title) for the top hit."""
    url = SEARCH_URL.format(term=quote(name), country=country)
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        return None, None
    top = results[0]
    return str(top["trackId"]), top.get("trackName", "")


def lookup_app_title(app_id, country):
    return fetch_store_stats(app_id, country).get("title", "")


def fetch_store_stats(app_id, country):
    """Return per-country store stats from the iTunes lookup API.

    Note: `total_ratings` is the count of STAR ratings (all versions), which is
    a superset of text reviews — Apple does not publish a separate text-review
    total. Use it as the denominator when reporting how much of the store the
    ~500 RSS reviews represent, and label it as "ratings" not "reviews".
    """
    try:
        url = LOOKUP_URL.format(app_id=app_id, country=country)
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return {}
        app = results[0]
        return {
            "title": app.get("trackName", ""),
            "avg_rating": app.get("averageUserRating"),
            "total_ratings": app.get("userRatingCount"),
            "avg_rating_current": app.get("averageUserRatingForCurrentVersion"),
            "ratings_current": app.get("userRatingCountForCurrentVersion"),
            "current_version": app.get("version"),
        }
    except Exception:
        return {}


def parse_entry(entry, country):
    """Convert one RSS JSON entry into a flat review dict.

    The first entry on page 1 is app metadata (no im:rating) — callers skip those.
    """
    if "im:rating" not in entry:
        return None

    def label(node, *path):
        cur = node
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                return ""
            cur = cur[key]
        if isinstance(cur, dict):
            return cur.get("label", "")
        return cur

    return {
        "review_id": label(entry, "id", "label"),
        "country": country,
        "author": label(entry, "author", "name", "label"),
        "rating": label(entry, "im:rating", "label"),
        "title": label(entry, "title", "label"),
        "content": label(entry, "content", "label"),
        "app_version": label(entry, "im:version", "label"),
        "updated": label(entry, "updated", "label"),
        "vote_sum": label(entry, "im:voteSum", "label"),
        "vote_count": label(entry, "im:voteCount", "label"),
    }


def fetch_country(app_id, country, sort, max_pages, delay):
    reviews = []
    for page in range(1, max_pages + 1):
        url = RSS_URL.format(country=country, page=page, app_id=app_id, sort=sort)
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
        except requests.RequestException as e:
            print(f"  [{country}] page {page} request error: {e}", file=sys.stderr)
            break
        if r.status_code != 200:
            print(f"  [{country}] page {page} HTTP {r.status_code}, stopping", file=sys.stderr)
            break
        try:
            feed = r.json().get("feed", {})
        except ValueError:
            print(f"  [{country}] page {page} non-JSON response, stopping", file=sys.stderr)
            break
        entries = feed.get("entry", [])
        if not entries:
            break  # no more reviews
        page_reviews = [pr for e in entries if (pr := parse_entry(e, country))]
        if not page_reviews:
            break
        reviews.extend(page_reviews)
        if len(entries) < 50:
            break  # last (partial) page
        if delay:
            time.sleep(delay)
    return reviews


def main():
    ap = argparse.ArgumentParser(description="Fetch App Store reviews via official RSS")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--app-id", help="Numeric App Store app id, e.g. 389801252")
    g.add_argument("--app-name", help="App name to look up the id automatically")
    ap.add_argument("--country", default="us",
                    help="Comma-separated country codes (us,cn,jp,...). Default: us")
    ap.add_argument("--sort", default="mostrecent",
                    choices=["mostrecent", "mosthelpful"], help="Sort order")
    ap.add_argument("--pages", type=int, default=MAX_PAGES,
                    help=f"Max pages per country (1-{MAX_PAGES}). Default: {MAX_PAGES}")
    ap.add_argument("--format", default="json", choices=["json", "csv", "both"],
                    help="Output file format. Default: json")
    ap.add_argument("--out", default="app_store_reviews",
                    help="Output path prefix (no extension). Default: app_store_reviews")
    ap.add_argument("--delay", type=float, default=0.3,
                    help="Seconds to sleep between page requests. Default: 0.3")
    ap.add_argument("--merge", metavar="MASTER.json",
                    help="Accumulate mode: load this master JSON, merge newly "
                         "fetched reviews into it (de-dup by review_id), and "
                         "write the growing total back. This is how scheduled "
                         "runs build toward the full set over time, since RSS "
                         "only ever shows the most recent ~500.")
    args = ap.parse_args()

    countries = [c.strip().lower() for c in args.country.split(",") if c.strip()]
    pages = max(1, min(args.pages, MAX_PAGES))

    app_id = args.app_id
    app_title = ""
    if args.app_name:
        app_id, app_title = resolve_app_id_by_name(args.app_name, countries[0])
        if not app_id:
            print(f"Could not find an app named {args.app_name!r} in store {countries[0]}",
                  file=sys.stderr)
            sys.exit(1)
        print(f"Resolved {args.app_name!r} -> id {app_id} ({app_title})")
    else:
        app_title = lookup_app_title(app_id, countries[0])

    all_reviews = []
    store_stats = {}
    seen = set()

    # Accumulate mode: preload the existing master so we only add new reviews.
    existing_count = 0
    if args.merge and os.path.exists(args.merge):
        try:
            with open(args.merge, encoding="utf-8") as f:
                prev = json.load(f)
            prev_reviews = prev.get("reviews", prev) if isinstance(prev, dict) else prev
            for r in prev_reviews:
                rid = r.get("review_id")
                if rid and rid not in seen:
                    seen.add(rid)
                    all_reviews.append(r)
            existing_count = len(all_reviews)
            if not app_title:
                app_title = (prev.get("app_title", "") if isinstance(prev, dict) else "")
            print(f"Accumulate mode: loaded {existing_count} existing reviews from {args.merge}")
        except (ValueError, OSError) as e:
            print(f"Warning: could not read master {args.merge}: {e}", file=sys.stderr)

    for country in countries:
        stats = fetch_store_stats(app_id, country)
        store_stats[country] = stats
        if not app_title and stats.get("title"):
            app_title = stats["title"]
        got = fetch_country(app_id, country, args.sort, pages, args.delay)
        # de-dup by review_id across countries (rare overlap, but be safe)
        fresh = [r for r in got if r["review_id"] and r["review_id"] not in seen]
        for r in fresh:
            seen.add(r["review_id"])
        all_reviews.extend(fresh)
        cov = coverage_str(len(fresh), stats.get("total_ratings"))
        print(f"  [{country}] fetched {len(fresh)} reviews" + (f"  /  该区{cov}" if cov else ""))

    # newest first
    all_reviews.sort(key=lambda r: r["updated"], reverse=True)

    payload = {
        "app_id": app_id,
        "app_title": app_title,
        "countries": countries,
        "sort": args.sort,
        "count": len(all_reviews),
        "store_stats": store_stats,
        "reviews": all_reviews,
    }

    # In accumulate mode the master JSON is the canonical output; CSV sits next to it.
    if args.merge:
        json_path = args.merge
        prefix = args.merge[:-5] if args.merge.endswith(".json") else args.merge
        write_json = True
        write_csv = args.format in ("csv", "both")
    else:
        prefix = args.out
        json_path = f"{args.out}.json"
        write_json = args.format in ("json", "both")
        write_csv = args.format in ("csv", "both")

    written = []
    if write_json:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        written.append(json_path)
    if write_csv:
        path = f"{prefix}.csv"
        fields = ["review_id", "country", "author", "rating", "title", "content",
                  "app_version", "updated", "vote_sum", "vote_count"]
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(all_reviews)
        written.append(path)

    new_count = len(all_reviews) - existing_count
    grand_total = sum(s.get("total_ratings") or 0 for s in store_stats.values())
    cov = coverage_str(len(all_reviews), grand_total)
    if args.merge:
        print(f"\n累积模式：本次新增 {new_count} 条，总表现有 {len(all_reviews)} 条"
              + (f"（占该区{cov}）" if cov else "") + "。")
    else:
        print(f"\nTotal: {len(all_reviews)} 条文字评论，来自 {len(countries)} 个区"
              + (f"，对应这些区{cov}" if cov else "") + "。")
    print("说明：官方 RSS 每区上限约 500 条文字评论；总评分数是 Apple 公开的打星总量，"
          "通常远多于文字评论，Apple 不单独公开文字评论总数。")
    if written:
        print("Saved: " + ", ".join(written))

    # Emit machine-readable summary so a calling agent gets raw JSON on stdout too.
    print("\n===JSON_SUMMARY===")
    print(json.dumps({
        "app_id": app_id,
        "app_title": app_title,
        "countries": countries,
        "count": len(all_reviews),
        "new_added": new_count,
        "store_stats": store_stats,
        "files": written,
        "sample": all_reviews[:3],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
