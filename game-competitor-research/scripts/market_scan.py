#!/usr/bin/env python3
"""One-shot market scan for a mobile game mechanic / category.

Pulls, with no API key:
  1. Apple top-free / top-grossing charts (per country, per genre) and marks
     every app whose name matches your keywords.
  2. iTunes search for each keyword x country (keywords may be in any language).
  3. Google Play search for each keyword x (lang, country)  [needs google-play-scraper].
  4. Big-publisher sweep: every iOS app by Rollic, Voodoo, Lion Studios, ...
     whose name/description matches the keywords — including small/dead ones,
     which are the "failed attempts".
  5. Per-country iOS rating counts for every candidate (batched lookup), so
     you see total size, top markets and growth velocity (ratings per day).

Outputs <out>.json (everything) and <out>.md (ranked tables to read first).

Usage:
  python3 market_scan.py --keywords "rotate rings,untie rings,リング 回転,링 회전,旋转圆环" \
      --out data/rings_scan
  python3 market_scan.py --keywords "screw jam,nuts bolts" --chart-countries us,jp,de --no-gp
"""
import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote

import requests

UA = {"User-Agent": "Mozilla/5.0 (game-competitor-research skill)"}
CHART_URL = "https://itunes.apple.com/{c}/rss/{feed}/limit=200/genre={g}/json"
SEARCH_URL = "https://itunes.apple.com/search?term={t}&country={c}&entity=software&limit={n}"
DEV_SEARCH_URL = ("https://itunes.apple.com/search?term={t}&country=us&entity=software"
                  "&attribute=softwareDeveloper&limit=200")
LOOKUP_URL = "https://itunes.apple.com/lookup?id={ids}&country={c}"

# Default rating-count countries: big English markets + JP/KR/CN-TW/EU/LatAm.
DEFAULT_RATING_COUNTRIES = "us,gb,ca,au,jp,kr,tw,hk,de,fr,it,es,br,mx,ru,tr,vn,in"
# Keyword search countries (each has its own store index & language).
DEFAULT_SEARCH_COUNTRIES = "us,tr,vn,jp,kr,fr,de,mx,tw,cn,br"
# Google Play (lang, country) pairs for search.
# EU storefronts (fr:fr, de:de, es:es) break google-play-scraper search, so
# French/German use Canada/Switzerland.
DEFAULT_GP_LOCALES = "en:us,tr:tr,vi:vn,ja:jp,ko:kr,fr:ca,de:ch,es:mx,zh-TW:tw,pt:br"

# Hyper/hybrid-casual publishers worth sweeping. Search terms match Apple's
# developer (artist) name; `match` must appear in the returned artistName.
BIG_PUBLISHERS = [
    ("Rollic", "rollic"), ("Voodoo", "voodoo"), ("Lion Studios", "lion studios"),
    ("Supersonic", "supersonic"), ("CrazyLabs", "crazy labs"), ("SayGames", "saygames"),
    ("Homa", "homa"), ("Azur Games", "azur"), ("Kwalee", "kwalee"), ("Good Job Games", "good job"),
    ("Popcore", "popcore"), ("ABI Global", "abi global"), ("iKame", "ikame"),
    ("Zego", "zego"), ("Playgendary", "playgendary"), ("Ketchapp", "ketchapp"),
    ("Grand Games", "grand games"), ("Oakever", "oakever"), ("Dream Games", "dream games"),
    ("Loom Games", "loom games"), ("Magic Tavern", "magic tavern"), ("Moonee", "moonee"),
    ("Tapnation", "tapnation"), ("Nebula Studio", "nebula"), ("Hungry Studio", "hungry studio"),
]


def get_json(url, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=20)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (403, 429):
                time.sleep(2 * (i + 1))
                continue
            return None
        except (requests.RequestException, ValueError):
            time.sleep(1 + i)
    return None


def kw_regex(keywords):
    # Match any keyword; for multi-word latin keywords require all words present.
    pats = []
    for k in keywords:
        words = [w for w in re.split(r"\s+", k.strip().lower()) if w]
        if not words:
            continue
        pats.append(words)

    def match(text):
        t = (text or "").lower()
        return any(all(w in t for w in words) for words in pats)
    return match


def days_since(iso):
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return max(1, (datetime.now(timezone.utc) - d).days)
    except (AttributeError, ValueError):
        return None


