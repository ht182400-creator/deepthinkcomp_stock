#!/usr/bin/env bash
# ============================================================
#  DeepThinkCompStock — 周报自动刷新 + 同步 Forgejo
#  1) live_compare.py   : 用最新 TDX 本地行情重算本周信号 + 生成
#                         data/live_compare.json（本周 vs 上周对比）
#  2) build_dashboard.py: 重新渲染 data/dashboard_<信号日>.html
#  3) git commit+push   : 把刷新后的看板同步到 Forgejo (localhost:3000)
#  用法: bash refresh_report.sh
#  说明: 手动运行即刷新并同步；原 WorkBuddy 定时任务已取消。
#  凭据: 设环境变量 FJ_PUSH_URL=http://user:pass@localhost:3000/ht182400/deepthinkcomp_stock.git
#        否则回退到 git remote 'forgejo'（需已配置 credential helper）。
# ============================================================
set -e

STRAT_DIR="E:/AI_Studio/deepthinkcomp_stock/modules/strategy"
PROJ_DIR="E:/AI_Studio/deepthinkcomp_stock"
PY="/c/Users/ht182/.workbuddy/binaries/python/versions/3.13.12/python.exe"

if [ ! -x "$PY" ]; then
  PY="python3"
fi

echo "[refresh_report] start $(date '+%Y-%m-%d %H:%M:%S')"
cd "$STRAT_DIR"

echo "[1/3] live_compare.py (重算信号 + 生成对比 JSON) ..."
"$PY" live_compare.py

echo "[2/3] build_dashboard.py (重渲染 HTML 看板) ..."
"$PY" build_dashboard.py

echo "[3/3] git commit + push to Forgejo (localhost:3000) ..."
cd "$PROJ_DIR"
if [ -n "$FJ_PUSH_URL" ]; then
  PUSH_DEST="$FJ_PUSH_URL"
else
  PUSH_DEST="forgejo"
fi
git add -A
git commit -m "auto: refresh weekly dashboard $(date '+%Y%m%d %H:%M')" || echo "  (no changes to commit)"
git push "$PUSH_DEST" main 2>&1 | tail -8

echo "[refresh_report] done $(date '+%Y-%m-%d %H:%M:%S')"
