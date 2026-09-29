#!/usr/bin/env python3
"""Fetch Google Play reviews and save them in the same shape as fetch_reviews.py.

Uses the `google-play-scraper` library (no API key). Unlike Apple's RSS feed,
Google Play has no hard 500 cap: `--count` pages back through the review
history. Output rows use the App Store field names, so analyze_reviews.py and
`--merge` accumulation work unchanged; the extra `store` field is "gplay".

Usage examples:
  pip3 install google-play-scraper
  python fetch_gplay.py --package com.example.game --country us --count 2000 --format both --out game_gp
  python fetch_gplay.py --app-name "watermelon merge" --country us       # resolve package by search
  python fetch_gplay.py --package com.example.game --merge data/game_gp_master.json
"""
import argparse
import csv
import json
import os
import sys

try:
    from google_play_scraper import Sort, app as gp_app, reviews as gp_reviews, search as gp_search
except ImportError:
    print("Missing dependency: pip3 install google-play-scraper", file=sys.stderr)
    sys.exit(1)

FIELDS = ["review_id", "country", "author", "rating", "title", "content",
          "app_version", "updated", "vote_sum", "vote_count", "store", "dev_reply"]
BATCH = 200  # library maximum per request


def resolve_package(name, lang, country):
    hits = gp_search(name, lang=lang, country=country, n_hits=5)
    hits = [h for h in hits if h.get("appId")]
    if not hits:
        return None, None
    return hits[0]["appId"], hits[0].get("title", "")


def store_stats(package, lang, country):
    try:
        d = gp_app(package, lang=lang, country=country)
    except Exception as e:  # network errors, delisted apps
        print(f"  [{country}] app details failed: {e}", file=sys.stderr)
        return {}
    return {
        "title": d.get("title", ""),
        "avg_rating": round(d["score"], 2) if d.get("score") else None,
        "total_ratings": d.get("ratings"),
        "installs": d.get("installs"),
        "version": d.get("version"),
        "updated": d.get("updated"),
    }


def to_row(r, country):
    at = r.get("at")
    return {
        "review_id": r.get("reviewId", ""),
        "country": country,
        "author": r.get("userName", ""),
        "rating": str(r.get("score", "")),
        "title": "",  # Google Play reviews have no title
        "content": r.get("content") or "",
        "app_version": r.get("reviewCreatedVersion") or r.get("appVersion") or "",
        "updated": at.isoformat() if hasattr(at, "isoformat") else str(at or ""),
        "vote_sum": str(r.get("thumbsUpCount", 0)),
        "vote_count": "",
        "store": "gplay",
        "dev_reply": r.get("replyContent") or "",
    }


def fetch_country(package, lang, country, sort, count):
    rows, token = [], None
    while len(rows) < count:
        try:
            batch, token = gp_reviews(package, lang=lang, country=country, sort=sort,
                                      count=min(BATCH, count - len(rows)),
                                      continuation_token=token)
        except Exception as e:
            print(f"  [{country}] request error after {len(rows)} reviews: {e}", file=sys.stderr)
            break
        if not batch:
            break
        rows.extend(to_row(r, country) for r in batch)
        if token is None or getattr(token, "token", None) is None:
            break
    return rows


def main():
    ap = argparse.ArgumentParser(description="Fetch Google Play reviews")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--package", help="Play package name, e.g. com.example.game")
    g.add_argument("--app-name", help="App name to resolve the package by search")
    ap.add_argument("--country", default="us", help="Comma-separated country codes. Default: us")
    ap.add_argument("--lang", default="en", help="Review language. Default: en")
    ap.add_argument("--sort", default="newest", choices=["newest", "relevant"])
    ap.add_argument("--count", type=int, default=1000, help="Max reviews per country. Default: 1000")
    ap.add_argument("--format", default="json", choices=["json", "csv", "both"])
    ap.add_argument("--out", default="gplay_reviews", help="Output path prefix (no extension)")
    ap.add_argument("--merge", metavar="MASTER.json",
                    help="Accumulate mode: merge into this master JSON, de-dup by review_id")
    args = ap.parse_args()

    countries = [c.strip().lower() for c in args.country.split(",") if c.strip()]
    sort = Sort.NEWEST if args.sort == "newest" else Sort.MOST_RELEVANT

    package, app_title = args.package, ""
    if args.app_name:
        package, app_title = resolve_package(args.app_name, args.lang, countries[0])
        if not package:
            print(f"Could not find an app named {args.app_name!r} on Google Play", file=sys.stderr)
            sys.exit(1)
        print(f"Resolved {args.app_name!r} -> {package} ({app_title})")

    all_rows, seen, existing_count = [], set(), 0
    if args.merge and os.path.exists(args.merge):
        try:
            with open(args.merge, encoding="utf-8") as f:
                prev = json.load(f)
            for r in (prev.get("reviews", []) if isinstance(prev, dict) else prev):
                rid = r.get("review_id")
                if rid and rid not in seen:
                    seen.add(rid)
                    all_rows.append(r)
            existing_count = len(all_rows)
            if not app_title and isinstance(prev, dict):
                app_title = prev.get("app_title", "")
            print(f"Accumulate mode: loaded {existing_count} existing reviews from {args.merge}")
        except (ValueError, OSError) as e:
            print(f"Warning: could not read master {args.merge}: {e}", file=sys.stderr)

    stats_by_country = {}
    for country in countries:
        stats = store_stats(package, args.lang, country)
        stats_by_country[country] = stats
        app_title = app_title or stats.get("title", "")
        got = fetch_country(package, args.lang, country, sort, max(1, args.count))
        fresh = [r for r in got if r["review_id"] and r["review_id"] not in seen]
        seen.update(r["review_id"] for r in fresh)
        all_rows.extend(fresh)
        extra = ""
        if stats.get("total_ratings"):
            extra = (f"  /  均分 {stats.get('avg_rating')}，总评分 {stats['total_ratings']:,}"
                     f"，安装 {stats.get('installs', '?')}")
        print(f"  [{country}] fetched {len(fresh)} new reviews{extra}")

    all_rows.sort(key=lambda r: r["updated"], reverse=True)
    payload = {
        "app_id": package,
        "app_title": app_title,
        "store": "gplay",
        "countries": countries,
        "sort": args.sort,
        "count": len(all_rows),
        "store_stats": stats_by_country,
        "reviews": all_rows,
    }

    if args.merge:
        json_path = args.merge
        prefix = args.merge[:-5] if args.merge.endswith(".json") else args.merge
        write_json, write_csv = True, args.format in ("csv", "both")
    else:
        prefix, json_path = args.out, f"{args.out}.json"
        write_json, write_csv = args.format in ("json", "both"), args.format in ("csv", "both")

    written = []
    if write_json:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        written.append(json_path)
    if write_csv:
        path = f"{prefix}.csv"
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(all_rows)
        written.append(path)

    print(f"\nTotal: {len(all_rows)} reviews (new this run: {len(all_rows) - existing_count}).")
    if written:
        print("Saved: " + ", ".join(written))
    print("\n===JSON_SUMMARY===")
    print(json.dumps({
        "app_id": package, "app_title": app_title, "store": "gplay", "countries": countries,
        "count": len(all_rows), "new_added": len(all_rows) - existing_count,
        "store_stats": stats_by_country, "files": written, "sample": all_rows[:3],
    }, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
