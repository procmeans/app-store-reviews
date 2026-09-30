#!/usr/bin/env python3
"""Fetch reviews for one game from BOTH stores in many languages, one JSON.

iOS: Apple's official RSS (up to ~500 newest per country), for every country
     where the app has ratings (auto-picked from iTunes lookup unless --ios-countries).
Google Play: google-play-scraper, per language (--gp-langs), newest first.

Output rows use the same schema as app-store-reviews/scripts/fetch_reviews.py
(plus `store` and `lang`), so analyze_reviews.py works on it directly:
  python3 ../../app-store-reviews/scripts/analyze_reviews.py out.json --profile game

Usage:
  python3 multilang_reviews.py --ios-id 6793924927 --gp-id com.nebula.rotaterings --out data/rotate_rings
  python3 multilang_reviews.py --ios-id 6452395870 --per-lang 300 --out data/pixon
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

UA = {"User-Agent": "Mozilla/5.0 (game-competitor-research skill)"}
RSS = ("https://itunes.apple.com/{c}/rss/customerreviews/page={p}/id={id}/"
       "sortby=mostrecent/json")
LOOKUP = "https://itunes.apple.com/lookup?id={id}&country={c}"
CANDIDATE_COUNTRIES = ("us,gb,ca,au,jp,kr,tw,hk,cn,de,fr,it,es,nl,se,br,mx,ru,tr,"
                       "sa,th,vn,id,ph,in,pl").split(",")
COUNTRY_LANG = {"jp": "ja", "kr": "ko", "tw": "zh", "hk": "zh", "cn": "zh", "de": "de",
                "fr": "fr", "it": "it", "es": "es", "nl": "nl", "se": "sv", "br": "pt",
                "mx": "es", "ru": "ru", "tr": "tr", "sa": "ar", "th": "th", "vn": "vi",
                "id": "id", "pl": "pl"}
DEFAULT_GP_LANGS = "en:us,tr:tr,vi:vn,ja:jp,ko:kr,fr:fr,de:de,es:mx,zh-TW:tw,pt:br,ru:ru,it:it"


def get_json(url):
    for i in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=20)
            if r.status_code == 200:
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(1 + i)
    return None


def ios_country_ratings(app_id, countries):
    def one(c):
        d = get_json(LOOKUP.format(id=app_id, c=c)) or {}
        res = d.get("results") or [{}]
        return c, res[0].get("userRatingCount", 0), res[0].get("trackName"), res[0].get("averageUserRating")
    with ThreadPoolExecutor(6) as ex:
        return list(ex.map(one, countries))


def ios_reviews(app_id, country, max_pages):
    out = []
    for p in range(1, max_pages + 1):
        d = get_json(RSS.format(c=country, p=p, id=app_id))
        entries = (d or {}).get("feed", {}).get("entry")
        if not entries:
            break
        if isinstance(entries, dict):
            entries = [entries]
        for e in entries:
            if "im:rating" not in e:
                continue
            out.append({
                "store": "ios", "country": country, "lang": COUNTRY_LANG.get(country, "en"),
                "review_id": "ios-" + e.get("id", {}).get("label", ""),
                "author": e.get("author", {}).get("name", {}).get("label", ""),
                "rating": int(e["im:rating"]["label"]),
                "title": e.get("title", {}).get("label", ""),
                "content": e.get("content", {}).get("label", ""),
                "app_version": e.get("im:version", {}).get("label", ""),
                "updated": e.get("updated", {}).get("label", ""),
                "vote_sum": e.get("im:voteSum", {}).get("label", "0"),
                "vote_count": e.get("im:voteCount", {}).get("label", "0"),
            })
        time.sleep(0.2)
    return out


def gp_reviews(pkg, lang, country, n):
    try:
        from google_play_scraper import reviews, Sort
    except ImportError:
        print("pip install google-play-scraper to include Google Play", file=sys.stderr)
        return []
    try:
        rows, _ = reviews(pkg, lang=lang, country=country, count=n, sort=Sort.NEWEST)
    except Exception as e:
        print(f"  GP {lang}:{country} failed: {e}", file=sys.stderr)
        return []
    return [{
        "store": "gp", "country": country, "lang": lang.split("-")[0],
        "review_id": "gp-" + r["reviewId"], "author": r.get("userName", ""),
        "rating": r.get("score", 0), "title": "", "content": r.get("content") or "",
        "app_version": r.get("reviewCreatedVersion") or "",
        "updated": r["at"].isoformat() if r.get("at") else "",
        "vote_sum": str(r.get("thumbsUpCount", 0)), "vote_count": "",
        "dev_reply": (r.get("replyContent") or "")[:300],
    } for r in rows]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ios-id", help="App Store numeric id")
    ap.add_argument("--gp-id", help="Google Play package name")
    ap.add_argument("--ios-countries", help="Comma list; default = every candidate country with >= --min-ratings")
    ap.add_argument("--min-ratings", type=int, default=50)
    ap.add_argument("--ios-pages", type=int, default=10, help="RSS pages per country (50 each, max 10)")
    ap.add_argument("--gp-langs", default=DEFAULT_GP_LANGS)
    ap.add_argument("--per-lang", type=int, default=200, help="GP reviews per language")
    ap.add_argument("--out", required=True, help="Output prefix (writes <out>.json)")
    args = ap.parse_args()
    if not args.ios_id and not args.gp_id:
        ap.error("need --ios-id and/or --gp-id")

    all_rows, stats, title = [], {}, None
    if args.ios_id:
        if args.ios_countries:
            countries = args.ios_countries.split(",")
        else:
            rc = ios_country_ratings(args.ios_id, CANDIDATE_COUNTRIES)
            for c, n, t, avg in rc:
                title = title or t
                if n:
                    stats[f"ios:{c}"] = {"total_ratings": n, "avg_rating": round(avg or 0, 2)}
            countries = [c for c, n, _, _ in sorted(rc, key=lambda x: -x[1]) if n >= args.min_ratings]
        print(f"iOS countries: {countries}", file=sys.stderr)
        with ThreadPoolExecutor(4) as ex:
            for c, rows in zip(countries, ex.map(lambda c: ios_reviews(args.ios_id, c, args.ios_pages), countries)):
                print(f"  ios/{c}: {len(rows)}", file=sys.stderr)
                all_rows += rows
    if args.gp_id:
        locs = [l.split(":") for l in args.gp_langs.split(",")]
        with ThreadPoolExecutor(4) as ex:
            for (lang, c), rows in zip(locs, ex.map(lambda lc: gp_reviews(args.gp_id, lc[0], lc[1], args.per_lang), locs)):
                print(f"  gp/{lang}: {len(rows)}", file=sys.stderr)
                all_rows += rows

    seen, uniq = set(), []
    for r in all_rows:
        if r["review_id"] not in seen:
            seen.add(r["review_id"])
            uniq.append(r)
    uniq.sort(key=lambda r: r["updated"], reverse=True)

    by = {}
    for r in uniq:
        k = f"{r['store']}:{r['lang']}"
        by.setdefault(k, [0, 0])
        by[k][0] += 1
        by[k][1] += r["rating"]
    payload = {"app_id": args.ios_id or args.gp_id, "gp_id": args.gp_id,
               "app_title": title or args.gp_id, "count": len(uniq),
               "store_stats": stats, "by_store_lang": {k: {"n": n, "avg": round(s / n, 2)} for k, (n, s) in by.items()},
               "reviews": uniq}
    with open(args.out + ".json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    print(f"{len(uniq)} reviews -> {args.out}.json")
    for k, v in sorted(payload["by_store_lang"].items(), key=lambda x: -x[1]["n"]):
        print(f"  {k:10s} n={v['n']:4d} avg={v['avg']}")


if __name__ == "__main__":
    main()
