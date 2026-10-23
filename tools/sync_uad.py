#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 UAD-NG 社区数据库同步各品牌清理候选列表。

数据源: Universal Android Debloater Next Generation(UAD-NG)
  https://github.com/Universal-Debloater-Alliance/universal-android-debloater-next-generation

用法:
  python3 -I tools/sync_uad.py            # 同步并生成 examples/<品牌>/uad-recommended.txt
  python3 -I tools/sync_uad.py --force    # 忽略本地缓存, 强制重新下载

说明:
  * 只提取 removal == "Recommended"(推荐停用)的包, 不影响系统核心功能
  * 生成的是"候选"文件, 不会覆盖手工维护的 debloat.txt; 请人工核对后再合并
  * 命中本项目安全规则(桌面/电话/短信/系统 UI 等)的包会被自动过滤, 永不生成
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = ROOT_DIR / "examples"
CACHE_FILE = ROOT_DIR / "tools" / "uad_data_cache.json"
UAD_URL = ("https://raw.githubusercontent.com/Universal-Debloater-Alliance/"
           "universal-android-debloater-next-generation/main/"
           "resources/assets/uad_lists.json")

# 品牌 -> (示例目录, 包名前缀)
BRANDS = {
    "xiaomi-hyperos": ("com.miui.", "com.xiaomi.", "com.mi.", "com.mfashiongallery."),
    "oppo-coloros": ("com.oppo.", "com.coloros.", "com.heytap.", "com.nearme.",
                     "com.realme.", "com.oplus."),
    "vivo-originos": ("com.vivo.", "com.bbk."),
    "honor-magicos": ("com.hihonor.", "com.huawei."),
    "samsung-oneui-cn": ("com.samsung.", "com.sec."),
    "meizu-flyme": ("com.meizu.",),
    "universal": (),  # 通用类单独处理(见下方 UNIVERSAL_HINTS)
}

UNIVERSAL_HINTS = {
    "com.google.android.apps.tachyon": "Google Duo(已停止服务)",
    "com.google.android.videos": "Google TV 影视",
    "com.google.android.music": "YouTube Music",
    "com.google.android.apps.wellbeing": "数字健康",
    "com.google.android.apps.turbo": "设备健康服务",
    "com.google.android.feedback": "Google 反馈",
    "com.google.android.printservice.recommendation": "打印服务推荐",
    "com.google.ar.core": "ARCore",
    "com.google.android.googlequicksearchbox": "Google 应用(信息流含推荐)",
    "com.android.adservices": "Android 广告服务(隐私沙盒)",
}

CATEGORIES = [
    ("1. 核心广告、统计与遥测追踪服务",
     ("analytics", "statistic", "bugreport", "telemetry", "msa", "mcs",
      "onetrack", "habit.analysis", "logkit", "tracking", "imonitor",
      "adservice", "adsolution")),
    ("2. 锁屏画报、壁纸与商业轮播",
     ("magazine", "wallpaper", "lockscreen", "emag", "pictorial", "livecontent")),
    ("3. 负一屏资讯、信息流与自带浏览器推广",
     ("assistant", "hybrid", "browser", "search", "spage", "hiboard", "feed",
      "news", "globalminusscreen", "personalassistant")),
    ("4. 视听娱乐、应用商店与游戏中心推广",
     ("game", "music", "video", "player", "mall", "store", "shop", "reader",
      "space", "yellowpage")),
]
FALLBACK_CAT = "5. 其他推荐停用的系统臃肿组件(UAD Recommended)"

