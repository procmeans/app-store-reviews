#!/usr/bin/env python3
"""Fallback: read the reviews Apple embeds in the public App Store web page.

When the iTunes RSS feed returns empty `feed` objects (seen from some networks
in 2026: HTTP 200, no `entry` list, even for the biggest apps), the public app
page at apps.apple.com still server-renders its "Ratings & Reviews" shelf as
JSON inside <script id="serialized-server-data">. Each storefront shows ~10
reviews, which are Apple's featured (most helpful) picks, not the newest — so
this is shallow per country; widen it with many storefronts. Output rows use the
fetch_reviews.py schema (`store: "ios-web"`, no app_version), so --merge and analyze_reviews.py
work unchanged.

The default, iPhone and Mac views of the page each feature a different set, so
all three are read per storefront (up to ~25 distinct reviews per country).

Usage:
  python fetch_appstore_web.py --app-id 6471572249 --country us,gb,ca,au,nz,ie --merge data/app_ios.json
"""
import argparse
import html
import json
import os
import re
import sys
import time

import requests

PAGE = "https://apps.apple.com/{country}/app/id{app_id}?see-all=reviews{view}"
LOOKUP = "https://itunes.apple.com/lookup"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")
ENGLISH = "us,gb,ca,au,nz,ie,in,sg,ph,za,my,ae"
# The default, iPhone and Mac views of the same page feature different reviews.
VIEWS = ",iphone,mac"


def page_reviews(app_id, country, view=""):
    for attempt in range(4):
        try:
            r = requests.get(PAGE.format(country=country, app_id=app_id,
                                         view=f"&platform={view}" if view else ""),
                             headers={"User-Agent": UA}, timeout=25)
        except requests.RequestException as e:
            print(f"  [{country}] request error: {e}", file=sys.stderr)
            return [], ""
        if r.status_code != 429:
            break
        time.sleep(5 * 2 ** attempt)  # Apple rate-limits bursts of page loads
    if r.status_code != 200:
        print(f"  [{country}] HTTP {r.status_code}", file=sys.stderr)
        return [], ""
    r.encoding = "utf-8"  # the page omits a charset header; requests would guess latin-1
    m = re.search(r'<script[^>]*id="serialized-server-data"[^>]*>(.*?)</script>', r.text, re.S)
    if not m:
        return [], ""
    data = json.loads(m.group(1))
    found, title = {}, ""

    def walk(o):
        nonlocal title
        if isinstance(o, dict):
            if o.get("$kind") == "Review" and o.get("contents") and o.get("id"):
                found.setdefault(o["id"], o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(data)
    t = re.search(r"<title>(.*?)</title>", r.text, re.S)
    if t:
        title = html.unescape(t.group(1))
        title = re.sub(r"\s+(- Ratings (&|and) Reviews|on the App Store).*$", "", title).strip("\u200e\u200f ")
    rows = [{
        "review_id": rv["id"], "country": country, "author": rv.get("reviewerName", ""),
        "rating": str(rv.get("rating", "")), "title": rv.get("title", ""),
        "content": rv.get("contents", ""), "app_version": "",
        "updated": rv.get("date", ""), "vote_sum": "", "vote_count": "",
        "store": "ios-web",
    } for rv in found.values()]
    return rows, title


def main():
    ap = argparse.ArgumentParser(description="App Store reviews from the public web page")
    ap.add_argument("--app-id", required=True)
    ap.add_argument("--country", default=ENGLISH,
                    help=f"Comma-separated storefronts. Default: English-speaking ({ENGLISH})")
    ap.add_argument("--out", default="appstore_web", help="Output prefix when not merging")
    ap.add_argument("--merge", metavar="MASTER.json", help="Merge into this master JSON")
    ap.add_argument("--views", default=VIEWS,
                    help="Comma-separated page views ('' = default, iphone, mac, ipad); "
                         f"each features different reviews. Default: {VIEWS!r}")
    ap.add_argument("--delay", type=float, default=0.5)
    args = ap.parse_args()

    path = args.merge or f"{args.out}.json"
    payload = {"app_id": args.app_id, "app_title": "", "store": "ios", "countries": [],
               "sort": "web-featured", "reviews": []}
    if args.merge and os.path.exists(args.merge):
        with open(args.merge, encoding="utf-8") as f:
            payload.update(json.load(f))
    seen = {r["review_id"] for r in payload["reviews"]}
    before = len(seen)
    stats = payload.setdefault("store_stats", {})
    views = [v.strip() for v in args.views.split(",")]
    for country in [c.strip().lower() for c in args.country.split(",") if c.strip()]:
        rows, title = [], ""
        for view in views:
            got, t = page_reviews(args.app_id, country, view)
            rows += got
            title = title or t
            time.sleep(args.delay)
        payload["app_title"] = payload.get("app_title") or title
        try:  # official average + rating count, for coverage and the "official vs sample" gap
            res = requests.get(LOOKUP, params={"id": args.app_id, "country": country},
                               timeout=20).json().get("results", [])
            if res:
                stats[country] = {"avg_rating": round(res[0].get("averageUserRating") or 0, 2),
                                  "total_ratings": res[0].get("userRatingCount") or 0}
        except (requests.RequestException, ValueError):
            pass
        fresh = [r for r in {r["review_id"]: r for r in rows}.values() if r["review_id"] not in seen]
        seen.update(r["review_id"] for r in fresh)
        payload["reviews"].extend(fresh)
        if country not in payload["countries"]:
            payload["countries"].append(country)
        print(f"  [{country}] {len(fresh)} new")
    payload["reviews"].sort(key=lambda r: r.get("updated") or "", reverse=True)
    payload["count"] = len(payload["reviews"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Total {payload['count']} (new {payload['count'] - before}) -> {path}")


if __name__ == "__main__":
    main()
