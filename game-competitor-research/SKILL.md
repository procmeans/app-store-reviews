---
name: game-competitor-research
description: >-
  Competitive research for a mobile game or game mechanic (e.g. "rotate rings",
  "screw jam", "tangle", "bus jam"): who is on the charts right now, every
  same-mechanic competitor on iOS and Google Play found with multilingual
  keywords, who did it first, multilingual review analysis of the leaders, and
  what big hyper/hybrid-casual publishers (Rollic, Voodoo, Lion Studios,
  Supersonic, SayGames, CrazyLabs...) tried — including failed or abandoned
  attempts. Use whenever the user asks for 竞品调研 / 竞品分析 / 品类调研 /
  赛道调研 / 从0到1调研 / "research this game" / "who are the competitors of X"
  for a game, even if they only give a game name or App Store link.
---

# Game competitor research

One agent, four scripts, one report. Do **not** fan out into parallel research
subagents or a multi-stage deep-research pipeline — the scripts pull hard data
in minutes; your job is to read it, check relevance, and judge.

Scripts live in `scripts/` next to this file; the review analyzer lives in the
sibling `app-store-reviews` skill. Resolve paths relative to this SKILL.md.
Install once: `pip install requests google-play-scraper`.

Write all intermediate files under `data/<slug>/` in the working directory.

## Workflow

Core languages for everything (store search, listings, reviews, web research):
**en, tr, vi, ja, ko, fr, de, es** (+ zh). Turkish and Vietnamese are not
optional — they are where many of these games and clones are made.

### 1. Keywords in many languages (2 min)

From the game name / mechanic, write short search phrases: English synonyms
(what store listings would say: "rotate rings", "untie rings", "unlock
circle") **plus** a first-guess translation in each core language. Keep them
1–3 words. Too-generic words ("puzzle", "ring" alone) flood the results.
After step 2b, replace your guesses with the words the stores actually use.

### 2. Market scan (≈2–3 min)

```bash
python3 scripts/market_scan.py --keywords "rotate rings,untie rings,リング 回転,링 회전,旋转圆环" --out data/<slug>/scan
```

Read `scan.md`. It has: (1) keyword-matching apps on the US/JP/GB/DE/KR top-200
free & grossing charts with ranks; (2) all iOS candidates by total ratings over
17 countries with top markets and ratings/day; (3) fast risers; (4) the
big-publisher sweep; (5) Google Play candidates with installs and IAP range;
(6) the top-10 of every chart.

Then **you** must:
- Drop irrelevant hits (read `desc` in `scan.json` when the name is unclear).
- Scan section 6 by eye for the same mechanic under a different name — chart
  hits only match by name.
- Name the **current leaders** by chart rank first, then ratings/day, then
  total size. Never call something "the leader" without checking charts.
- Build the **origin timeline**: sort relevant apps by release date on both
  stores; the earliest same-mechanic title and the first one that scaled are
  answers to "who invented this". Confirm the mechanic from `desc`.
- Chart ranks are a snapshot. If the user says an app hit #1, trust that and
  say history needs Sensor Tower / AppMagic.

### 2b. Localized listings + multilingual gameplay research (≈10 min)

For each leader (and each notable big-publisher attempt):

```bash
python3 scripts/localized_listings.py --ios-id <id> --gp-id <package> --out data/<slug>/<app>_listings
```

This gives the store title/summary/description in en/tr/vi/ja/ko/fr/de/es/zh:
the local name of the mechanic, positioning per market, advertised mechanics.
Then follow `references/multilingual.md`: re-run `market_scan.py` with the
local terms to catch local clones, and do web searches **in every core
language** (guides, walkthrough videos, local reviews, dev/industry posts —
Turkish and Vietnamese studio posts especially). Record findings per language.

### 2c. Industry sites in every language (≈10 min, mandatory)

Open `references/industry-sites.md` and, for **each** core language, run
site-restricted searches on that language's industry sites
(`site:<domain> <local mechanic name | game | publisher> <industry word>`),
at least 2 sites per language plus the English core set. Look for: market
size and chart stories, studio/publisher news, funding and layoffs, soft
launches, kills, postmortems, genre analyses. Keep a running log of
language × site × query × hit/no-hit — it becomes the report's 检索覆盖表.
Never drop a language silently; "checked, nothing found" is a valid row.

### 3. Reviews of the top 3–5, every language (≈10 s per app)

```bash
python3 scripts/multilang_reviews.py --ios-id <id> --gp-id <package> --out data/<slug>/<app>
python3 ../app-store-reviews/scripts/analyze_reviews.py data/<slug>/<app>.json --profile game --neg 30 --pos 10 --out data/<slug>/<app>_analysis.md
```

`multilang_reviews.py` auto-picks every iOS country with ≥50 ratings and pulls
Google Play in 11 languages. Read the negative samples **in all languages**
(translate as you go) and write for each app: top complaints with frequency
from the dimension table + one quote (original language + 中文 translation),
top praises, feature requests, and differences by market (e.g. JP avg vs US).
Look at `dev_reply` on GP rows to see how the developer handles players.

### 4. Big publishers & failures (≈5 min)

Section 4 of the scan lists, per publisher, the related titles still on the
App Store. Classify each:
- **Hit**: charted or large and still updated.
- **Faded / failed**: small rating count, or no update for 6+ months.
- **Killed**: not in the stores any more — only findable on the web.

Then do web searches (query patterns in `references/sources.md`; sites in
`references/industry-sites.md` — search the publisher's home-language press
too: Turkish for Rollic/Good Job/Grand Games, French for Voodoo/Homa,
Vietnamese for iKame/ABI) to find killed soft-launch tests, publisher statements,
and deconstructions. For each big-publisher attempt write what they changed
versus the base mechanic (3D, color sort, "Jam" layer, meta, live ops) and why
it likely worked or failed. Label these as inference unless sourced.

### 5. Report

Use `references/report-template.md`. Default language is the user's. Every
number carries a tag: **[硬数据]** (store/API), **[第三方]** (articles,
analytics snippets), **[推断]** (your reasoning). State the scan date. Keep it
tight: tables for data, short paragraphs for judgment. Save to
`reports/<title>.md` and send it to the user.

## Things that went wrong before (don't repeat)

- Treating the app the user named as the category leader without checking
  charts — the real #1–3 was a 2-month-old app.
- Reading only US English reviews — a leader's second market was Japan.
- Guessing downloads from rating counts when Google Play `realInstalls` is
  available from the scan.
- Skipping big-publisher and failed attempts — they explain why the category
  looks the way it does.
- Spawning many subagents that each fetch half the data and contradict each
  other. Run the scripts once and reason over the output.

## Limits to tell the user

Apple RSS gives ≤500 newest reviews per country; brand-new apps expose few
iOS text reviews (GP fills the gap). Revenue, DAU, retention and rank history
need Sensor Tower / AppMagic / data.ai. Meta Ad Library and TikTok Creative
Center need a browser and login — offer to use one if available.
