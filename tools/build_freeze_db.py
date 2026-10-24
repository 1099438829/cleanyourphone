#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成"可冻结预装清单" rules/freeze-packages.json 与 examples/freeze-recommended.txt。

数据来源:
  * tools/freeze-curated.tsv  手工分级(safe/recommended/caution)与冻结影响
  * examples/*/debloat.txt    本项目 14 个品牌清单里的 disable 条目(已过安全规则)

冻结语义参考:
  * Hail(aistra0528/Hail): 冻结三态 disable/hide/suspend, 解冻必须用同一模式;
    恢复: pm enable / pm unsuspend
  * FreezeYou(FreezeYou/FreezeYou): 手动/计划任务冻结, 省电流畅

用法: python3 tools/build_freeze_db.py [--check]
  --check  只校验覆盖度, 不写文件
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TSV = ROOT / "tools" / "freeze-curated.tsv"
OUT_DB = ROOT / "rules" / "freeze-packages.json"
OUT_LIST = ROOT / "examples" / "freeze-recommended.txt"

BRAND_OF_DIR = {
    "xiaomi-hyperos": "xiaomi", "oppo-coloros": "oppo", "oneplus-coloros": "oppo",
    "realme-ui": "oppo", "vivo-originos": "vivo", "huawei-harmonyos": "huawei",
    "honor-magicos": "honor", "samsung-oneui-cn": "samsung", "zte-nubia": "zte",
    "moto-myiui": "moto", "lenovo-zui": "lenovo", "transsion-hios": "transsion",
    "meizu-flyme": "meizu", "universal": "universal",
}
LINE_RE = re.compile(r"^([A-Za-z][\w.]*)\s+disable\s*(\[[^\]]*\])?\s*(?:#\s?(.*))?$")

# 冻结黑名单: 与 phone.py 的 DENY/PROTECTED 对齐, 冻结它们会让手机直接不可用
NEVER_FREEZE = {
    "reason": "冻结这些包会导致桌面/通话/短信/账号同步等核心功能不可用; "
              "与 tools/phone.py 的 DENY_PATTERNS/PROTECTED_PACKAGES 保持同步",
    "patterns": [
        "com.miui.home", "com.android.launcher", "com.hihonor.android.launcher",
        "com.android.systemui", "com.android.settings", "com.android.phone",
        "com.android.dialer", "com.android.incallui", "com.android.telecom",
        "com.android.mms", "com.android.messaging", "com.android.contacts",
        "com.miui.contentprovider", "com.lbe.security.miui",
        "com.xiaomi.account", "com.huawei.hwid", "com.heytap.usercenter",
        "com.bbk.account", "com.oplus.account", "com.zhihu.inputmethod",
        "com.baidu.input", "com.sohu.inputmethod.sogou",
        "com.google.android.gms", "com.google.android.gsf",
    ],
}


def load_curated():
    rows = {}
    for lineno, raw in enumerate(TSV.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            raise SystemExit(f"{TSV}:{lineno}: 需要 3 列(包名/分级/影响): {raw!r}")
        pkg, tier, impact = (p.strip() for p in parts)
        if tier not in ("safe", "recommended", "caution"):
            raise SystemExit(f"{TSV}:{lineno}: 分级必须是 safe/recommended/caution")
        rows[pkg] = {"tier": tier, "impact": impact}
    return rows


def load_examples():
    """examples/*/debloat.txt 中的 disable 条目 -> {pkg: {brand, gate, reason}}"""
    found = {}
    for path in sorted(ROOT.glob("examples/*/debloat.txt")):
        brand = BRAND_OF_DIR.get(path.parent.name, path.parent.name)
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            m = LINE_RE.match(s)
            if not m:
                continue
            pkg, gate, comment = m.groups()
            rec = found.setdefault(pkg, {"brands": set(), "gates": set(), "reason": ""})
            rec["brands"].add(brand)
            if gate:
                rec["gates"].add(gate.strip())
            if comment and not rec["reason"]:
                rec["reason"] = comment.strip()
    return found


def main():
    curated = load_curated()
    examples = load_examples()

    missing = sorted(set(examples) - set(curated))
    unknown = sorted(set(curated) - set(examples))
    if missing or unknown:
        for p in missing:
            print(f"[缺分级] {p} 出现在品牌清单但 freeze-curated.tsv 没有分级")
        for p in unknown:
            print(f"[多余]   {p} 在 freeze-curated.tsv 但品牌清单里没有")
        raise SystemExit("覆盖度校验失败: 请同步 tools/freeze-curated.tsv")

    packages = {}
    for pkg, rec in examples.items():
        cur = curated[pkg]
        entry = {
            "b": sorted(rec["brands"]),
            "t": cur["tier"],
            "r": rec["reason"] or cur["tier"],
            "i": cur["impact"],
            "s": ["cleanyourphone", "hail", "freezeyou"],
        }
        if rec["gates"]:
            entry["v"] = sorted(rec["gates"])
        packages[pkg] = entry

    db = {
        "meta": {
            "name": "CleanYourPhone 可冻结预装清单",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "total": len(packages),
            "concept": "冻结(freeze)= 让应用无法运行但不删除: pm disable-user 后应用消失且不可启动, "
                       "数据与 APK 都保留, pm enable 即恢复",
            "tiers": {
                "safe": "纯广告/统计/遥测/日志/测试组件, 冻结后几乎无感知",
                "recommended": "推荐冻结, 影响明确且可预期(推送通道/内容预装/负一屏等)",
                "caution": "会关掉某个功能, 冻结前先读 i(影响)字段",
            },
            "modes": {
                "disable": "pm disable-user --user 0: 应用从桌面消失, 不可启动(默认)",
                "suspend": "pm suspend --user 0: 图标变灰, 系统弹窗提示已挂起(部分 ROM 禁用被拒时兜底)",
                "hide": "pm hide --user 0: 需要 root 或设备所有者, adb shell 做不到, 本工具不使用",
            },
            "sources": [
                {"id": "hail", "note": "aistra0528/Hail: 冻结三态与工作模式矩阵; 解冻必须用同一模式; "
                                        "恢复用 pm enable / pm unsuspend"},
                {"id": "freezeyou", "note": "FreezeYou/FreezeYou: 手动/计划任务冻结, 省电流畅"},
                {"id": "cleanyourphone", "note": "本项目 14 个品牌 debloat 清单中的 disable 条目"},
            ],
            "warnings": [
                "冻结不是删除: 图标与数据都还在, 随时可恢复",
                "解冻必须用同一模式: disable 冻结的用 pm enable, suspend 挂起的用 pm unsuspend",
                "suspend 只挡住用户交互, 不阻止后台运行; 要彻底停后台用 disable",
                "冻结推送通道(如 com.heytap.push)会导致第三方应用收不到推送",
            ],
        },
        "packages": dict(sorted(packages.items())),
        "never_freeze": NEVER_FREEZE,
    }

    lines = [
        "# CleanYourPhone 推荐冻结清单(可冻结预装)",
        "#",
        "# 冻结 = 应用无法启动但不删除, 数据保留, 随时可恢复",
        "#   disable: 应用从桌面消失, 不可启动(默认)",
        "#   suspend: 图标变灰, 系统提示已挂起(禁用被拒时自动兜底)",
        "# 恢复: python3 tools/phone.py restore --all",
        "# 语义参考 Hail(aistra0528/Hail) 与 FreezeYou(FreezeYou/FreezeYou)",
        "# 用法: python3 tools/phone.py apply examples/freeze-recommended.txt",
        "",
    ]
    for tier, title in (("safe", "safe 几乎无感知"),
                        ("recommended", "recommended 推荐冻结"),
                        ("caution", "caution 冻结前先看影响")):
        rows = [(p, d) for p, d in packages.items() if d["t"] == tier]
        lines.append(f"# ================= {title}({len(rows)}) =================")
        for p, d in rows:
            gates = " ".join(sorted(d.get("v", [])))
            note = f"无感知({d['r']})" if d["i"] == "无感知" and d["r"] else d["i"]
            lines.append(f"{p} freeze{f' {gates}' if gates else ''}  # {note}".rstrip())
        lines.append("")

    if "--check" in sys.argv:
        tiers = {}
        for d in packages.values():
            tiers[d["t"]] = tiers.get(d["t"], 0) + 1
        print(f"[OK] {len(packages)} 个包, 分级: {tiers}")
        return
    OUT_DB.write_text(json.dumps(db, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    OUT_LIST.write_text("\n".join(lines), encoding="utf-8")
    tiers = {}
    for d in packages.values():
        tiers[d["t"]] = tiers.get(d["t"], 0) + 1
    print(f"[写出] {OUT_DB} ({len(packages)} 个包, 分级 {tiers})")
    print(f"[写出] {OUT_LIST}")


if __name__ == "__main__":
    main()
