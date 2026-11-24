#!/usr/bin/env bash
# AI 晨报播客本机兜底主力：每天检查线上当天音频是否存在，缺失则本地补跑并推送。
# 背景（2026-11-24）：GitHub Actions 云端 schedule 长期不可靠（延迟数小时 / 整日零触发），
#   本机兜底由「最后防线」提前为实际主力，WorkBuddy 定时任务每天北京时间 08:05 调用。
#   数据源 aihot 当日日报约 08:00 就绪，08:05 补跑可守住「早 8:30 上线」初衷。
# 原则：线上 audio/YYYY-MM-DD/brief_zh.mp3 的 HTTP 状态是「当天是否完成」的唯一事实源。
set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORK=$(cd "$SCRIPT_DIR/.." && pwd)
PAGES="https://anywise666.github.io/ai-news-dashboard"
CHECK_URL="$PAGES/audio/TODAY/brief_zh.mp3"

TODAY=$(python -c "from datetime import datetime,timedelta,timezone; print(datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d'))")
CHECK_URL="${CHECK_URL/TODAY/$TODAY}"

echo "=== AI 晨报兜底检查: $TODAY ==="
echo "检查线上音频: $CHECK_URL"

status=$(curl -sL -o /dev/null -w "%{http_code}" --max-time 20 "$CHECK_URL" || echo "000")
echo "HTTP 状态: $status"

if [ "$status" = "200" ]; then
  echo "ALREADY_OK 当天音频已在线，无需补跑"
  exit 0
fi

echo "当天音频缺失，开始本地补跑 ..."
cd "$WORK" || { echo "PUSH_FAILED 无法进入仓库目录"; exit 1; }

# 1) 生成本地音频（edge-tts）
# 数据源当日日报约 08:00 就绪，偶发延迟（几分钟）时首跑会拿到空数据而只生成空目录。
# 以 manifest.json 里是否真的有条目为成功判据，失败则等待重试，避免一次扑空就整天错过。
gen_ok=0
for attempt in 1 2 3 4 5; do
  python "$SCRIPT_DIR/gen_audio.py" "$TODAY"
  if python - "$TODAY" "$WORK" <<'PY' 2>/dev/null
import json, os, sys
date, work = sys.argv[1], sys.argv[2]
m = os.path.join(work, "audio", date, "manifest.json")
try:
    d = json.load(open(m, encoding="utf-8"))
    sys.exit(0 if (d.get("items") and d.get("brief")) else 1)
except Exception:
    sys.exit(1)
PY
  then
    gen_ok=1
    echo "音频生成成功（尝试 $attempt/5）"
    break
  fi
  echo "数据未就绪或生成不完整，等待 90 秒后重试（$attempt/5）..."
  [ "$attempt" -lt 5 ] && sleep 90
done
if [ "$gen_ok" != "1" ]; then
  echo "GEN_FAILED 数据就绪重试 5 次后仍未生成完整音频"
  exit 1
fi
# 2) 重建 RSS feed
python "$SCRIPT_DIR/gen_feed.py" || { echo "FEED_FAILED"; exit 1; }

# 3) 提交并推送（带重试，应对本地代理对 github.com 的间歇性拦截）
git add "audio/$TODAY" feed.xml
if git diff --cached --quiet; then
  echo "NO_CHANGES_SKIP 生成后无变化"
  exit 0
fi
git commit -m "Fallback podcast audio + feed: $TODAY (WorkBuddy local)" >/dev/null 2>&1 || true

pushed=0
for i in 1 2 3 4 5 6; do
  out=$(GIT_HTTP_VERSION=HTTP/1.1 git push origin HEAD:main 2>&1)
  echo "push try $i: $(echo "$out" | tail -1)"
  if echo "$out" | grep -qE "up-to-date|HEAD -> main|main -> main"; then
    pushed=1; break
  fi
done
if [ "$pushed" != "1" ]; then
  echo "PUSH_FAILED 推送未成功，请手动检查"
  exit 1
fi

# 4) 等待 Pages 部署后复核
for i in $(seq 1 12); do
  sleep 5
  s=$(curl -sL -o /dev/null -w "%{http_code}" --max-time 15 "$CHECK_URL" || echo "000")
  echo "复核 $i: HTTP $s"
  if [ "$s" = "200" ]; then
    echo "PUSH_OK 当天音频已上线: $CHECK_URL"
    exit 0
  fi
done
echo "PUSH_OK_PENDING Pages 部署延迟，稍后请手动复核"
exit 0
