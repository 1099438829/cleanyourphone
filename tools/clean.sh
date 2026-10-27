#!/usr/bin/env bash
# CleanYourPhone — 全流程编排(备份 -> 卸载/禁用 -> 设置级去广告 -> 摇一摇封杀)
# 用法:
#   tools/clean.sh                全流程(每步前都会要求确认)
#   tools/clean.sh --backup      仅建立备份快照
#   tools/clean.sh --debloat     仅执行阶段一: 卸载/禁用预装与广告包
#   tools/clean.sh --settings    仅执行阶段二: 写入系统设置(关闭广告/限制追踪)
#   tools/clean.sh --shake       仅执行阶段三: 封杀第三方 App 摇一摇
#   tools/clean.sh --auto        自动清单: 按本机预装匹配互联网知识库后清理
#   tools/clean.sh --adsw        App 内广告开关(热搜/商店推广位/信息流; 需守着手机)
#   tools/clean.sh --dry-run     全流程预演(不执行任何写操作)
#   tools/clean.sh --help        显示帮助
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "[错误] 未找到 python3, 请先安装 Python 3.8+"
  exit 1
fi
PHONE=("$PY" -I "$SCRIPT_DIR/phone.py")

DRY_RUN=()
for arg in "$@"; do
  [ "$arg" = "--dry-run" ] && DRY_RUN=(--dry-run)
done

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi

# 探测品牌并定位规则目录
BRAND_ID=$("${PHONE[@]}" info 2>/dev/null | sed -n 's/^推荐列表: //p' || true)
if [ -z "$BRAND_ID" ] || [ ! -d "$ROOT_DIR/$BRAND_ID" ]; then
  BRAND_ID="examples/universal"
  echo "[提示] 未能识别品牌, 使用通用列表: $BRAND_ID"
fi
DEBLOAT="$ROOT_DIR/$BRAND_ID/debloat.txt"
SETTINGS="$ROOT_DIR/$BRAND_ID/settings.conf"
SHAKE_LIST="$ROOT_DIR/examples/shake_apps.txt"
echo "== 设备规则目录: $BRAND_ID =="

run_backup() { "${PHONE[@]}" backup; }
run_debloat() { "${PHONE[@]}" apply "$DEBLOAT" "${DRY_RUN[@]}"; }
run_settings() { "${PHONE[@]}" settings "$SETTINGS" "${DRY_RUN[@]}"; }
# 自动清单: 预演模式只列清单, 实跑时由 phone.py 内部再确认一次
run_auto() {
  if [ ${#DRY_RUN[@]} -gt 0 ]; then
    "${PHONE[@]}" auto
  else
    "${PHONE[@]}" auto --apply
  fi
}
# shake 无 dry-run 参数, 预演模式下跳过
run_shake() {
  if [ ${#DRY_RUN[@]} -gt 0 ]; then
    echo "[预演] 跳过摇一摇封杀(该阶段无预演模式, 实跑时每项都会先确认)"
  else
    "${PHONE[@]}" shake on "$SHAKE_LIST"
  fi
}

# App 内开关: 需要人守着手机(工具会点屏幕), 所以不放进 all 全流程
run_adsw() {
  if [ ${#DRY_RUN[@]} -gt 0 ]; then
    "${PHONE[@]}" adsw run --dry-run
  else
    echo "[提示] 接下来工具会自己点屏幕: 请保持手机解锁、停在桌面, 期间不要手动操作"
    "${PHONE[@]}" adsw run
  fi
}

case "${1:-all}" in
  --backup)  run_backup ;;
  --debloat) run_debloat ;;
  --settings) run_settings ;;
  --shake)   run_shake ;;
  --auto)    run_auto ;;
  --adsw)    run_adsw ;;
  all)
    run_backup
    run_debloat
    run_settings
    run_shake
    echo ""
    echo "== 全部完成 =="
    echo "还有 App 内广告开关(热搜/商店推广位/信息流)可关: tools/clean.sh --adsw"
    echo "恢复: tools/restore.sh --all 或 python3 tools/phone.py restore --all"
    ;;
  *) echo "未知参数: $1 (查看帮助: tools/clean.sh --help)"; exit 1 ;;
esac
