#!/usr/bin/env bash
# CleanYourPhone — 应用清理列表(等价于 phone.py apply)
# 用法: tools/disable.sh <列表.txt> [--dry-run] [--yes]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "[错误] 未找到 python3, 请先安装 Python 3.8+"
  exit 1
fi
exec "$PY" -I "$SCRIPT_DIR/phone.py" apply "$@"
