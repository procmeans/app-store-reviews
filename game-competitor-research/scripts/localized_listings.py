#!/usr/bin/env python3
"""Pull a game's store listing in many languages (iOS + Google Play).

Why: the localized title / subtitle / description tell you
  - what the mechanic is called in each language (use these words for
    multilingual web + store searches — much better than your own translation),
  - how the game is positioned per market (relax vs brain vs ASMR ...),
  - which mechanics / boosters / modes are advertised.

Usage:
  python3 localized_listings.py --ios-id 6793924927 --gp-id com.nebula.rotaterings --out data/rr_listings
  python3 localized_listings.py --gp-id com.vnstart.ring.rotate.puzzle --langs tr,vi,ja
"""
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

UA = {"User-Agent": "Mozilla/5.0 (game-competitor-research skill)"}
# lang -> (iOS storefront, iOS lang param, GP lang, GP country)
# GP search/details in some EU storefronts fail in google-play-scraper, so
# French/German/Spanish use CA/CH/MX storefronts (same language text).
LOCALES = {
    "en": ("us", "en_us", "en", "us"),
    "tr": ("tr", "tr_tr", "tr", "tr"),
    "vi": ("vn", "vi_vn", "vi", "vn"),
    "ja": ("jp", "ja_jp", "ja", "jp"),
    "ko": ("kr", "ko_kr", "ko", "kr"),
    "fr": ("fr", "fr_fr", "fr", "ca"),
    "de": ("de", "de_de", "de", "ch"),
    "es": ("mx", "es_mx", "es", "mx"),
    "zh": ("tw", "zh_tw", "zh-TW", "tw"),
    "pt": ("br", "pt_br", "pt", "br"),
    "ru": ("ru", "ru_ru", "ru", "ru"),
}
DEFAULT_LANGS = "en,tr,vi,ja,ko,fr,de,es,zh"


def ios(app_id, lang):
    c, l, _, _ = LOCALES[lang]
    try:
        r = requests.get(f"https://itunes.apple.com/lookup?id={app_id}&country={c}&lang={l}",
                         headers=UA, timeout=20).json()["results"]
    except (requests.RequestException, ValueError, KeyError):
        return None
    if not r:
        return None
    r = r[0]
    return {"title": r.get("trackName"), "ratings": r.get("userRatingCount"),
            "avg": round(r.get("averageUserRating") or 0, 2),
            "languages": r.get("languageCodesISO2A"), "desc": r.get("description", "")}


def gp(pkg, lang):
    _, _, l, c = LOCALES[lang]
    try:
        from google_play_scraper import app
        d = app(pkg, lang=l, country=c)
    except Exception:
        return None
    return {"title": d.get("title"), "summary": d.get("summary"), "desc": d.get("description", ""),
            "installs": d.get("realInstalls"), "iap": d.get("inAppProductPrice"),
            "recent_changes": d.get("recentChanges")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ios-id")
    ap.add_argument("--gp-id")
    ap.add_argument("--langs", default=DEFAULT_LANGS, help=f"Subset of {','.join(LOCALES)}")
    ap.add_argument("--chars", type=int, default=700, help="Description chars to keep per language")
    ap.add_argument("--out", help="Write Markdown to <out>.md")
    args = ap.parse_args()
    if not (args.ios_id or args.gp_id):
        ap.error("need --ios-id and/or --gp-id")
    langs = [l for l in args.langs.split(",") if l in LOCALES]

    with ThreadPoolExecutor(6) as ex:
        ios_res = dict(zip(langs, ex.map(lambda l: ios(args.ios_id, l), langs))) if args.ios_id else {}
        gp_res = dict(zip(langs, ex.map(lambda l: gp(args.gp_id, l), langs))) if args.gp_id else {}

    L = [f"# Localized listings: iOS {args.ios_id or '-'} / GP {args.gp_id or '-'}", ""]
    if ios_res:
        first = next((v for v in ios_res.values() if v), None)
        if first:
            L += [f"iOS in-app UI languages (store text can still be localized): {', '.join(first.get('languages') or [])}", ""]
    L += ["| Lang | iOS title | iOS ratings (avg) | GP title | GP summary |", "|---|---|---|---|---|"]
    for l in langs:
        i, g = ios_res.get(l) or {}, gp_res.get(l) or {}
        L.append(f"| {l} | {i.get('title', '')} | {i.get('ratings', '')} ({i.get('avg', '')}) | "
                 f"{g.get('title', '')} | {g.get('summary', '')} |")
    L.append("")
    same = set()
    for l in langs:
        i, g = ios_res.get(l) or {}, gp_res.get(l) or {}
        L.append(f"## {l}")
        for label, d in (("iOS", i), ("GP", g)):
            text = (d.get("desc") or "").replace("\r", "").strip()
            key = text[:200]
            if not text:
                continue
            if key in same:
                L.append(f"- {label}: _same text as another language (not localized)_")
                continue
            same.add(key)
            L.append(f"- **{label}**: " + text[:args.chars].replace("\n", " "))
        if g.get("recent_changes"):
            L.append(f"- GP what's new: {g['recent_changes'][:200]}")
        L.append("")
    L += ["> Next: extract the local name of the mechanic and key feature words per language, "
          "then use them for web search (references/multilingual.md) and a second market_scan pass."]
    report = "\n".join(L)
    print(report)
    if args.out:
        with open(args.out + ".md", "w", encoding="utf-8") as f:
            f.write(report)
        print(f"[saved {args.out}.md]", file=sys.stderr)


if __name__ == "__main__":
    main()
