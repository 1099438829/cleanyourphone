#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CleanYourPhone — 互联网 debloat 数据聚合器

把散落在互联网上的「该卸载哪些预装应用」知识汇总成一份结构化数据库,
供 phone.py auto 在真机上直接匹配预装应用并卸载。

数据源(全部为公开数据, 仅读取, 不上传任何东西):
  1. UAD-NG 结构化库
     Universal Android Debloater Next Generation(5381 个包, 带
     Recommended/Advanced/Expert/Unsafe 风险分级与依赖关系) —— 主力数据源
  2. GitHub 代码搜索
     用 "pm uninstall --user 0" / "pm disable-user" / "debloat" 等关键词
     搜索社区维护的 debloat 列表与教程帖, 自动抓取并解析
  3. Gitee 搜索
     中文社区的「去广告 / 精简 / 预装」仓库
  4. 内置精选源
     已知高质量的仓库列表(见 CURATED)

输出:
  rules/known-packages.json   结构化知识库(供 phone.py auto 读取)
  rules/ALL-BLOAT.txt         人类可读的全量清单(按厂商分组)
  rules/harvest-report.md     抓取报告(来源、数量、失败原因)

用法:
  python3 tools/harvest.py                    # 全量抓取(约 2-5 分钟)
  python3 tools/harvest.py --offline          # 只用本地缓存, 不联网
  python3 tools/harvest.py --max-files 30     # 多抓一些社区列表
  GITHUB_TOKEN=ghp_xxx python3 tools/harvest.py   # 提高 GitHub 配额

设计取舍:
  * 抓取失败绝不中断 —— 每个源独立 try/except, 失败写进报告继续跑
  * raw.githubusercontent.com 在国内常被拦, 内置 ghproxy/jsdelivr 镜像回退
  * 多源同一包按「最保守」原则合并: 任一源标 Unsafe 就保持 Unsafe
  * 命中本项目安全规则(桌面/电话/短信/系统 UI)的包直接丢弃, 永不入库
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
RULES_DIR = ROOT_DIR / "rules"
CACHE_DIR = ROOT_DIR / "tools" / ".cache" / "harvest"
DB_FILE = RULES_DIR / "known-packages.json"
ALL_FILE = RULES_DIR / "ALL-BLOAT.txt"
REPORT_FILE = RULES_DIR / "harvest-report.md"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# ---------------------------------------------------------------------------
# 镜像: raw.githubusercontent.com 在国内经常不可达, 依次回退
# ---------------------------------------------------------------------------
RAW_MIRRORS = (
    "https://ghproxy.net/https://raw.githubusercontent.com/{repo}/{branch}/{path}",
    "https://fastly.jsdelivr.net/gh/{repo}@{branch}/{path}",
    "https://raw.githubusercontent.com/{repo}/{branch}/{path}",
)
API_MIRRORS = (
    "https://api.github.com/{path}",
    "https://ghproxy.net/https://api.github.com/{path}",
)

UAD_REPO = "Universal-Debloater-Alliance/universal-android-debloater-next-generation"
UAD_PATH = "resources/assets/uad_lists.json"
UAD_BRANCH = "main"

# GitHub 代码搜索: 发现社区 debloat 列表与教程帖
SEARCH_QUERIES = (
    '"pm uninstall --user 0" extension:txt',
    '"pm disable-user" extension:txt',
    "debloat in:path extension:txt",
    '"adb shell pm uninstall" extension:md',
    '"pm uninstall --user 0" extension:sh',
    "debloat in:path extension:md",
)

# Gitee 中文社区关键词(API 搜索; 该接口近年常返回空, 失败时如实写进报告)
GITEE_QUERIES = ("debloat", "去广告", "预装应用", "系统精简")

# 内置精选(已知高质量, 直接按树抓取)
CURATED = (
    ("Gathin23/cleanyourtv", "main"),
)