def scan_charts(countries, genres, match, apps, charts):
    for c in countries:
        for g in genres:
            for feed in ("topfreeapplications", "topgrossingapplications"):
                d = get_json(CHART_URL.format(c=c, feed=feed, g=g))
                entries = (d or {}).get("feed", {}).get("entry", []) or []
                if isinstance(entries, dict):
                    entries = [entries]
                key = f"{c}/{'free' if 'free' in feed else 'grossing'}/{g}"
                top = []
                for i, e in enumerate(entries, 1):
                    aid = e["id"]["attributes"]["im:id"]
                    name = e["im:name"]["label"]
                    top.append({"rank": i, "id": aid, "name": name,
                                "artist": e["im:artist"]["label"]})
                    if match(name):
                        a = apps.setdefault(aid, {"id": aid, "sources": set()})
                        a["sources"].add("chart")
                        a.setdefault("chart_ranks", {})[key] = i
                charts[key] = top[:30]
                time.sleep(0.2)


def scan_search(keywords, countries, apps):
    jobs = [(k, c) for k in keywords for c in countries]
    with ThreadPoolExecutor(4) as ex:
        results = ex.map(lambda kc: (kc, get_json(SEARCH_URL.format(t=quote(kc[0]), c=kc[1], n=50))), jobs)
        for (k, c), d in results:
            for r in (d or {}).get("results", []):
                aid = str(r["trackId"])
                a = apps.setdefault(aid, {"id": aid, "sources": set()})
                a["sources"].add(f"search:{c}")


def scan_publishers(match, apps, pubs_out):
    for label, needle in BIG_PUBLISHERS:
        d = get_json(DEV_SEARCH_URL.format(t=quote(label)))
        rows = [r for r in (d or {}).get("results", [])
                if needle in (r.get("artistName", "") + r.get("sellerName", "")).lower()]
        hits = [r for r in rows
                if match(r.get("trackName", "")) or match(r.get("description", "")[:600])]
        pubs_out[label] = {"apps_listed": len(rows), "matching": len(hits)}
        for r in hits:
            aid = str(r["trackId"])
            a = apps.setdefault(aid, {"id": aid, "sources": set()})
            a["sources"].add(f"publisher:{label}")
            a["big_publisher"] = label
        time.sleep(0.3)


def enrich_ios(apps, rating_countries):
    ids = list(apps)
    for i in range(0, len(ids), 150):
        batch = ids[i:i + 150]
        for c in rating_countries:
            d = get_json(LOOKUP_URL.format(ids=",".join(batch), c=c))
            for r in (d or {}).get("results", []):
                a = apps.get(str(r.get("trackId")))
                if not a:
                    continue
                a.setdefault("ratings", {})[c] = r.get("userRatingCount", 0)
                if c == "us" or "name" not in a:
                    a.update({
                        "genres": r.get("genres") or [],
                        "name": r.get("trackName"), "seller": r.get("sellerName"),
                        "artist": r.get("artistName"), "released": r.get("releaseDate", "")[:10],
                        "updated": r.get("currentVersionReleaseDate", "")[:10],
                        "version": r.get("version"), "size_mb": round(int(r.get("fileSizeBytes") or 0) / 1e6),
                        "genre": r.get("primaryGenreName"), "price": r.get("price"),
                        "desc": (r.get("description") or "")[:400].replace("\n", " "),
                        "url": r.get("trackViewUrl", "").split("?")[0],
                    })
                if c == "us":
                    a["us_avg"] = round(r.get("averageUserRating") or 0, 2)
            time.sleep(0.2)
    for a in apps.values():
        rs = a.get("ratings", {})
        a["ratings_total"] = sum(rs.values())
        a["top_markets"] = [f"{k}:{v}" for k, v in sorted(rs.items(), key=lambda x: -x[1])[:4] if v]
        ds = days_since(a.get("released", "") + "T00:00:00Z") if a.get("released") else None
        a["ratings_per_day"] = round(a["ratings_total"] / ds, 1) if ds else None
        if not a.get("big_publisher"):
            who = (a.get("artist", "") + " " + (a.get("seller") or "")).lower()
            for label, needle in BIG_PUBLISHERS:
                if needle in who:
                    a["big_publisher"] = label
                    break


GP_GAME_GENRES = {"Puzzle", "Casual", "Board", "Arcade", "Action", "Simulation", "Strategy",
                  "Word", "Trivia", "Card", "Adventure", "Racing", "Sports", "Role Playing",
                  "Educational", "Music", "Casino"}