# 与 phone.py 一致的安全规则(避免生成危险条目)
DENY_RE = [re.compile(p) for p in [
    r"(^|\.)launcher($|\.)", r"(^|\.)home($|\.)", r"(^|\.)systemui($|\.)",
    r"(^|\.)settings($|\.)", r"(^|\.)phone($|\.)", r"(^|\.)dialer($|\.)",
    r"(^|\.)telecom($|\.)", r"(^|\.)telephony($|\.)", r"(^|\.)mms($|\.)",
    r"(^|\.)messaging($|\.)", r"(^|\.)contacts($|\.)", r"(^|\.)shell($|\.)",
    r"(^|\.)webview($|\.)", r"(^|\.)nfc($|\.)", r"(^|\.)bluetooth($|\.)",
    r"(^|\.)gms($|\.)", r"(^|\.)keyguard($|\.)", r"(^|\.)vending($|\.)",
    r"(^|\.)gsf($|\.)", r"(^|\.)providers\.telephony($|\.)",
    r"(^|\.)inputmethod($|\.)", r"(^|\.)packageinstaller($|\.)",
    r"(^|\.)permissioncontroller($|\.)", r"(^|\.)keychain($|\.)",
    r"(^|\.)externalstorage($|\.)", r"(^|\.)documentsui($|\.)",
    r"(^|\.)fallback($|\.)", r"(^|\.)setupwizard($|\.)",
    r"(^|\.)networkstack($|\.)", r"(^|\.)printspooler($|\.)",
]]
PROTECTED = {"android", "com.android.settings", "com.android.systemui",
             "com.android.phone", "com.google.android.gms",
             "com.google.android.webview", "com.android.webview",
             "com.android.vending", "com.google.android.gsf"}


def is_safe(pkg: str) -> bool:
    return not (pkg in PROTECTED or any(r.search(pkg) for r in DENY_RE))


def load_uad_data(force: bool = False) -> dict:
    if CACHE_FILE.exists() and not force:
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    print(f"正在从 UAD-NG 仓库下载最新数据...\n  {UAD_URL}")
    req = urllib.request.Request(UAD_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")
    print("数据已缓存到 tools/uad_data_cache.json")
    return data


def categorize(pkg: str, desc: str) -> str:
    low = (pkg + " " + desc).lower()
    for name, keys in CATEGORIES:
        if any(k in low for k in keys):
            return name
    return FALLBACK_CAT


def generate(data: dict) -> int:
    total = 0
    for brand, prefixes in BRANDS.items():
        matched = {}
        for pkg, info in data.items():
            if not isinstance(info, dict):
                continue
            if str(info.get("removal", "")).lower() != "recommended":
                continue
            if not any(pkg.startswith(p) for p in prefixes):
                continue
            if not is_safe(pkg):
                continue
            desc = str(info.get("description", "")).strip().replace("\n", " ")
            matched[pkg] = desc.split(". ")[0][:120]
        for pkg, desc in UNIVERSAL_HINTS.items():
            if brand == "universal" and is_safe(pkg):
                matched.setdefault(pkg, desc)

        out_dir = EXAMPLES_DIR / brand
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "uad-recommended.txt"
        groups = {}
        for pkg in sorted(matched):
            groups.setdefault(categorize(pkg, matched[pkg]), []).append(pkg)
        lines = [
            f"# CleanYourPhone UAD-NG 候选列表 — {brand}",
            "# 来源: Universal Android Debloater Next Generation(Recommended)",
            "# 本文件由 tools/sync_uad.py 自动生成, 是候选清单, 不会覆盖手工维护的 debloat.txt",
            "# 使用前请逐条核对(尤其标注 4/5 类的娱乐应用), 再合并进 debloat.txt",
            "",
        ]
        for cat, _ in CATEGORIES + [(FALLBACK_CAT, ())]:
            if cat not in groups:
                continue
            lines.append(f"# ---------- {cat} ({len(groups[cat])} 项) ----------")
            for pkg in groups[cat]:
                desc = matched[pkg]
                lines.append(f"{pkg} disable  # {desc}" if desc else f"{pkg} disable")
            lines.append("")
        out_file.write_text("\n".join(lines), encoding="utf-8")
        total += len(matched)
        print(f"  [{brand}] {len(matched)} 个候选 -> {out_file.relative_to(ROOT_DIR)}")
    print(f"\n完成, 共 {total} 个候选包。")
    print("提示: 与手工列表对比合并: diff examples/<品牌>/uad-recommended.txt "
          "examples/<品牌>/debloat.txt")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="从 UAD-NG 同步品牌清理候选列表")
    ap.add_argument("--force", action="store_true", help="忽略缓存强制下载")
    args = ap.parse_args()
    try:
        data = load_uad_data(args.force)
    except Exception as e:
        print(f"[错误] 下载 UAD-NG 数据失败: {e}")
        print("请检查网络(需要访问 raw.githubusercontent.com), 或稍后重试。")
        return 2
    if not isinstance(data, dict):
        print("[错误] UAD-NG 数据格式异常(不是以包名为键的对象)。")
        return 2
    return generate(data)


if __name__ == "__main__":
    sys.exit(main())