# ---------------------------------------------------------------------------
# 安全规则: 直接复用 phone.py 的那一份, 避免两边正则漂移
#   (harvest 用 -I 运行时脚本目录不会自动进 sys.path, 这里显式补上)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from phone import is_denied as _phone_is_denied  # noqa: E402

    def is_safe(pkg: str) -> bool:
        return not _phone_is_denied(pkg)

    _RULE_SOURCE = "phone.py"
except Exception:  # pragma: no cover - phone.py 缺失时的兜底
    _RULE_SOURCE = "builtin"
    DENY_PATTERNS = (
        r"(^|\.)launcher($|\.)", r"(^|\.)home($|\.)", r"(^|\.)systemui($|\.)",
        r"(^|\.)settings($|\.)", r"(^|\.)setupwizard($|\.)", r"(^|\.)phone($|\.)",
        r"(^|\.)dialer($|\.)", r"(^|\.)incallui($|\.)", r"(^|\.)telecom($|\.)",
        r"(^|\.)telephony($|\.)", r"(^|\.)providers\.telephony($|\.)",
        r"(^|\.)mms($|\.)", r"(^|\.)messaging($|\.)", r"(^|\.)sms($|\.)",
        r"(^|\.)contacts($|\.)", r"(^|\.)providers\.contacts($|\.)",
        r"(^|\.)shell($|\.)", r"(^|\.)packageinstaller($|\.)",
        r"(^|\.)permissioncontroller($|\.)", r"(^|\.)keychain($|\.)",
        r"(^|\.)certinstaller($|\.)", r"(^|\.)webview($|\.)",
        r"(^|\.)externalstorage($|\.)", r"(^|\.)documentsui($|\.)",
        r"(^|\.)fallback($|\.)", r"(^|\.)nfc($|\.)", r"(^|\.)bluetooth($|\.)",
        r"(^|\.)role($|\.)", r"(^|\.)networkstack($|\.)", r"(^|\.)connectivity($|\.)",
        r"(^|\.)printspooler($|\.)", r"(^|\.)gms($|\.)", r"(^|\.)keyguard($|\.)",
        r"(^|\.)wallpaper($|\.)", r"(^|\.)vending($|\.)", r"(^|\.)gsf($|\.)",
        r"(^|\.)ext\.services($|\.)", r"(^|\.)providers\.media($|\.)",
        r"(^|\.)providers\.downloads($|\.)", r"(^|\.)inputmethod($|\.)",
    )
    DENY_RE = [re.compile(p) for p in DENY_PATTERNS]
    PROTECTED = frozenset({
        "android", "com.android.systemui", "com.android.settings",
        "com.android.phone", "com.android.providers.settings",
        "com.android.providers.telephony", "com.android.providers.media",
        "com.android.providers.downloads", "com.android.externalstorage",
        "com.android.documentsui", "com.android.packageinstaller",
        "com.android.permissioncontroller", "com.android.bluetooth",
        "com.android.nfc", "com.android.networkstack", "com.android.shell",
        "com.android.keychain", "com.google.android.gms",
        "com.google.android.gsf", "com.android.vending", "com.android.webview",
        "com.google.android.webview", "com.google.android.ext.services",
    })

    def is_safe(pkg: str) -> bool:
        return pkg not in PROTECTED and not any(r.search(pkg) for r in DENY_RE)


# ---------------------------------------------------------------------------
# 包名识别
# ---------------------------------------------------------------------------
PKG_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")
BAD_PREFIX = ("android.permission", "android.intent", "android.app.",
              "androidx.", "java.", "kotlin.", "org.jetbrains", "dalvik.",
              "android.hardware", "android.media.action", "com.android.intent")
PM_RE = re.compile(
    r"\bpm\s+(?:uninstall|disable-user|disable|suspend)\b[^\n#]*?"
    r"\b([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)")
