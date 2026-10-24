#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成"可冻结预装清单" rules/freeze-packages.json 与 examples/freeze-recommended.txt。

数据来源(优先级从高到低):
  1. tools/freeze-curated.tsv   手工分级(safe/recommended/caution)与冻结影响
  2. examples/*/debloat.txt     本项目 14 个品牌清单里的 disable 条目(已过安全规则)
  3. rules/known-packages.json  互联网聚合知识库(UAD-NG 等): OEM 预装 + 推荐级

冻结语义参考:
  * Hail(aistra0528/Hail): 冻结三态 disable/hide/suspend, 解冻必须用同一模式;
    恢复: pm enable / pm unsuspend
  * FreezeYou(FreezeYou/FreezeYou): 手动/计划任务冻结, 省电流畅

自动分级规则(仅对来源 3 生效, 来源 1/2 以人工分级为准):
  * UAD 推荐级 Recommended + 命中广告/统计/遥测关键词        -> safe
  * UAD 推荐级 Recommended + 命中功能类关键词               -> caution
  * UAD 推荐级 Recommended + 其他                           -> recommended
  * UAD 推荐级 Advanced(可能影响功能)                       -> caution
  * 一律排除: Expert/Unsafe 级, DENY/PROTECTED, 谨慎名单,
    非本项目覆盖品牌(Google/AOSP/LG/Sony/Asus/Alcatel 等)

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
KNOWN_DB = ROOT / "rules" / "known-packages.json"

sys.path.insert(0, str(ROOT / "tools"))
import phone  # noqa: E402  复用安全规则(DENY/PROTECTED/谨慎名单), 保证与运行时一致

BRAND_OF_DIR = {
    "xiaomi-hyperos": "xiaomi", "oppo-coloros": "oppo", "oneplus-coloros": "oppo",
    "realme-ui": "oppo", "vivo-originos": "vivo", "huawei-harmonyos": "huawei",
    "honor-magicos": "honor", "samsung-oneui-cn": "samsung", "zte-nubia": "zte",
    "moto-myiui": "moto", "lenovo-zui": "lenovo", "transsion-hios": "transsion",
    "meizu-flyme": "meizu", "universal": "universal",
}
LINE_RE = re.compile(r"^([A-Za-z][\w.]*)\s+disable\s*(\[[^\]]*\])?\s*(?:#\s?(.*))?$")

# 命名空间 -> 品牌(与 phone.py 的 VENDOR_NS 对齐, 只收本项目覆盖的国产/支持品牌)
BRAND_NS = (
    ("com.miui.", "xiaomi"), ("com.xiaomi.", "xiaomi"), ("com.mi.", "xiaomi"),
    ("com.blackshark.", "xiaomi"),
    ("com.oppo.", "oppo"), ("com.coloros.", "oppo"), ("com.heytap.", "oppo"),
    ("com.oplus.", "oppo"), ("com.nearme.", "oppo"), ("com.realme.", "oppo"),
    ("com.oneplus.", "oppo"),
    ("com.vivo.", "vivo"), ("com.bbk.", "vivo"), ("com.iqoo.", "vivo"),
    ("com.huawei.", "huawei"),
    ("com.hihonor.", "honor"),
    ("com.samsung.", "samsung"), ("com.sec.", "samsung"),
    ("cn.nubia.", "zte"), ("com.zte.", "zte"), ("com.redmagic.", "zte"),
    ("com.motorola.", "moto"),
    ("com.lenovo.", "lenovo"), ("com.zui.", "lenovo"),
    ("com.transsion.", "transsion"), ("com.tecno.", "transsion"),
    ("com.infinix.", "transsion"), ("com.itel.", "transsion"),
    ("com.meizu.", "meizu"), ("com.flyme.", "meizu"),
)

# 自动分级关键词 -> (分级, 中文影响说明)。按顺序匹配, 先命中先生效。
# 与 phone.py 的 HEURISTIC_RULES/SERVICE_HINTS 关键词保持一致。
# 匹配方式: 把包名按 "." 拆成段, 段等于/开头/结尾命中关键词才算
# (避免 "networkstate" 被 "stat" 误伤, "dialog" 被 "log" 误伤)
IMPACT_RULES = (
    # --- safe: 纯广告/统计/遥测/日志/测试, 冻结后几乎无感知 ---
    (("analytics", "statistics", "statistic", "mab", "imonitor", "onetrack",
      "onetrace", "logkit", "bugreport", "telemetry", "crashbox", "diagnos",
      "collect", "tracker", "tracking", "reporter", "logsystem", "logs",
      "logger", "logcore", "logupload", "stats", "datacollection",
      "usagestats", "feedback", "test", "agingtest", "factorytest",
      "factory", "demomode", "factorymode", "behaviordetection", "errorreport"),
     "safe", "统计/遥测/日志上报, 冻结后几乎无感知"),
    (("systemadsolution", "adservice", "adservices", "advert", "promotion",
      "splash", "asservice", "msa", "adhub", "adsservice", "dsp", "spage",
      "mipicks", "contentextension", "adplatform", "adsdk", "advertise",
      "adcenter", "adssetting"),
     "safe", "广告/推广服务, 冻结后几乎无感知"),
    # --- recommended: 推送通道/内容预装/负一屏, 影响明确 ---
    (("push", "mcs", "messagecenter"),
     "recommended", "推送通道, 冻结后第三方应用可能收不到推送"),
    (("magazine", "lockscreen", "pictorial", "livecontent",
      "livewallpaper", "alwaysondisplay", "aod"),
     "recommended", "锁屏杂志/常亮显示类内容, 冻结后对应内容不再更新"),
    (("personalassistant", "quicksearchbox", "searchbox", "hiboard", "assistant",
      "tips", "recommend", "feed", "reader", "news", "informationflow"),
     "recommended", "负一屏/资讯/推荐入口, 冻结后该页面不再有内容"),
    (("video", "music", "browser", "reader", "game", "mall", "shop", "store",
      "theme", "weather", "widget", "photoframe", "gallery", "camera",
      "scanner", "notes", "notepad", "calculator", "clock", "calendar",
      "email", "contacts", "dialer", "filemanager", "cleaner", "security",
      "battery", "powersave", "facewake", "faceunlock", "faceid",
      "fingerprint", "biometric", "applock", "antivirus", "securitycore",
      "securitycenter", "safecenter", "doubleapp", "apptimelock", "kidsmode",
      "paymentguard", "download", "downloader", "gps", "location"),
     "caution", "预装应用/工具, 冻结后该功能不可用(数据保留, 可随时解冻)"),
)
DEFAULT_TIER = "recommended"
DEFAULT_IMPACT = "预装组件, 冻结后对应功能不可用(数据保留, 可随时解冻)"

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


def brand_of_pkg(pkg: str):
    for ns, brand in BRAND_NS:
        if pkg.startswith(ns):
            return brand
    return None


def _seg_hit(pkg: str, keys) -> bool:
    """按段匹配: 包名拆成段后, 段等于/开头/结尾命中关键词即算。

    避免子串误伤: networkstate 不含独立 "stat" 段, dialog 不以 "log" 结尾。
    """
    segs = pkg.lower().split(".")
    for k in keys:
        kl = k.lower()
        for s in segs:
            if s == kl or s.startswith(kl) or s.endswith(kl):
                return True
    return False


def auto_tier(pkg: str, uad_level: str):
    """按关键词给知识库包自动分级, 返回 (tier, impact)。"""
    if uad_level == "Advanced":
        return "caution", "UAD 标记为 Advanced(卸载可能影响功能), 冻结同样会关掉相关能力"
    for keys, tier, impact in IMPACT_RULES:
        if _seg_hit(pkg, keys):
            return tier, impact
    return DEFAULT_TIER, DEFAULT_IMPACT


def load_knowledge_base():
    """rules/known-packages.json 中可冻结的 OEM 预装(过安全规则 + 品牌过滤)。"""
    if not KNOWN_DB.is_file():
        print(f"[提示] {KNOWN_DB} 不存在, 跳过知识库来源(可跑 tools/harvest.py 生成)")
        return {}
    data = json.loads(KNOWN_DB.read_text(encoding="utf-8"))
    pk = data.get("packages", {})
    never = NEVER_FREEZE["patterns"]
    out = {}
    stats = {"skip_level": 0, "skip_deny": 0, "skip_caution": 0,
             "skip_brand": 0, "skip_never": 0}
    for pkg, v in pk.items():
        if not isinstance(v, dict):
            continue
        if v.get("l") != "Oem":
            continue
        level = v.get("r")
        if level not in ("Recommended", "Advanced"):
            stats["skip_level"] += 1
            continue
        if phone.is_denied(pkg):
            stats["skip_deny"] += 1
            continue
        if phone.caution_reason(pkg):
            stats["skip_caution"] += 1
            continue
        if any(p and p in pkg for p in never):
            stats["skip_never"] += 1
            continue
        brand = brand_of_pkg(pkg)
        if not brand:
            stats["skip_brand"] += 1
            continue
        tier, impact = auto_tier(pkg, level)
        out[pkg] = {"brands": {brand}, "tier": tier, "impact": impact,
                    "reason": "", "desc": (v.get("d") or "")[:120],
                    "level": level}
    return out, stats


def main():
    curated = load_curated()
    examples = load_examples()
    kb, kb_stats = load_knowledge_base()

    # 覆盖度校验: 品牌清单(人工维护)必须在 curated 表里有分级; curated 不能有孤儿
    missing = sorted(set(examples) - set(curated))
    unknown = sorted(set(curated) - set(examples))
    if missing or unknown:
        for p in missing:
            print(f"[缺分级] {p} 出现在品牌清单但 freeze-curated.tsv 没有分级")
        for p in unknown:
            print(f"[多余]   {p} 在 freeze-curated.tsv 但品牌清单里没有")
        raise SystemExit("覆盖度校验失败: 请同步 tools/freeze-curated.tsv")

    packages = {}
    # 来源 2: 品牌清单(人工分级优先)
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
    # 来源 3: 知识库自动分级(不与来源 2 重复)
    for pkg, rec in kb.items():
        if pkg in packages:
            continue
        entry = {
            "b": sorted(rec["brands"]),
            "t": rec["tier"],
            "r": rec["reason"] or rec["tier"],
            "i": rec["impact"],
            "s": ["uad-ng", "hail", "freezeyou"],
        }
        if rec.get("desc"):
            entry["d"] = rec["desc"]
        if rec.get("level"):
            entry["u"] = rec["level"]
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
                {"id": "cleanyourphone", "note": "本项目 14 个品牌 debloat 清单中的 disable 条目(人工分级)"},
                {"id": "uad-ng", "note": "UAD-NG 社区数据库: OEM 预装 + Recommended/Advanced 级, "
                                         "按关键词自动分级(见 build_freeze_db.py 的 IMPACT_RULES)"},
                {"id": "hail", "note": "aistra0528/Hail: 冻结三态与工作模式矩阵; 解冻必须用同一模式; "
                                        "恢复用 pm enable / pm unsuspend"},
                {"id": "freezeyou", "note": "FreezeYou/FreezeYou: 手动/计划任务冻结, 省电流畅"},
            ],
            "auto_tier_rules": "知识库来源: Recommended+广告/统计关键词=safe; Recommended+推送/内容/"
                               "资讯=recommended; Recommended+功能类关键词=caution; Advanced=caution; "
                               "其他=recommended。品牌清单与 freeze-curated.tsv 始终以人工分级为准",
            "warnings": [
                "冻结不是删除: 图标与数据都还在, 随时可恢复",
                "解冻必须用同一模式: disable 冻结的用 pm enable, suspend 挂起的用 pm unsuspend",
                "suspend 只挡住用户交互, 不阻止后台运行; 要彻底停后台用 disable",
                "冻结推送通道(如 com.heytap.push)会导致第三方应用收不到推送",
                "知识库自动分级的条目未经真机验证, caution 级务必先读影响说明",
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
        "# 数据来源: 14 个品牌 debloat 清单 + UAD-NG 知识库(自动分级)",
        "# 用法: python3 tools/phone.py freeze --tier safe   # 或 apply 本文件",
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
        print(f"[OK] 知识库筛选: 跳过 级别不符 {kb_stats['skip_level']} / "
              f"DENY {kb_stats['skip_deny']} / 谨慎名单 {kb_stats['skip_caution']} / "
              f"never_freeze {kb_stats['skip_never']} / "
              f"非覆盖品牌 {kb_stats['skip_brand']}")
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
