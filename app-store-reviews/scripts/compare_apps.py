#!/usr/bin/env python3
"""Cross-competitor matrix: one row per app, one column per complaint / praise axis.

Runs the same metrics as analyze_reviews.py on every app and lays them side by
side, which is what the competitor-comparison report's "全赛道通病" table needs:
which pains are category-wide (high in most rows) and which are one app's own
self-inflicted wound. Several files can be pooled per app (iOS + Play).

Usage:
  python compare_apps.py --dims game-en \\
      brave=data/brave_ios.json,data/brave_gp.json \\
      magiclab=data/magiclab_gp.json  ... --out output/matrix.md
Cells are the share of that app's reviews hitting the axis; bold = ≥15% (the
report's completeness check threshold), `·` = fewer than 3 hits.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_reviews import PRESETS, compute, load_reviews, resolve_preset  # noqa: E402

SHORT = {  # compact column headers for the wide matrix
    "ads: frequency/interruption": "ads freq", "ads: paid removal not honored": "no-ads IAP",
    "ads: forced/unskippable/redirect": "forced ad", "ads: misleading (ad ≠ game)": "fake ad",
    "physics/fairness": "physics", "difficulty/luck": "diff/luck", "levels/goals": "levels",
    "repetitive/no progression": "repetitive", "boosters/power-ups": "boosters",
    "lives/energy/waiting": "lives", "monetization/price": "price", "cosmetics/collection":
    "cosmetic", "leaderboard/social": "social", "audio": "audio", "offline/connectivity":
    "offline", "crash/lag/battery": "crash", "data loss/sync": "data loss", "controls/ux":
    "controls", "readability/visual": "visual",
}


def cell(d, bold_at=0.15):
    if d["hits"] < 3:
        return "·"
    v = f"{100 * d['share']:.0f}%"
    return f"**{v}**" if d["share"] >= bold_at else v


def main():
    ap = argparse.ArgumentParser(description="Compare review metrics across apps")
    ap.add_argument("apps", nargs="+", help="alias=file.json[,file2.json]")
    ap.add_argument("--dims", default="game-en", help="Preset(s): " + ", ".join(sorted(PRESETS)))
    ap.add_argument("--min", type=int, default=15, help="Skip apps with fewer reviews")
    ap.add_argument("--out", help="Markdown output path")
    ap.add_argument("--json", help="Also dump the numbers as JSON here")
    args = ap.parse_args()
    preset = resolve_preset(args.dims)

    table = []
    for spec in args.apps:
        alias, _, files = spec.partition("=")
        reviews, meta = [], {}
        for path in files.split(","):
            if not os.path.exists(path):
                continue
            m, rv = load_reviews(path)
            store = m.get("store", "ios")
            for r in rv:
                r.setdefault("store", store)
            reviews += rv
            meta.setdefault("title", m.get("app_title"))
            for c, s in (m.get("store_stats") or {}).items():
                if s.get("total_ratings"):
                    meta.setdefault("official", {})[f"{'GP' if store == 'gplay' else 'iOS'}/{c}"] = s
        if len(reviews) < args.min:
            print(f"skip {alias}: {len(reviews)} reviews", file=sys.stderr)
            continue
        M = compute(reviews, preset)
        off = meta.get("official", {})
        tot = sum(s["total_ratings"] for s in off.values())
        oavg = (sum(s["avg_rating"] * s["total_ratings"] for s in off.values()) / tot) if tot else None
        recent = [x for x in M["months"][:3]]
        ravg = (sum(k * a for _, k, a, _ in recent) / sum(k for _, k, _, _ in recent)) if recent else None
        table.append({"alias": alias, "title": meta.get("title") or alias, "M": M,
                      "official_avg": oavg, "official_ratings": tot, "recent3_avg": ravg})

    table.sort(key=lambda t: -t["M"]["avg"])
    dims = list(preset["dimensions"])
    praise = list(preset.get("praise", {}))
    L = ["# 竞品评论矩阵", "",
         f"- App 数:{len(table)};预设:{args.dims};格子 = 命中该维度的评论占比,**粗体 ≥15%**,`·` = 命中 <3 条",
         "- 样本均分受抓取口径影响(Play 'relevant' 排序与 App Store 网页精选都偏向长评/差评),"
         "跨 app 比相对位置,不比绝对值", "",
         "## 一、口碑总览", "",
         "| App | 样本 | 商店 | 样本均分 | 差评率 | 近 3 个月均分 | 官方均分 | 官方评分数 | 开发者回复率(差评) | 跨度 |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for t in table:
        M = t["M"]
        stores = "+".join(sorted({"GP" if s == "gplay" else "iOS" for s in M["by_store"]}))
        dr = f"{100 * M['dev_reply']['low']:.0f}%" if "dev_reply" in M else "–"
        oa = f"{t['official_avg']:.2f}" if t["official_avg"] else "–"
        ra = f"{t['recent3_avg']:.2f}" if t["recent3_avg"] else "–"
        L.append(f"| {t['title'][:34]} | {M['n']} | {stores} | {M['avg']:.2f} | "
                 f"{100 * M['low_share']:.0f}% | {ra} | {oa} | {t['official_ratings']:,} | {dr} | "
                 f"{M['first'][:7]}→{M['latest'][:7]} |")
    L += ["", "## 二、吐槽维度矩阵(占该 app 全部评论)", "",
          "| App | " + " | ".join(SHORT.get(d, d) for d in dims) + " |",
          "|---|" + "---|" * len(dims)]
    for t in table:
        L.append(f"| {t['alias']} | " + " | ".join(cell(t["M"]["dims"][d]) for d in dims) + " |")
    # category-wide: how many apps have the axis at >= 10%
    L += ["", "**全赛道普遍度**(该维度 ≥10% 的 app 数 / 总数,以及命中评论的平均星级):", ""]
    rows = []
    for d in dims:
        k = sum(1 for t in table if t["M"]["dims"][d]["share"] >= 0.10)
        hits = sum(t["M"]["dims"][d]["hits"] for t in table)
        star = (sum((t["M"]["dims"][d]["avg"] or 0) * t["M"]["dims"][d]["hits"] for t in table)
                / hits) if hits else 0
        rows.append((k, d, hits, star))
    for k, d, hits, star in sorted(rows, reverse=True):
        L.append(f"- {d}: {k}/{len(table)} 个 app ≥10%;共 {hits} 条,命中均分 {star:.2f}")
    if praise:
        L += ["", "## 三、好评理由矩阵(占该 app 的 ≥4★ 评论)", "",
              "| App | " + " | ".join(praise) + " |", "|---|" + "---|" * len(praise)]
        for t in table:
            L.append(f"| {t['alias']} | " + " | ".join(cell(t["M"]["praise"][p]) for p in praise) + " |")
    L += ["", "## 四、各 app 差评高频短语", ""]
    for t in table:
        ph = ", ".join(f"`{g}` {k}" for g, k in t["M"]["neg_phrases"][:12])
        L.append(f"- **{t['alias']}**:{ph or '(样本太少)'}")
    report = "\n".join(L) + "\n"
    print(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report)
    if args.json:
        dump = [{"alias": t["alias"], "title": t["title"], "n": t["M"]["n"], "avg": t["M"]["avg"],
                 "low_share": t["M"]["low_share"], "official_avg": t["official_avg"],
                 "official_ratings": t["official_ratings"], "recent3_avg": t["recent3_avg"],
                 "dims": {d: {k: v for k, v in x.items() if k not in ("ids", "top")}
                          for d, x in t["M"]["dims"].items()},
                 "praise": {d: {k: v for k, v in x.items() if k not in ("ids", "top")}
                            for d, x in t["M"]["praise"].items()}} for t in table]
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(dump, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
