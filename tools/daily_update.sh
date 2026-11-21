#!/usr/bin/env bash
# AI 晨报播客每日更新：跨机器幂等补跑版
# 触发：每天 8:30 正常任务；以及任意已登录 WorkBuddy 账号的机器上线后的每小时补跑检查
# 原则：GitHub main 上当天 audio/YYYY-MM-DD/manifest.json 是“已完成”的唯一事实源
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORK=$(cd "$SCRIPT_DIR/.." && pwd)
GEN="$SCRIPT_DIR/gen_audio.py"
LIVE="$WORK/ai-daily-live"
REPO="git@github.com:Anywise666/ai-news-dashboard.git"
RAW_BASE="https://raw.githubusercontent.com/Anywise666/ai-news-dashboard/main"

TODAY=$(python -c "from datetime import datetime,timedelta,timezone; print(datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d'))")
LOCAL_MANIFEST="$LIVE/audio/$TODAY/manifest.json"
LOCK_BRANCH="automation-lock/$TODAY"
LOCK_ACQUIRED=0
TMP=""

echo "=== AI 晨报播客幂等更新: $TODAY ==="

cleanup() {
  if [ "$LOCK_ACQUIRED" = "1" ] && [ -n "$TMP" ]; then
    (cd "$TMP" && git push -q origin --delete "$LOCK_BRANCH" >/dev/null 2>&1) || true
  fi
  if [ -n "$TMP" ]; then
    rm -rf "$TMP"
  fi
}
trap cleanup EXIT

py_remote_raw_has_manifest() {
  python - "$RAW_BASE/audio/$TODAY/manifest.json" <<'PY'
import sys, urllib.request
url = sys.argv[1]
req = urllib.request.Request(url, headers={
    "User-Agent": "ai-news-dashboard-catchup/1.0",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
})
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        head = r.read(4096).decode("utf-8", "ignore")
    sys.exit(0 if '"items"' in head else 1)
except Exception:
    sys.exit(1)
PY
}

py_local_manifest_valid() {
  python - "$LOCAL_MANIFEST" <<'PY'
import json, sys
try:
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("items") or {}
    ok = sum(1 for v in items.values() if isinstance(v, dict) and (v.get("zh") or v.get("en")))
    sys.exit(0 if ok > 0 else 1)
except Exception:
    sys.exit(1)
PY
}

py_lock_stale() {
  python - "$1" <<'PY'
import sys, time
try:
    ts = int((sys.argv[1] or "").strip())
except Exception:
    sys.exit(1)
sys.exit(0 if int(time.time()) - ts > 7200 else 1)
PY
}

# 1) 先用公开 raw 快速判断；网络失败不阻断，后续用 git 状态复核
if py_remote_raw_has_manifest; then
  echo "ALREADY_DONE_REMOTE_RAW audio/$TODAY/manifest.json"
  exit 0
fi

echo "[1/5] 克隆仓库..."
TMP=$(mktemp -d "$WORK/.git-podcast-auto-XXXXXX")
GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new" \
  git -c credential.helper= clone -q "$REPO" "$TMP"
cd "$TMP"
git config user.name "Anywise666"
git config user.email "58287214@qq.com"

# 2) 以 main 分支当日 manifest 为准复核；避免 raw CDN 缓存误判
if git cat-file -e "origin/main:audio/$TODAY/manifest.json" 2>/dev/null; then
  echo "ALREADY_DONE_REMOTE_GIT audio/$TODAY/manifest.json"
  exit 0
fi

echo "[2/5] 获取跨机器补跑锁: $LOCK_BRANCH"
if git ls-remote --exit-code --heads origin "$LOCK_BRANCH" >/dev/null 2>&1; then
  git fetch -q origin "$LOCK_BRANCH" || true
  LOCK_TS=$(git show "FETCH_HEAD:LOCK_TIMESTAMP" 2>/dev/null | tr -d '\r\n' || true)
  if [ -n "$LOCK_TS" ] && py_lock_stale "$LOCK_TS"; then
    echo "  发现过期锁，尝试接管"
    git checkout -q --orphan "$LOCK_BRANCH"
    git rm -rf . >/dev/null 2>&1 || true
    python - <<'PY'