LIST_RE = re.compile(
    r"^(?P<pkg>[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)"
    r"(?:\s+(?P<action>uninstall|disable|suspend))?"
    r"(?:\s*(?:#|//)\s*(?P<comment>.*))?$")


def valid_pkg(pkg: str) -> bool:
    if len(pkg) > 120 or pkg.count(".") < 1:
        return False
    if pkg.lower().startswith(BAD_PREFIX):
        return False
    if not PKG_RE.match(pkg):
        return False
    # 过滤纯权限/常量类误判
    tail = pkg.rsplit(".", 1)[-1]
    if tail.isupper() or tail in ("action", "extra", "category", "provider"):
        return False
    return True


def extract(text: str, kind: str = "list") -> dict:
    """从文本中提取 {包名: {"action":..., "comment":...}}。

    kind="list": 允许裸包名(社区 debloat.txt 的常见写法)
    kind="post": 只认带 pm uninstall / pm disable 的行(避免教程里提到的
                 普通包名被误当成清理项)
    """
    found: dict = {}
    for raw in text.splitlines():
        line = raw.strip().strip("`").strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if kind == "post":
            m = PM_RE.search(line)
            if not m:
                continue
            pkg = m.group(1)
            action = "disable" if "disable" in line or "suspend" in line else "uninstall"
            if valid_pkg(pkg):
                found.setdefault(pkg, {"action": action, "comment": ""})
            continue
        # 去掉行首常见的 adb shell / $ / > 前缀
        body = re.sub(r"^(?:\$\s*|>\s*)?(?:adb\s+shell\s+)?", "", line, flags=re.I)
        m = LIST_RE.match(body)
        if m:
            pkg = m.group("pkg")
            if valid_pkg(pkg):
                found.setdefault(pkg, {
                    "action": m.group("action") or "uninstall",
                    "comment": (m.group("comment") or "").strip(),
                })
            continue
        m = PM_RE.search(line)
        if m:
            pkg = m.group(1)
            if valid_pkg(pkg):
                action = ("disable" if "disable" in line or "suspend" in line
                          else "uninstall")
                found.setdefault(pkg, {"action": action, "comment": ""})
    return found


# ---------------------------------------------------------------------------
# 网络
# ---------------------------------------------------------------------------
class Net:
    def __init__(self, token: str = "", offline: bool = False, timeout: int = 30):
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.offline = offline
        self.timeout = timeout
        self.failures: list = []
        self.requests = 0

    def _get(self, url: str, use_api: bool = False) -> bytes:
        if self.offline:
            raise RuntimeError("offline 模式不联网")
        headers = {"User-Agent": UA, "Accept-Encoding": "gzip"}
        if use_api:
            headers["Accept"] = "application/vnd.github+json"
            if self.token:
                headers["Authorization"] = f"token {self.token}"
        req = urllib.request.Request(url, headers=headers)
        self.requests += 1
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            return data

    def get_text(self, url: str, use_api: bool = False) -> str:
        return self._get(url, use_api).decode("utf-8", errors="replace")

    def github_file(self, repo: str, path: str, branch: str = "main",
                    cache_key: str = "") -> str:
        key = cache_key or f"{repo}@{branch}/{path}"
        cached = _cache_path(key)
        if cached.exists():
            return cached.read_text(encoding="utf-8", errors="replace")
        last = ""
        for tpl in RAW_MIRRORS:
            url = tpl.format(repo=repo, branch=branch, path=path)
            try:
                text = self.get_text(url)
                if len(text) < 20:
                    raise RuntimeError("响应过短")
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_text(text, encoding="utf-8")
                return text
            except Exception as e:  # noqa: BLE001
                last = f"{url} -> {e}"
                continue
        raise RuntimeError(f"全部镜像失败({last})")

    def github_api(self, path: str):
        last = ""
        for tpl in API_MIRRORS:
            url = tpl.format(path=path)
            try:
                return json.loads(self.get_text(url, use_api=True))
            except Exception as e:  # noqa: BLE001
                last = f"{url} -> {e}"
                continue
        raise RuntimeError(f"API 失败({last})")


