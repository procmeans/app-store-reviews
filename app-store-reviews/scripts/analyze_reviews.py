#!/usr/bin/env python3
"""Summarize scraped App Store reviews into stats + sample buckets.

Reads a JSON file produced by fetch_reviews.py (or any JSON with a top-level
`reviews` list of dicts having rating/title/content/app_version/country/updated)
and prints a Markdown report skeleton: rating distribution, per-version table
(to spot regressions), and buckets of representative negative / positive
reviews. The calling agent reads these buckets and writes the qualitative
"common complaints / highlights" synthesis — that judgment is better left to the
model than to brittle keyword counting (especially for CJK text).

Usage:
  python analyze_reviews.py reviews.json
  python analyze_reviews.py reviews.json --neg 15 --pos 8 --out report.md
"""
import argparse
import datetime
import json
import re
import sys
from collections import Counter, defaultdict

# Keyword presets. Each has the complaint dimensions (a recall floor, see main())
# and the wish/suggestion signals used to pick feature-request candidates.
# Keywords are matched lower-cased, so English entries must be lower-case.
PRESETS = {
    "vocab-cn": {
        "dimensions": {
            "价格/会员太贵": ["贵", "会员", "价格", "收费", "氪", "付费", "充钱", "充值",
                           "订阅", "涨价", "割韭菜", "白嫖", "舍不得", "太黑", "圈钱"],
            "广告": ["广告", "弹窗", "开屏", "摇一摇", "推广", "插屏", "跳转淘宝", "跳转"],
            "自动扣费/退款": ["扣费", "乱扣", "自动续费", "退款", "退费", "诱导", "默认勾选", "偷偷扣"],
            "闪退/卡顿/bug": ["闪退", "崩溃", "卡顿", "卡死", "白屏", "黑屏", "死机", "打不开",
                           "加载不", "bug", "进不去", "登录不"],
            "多端同步/数据丢失": ["同步", "多设备", "换手机", "电脑", "平板", "ipad", "网页版",
                              "数据丢", "清空", "记录没", "进度没", "丢失"],
            "客服/反馈": ["客服", "没人理", "不回复", "不回应", "投诉", "反馈无", "找不到客服"],
            "内容质量": ["错误", "错别字", "释义", "例句", "发音不", "翻译不", "不准", "音标错", "质量差"],
            "学习机制/强制": ["复习量", "任务", "强制", "归零", "能量", "限制", "断签", "逼着", "门槛"],
        },
        "requests": ["希望", "能不能", "建议", "要是能", "要是有", "最好能", "最好有",
                     "加个", "加上", "出个", "想要", "为什么不", "为啥不", "求", "期待",
                     "可以加", "增加", "添加", "改进", "什么时候", "盼", "希望能", "能加"],
    },
    "game-en": {
        "dimensions": {
            "ads: frequency/interruption": [" ad ", " ads", "ad break", "commercial",
                                            "every game", "after every", "too many ad",
                                            "mid game", "middle of"],
            "ads: paid removal not honored": ["paid to remove", "paid for no ads", "remove ads",
                                              "no ads", "ad free", "ad-free", "still get ads",
                                              "still see ads", "still ads", "refund"],
            "ads: forced/unskippable/redirect": ["can't skip", "cant skip", "unskippable",
                                                 "no x", "no exit", "redirect", "sends you to",
                                                 "app store", "play store", "30 second"],
            "ads: misleading (ad ≠ game)": ["misleading", "false advertis", "fake ad",
                                            "not like the ad", "nothing like the ad",
                                            "not what the ad", "clickbait", "scam"],
            "physics/fairness": ["physics", "unfair", "pushed out", "flew out", "fly out",
                                 "bounce", "glitch", "overlap", "jumps", "launched",
                                 "didn't merge", "didnt merge", "won't merge", "wont merge",
                                 "rigged", "wobble", "jiggl", "death line", "over the line",
                                 "top line", "touching", "hitbox"],
            "difficulty/luck": ["too hard", "impossible", "too easy", "luck", "rng",
                                "same fruit", "keeps giving", "can't win", "cant win", "random"],
            "levels/goals": ["levels are", "level design", "stuck on level", "stuck on a level",
                             "beat level", "beat the level", "hard level", "stage", "goal",
                             "target", "mission", "moves", "objective", "time limit",
                             "levels get", "new levels"],
            "repetitive/no progression": ["boring", "repetitive", "same thing", "nothing to do",
                                          "no goal", "gets old", "no levels", "more levels",
                                          "progress", "endless"],
            "boosters/power-ups": ["booster", "power up", "power-up", "powerup", "shake",
                                   "hammer", "bomb", "remove fruit", "tool", "item"],
            "lives/energy/waiting": ["lives", "energy", "wait for", "hearts", "out of life",
                                     "refill", "timer to play"],
            "monetization/price": ["pay to", "paywall", "expensive", "price", "coins",
                                   "gems", "subscription", "unlock", "locked", "$", "purchase"],
            "cosmetics/collection": ["skin", "theme", "collection", "unlock new", "album",
                                     "outfit", "decorat"],
            "leaderboard/social": ["leaderboard", "high score", "highscore", "compete",
                                   "friends", "ranking", "global", "multiplayer", "pvp"],
            "audio": ["sound", "music", "audio", "mute", "noise", "song"],
            "offline/connectivity": ["offline", "wifi", "wi-fi", "internet", "airplane",
                                     "connection", "no signal"],
            "crash/lag/battery": ["crash", "freez", "lag", "slow", "battery", "overheat",
                                  "won't load", "wont load", "black screen", "bug"],
            "data loss/sync": ["lost my", "progress gone", "reset", "high score gone",
                               "new phone", "sync", "cloud", "ipad"],
            "controls/ux": ["control", "aiming", "drag", "tap", "accidentally", "misclick",
                            "button", "undo", "preview", "next fruit"],
            "readability/visual": ["hard to see", "can't tell", "cant tell", "similar color",
                                   "same color", "too small", "tiny", "graphics", "blurry",
                                   "colors"],
        },
        # Praise axes, tallied the same way on >=4 star reviews: why players stay.
        "praise": {
            "relaxing/calming": ["relax", "calm", "chill", "stress", "unwind", "soothing",
                                 "zen", "anxiety"],
            "addictive/can't stop": ["addict", "can't stop", "cant stop", "hooked",
                                     "one more", "hours"],
            "satisfying merges/physics": ["satisfy", "physics", "smooth", "combo", "chain",
                                          "juicy", "feel"],
            "cute art/characters": ["cute", "adorable", "graphics", "art", "design",
                                    "colorful", "kawaii"],
            "few/fair ads": ["no ads", "not many ads", "few ads", "ads are fair",
                             "ads aren't", "not too many", "optional ad", "no ad"],
            "challenge/strategy": ["challeng", "strategy", "think", "brain", "skill"],
            "offline play": ["offline", "no wifi", "without wifi", "airplane"],
            "progression/levels": ["level", "unlock", "collect", "skins", "rewards"],
        },
        "requests": ["wish", "please add", "should add", "would be nice", "would love",
                     "it would be", "i want", "need a", "needs a", "add a", "add an",
                     "hope", "suggest", "if only", "could you", "can you", "why can't",
                     "why cant", "option to", "feature"],
    },
    "game-ja": {
        "dimensions": {
            "広告": ["広告", "cm", "動画"],
            "広告削除/課金": ["広告削除", "課金", "有料", "買", "返金", "払"],
            "物理/理不尽": ["物理", "理不尽", "飛", "跳ね", "はみ出", "揺れ", "くっつかない",
                          "合体しない", "判定"],
            "難易度/運": ["難し", "簡単", "運", "クリアできない", "無理"],
            "ステージ/目標": ["ステージ", "レベル", "目標", "ミッション", "手数"],
            "バグ/落ちる/重い": ["バグ", "落ちる", "強制終了", "固ま", "重い", "フリーズ", "不具合"],
            "データ消失": ["データ", "消え", "引き継", "リセット"],
            "操作性": ["操作", "タップ", "誤", "ボタン"],
        },
        "praise": {
            "癒し": ["癒", "リラックス", "のんびり", "暇つぶし"],
            "ハマる": ["ハマ", "夢中", "中毒", "止まらない"],
            "かわいい": ["かわい", "可愛", "キャラ", "デザイン"],
        },
        "requests": ["欲しい", "ほしい", "希望", "してほしい", "追加", "改善", "お願い", "できれば"],
    },
}