import time
open("LOCK_TIMESTAMP", "w", encoding="utf-8").write(str(int(time.time())))
PY
    printf "%s %s\n" "${HOSTNAME:-unknown}" "$$" > LOCK_OWNER
    git add LOCK_TIMESTAMP LOCK_OWNER
    git commit -q -m "catchup lock $TODAY"
    if ! git push -q -f origin "HEAD:refs/heads/$LOCK_BRANCH"; then
      echo "REMOTE_LOCK_SKIP 其他机器已接管锁"
      exit 0
    fi
    LOCK_ACQUIRED=1
  else
    echo "REMOTE_LOCK_SKIP 其他机器正在补跑，本次跳过"
    exit 0
  fi
else
  git checkout -q --orphan "$LOCK_BRANCH"
  git rm -rf . >/dev/null 2>&1 || true
  python - <<'PY'
import time
open("LOCK_TIMESTAMP", "w", encoding="utf-8").write(str(int(time.time())))
PY
  printf "%s %s\n" "${HOSTNAME:-unknown}" "$$" > LOCK_OWNER
  git add LOCK_TIMESTAMP LOCK_OWNER
  git commit -q -m "catchup lock $TODAY"
  if ! git push -q origin "HEAD:refs/heads/$LOCK_BRANCH"; then
    echo "REMOTE_LOCK_SKIP 其他机器先拿到锁，本次跳过"
    exit 0
  fi
  LOCK_ACQUIRED=1
fi

# 3) 拿到锁后切回 main，并再次确认远端没有完成
git checkout -q -f main
git fetch -q origin main
if git cat-file -e "origin/main:audio/$TODAY/manifest.json" 2>/dev/null; then
  echo "ALREADY_DONE_REMOTE_AFTER_LOCK audio/$TODAY/manifest.json"
  exit 0
fi
git reset --hard --quiet origin/main

# 4) 本地生成或复用今日音频
echo "[3/5] 准备今日音频..."
if py_local_manifest_valid; then
  echo "  复用本地已有 manifest: $LOCAL_MANIFEST"
else
  echo "  调用 gen_audio.py 生成..."
  python "$GEN" "$TODAY"
fi

if ! py_local_manifest_valid; then
  echo "NO_REPORT_SKIP 当天日报未生成或音频生成失败，跳过推送"
  exit 0
fi

# 5) 拷贝并提交推送
echo "[4/5] 拷贝页面与音频..."
cp "$LIVE/index.html" "$TMP/index.html"
mkdir -p "$TMP/audio"
cp -r "$LIVE/audio/." "$TMP/audio/"

cd "$TMP"
git add -A
if git diff --cached --quiet; then
  echo "NO_CHANGES_SKIP 无变更"
  exit 0
fi
git commit -q -m "Daily podcast audio: $TODAY"

echo "[5/5] 推送..."
if GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=15" git -c credential.helper= push -q origin main; then
  echo "PUSH_OK"
  echo "DONE date=$TODAY"
  exit 0
fi

echo "  推送失败，检查远端是否已被其他机器更新..."
git fetch -q origin main || true
if git cat-file -e "origin/main:audio/$TODAY/manifest.json" 2>/dev/null; then
  echo "ANOTHER_MACHINE_DONE 远端已有今日 manifest，本次跳过"
  exit 0
fi

echo "  尝试 rebase 后重试..."
git rebase origin/main
if GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=15" git -c credential.helper= push -q origin main; then
  echo "PUSH_OK_AFTER_REBASE"
  echo "DONE date=$TODAY"
  exit 0
fi

echo "PUSH_FAILED 推送失败，请检查 SSH/GitHub 状态"
exit 1