def _cache_path(key: str) -> Path:
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", key)[-60:]
    return CACHE_DIR / f"{safe}-{h}.txt"


# ---------------------------------------------------------------------------
# 聚合
# ---------------------------------------------------------------------------
LEVEL_ORDER = {"Unsafe": 4, "Expert": 3, "Advanced": 2, "Recommended": 1,
               "Community": 0}


def merge(db: dict, pkg: str, *, source: str, removal: str = "",
          listname: str = "", desc: str = "", action: str = "",
          deps=None, needed_by=None) -> None:
    if not valid_pkg(pkg) or not is_safe(pkg):
        return
    rec = db.setdefault(pkg, {"r": "", "l": "", "d": "", "s": [], "a": ""})
    # 风险分级取最保守的那个(Unsafe > Expert > Advanced > Recommended)
    if removal and LEVEL_ORDER.get(removal, 0) > LEVEL_ORDER.get(rec["r"], 0):
        rec["r"] = removal
    if listname and not rec["l"]:
        rec["l"] = listname
    if desc and len(desc) > len(rec["d"]):
        rec["d"] = desc[:180]
    if action and not rec["a"]:
        rec["a"] = action
    if deps:
        rec["dep"] = sorted(set(deps))
    if needed_by:
        rec["nb"] = sorted(set(needed_by))
    if not rec["r"]:
        rec["r"] = "Community"      # 仅社区来源, 无官方分级
    if source not in rec["s"]:
        rec["s"].append(source)


def source_uad(net: Net, db: dict, report: dict) -> int:
    """UAD-NG 结构化库(主力数据源)。"""
    print("  [1/4] UAD-NG 结构化库 ...", flush=True)
    try:
        text = net.github_file(UAD_REPO, UAD_PATH, UAD_BRANCH, cache_key="uad-ng.json")
        data = json.loads(text)
    except Exception as e:  # noqa: BLE001
        report["errors"].append(f"UAD-NG: {e}")
        print(f"        失败: {e}")
        return 0
    n = 0
    for pkg, info in data.items():
        if not isinstance(info, dict):
            continue
        merge(db, pkg, source="uad-ng",
              removal=str(info.get("removal", "")),
              listname=str(info.get("list", "")),
              desc=str(info.get("description", "")).replace("\n", " ").strip(),
              deps=info.get("dependencies") or None,
              needed_by=info.get("neededBy") or None)
        n += 1
    report["sources"].append({"id": "uad-ng", "count": n,
                              "note": f"{len(data)} 条原始记录"})
    print(f"        {n} 个包")
    return n


def source_code_search(net: Net, db: dict, report: dict, max_files: int) -> int:
    """GitHub 代码搜索: 发现社区维护的 debloat 列表与教程帖。"""
    print("  [2/4] GitHub 代码搜索(社区列表/帖子) ...", flush=True)
    if not net.token:
        print("        未提供 GITHUB_TOKEN, 跳过(设置后额度更高)")
        report["errors"].append("GitHub 代码搜索: 未提供 token")
        return 0
    seen: set = set()
    files: list = []
    for q in SEARCH_QUERIES:
        if len(files) >= max_files:
            break
        path = "search/code?q=" + urllib.parse.quote(q) + "&per_page=20"
        try:
            data = net.github_api(path)
        except Exception as e:  # noqa: BLE001
            report["errors"].append(f"代码搜索 {q}: {e}")
            continue
        for item in data.get("items", []):
            key = (item["repository"]["full_name"], item["path"])
            if key in seen:
                continue
            seen.add(key)
            files.append(key)
        time.sleep(2)  # 代码搜索限流较严(10 次/分钟)
    n = 0
    got = 0
    for repo, path in files[:max_files]:
        try:
            text = net.github_file(repo, path)
        except Exception as e:  # noqa: BLE001
            report["errors"].append(f"{repo}/{path}: {e}")
            continue
        kind = "post" if path.lower().endswith((".md", ".markdown")) else "list"
        found = extract(text, kind)
        if not found:
            continue
        got += 1
        for pkg, meta in found.items():
            merge(db, pkg, source=f"gh:{repo}", action=meta["action"],
                  desc=meta["comment"])
        n += len(found)
    report["sources"].append({"id": "github-code-search", "count": n,
                              "note": f"{got}/{min(len(files), max_files)} 个文件有效"})
    print(f"        {got} 个文件, {n} 条记录")
    return n


