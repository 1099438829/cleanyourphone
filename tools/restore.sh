#!/usr/bin/env bash
# CleanYourPhone — 恢复(等价于 phone.py restore)
# 用法: tools/restore.sh <列表.txt> | --all
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "[错误] 未找到 python3, 请先安装 Python 3.8+"
  exit 1
fi
exec "$PY" -I "$SCRIPT_DIR/phone.py" restore "$@"