def scan_gp(keywords, locales, match, max_details=60):
    try:
        from google_play_scraper import search, app as gp_app
    except ImportError:
        print("google-play-scraper not installed; skipping Google Play "
              "(pip install google-play-scraper)", file=sys.stderr)
        return {}
    found = {}

    def do_search(job):
        k, loc = job
        lang, country = loc.split(":")
        try:
            return job, search(k, lang=lang, country=country, n_hits=30)
        except Exception as e:  # scraper raises many types
            print(f"  GP search {k!r} {loc} failed: {e}", file=sys.stderr)
            return job, []

    with ThreadPoolExecutor(4) as ex:
        for (k, loc), res in ex.map(do_search, [(k, l) for k in keywords for l in locales]):
            for r in res:
                pid = r.get("appId")
                if pid:
                    g = found.setdefault(pid, {"appId": pid, "sources": set(), "title": r.get("title")})
                    g["sources"].add(f"gp:{loc}")
                    if r.get("genre"):
                        g["genre"] = r.get("genre")
    # Details only for game results, ranked by how many searches surfaced them.
    games = {p: g for p, g in found.items()
             if not g.get("genre") or g["genre"] in GP_GAME_GENRES}
    cand = sorted(games, key=lambda p: -len(games[p]["sources"]))[:max_details]

    def do_detail(pid):
        try:
            return pid, gp_app(pid, lang="en", country="us")
        except Exception:
            return pid, None

    with ThreadPoolExecutor(4) as ex:
        details = list(ex.map(do_detail, cand))
    found = {p: games[p] for p in cand}
    for pid, d in details:
        if not d:
            continue
        g = found[pid]
        g.update({"title": d.get("title"), "developer": d.get("developer"),
                  "installs": d.get("realInstalls") or d.get("minInstalls"),
                  "score": round(d.get("score") or 0, 2), "ratings": d.get("ratings"),
                  "released": d.get("released"), "updated": d.get("lastUpdatedOn"),
                  "iap": d.get("offersIAP"), "iap_range": d.get("inAppProductPrice"),
                  "ads": d.get("containsAds"), "genre": d.get("genre"),
                  "matches_kw": match(d.get("title", ""))})
    return found