def source_curated(net: Net, db: dict, report: dict, max_files: int) -> int:
    """内置精选仓库: 已知高质量列表, 按仓库树抓取。"""
    print("  [3/4] 内置精选仓库 ...", flush=True)
    n = 0
    got = 0
    for repo, branch in CURATED:
        try:
            tree = net.github_api(f"repos/{repo}/git/trees/{branch}?recursive=1")
        except Exception as e:  # noqa: BLE001
            report["errors"].append(f"{repo} 树: {e}")
            continue
        paths = [t["path"] for t in tree.get("tree", [])
                 if t.get("type") == "blob" and t["path"].endswith((".txt", ".md"))
                 and "debloat" in t["path"].lower()]
        for path in paths[:max_files]:
            try:
                text = net.github_file(repo, path, branch)
            except Exception as e:  # noqa: BLE001
                report["errors"].append(f"{repo}/{path}: {e}")
                continue
            kind = "post" if path.lower().endswith(".md") else "list"
            found = extract(text, kind)
            if not found:
                continue
            got += 1
            for pkg, meta in found.items():
                merge(db, pkg, source=f"gh:{repo}", action=meta["action"],
                      desc=meta["comment"])
            n += len(found)
    report["sources"].append({"id": "curated", "count": n,
                              "note": f"{got} 个文件有效"})
    print(f"        {got} 个文件, {n} 条记录")
    return n


def source_gitee(net: Net, db: dict, report: dict, max_files: int,
                 extra_repos=()) -> int:
    """Gitee 中文社区: 搜索「去广告/精简/预装」仓库并解析其中的列表。

    Gitee 的搜索页已改为 JS 渲染(so.gitee.com), API v5 的 search 接口
    近年对所有关键词都返回空数组。因此这里以「手动指定仓库」为主,
    API 搜索能出结果时自动纳入; 两者都没有就如实写进报告。
    """
    print("  [4/4] Gitee 中文社区 ...", flush=True)
    repos: list = list(extra_repos)
    for q in GITEE_QUERIES:
        url = ("https://gitee.com/api/v5/search/repositories?q="
               + urllib.parse.quote(q) + "&per_page=5")
        try:
            data = json.loads(net.get_text(url))
        except Exception as e:  # noqa: BLE001
            report["errors"].append(f"Gitee 搜索 {q}: {e}")
            continue
        for r in data if isinstance(data, list) else []:
            full = r.get("full_name") or ""
            if full and full not in repos:
                repos.append(full)

    if not repos:
        report["sources"].append({"id": "gitee", "count": 0,
                                  "note": "搜索接口返回空(已改为 JS 渲染), 跳过"})
        print("        搜索接口不可用, 跳过(可用 --gitee-repo 手动指定)")
        return 0

    n = 0
    got = 0
    for full in repos[:4]:
        tree = None
        for branch in ("master", "main"):
            try:
                tree = json.loads(net.get_text(
                    f"https://gitee.com/api/v5/repos/{full}/git/trees/"
                    f"{branch}?recursive=1"))
                break
            except Exception as e:  # noqa: BLE001
                report["errors"].append(f"Gitee {full}@{branch}: {e}")
        if not tree:
            continue
        paths = [t["path"] for t in tree.get("tree", [])
                 if t.get("type") == "blob"
                 and t["path"].endswith((".txt", ".md", ".sh"))]
        for path in paths[:max_files]:
            try:
                text = net.get_text(
                    f"https://gitee.com/{full}/raw/master/{path}")
            except Exception as e:  # noqa: BLE001
                report["errors"].append(f"Gitee {full}/{path}: {e}")
                continue
            kind = "post" if path.lower().endswith(".md") else "list"
            found = extract(text, kind)
            if not found:
                continue
            got += 1
            for pkg, meta in found.items():
                merge(db, pkg, source=f"gitee:{full}", action=meta["action"],
                      desc=meta["comment"])
            n += len(found)
    report["sources"].append({"id": "gitee", "count": n,
                              "note": f"{len(repos)} 个仓库, {got} 个文件有效"})
    print(f"        {len(repos)} 个仓库, {n} 条记录")
    return n


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
VENDOR_GROUPS = (
    ("小米 / 红米 / POCO", ("com.miui.", "com.xiaomi.", "com.mi.", "com.mfashiongallery.")),
    ("华为 / 荣耀", ("com.huawei.", "com.hihonor.")),
    ("OPPO / 一加 / realme", ("com.oppo.", "com.coloros.", "com.heytap.",
                             "com.oplus.", "com.nearme.", "com.realme.")),
    ("vivo / iQOO", ("com.vivo.", "com.bbk.", "com.iqoo.")),
    ("三星", ("com.samsung.", "com.sec.")),
    ("魅族", ("com.meizu.",)),
    ("Google / AOSP", ("com.google.", "com.android.")),
)


