#!/usr/bin/env python3
"""Discover a competitor set by fanning keyword searches across stores and countries.

Hand-picking 5 rivals misses clones that are big in one market, and new entrants.
This script runs every keyword in every country on the App Store (iTunes search
API, no key) and optionally Google Play (google-play-scraper), merges hits by
app, and ranks them by rating volume. Each candidate records which keywords and
countries surfaced it, so a broad-but-relevant set can be chosen with evidence.

A relevance filter keeps only apps whose title/description contains one of the
`--must` terms (case-insensitive), which drops the generic hits every search
returns (e.g. match-3 games for "merge").

Usage:
  python discover_competitors.py \
      --keywords "suika,watermelon game,fruit merge,drop merge,merge fruit,cat merge" \
      --country us,gb,ca,au,jp --must "merge,suika,watermelon,drop" \
      --gplay --top 40 --out data/competitors
Outputs <out>.json (all candidates with evidence) and <out>.md (ranked table).
"""
import argparse
import json
import sys
import time

import requests

ITUNES_SEARCH = "https://itunes.apple.com/search"


def itunes_search(term, country, limit):
    params = {"term": term, "country": country, "entity": "software", "limit": limit}
    for attempt in range(3):
        try:
            r = requests.get(ITUNES_SEARCH, params=params, timeout=20)
            if r.status_code == 200:
                return r.json().get("results", [])
            if r.status_code in (403, 429):  # Apple throttles bursts
                time.sleep(3 * (attempt + 1))
                continue
            return []
        except requests.RequestException:
            time.sleep(2 * (attempt + 1))
    return []


def gplay_search(term, country, lang, n):
    try:
        from google_play_scraper import search
    except ImportError:
        print("Google Play skipped: pip3 install google-play-scraper", file=sys.stderr)
        return None
    try:
        return search(term, lang=lang, country=country, n_hits=n)
    except Exception as e:
        print(f"  gplay search {term!r}/{country} failed: {e}", file=sys.stderr)
        return []


def relevant(text, must):
    t = (text or "").lower()
    return not must or any(m in t for m in must)