def md_report(args, apps, charts, pubs, gp):
    L = [f"# Market scan: {args.keywords}", "",
         f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC. iOS ratings summed over: {args.rating_countries}._", ""]

    rel = [a for a in apps.values() if a.get("name")]
    rel.sort(key=lambda a: -a.get("ratings_total", 0))

    charted = [a for a in rel if a.get("chart_ranks")]
    L += ["## 1. Keyword-matching apps on the charts right now", ""]
    if charted:
        L += ["| App | Seller | Released | Chart ranks |", "|---|---|---|---|"]
        for a in sorted(charted, key=lambda a: min(a["chart_ranks"].values())):
            ranks = ", ".join(f"{k}#{v}" for k, v in sorted(a["chart_ranks"].items(), key=lambda x: x[1]))
            L.append(f"| {a['name']} | {a.get('seller')} | {a.get('released')} | {ranks} |")
    else:
        L.append("_None of the top-200 chart entries match the keywords (names only — check section 5 by eye)._")
    L.append("")

    L += ["## 2. All iOS candidates by size (verify relevance by reading `desc` in the JSON)", "",
          "| # | App | Seller | Big pub | Released | Updated | Ratings total | US avg | /day | Top markets |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for i, a in enumerate(rel[:args.top], 1):
        L.append(f"| {i} | [{a['name']}]({a.get('url')}) | {a.get('seller')} | {a.get('big_publisher','')} | "
                 f"{a.get('released')} | {a.get('updated')} | {a.get('ratings_total',0):,} | {a.get('us_avg','')} | "
                 f"{a.get('ratings_per_day','')} | {' '.join(a.get('top_markets', []))} |")
    L.append("")

    fast = [a for a in rel if (a.get("ratings_per_day") or 0) >= 20]
    fast.sort(key=lambda a: -a["ratings_per_day"])
    L += ["## 3. Fast risers (≥20 iOS ratings/day since launch) — usually paid UA", ""]
    for a in fast[:15]:
        L.append(f"- **{a['name']}** ({a.get('seller')}, {a.get('released')}): {a['ratings_per_day']}/day, {a['ratings_total']:,} total")
    if not fast:
        L.append("_none_")
    L.append("")

    L += ["## 4. Big-publisher attempts (small or stale ones = likely failed tests)", "",
          "| Publisher | iOS apps listed | Keyword hits in catalog | Related titles found (ratings, last update) |", "|---|---|---|---|"]
    for label, p in pubs.items():
        titles = [f"{a['name']} ({a.get('ratings_total',0):,}, {a.get('updated')})"
                  for a in rel if a.get("big_publisher") == label]
        L.append(f"| {label} | {p['apps_listed']} | {p['matching']} | {'; '.join(titles[:8])} |")
    L += ["", "> Delisted tests do not appear in Apple's API. Search the web for "
          "\"<publisher> <mechanic> soft launch\" / killed / sunset to find them.", ""]

    if gp:
        gl = sorted(gp.values(), key=lambda g: -(g.get("installs") or 0))
        L += ["## 5. Google Play candidates", "",
              "| App | Developer | Installs | Score | Ratings | Released | IAP | Found via |",
              "|---|---|---|---|---|---|---|---|"]
        for g in gl[:args.top]:
            L.append(f"| {g.get('title')} (`{g['appId']}`) | {g.get('developer')} | {g.get('installs') or 0:,} | "
                     f"{g.get('score')} | {g.get('ratings') or 0:,} | {g.get('released')} | {g.get('iap_range') or g.get('iap')} | "
                     f"{', '.join(sorted(g['sources']))[:60]} |")
        L.append("")

    L += ["## 6. Chart context (top 10 per chart, for spotting similar mechanics under other names)", ""]
    for k, top in charts.items():
        L.append(f"- **{k}**: " + "; ".join(f"{t['rank']}. {t['name']} ({t['artist']})" for t in top[:10]))
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keywords", required=True,
                    help="Comma-separated keywords, ideally in several languages")
    ap.add_argument("--search-countries", default=DEFAULT_SEARCH_COUNTRIES)
    ap.add_argument("--chart-countries", default="us,jp,kr,gb,de,fr,tr,vn")
    ap.add_argument("--genres", default="6014,7012",
                    help="Apple genre ids for charts (6014 Games, 7012 Puzzle, 7003 Casual, 7001 Action...)")
    ap.add_argument("--rating-countries", default=DEFAULT_RATING_COUNTRIES)
    ap.add_argument("--gp-locales", default=DEFAULT_GP_LOCALES)
    ap.add_argument("--no-gp", action="store_true", help="Skip Google Play")
    ap.add_argument("--all-genres", action="store_true", help="Keep non-game apps (default: games only)")
    ap.add_argument("--gp-details", type=int, default=60, help="Max Google Play apps to fetch details for")
    ap.add_argument("--no-publishers", action="store_true", help="Skip big-publisher sweep")
    ap.add_argument("--min-ratings", type=int, default=0, help="Drop iOS apps below this total")
    ap.add_argument("--top", type=int, default=40, help="Rows per table")
    ap.add_argument("--out", default="market_scan")
    args = ap.parse_args()

    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
    match = kw_regex(keywords)
    apps, charts, pubs = {}, {}, {}

    print("[1/5] charts...", file=sys.stderr)
    scan_charts(args.chart_countries.split(","), args.genres.split(","), match, apps, charts)
    print("[2/5] iOS keyword search...", file=sys.stderr)
    scan_search(keywords, args.search_countries.split(","), apps)
    if not args.no_publishers:
        print("[3/5] big-publisher sweep...", file=sys.stderr)
        scan_publishers(match, apps, pubs)
    print(f"[4/5] iOS lookup for {len(apps)} apps x {len(args.rating_countries.split(','))} countries...", file=sys.stderr)
    enrich_ios(apps, args.rating_countries.split(","))
    if not args.all_genres:
        apps = {k: v for k, v in apps.items() if "Games" in v.get("genres", []) or v.get("genre") == "Games"}
    if args.min_ratings:
        apps = {k: v for k, v in apps.items()
                if v.get("ratings_total", 0) >= args.min_ratings or v.get("chart_ranks") or v.get("big_publisher")}
    gp = {}
    if not args.no_gp:
        print("[5/5] Google Play...", file=sys.stderr)
        gp = scan_gp(keywords, args.gp_locales.split(","), match, args.gp_details)

    for d in list(apps.values()) + list(gp.values()):
        d["sources"] = sorted(d.get("sources", []))
    with open(args.out + ".json", "w", encoding="utf-8") as f:
        json.dump({"keywords": keywords, "ios": apps, "gp": gp, "charts": charts,
                   "publishers": pubs}, f, ensure_ascii=False, indent=1, default=str)
    report = md_report(args, apps, charts, pubs, gp)
    with open(args.out + ".md", "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print(f"\n[saved {args.out}.json and {args.out}.md]", file=sys.stderr)


if __name__ == "__main__":
    main()