def vendor_of(pkg: str) -> str:
    for name, prefixes in VENDOR_GROUPS:
        if any(pkg.startswith(p) for p in prefixes):
            return name
    return "其他第三方"


def write_all_bloat(db: dict) -> int:
    groups: dict = {}
    for pkg, rec in db.items():
        if rec.get("r") not in ("Recommended", "Advanced"):
            continue
        groups.setdefault(vendor_of(pkg), []).append(pkg)
    lines = [
        "# CleanYourPhone 全量预装清理清单(自动聚合)",
        "# 来源: UAD-NG + GitHub 社区列表/教程 + Gitee 中文社区",
        "# 由 tools/harvest.py 自动生成, 请勿手工编辑",
        "# 仅收录 Recommended(推荐) 与 Advanced(进阶) 两级; Expert/Unsafe 不在此列",
        "# 真机使用: python3 tools/phone.py auto --dry-run  (按本机预装自动匹配)",
        "",
    ]
    total = 0
    for name, _ in VENDOR_GROUPS + (("其他第三方", ()),):
        if name not in groups:
            continue
        pkgs = sorted(groups[name])
        lines.append(f"# ---------- {name} ({len(pkgs)}) ----------")
        for pkg in pkgs:
            rec = db[pkg]
            desc = (rec.get("d") or "").replace("\n", " ")[:100]
            level = rec.get("r", "")
            lines.append(f"{pkg} uninstall  # [{level}] {desc}".rstrip())
        lines.append("")
        total += len(pkgs)
    ALL_FILE.write_text("\n".join(lines), encoding="utf-8")
    return total


def write_db(db: dict, report: dict) -> None:
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).astimezone().isoformat(
                timespec="seconds"),
            "tool": "tools/harvest.py",
            "total": len(db),
            "sources": report["sources"],
            "levels": {k: sum(1 for r in db.values() if r.get("r") == k)
                       for k in ("Recommended", "Advanced", "Expert",
                                 "Unsafe", "Community")},
        },
        "packages": dict(sorted(db.items())),
    }
    DB_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                       encoding="utf-8")