def load_reviews(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data, data.get("reviews", [])
    if isinstance(data, list):
        return {}, data
    raise ValueError("Unrecognized JSON shape")


def to_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def bar(n, total, width=24):
    if total == 0:
        return ""
    filled = round(width * n / total)
    return "█" * filled + "·" * (width - filled)


STOPWORDS = set("""a an the and or but if then so to of in on at for with from by is are was
were be been being it its it's this that these those i me my we our you your he she they them
their game games app just very really so too not no can can't cant do don't dont does did
have has had get got getting will would could should im i'm ive i've it’s i’m there here
what when which who how all any some more most one two up out about than also only even
because like play playing played make makes made time times fruit fruits merge""".split())


def text_of(r):
    return ((r.get("title") or "") + " " + (r.get("content") or "")).strip()


def ngrams(texts, n, top):
    """Most frequent English word n-grams (stop-word-only grams dropped), counted
    once per review so one long rant can't dominate."""
    c = Counter()
    for t in texts:
        words = re.findall(r"[a-z0-9][a-z0-9']*", t.lower().replace("\u2019", "'"))
        grams = set()
        for i in range(len(words) - n + 1):
            g = words[i:i + n]
            if all(w in STOPWORDS for w in g) or g[0] in STOPWORDS and g[-1] in STOPWORDS:
                continue
            grams.add(" ".join(g))
        c.update(grams)
    return [(g, k) for g, k in c.most_common(top) if k >= 3]


def resolve_preset(names):
    """--dims accepts one preset or a comma list (e.g. game-en,game-ja for a
    mixed-language pool); dimensions with the same name are keyword-unioned."""
    out = {"dimensions": {}, "praise": {}, "requests": []}
    for name in names.split(","):
        p = PRESETS[name.strip()]
        for key in ("dimensions", "praise"):
            for dim, kws in p.get(key, {}).items():
                out[key].setdefault(dim, []).extend(kws)
        out["requests"].extend(p["requests"])
    return out


def compute(reviews, preset, recent_days=90):
    """All numbers in the report, as a dict (also what compare_apps.py consumes)."""
    rows = [r for r in reviews if 1 <= to_int(r.get("rating")) <= 5]
    n = len(rows)
    rating = lambda r: to_int(r.get("rating"))
    low = lambda r: rating(r) <= 2
    texts = {id(r): text_of(r).lower() for r in rows}
    dates = sorted((r.get("updated") or "")[:10] for r in rows if r.get("updated"))
    latest = dates[-1] if dates else ""
    cutoff = ""
    if latest:
        try:
            cutoff = (datetime.date.fromisoformat(latest)
                      - datetime.timedelta(days=recent_days)).isoformat()
        except ValueError:
            pass
    is_recent = lambda r: cutoff and (r.get("updated") or "")[:10] >= cutoff

    m = {"n": n, "avg": sum(map(rating, rows)) / n if n else 0,
         "dist": Counter(map(rating, rows)), "low_share": sum(map(low, rows)) / n if n else 0,
         "first": dates[0] if dates else "", "latest": latest, "recent_cutoff": cutoff,
         "by_country": Counter(r.get("country", "?") for r in rows),
         "by_store": Counter(r.get("store", "ios") for r in rows)}

    def tally(dims, subset):
        out = {}
        for name, kws in dims.items():
            hit = [r for r in subset if any(k in texts[id(r)] for k in kws)]
            rec = [r for r in hit if is_recent(r)]
            out[name] = {
                "hits": len(hit), "share": len(hit) / len(subset) if subset else 0,
                "low": sum(map(low, hit)),
                "avg": sum(map(rating, hit)) / len(hit) if hit else None,
                "recent_share": (len(rec) / sum(1 for r in subset if is_recent(r))
                                 if any(is_recent(r) for r in subset) else None),
                "votes": sum(to_int(r.get("vote_sum")) for r in hit),
                "top": sorted(hit, key=lambda r: -to_int(r.get("vote_sum")))[:2],
                "ids": {id(r) for r in hit},
            }
        return out

    m["dims"] = tally(preset["dimensions"], rows)
    m["praise"] = tally(preset.get("praise", {}), [r for r in rows if rating(r) >= 4])

    # which complaints travel together (e.g. ads + physics = "rigged to sell boosters")
    names = list(m["dims"])
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            k = len(m["dims"][a]["ids"] & m["dims"][b]["ids"])
            if k >= 3:
                pairs.append((a, b, k))
    m["cooccur"] = sorted(pairs, key=lambda x: -x[2])[:8]

    months = defaultdict(list)
    for r in rows:
        if r.get("updated"):
            months[r["updated"][:7]].append(rating(r))
    m["months"] = [(k, len(v), sum(v) / len(v), sum(x <= 2 for x in v) / len(v))
                   for k, v in sorted(months.items(), reverse=True)]

    lens = sorted(len(text_of(r)) for r in rows)
    m["median_len"] = lens[len(lens) // 2] if lens else 0
    m["long_low"] = sum(1 for r in rows if low(r) and len(text_of(r)) >= 300)

    gp = [r for r in rows if r.get("store") == "gplay"]
    if gp:
        gpl = [r for r in gp if low(r)]
        m["dev_reply"] = {"all": sum(bool(r.get("dev_reply")) for r in gp) / len(gp),
                          "low": (sum(bool(r.get("dev_reply")) for r in gpl) / len(gpl)) if gpl else 0}

    # near-verbatim duplicate bodies (template / incentivised reviews)
    bodies = Counter(re.sub(r"\W+", " ", (r.get("content") or "").lower()).strip()
                     for r in rows if len(r.get("content") or "") >= 40)
    m["dupes"] = [(b, k) for b, k in bodies.most_common(5) if k >= 2]

    neg_txt = [texts[id(r)] for r in rows if low(r)]
    pos_txt = [texts[id(r)] for r in rows if rating(r) >= 4]
    m["neg_phrases"] = ngrams(neg_txt, 2, 15) + ngrams(neg_txt, 3, 10)
    m["pos_phrases"] = ngrams(pos_txt, 2, 12)
    return m


def pct(x):
    return "–" if x is None else f"{100 * x:.1f}%"


def main():
    ap = argparse.ArgumentParser(description="Analyze scraped App Store / Google Play reviews")
    ap.add_argument("json_file", nargs="+",
                    help="Reviews JSON from fetch_reviews.py / fetch_gplay.py; several files "
                         "(e.g. one app's iOS + Play masters) are pooled into one report")
    ap.add_argument("--neg", type=int, default=12, help="How many negative samples (rating<=2)")
    ap.add_argument("--pos", type=int, default=6, help="How many positive samples (rating>=4)")
    ap.add_argument("--out", help="Write Markdown to this file (also prints to stdout)")
    ap.add_argument("--dims", default="vocab-cn",
                    help="Keyword preset(s), comma-separated: " + ", ".join(sorted(PRESETS)) +
                         ". vocab-cn = Chinese learning apps (default); game-en / game-ja = "
                         "casual-game reviews (App Store or Google Play)")
    ap.add_argument("--recent-days", type=int, default=90,
                    help="Window for the 'recent share' column (vs. the whole sample)")
    ap.add_argument("--sample", choices=["recent", "helpful"], default="recent",
                    help="Order of the sample buckets: newest first, or most up-voted first")
    args = ap.parse_args()
    for name in args.dims.split(","):
        if name.strip() not in PRESETS:
            ap.error(f"unknown preset {name!r}; choose from {', '.join(sorted(PRESETS))}")
    preset = resolve_preset(args.dims)

    meta, reviews = {}, []
    for path in args.json_file:
        m_, rv = load_reviews(path)
        for k, v in m_.items():
            if k == "store_stats":
                meta.setdefault("store_stats", {}).update(
                    {f"{m_.get('store', 'ios')}/{c}": s for c, s in (v or {}).items()})
            elif k != "reviews":
                meta.setdefault(k, v)
        for r in rv:
            r.setdefault("store", m_.get("store", "ios"))
        reviews.extend(rv)
    reviews.sort(key=lambda r: r.get("updated") or "", reverse=True)
    if not reviews:
        print("No reviews found in file.", file=sys.stderr)
        sys.exit(1)
    if args.sample == "helpful":
        reviews.sort(key=lambda r: -to_int(r.get("vote_sum")))

    M = compute(reviews, preset, args.recent_days)
    avg, dist, total = M["avg"], M["dist"], M["n"]

    # per-version: count + avg rating, to surface regressions
    ver_counts = defaultdict(int)
    ver_sum = defaultdict(int)
    for r in reviews:
        v = r.get("app_version") or "(unknown)"
        rt = to_int(r.get("rating"))
        if 1 <= rt <= 5:
            ver_counts[v] += 1
            ver_sum[v] += rt

    def ver_key(v):
        # best-effort numeric sort so versions read in order
        parts = []
        for p in str(v).replace("(unknown)", "0").split("."):
            parts.append(to_int("".join(ch for ch in p if ch.isdigit())))
        return parts
    versions = sorted(ver_counts, key=ver_key, reverse=True)

    def fmt(r):
        rt = to_int(r.get("rating"))
        store = "GP/" if r.get("store") == "gplay" else ""
        votes = f" 👍{r.get('vote_sum')}" if to_int(r.get("vote_sum")) > 0 else ""
        head = (f"- **{'★'*rt}** [{store}{r.get('country','?')}/{r.get('app_version','?')}/"
                f"{(r.get('updated') or '')[:10]}{votes}] ")
        t = (r.get("title") or "").strip()
        c = (r.get("content") or "").strip().replace("\n", " ")
        reply = " ↳ *dev replied*" if r.get("dev_reply") else ""
        return head + (f"**{t}** — " if t else "") + c + reply

    negatives = [r for r in reviews if to_int(r.get("rating")) <= 2]
    positives = [r for r in reviews if to_int(r.get("rating")) >= 4]

    # feature-request candidates: reviews whose text signals a wish/suggestion.
    # This is a quantitative pre-filter — the qualitative grouping of WHAT users
    # want is left to the model reading these, since intent needs comprehension.
    REQ_SIGNALS = preset["requests"]
    requests_ = [r for r in reviews if any(s in text_of(r).lower() for s in REQ_SIGNALS)]

    title = meta.get("app_title") or "App"
    app_id = meta.get("app_id", "?")

    lines = []
    lines.append(f"# 评论分析:{title} (id {app_id})")
    lines.append("")
    lines.append(f"- 抓取文字评论数:**{len(reviews)}**　样本平均评分:**{avg:.2f}** / 5　"
                 f"差评率(≤2★):**{pct(M['low_share'])}**")
    lines.append(f"- 时间跨度:{M['first']} → {M['latest']}　评论中位长度:{M['median_len']} 字符　"
                 f"长差评(≥300 字符):{M['long_low']}")
    lines.append(f"- 国家/地区:" + ", ".join(f"{c} ({n})" for c, n in M["by_country"].most_common()))
    if len(M["by_store"]) > 1 or "gplay" in M["by_store"]:
        lines.append(f"- 商店:" + ", ".join(f"{s} ({n})" for s, n in M["by_store"].items()))
    if "dev_reply" in M:
        lines.append(f"- Google Play 开发者回复率:全部 {pct(M['dev_reply']['all'])},"
                     f"差评 {pct(M['dev_reply']['low'])}")

    # coverage vs official store ratings, if fetch_reviews saved store_stats
    stats = meta.get("store_stats") or {}
    grand_total = sum((s.get("total_ratings") or 0) for s in stats.values())
    if grand_total:
        cover = 100 * len(reviews) / grand_total
        per = "，".join(
            f"{c} 官方均分 {s.get('avg_rating','?')}（总评分 {s.get('total_ratings'):,}）"
            for c, s in stats.items() if s.get("total_ratings"))
        if cover >= 0.5:
            cov = f"{len(reviews)} / {grand_total:,} ≈ **{cover:.2f}%**"
        else:
            cov = (f"{len(reviews)} / {grand_total:,}，"
                   f"**约每 {round(grand_total/len(reviews)):,} 条评分中抓到 1 条文字评论**")
        lines.append(f"- **官方汇总**:{per}")
        lines.append(f"- **抓取覆盖率**:{cov} "
                     f"（分母为打星总量，非纯文字评论；RSS 每区上限约 500 条文字评论）")
    if meta.get("sort"):
        lines.append(f"- 排序方式:{meta['sort']}")
    lines.append("")

    lines.append("## 评分分布")
    lines.append("")
    lines.append("| 星级 | 数量 | 占比 | |")
    lines.append("|---|---|---|---|")
    for star in (5, 4, 3, 2, 1):
        k = dist.get(star, 0)
        lines.append(f"| {'★'*star} | {k} | {pct(k / total if total else 0)} | `{bar(k, total)}` |")
    lines.append("")

    lines.append("## 月度趋势(口碑在变好还是变坏)")
    lines.append("")
    lines.append("| 月份 | 评论数 | 平均分 | 差评率 |")
    lines.append("|---|---|---|---|")
    for mo, k, a, lo in M["months"][:12]:
        lines.append(f"| {mo} | {k} | {a:.2f} | {pct(lo)} |")
    lines.append("")

    lines.append("## 各版本评分(发现版本回归)")
    lines.append("")
    lines.append("| 版本 | 评论数 | 平均分 |")
    lines.append("|---|---|---|")
    for v in versions[:20]:
        c = ver_counts[v]
        a = ver_sum[v] / c if c else 0
        lines.append(f"| {v} | {c} | {a:.2f} |")
    lines.append("")
    lines.append("> 关注:评论数足够(≥5)却平均分明显低于整体的版本,通常是一次更新引入了问题。")
    lines.append("")

    lines.append("## 吐槽维度计数(关键词命中,硬数字防漏项)")
    lines.append("")
    lines.append("> 一条评论可命中多个维度;这是召回辅助,不是互斥分类。归纳时**频次以此为准、别只凭语感**;"
                 "每个维度都要回应,哪怕命中低也要说明。**命中均分**越低 = 该痛点越致命;"
                 f"**近 {args.recent_days} 天占比**高于全样本 = 正在恶化;**点赞**= 其他用户的认同量。")
    lines.append("")
    lines.append(f"| 吐槽维度 | 命中条数 | 占全样本 | 近{args.recent_days}天占比 | 其中差评(≤2★) | 命中均分 | 点赞 |")
    lines.append("|---|---|---|---|---|---|---|")
    for name, d in sorted(M["dims"].items(), key=lambda x: -x[1]["low"]):
        a = "–" if d["avg"] is None else f"{d['avg']:.2f}"
        lines.append(f"| {name} | {d['hits']} | {pct(d['share'])} | {pct(d['recent_share'])} | "
                     f"{d['low']} | {a} | {d['votes']} |")
    lines.append("")
    if M["cooccur"]:
        lines.append("**常一起出现的吐槽**(同一条评论命中两个维度):" + ";".join(
            f"{a} + {b} ({k})" for a, b, k in M["cooccur"]))
        lines.append("")

    if M["praise"]:
        lines.append("## 好评理由计数(≥4★ 评论中的关键词命中)")
        lines.append("")
        lines.append("| 好评理由 | 命中条数 | 占好评 |")
        lines.append("|---|---|---|")
        for name, d in sorted(M["praise"].items(), key=lambda x: -x[1]["hits"]):
            lines.append(f"| {name} | {d['hits']} | {pct(d['share'])} |")
        lines.append("")

    if M["neg_phrases"] or M["pos_phrases"]:
        lines.append("## 高频短语(英文 n-gram,每条评论只计一次)")
        lines.append("")
        lines.append("- 差评:" + ", ".join(f"`{g}` {k}" for g, k in M["neg_phrases"]))
        lines.append("- 好评:" + ", ".join(f"`{g}` {k}" for g, k in M["pos_phrases"]))
        lines.append("")
        lines.append("> 关键词表之外冒出来的短语,往往就是预设维度没覆盖的新痛点。")
        lines.append("")

    if M["dupes"]:
        lines.append("## 疑似模板/重复评论")
        lines.append("")
        for b, k in M["dupes"]:
            lines.append(f"- ×{k}:{b[:160]}")
        lines.append("")

    order = "最多点赞" if args.sample == "helpful" else "最新"
    lines.append(f"## 负面评论样本(差评 {len(negatives)} 条,按{order}展示前 {min(args.neg, len(negatives))})")
    lines.append("")
    for r in negatives[:args.neg]:
        lines.append(fmt(r))
    lines.append("")
    lines.append(f"## 正面评论样本(好评 {len(positives)} 条,按{order}展示前 {min(args.pos, len(positives))})")
    lines.append("")
    for r in positives[:args.pos]:
        lines.append(fmt(r))
    lines.append("")
    req_pct = 100 * len(requests_) / len(reviews) if reviews else 0
    lines.append(f"## 新需求候选(含建议/愿望信号词 {len(requests_)} 条,占 {req_pct:.1f}%,展示前 {min(args.neg, len(requests_))})")
    lines.append("")
    lines.append("> 这些是带「希望/能不能/建议/加个…」的评论,是新需求的原料。具体归纳成几条需求点由助手完成。")
    lines.append("")
    for r in requests_[:args.neg]:
        lines.append(fmt(r))
    lines.append("")
    lines.append("## 三类洞察:高频吐槽 / 高频表扬 / 新需求(由助手归纳)")
    lines.append("")
    lines.append("> 阅读上面三个样本桶,填写:")
    lines.append("> - **高频吐槽**:3-6 条反复出现的不满主题,每条配代表原话 + 粗略频次/占比")
    lines.append("> - **高频表扬**:2-4 条用户最买账的点(留存/付费的理由)")
    lines.append("> - **新需求洞察**:3-5 条用户主动提的功能/内容诉求,标注呼声强度,挑出值得做的")
    lines.append("")

    report = "\n".join(lines)
    print(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n[saved report -> {args.out}]", file=sys.stderr)


if __name__ == "__main__":
    main()