def main():
    ap = argparse.ArgumentParser(description="Discover competitor apps across stores/countries")
    ap.add_argument("--keywords", required=True, help="Comma-separated search terms")
    ap.add_argument("--country", default="us", help="Comma-separated country codes. Default: us")
    ap.add_argument("--must", default="", help="Comma-separated relevance terms; an app must "
                    "contain one in its title or description. Empty = keep all")
    ap.add_argument("--limit", type=int, default=50, help="App Store results per search (max 200)")
    ap.add_argument("--gplay", action="store_true", help="Also search Google Play")
    ap.add_argument("--gplay-country", default="us", help="Google Play countries. Default: us")
    ap.add_argument("--lang", default="en", help="Google Play language. Default: en")
    ap.add_argument("--min-ratings", type=int, default=50, help="Drop apps with fewer ratings")
    ap.add_argument("--top", type=int, default=40, help="Rows in the Markdown table per store")
    ap.add_argument("--out", default="competitors", help="Output prefix")
    args = ap.parse_args()

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    countries = [c.strip().lower() for c in args.country.split(",") if c.strip()]
    must = [m.strip().lower() for m in args.must.split(",") if m.strip()]

    ios = {}
    for country in countries:
        for kw in keywords:
            results = itunes_search(kw, country, args.limit)
            for rank, a in enumerate(results, 1):
                if not relevant(a.get("trackName", "") + " " + a.get("description", ""), must):
                    continue
                aid = str(a["trackId"])
                c = ios.setdefault(aid, {
                    "store": "ios", "app_id": aid, "title": a.get("trackName", ""),
                    "developer": a.get("artistName", ""), "genres": a.get("genres", []),
                    "price": a.get("price", 0), "released": (a.get("releaseDate") or "")[:10],
                    "updated": (a.get("currentVersionReleaseDate") or "")[:10],
                    "version": a.get("version", ""), "iap": None,
                    "url": (a.get("trackViewUrl") or "").split("?")[0],
                    "per_country": {}, "hits": [],
                })
                c["per_country"][country] = {
                    "avg_rating": round(a.get("averageUserRating") or 0, 2),
                    "ratings": a.get("userRatingCount") or 0,
                }
                c["hits"].append({"kw": kw, "country": country, "rank": rank})
            time.sleep(0.4)
        print(f"[ios/{country}] {len(ios)} relevant apps so far", file=sys.stderr)

    for c in ios.values():
        c["total_ratings"] = sum(p["ratings"] for p in c["per_country"].values())
        c["best_rank"] = min(h["rank"] for h in c["hits"])
        c["keyword_hits"] = len({h["kw"] for h in c["hits"]})
    ios_list = sorted((c for c in ios.values() if c["total_ratings"] >= args.min_ratings),
                      key=lambda c: -c["total_ratings"])

    gp_list = []
    if args.gplay:
        gp = {}
        for country in [c.strip() for c in args.gplay_country.split(",") if c.strip()]:
            for kw in keywords:
                results = gplay_search(kw, country, args.lang, 30)
                if results is None:
                    break
                for rank, a in enumerate(results, 1):
                    pkg = a.get("appId")
                    if not pkg or not relevant(a.get("title", "") + " " + (a.get("description") or ""), must):
                        continue
                    c = gp.setdefault(pkg, {"store": "gplay", "app_id": pkg,
                                            "title": a.get("title", ""),
                                            "developer": a.get("developer", ""),
                                            "avg_rating": round(a.get("score") or 0, 2),
                                            "installs": a.get("installs", ""), "hits": []})
                    c["hits"].append({"kw": kw, "country": country, "rank": rank})
            print(f"[gplay/{country}] {len(gp)} relevant apps so far", file=sys.stderr)
        # search results carry no rating count; fetch details for each candidate
        try:
            from google_play_scraper import app as gp_app
            for c in gp.values():
                try:
                    d = gp_app(c["app_id"], lang=args.lang, country="us")
                    c.update(total_ratings=d.get("ratings") or 0,
                             installs=d.get("installs", c["installs"]),
                             real_installs=d.get("realInstalls"),
                             released=d.get("released") or "",
                             genre=d.get("genre", ""), iap=d.get("offersIAP"),
                             ads=d.get("containsAds"), url=d.get("url", ""))
                except Exception:
                    c["total_ratings"] = 0
        except ImportError:
            pass
        for c in gp.values():
            c["best_rank"] = min(h["rank"] for h in c["hits"])
            c["keyword_hits"] = len({h["kw"] for h in c["hits"]})
        gp_list = sorted((c for c in gp.values() if c.get("total_ratings", 0) >= args.min_ratings),
                         key=lambda c: -c.get("total_ratings", 0))

    with open(f"{args.out}.json", "w", encoding="utf-8") as f:
        json.dump({"keywords": keywords, "countries": countries, "must": must,
                   "ios": ios_list, "gplay": gp_list}, f, ensure_ascii=False, indent=2)

    lines = [f"# Competitor discovery", "",
             f"- Keywords ({len(keywords)}): " + ", ".join(keywords),
             f"- App Store countries: {', '.join(countries)}; relevance terms: {', '.join(must) or '(none)'}",
             f"- Relevant apps: App Store {len(ios_list)}, Google Play {len(gp_list)} "
             f"(≥{args.min_ratings} ratings)", "",
             "## App Store (ranked by ratings summed over searched countries)", "",
             "| # | App | Developer | id | Ratings | " + " | ".join(countries) + " | Released | KW hits |",
             "|---|---|---|---|---|" + "---|" * len(countries) + "---|---|"]
    for i, c in enumerate(ios_list[:args.top], 1):
        cells = []
        for co in countries:
            p = c["per_country"].get(co)
            cells.append(f"{p['avg_rating']}★ {p['ratings']:,}" if p else "–")
        lines.append(f"| {i} | {c['title'][:40]} | {c['developer'][:24]} | {c['app_id']} | "
                     f"{c['total_ratings']:,} | " + " | ".join(cells) +
                     f" | {c['released']} | {c['keyword_hits']} |")
    if gp_list:
        lines += ["", "## Google Play (ranked by rating count)", "",
                  "| # | App | Developer | package | Ratings | Avg | Installs | Ads | IAP | KW hits |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for i, c in enumerate(gp_list[:args.top], 1):
            lines.append(f"| {i} | {c['title'][:40]} | {c['developer'][:24]} | {c['app_id']} | "
                         f"{c.get('total_ratings', 0):,} | {c['avg_rating']} | {c.get('installs', '')} | "
                         f"{'Y' if c.get('ads') else '–'} | {'Y' if c.get('iap') else '–'} | "
                         f"{c['keyword_hits']} |")
    with open(f"{args.out}.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