def write_report(db: dict, report: dict, elapsed: float) -> None:
    levels = {k: sum(1 for r in db.values() if r.get("r") == k)
              for k in ("Recommended", "Advanced", "Expert", "Unsafe", "Community")}
    lines = [
        "# 抓取报告",
        "",
        f"- 生成时间: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- 耗时: {elapsed:.0f} 秒, 网络请求 {report['requests']} 次",
        f"- 入库包数: **{len(db)}**",
        "",
        "## 分级分布",
        "",
        "| 分级 | 含义 | 数量 |",
        "| --- | --- | --- |",
        f"| Recommended | 推荐清理(安全) | {levels['Recommended']} |",
        f"| Advanced | 进阶(需知道用途) | {levels['Advanced']} |",
        f"| Expert | 专家(可能影响功能) | {levels['Expert']} |",
        f"| Unsafe | 危险(会破坏系统, auto 永不处理) | {levels['Unsafe']} |",
        f"| Community | 仅社区来源, 无官方分级 | {levels['Community']} |",
        "",
        "## 数据源",
        "",
        "| 源 | 记录数 | 备注 |",
        "| --- | --- | --- |",
    ]
    for s in report["sources"]:
        lines.append(f"| {s['id']} | {s['count']} | {s.get('note', '')} |")
    if report["errors"]:
        lines += ["", "## 失败/跳过", ""]
        lines += [f"- {e}" for e in report["errors"][:40]]
    REPORT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="聚合互联网上的 Android 预装清理知识库")
    ap.add_argument("--token", default="", help="GitHub token(或用 GITHUB_TOKEN 环境变量)")
    ap.add_argument("--max-files", type=int, default=20,
                    help="每个来源最多抓取的文件数(默认 20)")
    ap.add_argument("--offline", action="store_true",
                    help="只用本地缓存, 不联网")
    ap.add_argument("--no-cache", action="store_true", help="忽略缓存重新下载")
    ap.add_argument("--gitee-repo", action="append", default=[], metavar="OWNER/REPO",
                    help="手动指定 Gitee 仓库(可重复), 如 --gitee-repo someone/debloat")
    args = ap.parse_args()

    if args.no_cache and CACHE_DIR.exists():
        for f in CACHE_DIR.glob("*"):
            f.unlink()

    t0 = time.time()
    net = Net(token=args.token, offline=args.offline)
    db: dict = {}
    report = {"sources": [], "errors": []}

    print("CleanYourPhone 数据聚合")
    print("=" * 52)
    source_uad(net, db, report)
    source_code_search(net, db, report, args.max_files)
    source_curated(net, db, report, args.max_files)
    source_gitee(net, db, report, args.max_files, args.gitee_repo)

    # 清理: 丢掉没有任何来源标记的(理论上不会有)
    db = {k: v for k, v in db.items() if v.get("s")}

    RULES_DIR.mkdir(parents=True, exist_ok=True)
    write_db(db, report)
    total_bloat = write_all_bloat(db)
    elapsed = time.time() - t0
    report["requests"] = net.requests
    write_report(db, report, elapsed)

    levels = {k: sum(1 for r in db.values() if r.get("r") == k)
              for k in ("Recommended", "Advanced", "Expert", "Unsafe", "Community")}
    print("=" * 52)
    print(f"入库 {len(db)} 个包 (推荐 {levels['Recommended']} / 进阶 "
          f"{levels['Advanced']} / 专家 {levels['Expert']} / 危险 "
          f"{levels['Unsafe']} / 社区 {levels['Community']})")
    print(f"全量清单 {total_bloat} 条 -> {ALL_FILE.relative_to(ROOT_DIR)}")
    print(f"知识库 -> {DB_FILE.relative_to(ROOT_DIR)}")
    print(f"报告 -> {REPORT_FILE.relative_to(ROOT_DIR)}")
    if report["errors"]:
        print(f"注意: {len(report['errors'])} 个源/文件抓取失败(不影响已入库数据)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
