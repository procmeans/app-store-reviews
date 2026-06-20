#!/bin/bash
# 定时增量抓取 App Store 评论(官方 RSS + 累积去重)。
# 每个 app 一行:  "应用别名 app_id 国家列表"
# 国家列表用逗号分隔(cn,us,hk...)。脚本会把评论合并进 data/<别名>_master.json,
# 只增不重。配合 launchd/cron 定时运行即可逐步攒齐"从现在起"的全部新评论。

set -euo pipefail
cd "$(dirname "$0")"

PY=$(command -v python3)
FETCH="app-store-reviews/scripts/fetch_reviews.py"
OUTDIR="data"
mkdir -p "$OUTDIR"

# ===== 在这里配置要监控的 app =====
APPS=(
  "naolao 1600837891 cn"     # 奶酪单词(目标)
  "baicizhan 557545298 cn"   # 百词斩
  "momo 888483369 cn"        # 墨墨背单词
  "bubei 698570469 cn"       # 不背单词
  "shanbay 698013609 cn"     # 扇贝单词
  "zhimi 893122685 cn"       # 知米背单词
  "chaoji 6463413369 cn"     # 超级单词表
  "eudic 367278030 cn"       # 欧路词典
  "duolingo 570060128 cn"    # 多邻国
  "youdao 353115739 cn"      # 有道词典
)
# =================================

ts() { date "+%Y-%m-%d %H:%M:%S"; }
echo "[$(ts)] === accumulate run start ==="
for line in "${APPS[@]}"; do
  set -- $line
  alias="$1"; appid="$2"; countries="$3"
  echo "[$(ts)] -> $alias (id=$appid, $countries)"
  "$PY" "$FETCH" --app-id "$appid" --country "$countries" \
      --merge "$OUTDIR/${alias}_master.json" --format both \
      2>&1 | grep -E "累积模式|loaded|error|Warning" || true
done
echo "[$(ts)] === accumulate run done ==="
