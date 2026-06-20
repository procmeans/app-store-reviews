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
import json
import sys
from collections import Counter, defaultdict


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


def main():
    ap = argparse.ArgumentParser(description="Analyze scraped App Store reviews")
    ap.add_argument("json_file", help="Path to reviews JSON from fetch_reviews.py")
    ap.add_argument("--neg", type=int, default=12, help="How many negative samples (rating<=2)")
    ap.add_argument("--pos", type=int, default=6, help="How many positive samples (rating>=4)")
    ap.add_argument("--out", help="Write Markdown to this file (also prints to stdout)")
    args = ap.parse_args()

    meta, reviews = load_reviews(args.json_file)
    if not reviews:
        print("No reviews found in file.", file=sys.stderr)
        sys.exit(1)

    ratings = [to_int(r.get("rating")) for r in reviews]
    valid = [x for x in ratings if 1 <= x <= 5]
    avg = sum(valid) / len(valid) if valid else 0
    dist = Counter(valid)
    by_country = Counter(r.get("country", "?") for r in reviews)

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
        head = f"- **{'★'*rt}** [{r.get('country','?')}/{r.get('app_version','?')}] "
        t = (r.get("title") or "").strip()
        c = (r.get("content") or "").strip().replace("\n", " ")
        return head + (f"**{t}** — " if t else "") + c

    negatives = [r for r in reviews if to_int(r.get("rating")) <= 2]
    positives = [r for r in reviews if to_int(r.get("rating")) >= 4]

    # feature-request candidates: reviews whose text signals a wish/suggestion.
    # This is a quantitative pre-filter — the qualitative grouping of WHAT users
    # want is left to the model reading these, since intent needs comprehension.
    REQ_SIGNALS = ["希望", "能不能", "建议", "要是能", "要是有", "最好能", "最好有",
                   "加个", "加上", "出个", "想要", "为什么不", "为啥不", "求", "期待",
                   "可以加", "增加", "添加", "改进", "什么时候", "盼", "希望能", "能加"]
    def is_request(r):
        t = (r.get("title", "") + " " + r.get("content", ""))
        return any(s in t for s in REQ_SIGNALS)
    requests_ = [r for r in reviews if is_request(r)]

    # Complaint-dimension tally: a keyword floor so common pain axes can't be
    # silently dropped and so frequencies aren't eyeballed. A review can hit
    # several dimensions (overlap is fine — this is a recall aid, not a
    # mutually-exclusive classification). The model still does the semantic
    # grouping; these counts just keep it honest about what's actually frequent.
    DIMENSIONS = {
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
    }
    dim_counts = {}
    for name, kws in DIMENSIONS.items():
        hit = [r for r in reviews if any(k in (r.get("title", "") + r.get("content", "")) for k in kws)]
        neg_hit = [r for r in hit if to_int(r.get("rating")) <= 2]
        dim_counts[name] = (len(hit), len(neg_hit))

    title = meta.get("app_title") or "App"
    app_id = meta.get("app_id", "?")

    lines = []
    lines.append(f"# App Store 评论分析:{title} (id {app_id})")
    lines.append("")
    lines.append(f"- 抓取文字评论数:**{len(reviews)}**　样本平均评分:**{avg:.2f}** / 5")
    lines.append(f"- 国家/地区:" + ", ".join(f"{c} ({n})" for c, n in by_country.most_common()))

    # coverage vs official store ratings, if fetch_reviews saved store_stats
    stats = meta.get("store_stats") or {}
    grand_total = sum((s.get("total_ratings") or 0) for s in stats.values())
    if grand_total:
        pct = 100 * len(reviews) / grand_total
        per = "，".join(
            f"{c} 官方均分 {s.get('avg_rating','?')}（总评分 {s.get('total_ratings'):,}）"
            for c, s in stats.items() if s.get("total_ratings"))
        if pct >= 0.5:
            cov = f"{len(reviews)} / {grand_total:,} ≈ **{pct:.2f}%**"
        else:
            cov = (f"{len(reviews)} / {grand_total:,}，"
                   f"**约每 {round(grand_total/len(reviews)):,} 条评分中抓到 1 条文字评论**")
        lines.append(f"- **官方汇总**:{per}")
        lines.append(f"- **抓取覆盖率**:{cov} "
                     f"（分母为打星总量，非纯文字评论；RSS 每区上限约 500 条文字评论）")
    if meta.get("sort"):
        lines.append(f"- 排序方式:{meta['sort']}　(官方 RSS,每国≤500 条)")
    lines.append("")

    lines.append("## 评分分布")
    lines.append("")
    lines.append("| 星级 | 数量 | 占比 | |")
    lines.append("|---|---|---|---|")
    total = len(valid)
    for star in (5, 4, 3, 2, 1):
        n = dist.get(star, 0)
        pct = (100 * n / total) if total else 0
        lines.append(f"| {'★'*star} | {n} | {pct:.1f}% | `{bar(n, total)}` |")
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
    lines.append("> 一条评论可命中多个维度;这是召回辅助,不是互斥分类。归纳时**频次以此为准、别只凭语感**;每个维度都要回应,哪怕命中低也要说明。")
    lines.append("")
    lines.append("| 吐槽维度 | 命中条数 | 占全样本 | 其中差评(≤2★) |")
    lines.append("|---|---|---|---|")
    for name, (h, nh) in sorted(dim_counts.items(), key=lambda x: -x[1][1]):
        pct = 100 * h / len(reviews) if reviews else 0
        lines.append(f"| {name} | {h} | {pct:.1f}% | {nh} |")
    lines.append("")

    # most recent first (reviews already sorted newest-first from fetch)
    lines.append(f"## 负面评论样本(差评 {len(negatives)} 条,展示前 {min(args.neg, len(negatives))})")
    lines.append("")
    for r in negatives[:args.neg]:
        lines.append(fmt(r))
    lines.append("")
    lines.append(f"## 正面评论样本(好评 {len(positives)} 条,展示前 {min(args.pos, len(positives))})")
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
