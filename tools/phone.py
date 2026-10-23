#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CleanYourPhone — 国产手机清理工具

参考 CleanYourTV(Gathin23)/ CleanYourAndroid(Bhargi777)/ cleanyourphone(upfind)
三家思路, 适配国产 ROM。

设计原则:
  * 无 root、不解锁 BL、不在手机上安装任何软件
  * 三层清理: 卸载预装 / 禁用广告服务 / 设置级去广告 + 摇一摇封杀
  * 全部可逆: install-existing / pm enable / settings 还原 / appops 还原
  * 内置硬性安全规则 + 当前桌面/Recents/输入法动态保护, 误触核心组件不可能

依赖: Python 标准库; adb 不存在时自动从 Google 官方下载免安装平台工具。

主要命令:
  doctor                          自检: adb / 设备连接 / 授权状态
  info                            设备信息与推荐列表
  pair <ip:port> <配对码>          Android 11+ 无线调试配对
  connect <ip[:port]>              连接无线设备
  disconnect [目标]                断开无线连接
  tcpip [端口]                     (USB 连接时) 开启无线调试端口
  shell "<命令>"                   在手机上执行 shell
  packages [--uninstalled|--disabled]   列出包
  screenshot [名字]                截图(用于分批清理后验证)
  backup                          备份包列表与系统设置
  apply <列表.txt> [--dry-run] [--batch N] [--screenshot]  卸载/禁用预装与广告包
  restore <列表.txt>|--all        恢复(包/设置/传感器限制一并还原)
  check <列表.txt> [--fix]        检查(OTA 后)并可选重新应用
  audit [--write 文件]            扫描设备上的广告/遥测候选包
  auto [--tier safe|standard|aggressive] [--apply]
                                  自动识别本机预装, 匹配互联网聚合知识库后清理
  settings <settings.conf> [--dry-run]   写入系统设置(关闭广告/限制追踪)
  dns on [主机名] | off | status   Private DNS 去广告(带自愈: 解析失败自动关闭)
  shake on|off|status [清单]       封杀第三方 App "摇一摇"开屏广告(appops)
  finish                          收尾: 关闭 USB 调试并断开无线连接
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

VERSION = "2.1.0"
HOME_DIR = Path.home() / ".cleanyourphone"
DEFAULT_WIRELESS_PORT = 5555

# ---------------------------------------------------------------------------
# 安全规则一: 包名正则(桌面/电话/短信/系统框架等, 永不触碰)
# ---------------------------------------------------------------------------
DENY_PATTERNS = [
    r"(^|\.)launcher($|\.)",              # 桌面启动器
    r"(^|\.)nemu($|\.)",
    r"(^|\.)home($|\.)",                  # 桌面(如 com.miui.home)
    r"(^|\.)systemui($|\.)",              # 系统 UI
    r"(^|\.)settings($|\.)",              # 设置(含 com.android.providers.settings)
    r"(^|\.)setupwizard($|\.)",           # 开机向导
    r"(^|\.)phone($|\.)",                 # 电话
    r"(^|\.)dialer($|\.)",                # 拨号
    r"(^|\.)incallui($|\.)",              # 来电界面
    r"(^|\.)telecom($|\.)",               # 通话框架
    r"(^|\.)telephony($|\.)",             # 电话服务
    r"(^|\.)providers\.telephony($|\.)",  # 电话数据提供器
    r"(^|\.)mms($|\.)",                   # 短信
    r"(^|\.)messaging($|\.)",
    r"(^|\.)sms($|\.)",
    r"(^|\.)smspush($|\.)",
    r"(^|\.)contacts($|\.)",              # 联系人
    r"(^|\.)providers\.contacts($|\.)",
    r"(^|\.)shell($|\.)",
    r"(^|\.)packageinstaller($|\.)",
    r"(^|\.)permissioncontroller($|\.)",
    r"(^|\.)keychain($|\.)",
    r"(^|\.)certinstaller($|\.)",
    r"(^|\.)webview($|\.)",
    r"(^|\.)htmlviewer($|\.)",
    r"(^|\.)externalstorage($|\.)",
    r"(^|\.)documentsui($|\.)",
    r"(^|\.)fallback($|\.)",              # 兜底桌面
    r"(^|\.)nfc($|\.)",
    r"(^|\.)bluetooth($|\.)",
    r"(^|\.)inputdevices($|\.)",
    r"(^|\.)credentials($|\.)",
    r"(^|\.)role($|\.)",
    r"(^|\.)networkstack($|\.)",
    r"(^|\.)connectivity($|\.)",
    r"(^|\.)proxyhandler($|\.)",
    r"(^|\.)localtransport($|\.)",
    r"(^|\.)printspooler($|\.)",
    r"(^|\.)bips($|\.)",
    r"(^|\.)gms($|\.)",                   # com.google.android.gms
    r"(^|\.)keyguard($|\.)",              # 锁屏
    r"(^|\.)wallpaper($|\.)",             # 壁纸
    r"(^|\.)vending($|\.)",               # Play 商店
    r"(^|\.)gsf($|\.)",                   # Google 服务框架
    r"(^|\.)ext\.services($|\.)",         # WebView 提供器
    r"(^|\.)providers\.media($|\.)",      # 媒体数据库
    r"(^|\.)providers\.downloads($|\.)",  # 下载提供器
    r"(^|\.)inputmethod($|\.)",           # 输入法框架
]
DENY_RE = [re.compile(p) for p in DENY_PATTERNS]

# ---------------------------------------------------------------------------
# 安全规则二: 显式核心包清单(来自 CleanYourAndroid 的护栏实践)
# ---------------------------------------------------------------------------
PROTECTED_PACKAGES = frozenset({
    "android",
    "com.android.systemui",
    "com.android.settings",
    "com.android.phone",
    "com.android.providers.settings",
    "com.android.providers.telephony",
    "com.android.providers.media",
    "com.android.providers.downloads",
    "com.android.externalstorage",
    "com.android.documentsui",
    "com.android.packageinstaller",
    "com.google.android.packageinstaller",
    "com.android.permissioncontroller",
    "com.google.android.permissioncontroller",
    "com.android.bluetooth",
    "com.android.nfc",
    "com.android.networkstack",
    "com.google.android.networkstack",
    "com.android.shell",
    "com.android.keychain",
    "com.android.certinstaller",
    "com.google.android.gms",
    "com.google.android.gsf",
    "com.android.vending",
    "com.google.android.webview",
    "com.android.webview",
    "com.google.android.ext.services",
    "com.android.ext.services",
    "com.google.android.inputmethod.latin",
    "com.samsung.android.honeyboard",
})


def is_denied(pkg: str) -> bool:
    """包名是否命中硬性安全规则(核心系统组件, 永不触碰)。"""
    return pkg in PROTECTED_PACKAGES or any(r.search(pkg) for r in DENY_RE)


# ---------------------------------------------------------------------------
# 清理列表解析
# 行格式: <包名> [uninstall|disable] [# 注释]
#   - 行首 # 为注释, 空行忽略; 兼容 CRLF 与 UTF-8 BOM
#   - 动作缺省为 uninstall
# ---------------------------------------------------------------------------
LIST_LINE_RE = re.compile(
    r"^(?P<pkg>[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)"   # 包名
    r"(?:\s+(?P<action>uninstall|disable))?"                  # 可选动作
    r"(?:\s+#\s?(?P<comment>.*))?$"                           # 可选注释
)


def parse_list(text: str, source: str = "<list>"):
    text = text.lstrip("\ufeff")
    entries = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = LIST_LINE_RE.match(line)
        if not m:
            raise ValueError(f"{source}:{lineno}: 无法解析的行: {raw!r}")
        entries.append({
            "pkg": m.group("pkg"),
            "action": m.group("action") or "uninstall",
            "comment": (m.group("comment") or "").strip(),
        })
    return entries


def parse_list_file(path) -> list:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"列表文件不存在: {p}")
    return parse_list(p.read_text(encoding="utf-8-sig"), str(p))


# ---------------------------------------------------------------------------
# 系统设置文件解析(settings.conf)
# 行格式: <global|secure|system> <键名> <值> [# 注释]
# ---------------------------------------------------------------------------
SETTINGS_LINE_RE = re.compile(
    r"^(?P<ns>global|secure|system)\s+"
    r"(?P<key>[A-Za-z][A-Za-z0-9_.]*)\s+"
    r"(?P<value>\S+)"
    r"(?:\s+#\s?(?P<comment>.*))?$"
)


def parse_settings(text: str, source: str = "<settings>"):
    text = text.lstrip("\ufeff")
    entries = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = SETTINGS_LINE_RE.match(line)
        if not m:
            raise ValueError(f"{source}:{lineno}: 无法解析的行: {raw!r}")
        entries.append({
            "ns": m.group("ns"),
            "key": m.group("key"),
            "value": m.group("value"),
            "comment": (m.group("comment") or "").strip(),
        })
    return entries


def parse_settings_file(path) -> list:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"设置文件不存在: {p}")
    return parse_settings(p.read_text(encoding="utf-8-sig"), str(p))


# ---------------------------------------------------------------------------
# 摇一摇封杀: 传感器相关 appops
# ---------------------------------------------------------------------------
SHAKE_OPS = ("BODY_SENSORS", "ACTIVITY_RECOGNITION", "READ_SENSORS")


# ---------------------------------------------------------------------------
# ADB 自动准备(零门槛: 没有 adb 时自动从 Google 官方下载免安装平台工具)
# ---------------------------------------------------------------------------
PLATFORM_TOOLS_URLS = {
    "Darwin": "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip",
    "Linux": "https://dl.google.com/android/repository/platform-tools-latest-linux.zip",
    "Windows": "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
}


class AdbError(RuntimeError):
    pass


def _local_adb_path() -> Path:
    bin_name = "adb.exe" if platform.system() == "Windows" else "adb"
    return HOME_DIR / "platform-tools" / bin_name


def ensure_adb(verbose=True) -> str:
    """返回可用的 adb 路径; 没有则自动下载官方 platform-tools 到用户目录。"""
    cand = os.environ.get("ADB")
    if cand and Path(cand).exists():
        return str(cand)
    found = shutil.which("adb")
    if found:
        return found
    local = _local_adb_path()
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    # 常见安装位置
    for g in (Path.home() / "Library/Android/sdk/platform-tools/adb",
              Path("/opt/homebrew/bin/adb"), Path("/usr/local/bin/adb")):
        try:
            if g and Path(g).exists():
                return str(g)
        except OSError:
            continue
    # 自动下载
    system = platform.system()
    url = PLATFORM_TOOLS_URLS.get(system)
    if not url:
        raise AdbError(
            f"未找到 adb 且不支持为 {system} 自动下载。请手动安装 Android 平台工具:\n"
            "  https://developer.android.com/tools/releases/platform-tools"
        )
    if verbose:
        print("[准备] 未检测到 adb, 正在从 Google 官方自动下载 platform-tools(约 10MB)...",
              file=sys.stderr)
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = HOME_DIR / "platform-tools.zip"
    try:
        urllib.request.urlretrieve(url, zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(HOME_DIR)
        zip_path.unlink(missing_ok=True)
        if platform.system() != "Windows":
            local.chmod(0o755)
    except Exception as e:
        zip_path.unlink(missing_ok=True)
        raise AdbError(f"自动下载 adb 失败: {e}\n请检查网络, 或手动安装 platform-tools。")
    if not local.is_file():
        raise AdbError("下载的 platform-tools 中未找到 adb, 请手动安装。")
    if verbose:
        print(f"[准备] adb 已就绪: {local}(无需配置环境变量)", file=sys.stderr)
    return str(local)


class Adb:
    """官方 adb 的轻量封装(仅使用标准库)。"""

    def __init__(self, adb_path=None, serial=None):
        self.adb = adb_path or ensure_adb()
        self.serial = serial

    def _cmd(self, *args):
        cmd = [self.adb]
        if self.serial:
            cmd += ["-s", self.serial]
        return cmd + [str(a) for a in args]

    def run(self, *args, timeout=120):
        return subprocess.run(
            self._cmd(*args), capture_output=True, text=True, timeout=timeout
        )

    def shell(self, command, timeout=120) -> str:
        """在设备上执行 shell 命令, 返回 stdout(已 strip, 去掉部分 adb  builds 的 CR)。"""
        proc = self.run("shell", command, timeout=timeout)
        return proc.stdout.strip().replace("\r", "")

    def shell_all(self, command, timeout=120) -> str:
        """执行 shell 命令并合并 stdout/stderr(用于 appops 等需要看报错的场景)。"""
        proc = self.run("shell", command, timeout=timeout)
        return (proc.stdout + proc.stderr).strip().replace("\r", "")

    def screenshot(self, path) -> Path:
        """用 exec-out 截图(不经 shell 转换, 二进制安全)。"""
        cmd = [self.adb]
        if self.serial:
            cmd += ["-s", self.serial]
        cmd += ["exec-out", "screencap", "-p"]
        proc = subprocess.run(cmd, capture_output=True, timeout=60)
        if not proc.stdout:
            raise AdbError("截图失败(屏幕可能处于关闭状态, 请唤醒手机后重试)")
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(proc.stdout)
        return p

    def devices(self) -> list:
        proc = self.run("devices", "-l")
        out = []
        for line in proc.stdout.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            serial = parts[0]
            state = parts[1] if len(parts) > 1 else "unknown"
            out.append({
                "serial": serial,
                "state": state,
                "transport": "wifi" if ":" in serial else "usb",
                "raw": line,
            })
        return out


def pick_device(adb: Adb, serial=None) -> str:
    """选择一台在线设备, 返回序列号; 有问题时抛出带指引的 AdbError。"""
    devs = adb.devices()
    online = [d for d in devs if d["state"] == "device"]
    if serial:
        match = [d for d in devs if d["serial"] == serial]
        if not match:
            raise AdbError(
                f"指定设备 {serial} 未连接。当前设备: "
                f"{[d['serial'] for d in devs] or '无'}"
            )
        if match[0]["state"] != "device":
            raise AdbError(
                f"设备 {serial} 状态为 {match[0]['state']}。"
                "若显示 unauthorized, 请在手机上撤销 USB 调试授权后重新允许。"
            )
        return serial
    if not devs:
        raise AdbError(
            "没有已连接的设备。请检查: 1) 数据线与驱动 2) 手机已解锁并允许 USB 调试 "
            "3) 手机弹出的授权对话框已点“允许”"
        )
    if len(devs) == 1:
        if devs[0]["state"] != "device":
            raise AdbError(
                f"设备状态: {devs[0]['state']}。"
                "若为 unauthorized, 请在手机上重新确认 USB 调试授权; 若为 offline, 请插拔数据线。"
            )
        return devs[0]["serial"]
    if len(online) == 1:
        return online[0]["serial"]
    raise AdbError(
        "检测到多台设备, 请用 --serial 指定其中一台(可先运行: adb devices -l 查看)。"
    )


# ---------------------------------------------------------------------------
# 设备信息与动态保护目标(桌面 / Recents / 当前输入法)
# ---------------------------------------------------------------------------
INFO_PROPS = [
    "ro.product.brand", "ro.product.model", "ro.product.name", "ro.product.device",
    "ro.product.marketname",
    "ro.build.version.release", "ro.build.version.sdk", "ro.build.display.id",
    "ro.miui.ui.version.name",        # 小米 MIUI/HyperOS
    "ro.build.version.emui",          # 华为 EMUI/HarmonyOS
    "ro.build.version.opporom",       # OPPO ColorOS
    "ro.vivo.os.version", "ro.vivo.rom.version",   # vivo OriginOS
    "ro.build.version.magic", "ro.build.version.hihonor",  # 荣耀 MagicOS
]

BRAND_TO_EXAMPLE = {
    "xiaomi": "examples/xiaomi-hyperos",
    "redmi": "examples/xiaomi-hyperos",
    "poco": "examples/xiaomi-hyperos",
    "blackshark": "examples/xiaomi-hyperos",
    "huawei": "examples/huawei-harmonyos",
    "honor": "examples/honor-magicos",
    "oppo": "examples/oppo-coloros",
    "oneplus": "examples/oppo-coloros",
    "realme": "examples/oppo-coloros",
    "vivo": "examples/vivo-originos",
    "iqoo": "examples/vivo-originos",
    "samsung": "examples/samsung-oneui-cn",
    "meizu": "examples/meizu-flyme",
}


def get_props(dev: Adb) -> dict:
    props = {}
    for key in INFO_PROPS:
        try:
            props[key] = dev.shell(f"getprop {key}")
        except Exception:
            props[key] = ""
    return props


def describe_device(dev: Adb) -> dict:
    props = get_props(dev)
    brand = (props.get("ro.product.brand") or "").strip()
    model = (props.get("ro.product.model") or "").strip()
    rom = ""
    for key in ("ro.miui.ui.version.name", "ro.build.version.emui",
                "ro.build.version.opporom", "ro.vivo.os.version",
                "ro.build.version.magic", "ro.build.version.hihonor"):
        if props.get(key):
            rom = props[key]
            break
    example = BRAND_TO_EXAMPLE.get(brand.lower(), "examples/universal")
    return {
        "brand": brand, "model": model, "rom": rom,
        "marketname": props.get("ro.product.marketname", ""),
        "android": props.get("ro.build.version.release", ""),
        "sdk": props.get("ro.build.version.sdk", ""),
        "display": props.get("ro.build.display.id", ""),
        "example": example,
        "props": props,
    }


def resolve_home(dev: Adb):
    """解析当前默认桌面包名。解析失败返回 None。"""
    try:
        out = dev.shell(
            "cmd package resolve-activity -a android.intent.action.MAIN "
            "-c android.intent.category.HOME --brief"
        )
    except Exception:
        return None
    for raw in reversed(out.splitlines()):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("name="):
            line = line[len("name="):].strip()
        if line.startswith("priority=") or line.startswith("match="):
            continue
        pkg = line.split("/")[0].strip()
        if pkg and "." in pkg and " " not in pkg:
            return pkg
    return None


def resolve_recents(dev: Adb):
    """解析提供"最近任务"的包(Android 10+ 通常是桌面自带 Quickstep,
    禁用会导致任务切换失灵)。解析失败返回 None。"""
    try:
        out = dev.shell("dumpsys activity recents")
    except Exception:
        return None
    m = re.search(r"mRecentsComponent=ComponentInfo\{([^/}]+)", out)
    if m:
        return m.group(1).strip() or None
    return None


def current_ime(dev: Adb):
    """当前默认输入法包名(禁用了它, 重启后就无法输入 PIN 解锁)。"""
    try:
        out = dev.shell("settings get secure default_input_method")
    except Exception:
        return None
    if not out or out in ("null", "1"):
        return None
    return out.split("/")[0].strip() or None


def protected_targets(dev: Adb) -> dict:
    """本次运行的动态保护目标: 桌面 / Recents / 输入法。"""
    return {
        "home": resolve_home(dev),
        "recents": resolve_recents(dev),
        "ime": current_ime(dev),
    }


# ---------------------------------------------------------------------------
# 包列表查询
# ---------------------------------------------------------------------------
def _parse_pm_list(out: str) -> set:
    pkgs = set()
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            pkgs.add(line[len("package:"):].strip())
    return pkgs


def list_packages(dev: Adb) -> set:
    """当前用户已安装的包。"""
    return _parse_pm_list(dev.shell("pm list packages"))


def list_disabled(dev: Adb) -> set:
    """已被禁用的包。"""
    return _parse_pm_list(dev.shell("pm list packages -d"))


def list_suspended(dev: Adb) -> set:
    """已被挂起(pm suspend)的包; 部分 ROM(如 ColorOS 乐划锁屏)禁止
    pm disable-user, 但允许 suspend, 挂起后应用无法启动, 效果等同禁用。"""
    out = dev.shell("dumpsys package")
    pkgs = set()
    cur = None
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("Package ["):
            cur = s.split("[", 1)[1].split("]", 1)[0] if "[" in s else None
        elif "suspended=true" in s and cur:
            pkgs.add(cur)
    return pkgs


# ---------------------------------------------------------------------------
# 备份与状态记录
# ---------------------------------------------------------------------------
def now_ts() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def state_path(serial: str, base=HOME_DIR) -> Path:
    return Path(base) / serial / "state.json"


def load_state(serial: str, base=HOME_DIR) -> dict:
    p = state_path(serial, base)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"serial": serial, "packages": {}, "settings": {}, "shake": {}}


def save_state(state: dict, base=HOME_DIR):
    p = state_path(state["serial"], base)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def record_pkg(state: dict, pkg: str, action: str, list_file: str, base=HOME_DIR):
    state.setdefault("packages", {})[pkg] = {
        "action": action,
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "list": str(list_file),
    }
    state["updated"] = dt.datetime.now().isoformat(timespec="seconds")
    save_state(state, base)


def backup_device(dev: Adb, label=None, base=HOME_DIR) -> Path:
    """备份包列表/禁用列表/系统设置/getprop/Home/Recents/输入法, 返回备份目录。"""
    ts = now_ts()
    d = Path(base) / dev.serial / f"backup-{ts}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "packages.txt").write_text(
        dev.shell("pm list packages -u -f") + "\n", encoding="utf-8")
    (d / "packages-disabled.txt").write_text(
        dev.shell("pm list packages -d") + "\n", encoding="utf-8")
    (d / "packages-enabled.txt").write_text(
        dev.shell("pm list packages -e") + "\n", encoding="utf-8")
    for scope in ("global", "system", "secure"):
        try:
            (d / f"settings-{scope}.txt").write_text(
                dev.shell(f"settings list {scope}") + "\n", encoding="utf-8")
        except Exception:
            pass
    try:
        (d / "props.txt").write_text(dev.shell("getprop") + "\n", encoding="utf-8")
    except Exception:
        pass
    try:
        (d / "dumpsys-recents.txt").write_text(
            dev.shell("dumpsys activity recents")[:200000] + "\n", encoding="utf-8")
    except Exception:
        pass
    protect = protected_targets(dev)
    manifest = {
        "serial": dev.serial,
        "label": label,
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "device": {k: v for k, v in get_props(dev).items() if v},
        "home": protect["home"],
        "recents": protect["recents"],
        "ime": protect["ime"],
    }
    (d / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return d


# ---------------------------------------------------------------------------
# 核心动作: 应用 / 恢复 / 检查 / 审计
# ---------------------------------------------------------------------------
def apply_list(dev: Adb, entries: list, list_file: str = "", dry_run: bool = False,
               do_backup: bool = True, batch: int = 0, screenshot: bool = False,
               base=HOME_DIR, log=print) -> dict:
    """应用清理列表。返回分类结果字典。

    规则:
      * 命中 DENY 规则/显式核心包清单 -> 拒绝
      * 当前默认桌面 / Recents 提供者 / 当前输入法 -> 拒绝(动态保护)
      * 设备上不存在的包 -> 跳过(不同 ROM 包名有差异, 属正常)
      * uninstall 失败(ROM 限制) -> 自动降级为 disable
      * batch>0 时按批次处理, 每批之后截图(需 --screenshot), 方便逐段验证
    """
    installed = list_packages(dev)
    disabled = list_disabled(dev)
    suspended = list_suspended(dev)
    protect = protected_targets(dev)
    protected = {p for p in protect.values() if p}
    if protect.get("ime"):
        log(f"[保护] 当前输入法: {protect['ime']}(禁用后重启将无法解锁, 已加入保护)")
    if protect.get("recents") and protect["recents"] != protect.get("home"):
        log(f"[保护] 最近任务提供者: {protect['recents']}(禁用它会导致任务切换失灵)")
    if protect.get("home"):
        log(f"[保护] 当前默认桌面: {protect['home']}")

    state = load_state(dev.serial, base)
    result = {"ok": [], "skipped_deny": [], "skipped_missing": [],
              "skipped_protected": [], "already": [], "fail": []}

    if do_backup and not dry_run:
        bdir = backup_device(dev, label=f"before-apply:{list_file}", base=base)
        log(f"[备份] 设备快照已保存到 {bdir}")

    shots_dir = Path(base) / dev.serial / "shots" / now_ts()

    def do_one(e) -> None:
        pkg, action = e["pkg"], e["action"]
        if is_denied(pkg):
            result["skipped_deny"].append(pkg)
            log(f"[拒绝] {pkg} 命中安全规则(核心系统组件), 已跳过")
            return
        if pkg in protected:
            result["skipped_protected"].append(pkg)
            log(f"[保护] {pkg} 是桌面/最近任务/输入法, 已跳过")
            return
        if pkg not in installed:
            result["skipped_missing"].append(pkg)
            log(f"[跳过] {pkg} 未在本机安装(可能该机型/版本无此应用)")
            return
        if action == "disable" and (pkg in disabled or pkg in suspended):
            result["already"].append(pkg)
            log(f"[跳过] {pkg} 已处于禁用/挂起状态")
            return
        if dry_run:
            result["ok"].append(pkg)
            log(f"[预演] {action:9s} {pkg}  # {e['comment']}")
            return
        if action == "uninstall":
            out = dev.shell(f"pm uninstall --user 0 {pkg}")
            if "Success" in out:
                record_pkg(state, pkg, "uninstall", list_file, base)
                result["ok"].append(pkg)
                log(f"[已卸载] {pkg}  # {e['comment']}")
                return
            log(f"[降级] {pkg} 卸载失败({out.strip() or '无输出'}), 尝试改为禁用")
            action = "disable"
        out = dev.shell_all(f"pm disable-user {pkg}")
        low = out.lower()
        # 成功输出为 "new state: disabled-user"; 部分 ROM(如 ColorOS 的
        # 乐划锁屏)会返回 "new state: default" 静默拒绝, 退出码仍为 0
        if "disabled-user" in low:
            record_pkg(state, pkg, action, list_file, base)
            result["ok"].append(pkg)
            log(f"[已禁用] {pkg}  # {e['comment']}")
            return
        # 兜底: 改用 pm suspend 挂起(应用无法启动, 效果等同禁用)
        out2 = dev.shell(f"pm suspend --user 0 {pkg}")
        if "true" in out2.lower():
            record_pkg(state, pkg, "suspend", list_file, base)
            result["ok"].append(pkg)
            log(f"[已挂起] {pkg}(该 ROM 禁止禁用, 已挂起: 无法启动)  # {e['comment']}")
        else:
            result["fail"].append(pkg)
            log(f"[失败] {pkg}: {out.strip() or '无输出'}")

    if batch and batch > 0 and not dry_run:
        total = len(entries)
        done = 0
        for i in range(0, total, batch):
            chunk = entries[i:i + batch]
            log(f"\n--- 第 {i // batch + 1} 批({len(chunk)} 项) ---")
            for e in chunk:
                do_one(e)
            done += len(chunk)
            if screenshot and done < total:
                try:
                    p = dev.screenshot(shots_dir / f"batch-{i // batch + 1}.png")
                    log(f"[截图] 已保存 {p}(请确认手机界面正常)")
                except AdbError as e:
                    log(f"[截图] 失败: {e}(不影响清理, 请手动看一眼手机)")
    else:
        for e in entries:
            do_one(e)

    log("")
    log(f"完成: 成功 {len(result['ok'])} | 不存在跳过 {len(result['skipped_missing'])} | "
        f"已处于目标状态 {len(result['already'])} | 安全拒绝 "
        f"{len(result['skipped_deny']) + len(result['skipped_protected'])} | "
        f"失败 {len(result['fail'])}")
    if result["fail"]:
        log("失败项通常是因为该 ROM 受保护, 可尝试重启后重试或在列表中改为 disable。")
    return result


def restore_pkgs(dev: Adb, pkgs: list, state: dict, base=HOME_DIR, log=print,
                 revert_extra: bool = True) -> dict:
    """按 state 中记录的动作逆操作恢复; revert_extra=True 时一并还原设置与传感器限制。"""
    result = {"ok": [], "fail": []}
    for pkg in pkgs:
        if is_denied(pkg):
            log(f"[拒绝] {pkg} 命中安全规则, 已跳过")
            continue
        info = state.get("packages", {}).get(pkg, {})
        action = info.get("action", "uninstall")
        if action == "uninstall":
            out = dev.shell(f"cmd package install-existing --user 0 {pkg}")
            if "installed for user" in out.lower():
                log(f"[已恢复] {pkg}")
                result["ok"].append(pkg)
                state.get("packages", {}).pop(pkg, None)
            else:
                log(f"[未恢复] {pkg}: {out.strip() or '无输出'}")
                result["fail"].append(pkg)
        elif action == "suspend":
            dev.shell(f"pm unsuspend --user 0 {pkg}")
            dev.shell(f"pm enable --user 0 {pkg}")
            log(f"[已恢复] {pkg}(取消挂起)")
            result["ok"].append(pkg)
            state.get("packages", {}).pop(pkg, None)
        else:
            out = dev.shell(f"pm enable --user 0 {pkg}")
            log(f"[已恢复] {pkg}" + (f" ({out.strip()})" if out.strip() else ""))
            result["ok"].append(pkg)
            state.get("packages", {}).pop(pkg, None)
    if revert_extra:
        for ns_key, old in list(state.get("settings", {}).items()):
            ns, _, key = ns_key.partition(":")
            if old in ("", "null"):
                dev.shell_all(f"settings delete {ns} {key}")
                log(f"[已还原] 设置 {ns} {key}(删除, 原值: {old or '空'})")
                state["settings"].pop(ns_key, None)
            else:
                out = dev.shell_all(f"settings put {ns} {key} {old}")
                back = dev.shell(f"settings get {ns} {key}")
                if back == str(old):
                    log(f"[已还原] 设置 {ns} {key} -> {old}")
                    state["settings"].pop(ns_key, None)
                else:
                    hint = ("ROM 禁止 adb 写入系统设置, 请手动改回"
                            if "SecurityException" in out or "not granted" in out
                            else out)
                    log(f"[未还原] 设置 {ns} {key}(期望 {old}, 实际 {back or '空'}): {hint}")
        for pkg, ops in list(state.get("shake", {}).items()):
            for op in ops:
                dev.shell(f"appops set {pkg} {op} default")
            log(f"[已还原] 传感器限制: {pkg}")
            state["shake"].pop(pkg, None)
    state["updated"] = dt.datetime.now().isoformat(timespec="seconds")
    save_state(state, base)
    return result


def check_list(dev: Adb, entries: list, fix: bool = False,
               base=HOME_DIR, log=print) -> list:
    """对比列表与设备实际状态; fix=True 时把"回潮"项重新应用。"""
    if fix:
        bdir = backup_device(dev, label="before-check-fix", base=base)
        log(f"[备份] 已保存到 {bdir}")
    installed = list_packages(dev)
    disabled = list_disabled(dev)
    suspended = list_suspended(dev)
    state = load_state(dev.serial, base)
    protect = protected_targets(dev)
    protected = {p for p in protect.values() if p}
    rows = []
    for e in entries:
        pkg, action = e["pkg"], e["action"]
        if is_denied(pkg) or pkg in protected:
            continue
        actual = state.get("packages", {}).get(pkg, {}).get("action", "")
        if pkg not in installed and action == "uninstall":
            cur, ok = "已卸载", True
        elif pkg in suspended:
            cur, ok = "已挂起" + ("(卸载降级)" if action == "uninstall" else ""), True
        elif action == "disable":
            ok = pkg in disabled
            cur = "已禁用" if ok else "仍启用"
        elif actual == "disable" and pkg in disabled:
            # 列表写 uninstall 但 ROM 禁止卸载, 执行时已降级为禁用
            cur, ok = "已禁用(卸载降级)", True
        else:
            ok = False
            cur = "仍安装"
        rows.append({"pkg": pkg, "action": action, "ok": ok, "current": cur,
                     "comment": e["comment"]})
        log(f"{'[OK]   ' if ok else '[变化] '} {pkg} ({action}) -> {cur}  # {e['comment']}")
        if not ok and fix:
            log(f"        -> 重新应用 {action}")
            apply_list(dev, [e], list_file="check-fix", dry_run=False,
                       do_backup=False, base=base, log=log)
    changed = [r for r in rows if not r["ok"]]
    log("")
    log(f"共检查 {len(rows)} 项, 状态变化 {len(changed)} 项"
        + ("(已重新应用)" if fix and changed else ""))
    return rows


# ---------------------------------------------------------------------------
# 设置级去广告(settings.conf)
# ---------------------------------------------------------------------------
def apply_settings(dev: Adb, entries: list, dry_run: bool = False,
                   base=HOME_DIR, log=print) -> dict:
    """写入系统设置(命名空间 global/secure/system), 旧值记入 state 供还原。

    写入后会回读校验: 部分国产 ROM(实测 ColorOS 13)禁止 adb shell 写入
    settings(SecurityException: WRITE_SETTINGS 未授予 shell), 此时如实报告
    失败并提示手动操作, 不会误报成功; 写入未生效的项也不记入 state。
    """
    state = load_state(dev.serial, base)
    state.setdefault("settings", {})
    result = {"ok": [], "fail": []}
    for e in entries:
        ns, key, val = e["ns"], e["key"], e["value"]
        skey = f"{ns}:{key}"
        old = dev.shell(f"settings get {ns} {key}")
        if skey not in state["settings"]:
            state["settings"][skey] = old
        if dry_run:
            log(f"[预演] settings put {ns} {key} {val}  # {e['comment']}")
            result["ok"].append(skey)
            continue
        out = dev.shell_all(f"settings put {ns} {key} {val}")
        back = dev.shell(f"settings get {ns} {key}")
        if back == str(val):
            log(f"[已设置] {ns} {key} -> {val}  # {e['comment']}")
            result["ok"].append(skey)
        else:
            if "SecurityException" in out or "not granted" in out:
                hint = ("该 ROM 禁止 adb 写入系统设置(实测 ColorOS 13 已封禁 "
                        "shell 的 WRITE_SETTINGS 权限), 请按品牌 README 手动操作")
            else:
                hint = out or f"回读值不符(期望 {val}, 实际 {back or '空'})"
            log(f"[失败] {ns} {key} -> {val}: {hint}")
            result["fail"].append(skey)
            # 写入未生效, 不保留旧值记录(避免 restore 时无意义地回写)
            if old == state["settings"].get(skey):
                state["settings"].pop(skey, None)
    state["updated"] = dt.datetime.now().isoformat(timespec="seconds")
    save_state(state, base)
    return result


# ---------------------------------------------------------------------------
# Private DNS 去广告(带自愈: 解析失败自动回退, 参考 CleanYourAndroid)
# ---------------------------------------------------------------------------
DEFAULT_DNS_HOST = "dns.adguard-dns.com"
HOSTNAME_RE = re.compile(r"^[A-Za-z0-9.-]+$")


def _resolves(dev: Adb, host: str) -> bool:
    out = dev.shell(f"ping -c 1 -W 3 {host}")
    return "PING" in out


def dns_on(dev: Adb, host: str = DEFAULT_DNS_HOST, base=HOME_DIR, log=print) -> bool:
    """开启 Private DNS(DoT)。若 6 次探测都无法解析(网络封锁 853 端口),
    自动回退到 opportunistic 并报错, 不会把手机网络搞挂。"""
    if not HOSTNAME_RE.match(host):
        raise AdbError(f"非法 DNS 主机名: {host}")
    state = load_state(dev.serial, base)
    state.setdefault("settings", {})
    for k in ("global:private_dns_mode", "global:private_dns_specifier"):
        if k not in state["settings"]:
            ns, _, key = k.partition(":")
            state["settings"][k] = dev.shell(f"settings get {ns} {key}")
    dev.shell(f"settings put global private_dns_specifier {host}")
    dev.shell("settings put global private_dns_mode hostname")
    log(f"[进行中] Private DNS 已设为 {host}, 正在验证解析(最多 6 次)...")
    for i in range(6):
        time.sleep(3)
        if _resolves(dev, "www.google.com"):
            if _resolves(dev, "doubleclick.net"):
                log(f"[提示] {host} 已生效, 但 doubleclick.net 仍可解析, "
                    "请确认该 DNS 是否具备去广告能力")
            else:
                log(f"[OK] Private DNS({host}) 已生效: 正常网站可访问, "
                    "doubleclick.net 等广告域已被拦截")
            state["updated"] = dt.datetime.now().isoformat(timespec="seconds")
            save_state(state, base)
            return True
        log(f"[验证] 第 {i + 1} 次解析失败, 重试...")
    dev.shell("settings put global private_dns_mode opportunistic")
    dev.shell("settings delete global private_dns_specifier")
    state["settings"].pop("global:private_dns_specifier", None)
    state["settings"].pop("global:private_dns_mode", None)
    save_state(state, base)
    raise AdbError(
        f"通过 {host} 无法解析任何域名(当前网络可能封锁了 DoT 的 853 端口), "
        "已自动回退为“自动”模式, 手机网络不受影响"
    )


def dns_off(dev: Adb, base=HOME_DIR, log=print):
    state = load_state(dev.serial, base)
    state.setdefault("settings", {})
    for k in ("global:private_dns_mode", "global:private_dns_specifier"):
        if k not in state["settings"]:
            ns, _, key = k.partition(":")
            state["settings"][k] = dev.shell(f"settings get {ns} {key}")
    dev.shell("settings put global private_dns_mode opportunistic")
    dev.shell("settings delete global private_dns_specifier")
    log("[OK] Private DNS 已关闭(恢复为“自动”模式)")


def dns_status(dev: Adb, log=print):
    mode = dev.shell("settings get global private_dns_mode")
    host = dev.shell("settings get global private_dns_specifier")
    log(f"private_dns_mode={mode or '未设置'}  private_dns_specifier={host or '未设置'}")


# ---------------------------------------------------------------------------
# 摇一摇封杀(appops 限制传感器)
# ---------------------------------------------------------------------------
def shake_on(dev: Adb, pkgs: list, base=HOME_DIR, log=print) -> dict:
    """对已安装的 App 限制传感器(加速度计/陀螺仪/身体传感器),
    终结“摇一摇”开屏广告跳转; 不影响 App 其他功能。"""
    installed = list_packages(dev)
    state = load_state(dev.serial, base)
    state.setdefault("shake", {})
    result = {"ok": [], "missing": [], "fail": []}
    for pkg in pkgs:
        if pkg not in installed:
            result["missing"].append(pkg)
            continue
        applied = []
        for op in SHAKE_OPS:
            out = dev.shell_all(f"appops set {pkg} {op} ignore")
            low = out.lower()
            if "error" in low or "unknown" in low or "bad" in low:
                continue  # 该 ROM 不支持此 op, 静默跳过
            applied.append(op)
        if applied:
            state["shake"][pkg] = applied
            result["ok"].append(pkg)
            log(f"[已封杀] {pkg} 传感器({'+'.join(applied)})")
        else:
            result["fail"].append(pkg)
            log(f"[失败] {pkg}: 当前 ROM 不支持相关传感器 op")
    state["updated"] = dt.datetime.now().isoformat(timespec="seconds")
    save_state(state, base)
    if result["missing"]:
        log(f"[跳过] {len(result['missing'])} 个未安装: {' '.join(result['missing'])}")
    return result


def shake_off(dev: Adb, pkgs: list = None, base=HOME_DIR, log=print) -> dict:
    """还原传感器限制(恢复为 default 模式)。"""
    state = load_state(dev.serial, base)
    recorded = state.get("shake", {})
    targets = pkgs if pkgs else list(recorded.keys())
    result = {"ok": [], "fail": []}
    for pkg in targets:
        ops = recorded.get(pkg, list(SHAKE_OPS))
        for op in ops:
            dev.shell(f"appops set {pkg} {op} default")
        recorded.pop(pkg, None)
        result["ok"].append(pkg)
        log(f"[已还原] {pkg} 传感器限制")
    state["updated"] = dt.datetime.now().isoformat(timespec="seconds")
    save_state(state, base)
    if not targets:
        log("没有记录的传感器限制。")
    return result


def shake_status(dev: Adb, pkgs: list = None, base=HOME_DIR, log=print):
    state = load_state(dev.serial, base)
    recorded = state.get("shake", {})
    targets = pkgs if pkgs else list(recorded.keys())
    if not targets:
        log("没有记录的传感器限制。运行 shake on 启用。")
        return
    for pkg in targets:
        modes = []
        for op in recorded.get(pkg, list(SHAKE_OPS)):
            out = dev.shell(f"appops get {pkg} {op}")
            modes.append(f"{op}={out.strip() or 'default'}")
        log(f"{pkg}: {'  '.join(modes)}")


# ---------------------------------------------------------------------------
# 广告/遥测审计
# ---------------------------------------------------------------------------
AUDIT_RULES = [
    ("广告与推广服务", ["systemadsolution", "msa", "adservices", "adservice",
                        "pictorial", "spage", "mipicks", "contentextension",
                        "habit.analysis", "magazine", "livecontent", "space"]),
    ("统计与遥测", ["analytics", "statistics", "mab", "imonitor", "logkit",
                    "bugreport", "telemetry", "onetrack", "aon"]),
    ("内容推荐/资讯", ["personalassistant", "quicksearchbox", "reader",
                       "video", "player", "music", "browser", "hiboard"]),
]


def audit_device(dev: Adb, log=print) -> dict:
    installed = list_packages(dev)
    disabled = list_disabled(dev)
    found = {}
    for pkg in sorted(installed):
        low = pkg.lower()
        for cat, keys in AUDIT_RULES:
            if any(k in low for k in keys):
                found.setdefault(cat, []).append(pkg)
                break
    if not found:
        log("未发现已知的广告/遥测候选包。")
        return found
    for cat, pkgs in found.items():
        log(f"\n== {cat} ({len(pkgs)}) ==")
        for p in pkgs:
            tag = "[已禁用]" if p in disabled else ""
            log(f"  {p} {tag}")
    log("\n提示: 以上为启发式候选, 建议逐条确认后再用 apply 处理; "
        "也可用 --write 生成待确认列表。")
    return found


def write_audit_list(dev: Adb, path, log=print) -> Path:
    found = audit_device(dev, log=lambda *a, **k: None)
    lines = [
        "# CleanYourPhone 审计生成的候选列表(请逐条确认后再应用)",
        "# 用法: tools/disable.sh <本文件>",
        "",
    ]
    for cat, pkgs in found.items():
        lines.append(f"# ---------- {cat} ----------")
        for p in pkgs:
            lines.append(f"{p} disable")
        lines.append("")
    out = Path(path)
    out.write_text("\n".join(lines), encoding="utf-8")
    log(f"已写入候选列表: {out}")
    return out


# ---------------------------------------------------------------------------
# 自动清单: 本机预装应用 × 互联网聚合知识库
#   知识库由 tools/harvest.py 生成(rules/known-packages.json),
#   收录 UAD-NG 结构化分级 + GitHub/Gitee 社区列表与教程帖的共识。
# ---------------------------------------------------------------------------
KNOWN_DB_FILE = Path(__file__).resolve().parent.parent / "rules" / "known-packages.json"

# 系统分区前缀(命中即视为"出厂预装", 而非用户自己装的)
SYSTEM_PARTITIONS = (
    "/system/", "/system_ext/", "/product/", "/vendor/", "/odm/", "/oem/",
    "/my_product/", "/my_heytap/", "/my_stock/", "/my_preload/",
    "/my_carrier/", "/prism/", "/opt/", "/cust/", "/version/", "/special_preload/",
)

# 分级 -> 允许自动处理的等级
TIER_LEVELS = {
    "safe": ("Recommended",),
    "standard": ("Recommended", "Advanced"),
    "aggressive": ("Recommended", "Advanced", "Expert"),
}

# 服务型包优先"禁用"而非"卸载"(避免依赖它的功能报错)
SERVICE_HINTS = (
    "service", "provider", "daemon", "analytics", "statistics", "statistic",
    "telemetry", "push", "mcs", "msa", "tracker", "agent", "sdk", "receiver",
    "collect", "report",
)

# 启发式规则: 只对厂商预装命名空间生效(不会误伤用户自己装的应用)
HEURISTIC_RULES = (
    ("广告/推广服务", ("systemadsolution", "msa", "adservices", "adservice",
                       "pictorial", "spage", "mipicks", "contentextension",
                       "habit.analysis", "magazine", "livecontent",
                       "advert", "promotion", "splash", "dsp")),
    ("统计/遥测上报", ("analytics", "statistics", "statistic", "mab", "imonitor",
                       "logkit", "bugreport", "telemetry", "onetrack", "onetrace",
                       "crashbox", "diagnos", "experience")),
    ("内容推荐/信息流", ("personalassistant", "quicksearchbox", "searchbox",
                         "reader", "news", "feed", "hiboard", "video", "music",
                         "browser", "game", "mall", "shop", "store")),
)
VENDOR_NS = ("com.miui.", "com.xiaomi.", "com.mi.", "com.huawei.", "com.hihonor.",
             "com.oppo.", "com.coloros.", "com.heytap.", "com.oplus.",
             "com.nearme.", "com.realme.", "com.vivo.", "com.bbk.", "com.iqoo.",
             "com.samsung.", "com.sec.", "com.meizu.")

# ---------------------------------------------------------------------------
# 谨慎名单: 这些包 UAD 常标"推荐", 但在国内机型上删了会丢功能/丢数据/丢保修,
# 默认只提示不处理; 确认不需要时加 --allow-caution。
# (真机实测 OPPO ColorOS 13 时发现的问题, 见 examples/oppo-coloros/device-inventory.md)
# ---------------------------------------------------------------------------
CAUTION_RULES = (
    (r"findmyphone|findmydevice|find_my|antitheft|anti_theft|remoteguard",
     "防盗/查找手机(删了无法定位与远程锁定)"),
    (r"securepay|payment|wallet|(^|\.)pay($|\.)", "支付与支付安全"),
    (r"codebook|password", "密码本(可能存有已保存的密码)"),
    (r"(^|\.)cloud($|\.)|cloudservice|cloudsync", "云同步/云备份"),
    (r"usercenter|(^|\.)account($|\.)|(^|\.)auth", "厂商账号(删了会退出登录)"),
    (r"softsim|esim", "虚拟 SIM"),
    (r"(^|\.)ota($|\.)|updater|softwareupdate", "系统更新"),
    (r"backup|restore", "备份恢复"),
    (r"speechsuite|iflytek", "语音识别(语音输入/语音助手依赖)"),
    (r"accessibility", "无障碍服务"),
    (r"remoteprovisioner|attestation", "设备认证(部分银行/支付 App 会校验)"),
    (r"childrenspace|parental", "儿童/家长模式"),
)
CAUTION_RE = [(re.compile(p, re.I), why) for p, why in CAUTION_RULES]


def caution_reason(pkg: str):
    for r, why in CAUTION_RE:
        if r.search(pkg):
            return why
    return None


def resolve_default_browser(dev: Adb):
    """当前默认浏览器包名(删了它, 点链接会没有应用可打开)。"""
    try:
        out = dev.shell(
            "cmd package resolve-activity -a android.intent.action.VIEW "
            "-d https://example.com --brief")
    except Exception:
        return None
    for raw in reversed(out.splitlines()):
        line = raw.strip()
        if not line or line.startswith(("priority=", "match=", "name=")):
            continue
        pkg = line.split("/")[0].strip()
        if pkg and "." in pkg and " " not in pkg:
            return pkg
    return None


def partition_of(path: str) -> str:
    if not path:
        return "?"
    for p in SYSTEM_PARTITIONS:
        if path.startswith(p):
            return p.strip("/")
    if path.startswith("/data/app"):
        return "data"
    return path.strip("/").split("/", 1)[0] or "?"


def _parse_pm_list_f(out: str) -> dict:
    """解析 `pm list packages -f`: package:<apk路径>=<包名> -> {包名: 路径}。"""
    rows = {}
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("package:"):
            continue
        body = line[len("package:"):]
        if "=" in body:
            path, pkg = body.rsplit("=", 1)
        else:
            path, pkg = "", body
        rows[pkg.strip()] = path.strip()
    return rows


def preinstalled_packages(dev: Adb, include_third_party: bool = False) -> dict:
    """列出出厂预装应用 -> {包名: 安装路径}。

    默认只取 `pm list packages -s`(系统分区应用); include_third_party=True
    时把 /data/app 下的第三方包也纳入(部分国产 ROM 会把合作 App 预装到
    data 分区), 这类包无法与"用户自己安装"区分, 需谨慎。
    """
    rows = _parse_pm_list_f(dev.shell("pm list packages -s -f"))
    if include_third_party:
        for pkg, path in _parse_pm_list_f(
                dev.shell("pm list packages -3 -f")).items():
            rows.setdefault(pkg, path)
    return rows


def load_known_db(path=None) -> tuple:
    """读取聚合知识库, 返回 (meta, packages)。"""
    p = Path(path) if path else KNOWN_DB_FILE
    if not p.exists():
        raise FileNotFoundError(
            f"知识库不存在: {p}\n"
            "请先运行: python3 tools/harvest.py  (从 UAD-NG/GitHub/Gitee 聚合)")
    data = json.loads(p.read_text(encoding="utf-8"))
    pkgs = data.get("packages") or {}
    if not isinstance(pkgs, dict) or not pkgs:
        raise ValueError(f"知识库格式异常或为空: {p}")
    return data.get("meta") or {}, pkgs


def default_action(pkg: str) -> str:
    low = pkg.lower()
    return "disable" if any(h in low for h in SERVICE_HINTS) else "uninstall"


def heuristic_hit(pkg: str):
    """厂商预装命名空间里的广告/遥测特征命中, 返回 (分类, 关键词) 或 None。"""
    if not pkg.startswith(VENDOR_NS):
        return None
    low = pkg.lower()
    for cat, keys in HEURISTIC_RULES:
        for k in keys:
            if k in low:
                return cat, k
    return None


def auto_candidates(dev: Adb, db: dict, tier: str = "standard",
                    include_third_party: bool = False,
                    include_heuristic: bool = True,
                    min_sources: int = 1, allow_caution: bool = False,
                    exclude_re: str = "", log=print) -> dict:
    """生成自动候选: 本机预装 ∩ 知识库(按分级) + 启发式补充。

    安全护栏(与 apply 一致, 但更严):
      * 命中 DENY 规则/显式核心清单 -> 剔除
      * 当前桌面/最近任务/输入法/默认浏览器 -> 剔除
      * 知识库标 Unsafe -> 剔除
      * 依赖核心组件、或被核心组件依赖 -> 剔除
      * 命中谨慎名单(查找手机/支付/账号/云服务/系统更新等) -> 默认只提示
    """
    levels = TIER_LEVELS.get(tier, TIER_LEVELS["standard"])
    installed = preinstalled_packages(dev, include_third_party)
    protect = protected_targets(dev)
    prot = {p for p in protect.values() if p}
    browser = resolve_default_browser(dev)

    ex = re.compile(exclude_re) if exclude_re else None
    rows, blocked, skipped_dep, caution = [], [], [], []
    for pkg, path in sorted(installed.items()):
        if is_denied(pkg) or pkg in prot:
            continue
        if ex and ex.search(pkg):
            continue
        rec = db.get(pkg)
        cand = None
        if rec:
            lvl = rec.get("r") or "Community"
            if lvl == "Unsafe":
                blocked.append(pkg)
                continue
            if lvl not in levels:
                continue
            if len(rec.get("s") or []) < min_sources:
                continue
            dep = set(rec.get("dep") or [])
            if dep & PROTECTED_PACKAGES:
                skipped_dep.append(pkg)
                continue
            nb = set(rec.get("nb") or [])
            if nb & PROTECTED_PACKAGES:
                # 被核心系统组件依赖(如"设置"依赖某个服务)
                skipped_dep.append(pkg)
                continue
            cand = {
                "pkg": pkg, "level": lvl, "action": rec.get("a") or default_action(pkg),
                "desc": (rec.get("d") or "").strip(), "path": path,
                "partition": partition_of(path), "sources": len(rec.get("s") or []),
                "nb": nb, "kind": "kb",
            }
        elif include_heuristic:
            hit = heuristic_hit(pkg)
            if hit:
                cat, kw = hit
                cand = {
                    "pkg": pkg, "level": "Heuristic", "action": "disable",
                    "desc": f"{cat}(命中关键词 {kw}, 知识库未收录)",
                    "path": path, "partition": partition_of(path), "sources": 0,
                    "nb": set(), "kind": "heuristic",
                }
        if cand is None:
            continue
        # 谨慎名单: 删了会丢功能/丢数据, 默认只提示
        why = caution_reason(pkg)
        if not why and pkg == browser:
            why = "当前默认浏览器(删了点链接没有应用可打开)"
        if why and not allow_caution:
            caution.append((pkg, why))
            continue
        if why:
            cand["desc"] = f"[谨慎:{why}] {cand['desc']}"
        rows.append(cand)

    # 依赖保护: 候选包若是某个"将被保留的包"的依赖, 则剔除
    remove = {r["pkg"] for r in rows}
    kept = set(installed) - remove
    for r in list(rows):
        if r["nb"] & kept and r["kind"] == "kb":
            rows.remove(r)
            skipped_dep.append(r["pkg"])

    order = {"Recommended": 0, "Advanced": 1, "Expert": 2, "Community": 3,
             "Heuristic": 4}
    rows.sort(key=lambda r: (order.get(r["level"], 9), r["pkg"]))
    return {
        "rows": rows, "installed": len(installed), "blocked": blocked,
        "skipped_dep": skipped_dep, "caution": caution, "tier": tier,
        "protect": protect, "browser": browser,
        "protected_hit": sorted(set(installed) & prot),
    }


def write_auto_list(rows: list, path, desc: dict) -> Path:
    lines = [
        f"# CleanYourPhone 自动生成清单 — {desc.get('brand','')} {desc.get('model','')}",
        f"# 生成时间: {now_ts()}  Android {desc.get('android','')} "
        f"{('ROM ' + desc['rom']) if desc.get('rom') else ''}",
        "# 来源: rules/known-packages.json (UAD-NG + GitHub/Gitee 社区共识)",
        "# 恢复: python3 tools/phone.py restore --all",
        "",
    ]
    cur = None
    for r in rows:
        if r["level"] != cur:
            cur = r["level"]
            lines.append(f"# ---------- {cur} ----------")
        note = r["desc"].replace("\n", " ")[:90]
        lines.append(f"{r['pkg']} {r['action']}  # {note}".rstrip())
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# 命令行接口
# ---------------------------------------------------------------------------
def confirm(prompt: str) -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="phone.py",
        description="CleanYourPhone — 国产手机清理工具(无 root/不装软件/可逆)")
    ap.add_argument("--serial", "-s", help="指定设备序列号(多设备时必填)")
    ap.add_argument("--version", action="version", version=f"CleanYourPhone {VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="自检 adb 与设备连接")
    sub.add_parser("info", help="设备信息与推荐列表")

    p = sub.add_parser("pair", help="Android 11+ 无线调试配对")
    p.add_argument("ip_port", help="形如 192.168.1.50:37123")
    p.add_argument("code", help="配对码")

    p = sub.add_parser("connect", help="连接无线设备")
    p.add_argument("target", help="形如 192.168.1.50 或 192.168.1.50:5555")

    p = sub.add_parser("disconnect", help="断开无线连接")
    p.add_argument("target", nargs="?", help="省略则断开全部")

    p = sub.add_parser("tcpip", help="(USB 连接时)开启无线调试端口")
    p.add_argument("port", nargs="?", type=int, default=DEFAULT_WIRELESS_PORT)

    p = sub.add_parser("shell", help="在手机上执行 shell 命令")
    p.add_argument("command", help='例如: "pm list packages -d"')

    p = sub.add_parser("packages", help="列出包")
    p.add_argument("--uninstalled", action="store_true", help="含对用户已卸载的包")
    p.add_argument("--disabled", action="store_true", help="仅已禁用的包")

    p = sub.add_parser("screenshot", help="截图(验证分批清理后的界面)")
    p.add_argument("name", nargs="?", help="文件名(可选)")

    sub.add_parser("backup", help="备份包列表与系统设置")

    p = sub.add_parser("apply", help="应用清理列表")
    p.add_argument("list", help="列表文件, 如 examples/xiaomi-hyperos/debloat.txt")
    p.add_argument("--dry-run", action="store_true", help="只预演不执行")
    p.add_argument("--yes", "-y", action="store_true", help="跳过确认")
    p.add_argument("--no-backup", action="store_true", help="跳过自动备份(不建议)")
    p.add_argument("--batch", type=int, default=0, metavar="N",
                   help="每批处理 N 个(0=一次性全部), 配合 --screenshot 逐批验证")
    p.add_argument("--screenshot", action="store_true",
                   help="每批处理后自动截图到 ~/.cleanyourphone/<序列号>/shots/")

    p = sub.add_parser("restore", help="恢复(包/设置/传感器限制)")
    p.add_argument("list", nargs="?", help="列表文件; 与 --all 二选一")
    p.add_argument("--all", action="store_true", help="恢复 state 记录中的所有包")
    p.add_argument("--yes", "-y", action="store_true", help="跳过确认")

    p = sub.add_parser("check", help="检查列表状态(OTA 后用)")
    p.add_argument("list", help="列表文件")
    p.add_argument("--fix", action="store_true", help="把状态变化的项重新应用")
    p.add_argument("--yes", "-y", action="store_true", help="修复时跳过确认")

    p = sub.add_parser("audit", help="扫描广告/遥测候选包")
    p.add_argument("--write", metavar="文件", help="把候选写入列表文件")

    p = sub.add_parser("auto", help="自动识别本机预装并清理(基于互联网聚合库)")
    p.add_argument("--tier", choices=["safe", "standard", "aggressive"],
                   default="standard",
                   help="清理力度: safe=仅推荐项 / standard=推荐+进阶(默认) / "
                        "aggressive=再加专家项与启发式")
    p.add_argument("--apply", action="store_true",
                   help="真正执行(默认只生成清单, 不动手机)")
    p.add_argument("--yes", "-y", action="store_true", help="执行时跳过确认")
    p.add_argument("--write", metavar="文件", help="清单保存路径")
    p.add_argument("--db", metavar="文件", help="指定知识库(默认 rules/known-packages.json)")
    p.add_argument("--include-third-party", action="store_true",
                   help="把 /data/app 下的预装第三方 App 也纳入(默认不含)")
    p.add_argument("--no-heuristic", action="store_true",
                   help="只按知识库匹配, 不用启发式规则补充")
    p.add_argument("--min-sources", type=int, default=1, metavar="N",
                   help="知识库条目至少被 N 个来源收录才处理(默认 1)")
    p.add_argument("--allow-caution", action="store_true",
                   help="允许处理谨慎名单(查找手机/支付/账号/云服务/系统更新等)")
    p.add_argument("--exclude", default="", metavar="正则",
                   help="排除匹配该正则的包名, 如 --exclude 'browser|music'")
    p.add_argument("--limit", type=int, default=0, metavar="N",
                   help="最多列出/处理 N 项(0=不限)")

    p = sub.add_parser("settings", help="写入系统设置(settings.conf)")
    p.add_argument("file", help="如 examples/xiaomi-hyperos/settings.conf")
    p.add_argument("--dry-run", action="store_true", help="只预演不执行")

    p = sub.add_parser("dns", help="Private DNS 去广告")
    p.add_argument("action", choices=["on", "off", "status"])
    p.add_argument("host", nargs="?", default=DEFAULT_DNS_HOST,
                   help=f"DNS 主机名(默认 {DEFAULT_DNS_HOST}; 国内可用 dot.pub)")

    p = sub.add_parser("shake", help="封杀第三方 App “摇一摇”开屏广告")
    p.add_argument("action", choices=["on", "off", "status"])
    p.add_argument("list", nargs="?", default="examples/shake_apps.txt",
                   help="应用清单文件, 或 off/status 时的单个包名")
    p.add_argument("--yes", "-y", action="store_true", help="跳过确认")

    sub.add_parser("finish", help="收尾: 关闭 USB 调试并断开无线连接")
    return ap


def _need_device(args):
    adb = Adb()
    serial = pick_device(adb, args.serial)
    return adb, Adb(adb.adb, serial)


def cmd_doctor(args) -> int:
    try:
        adb_path = ensure_adb()
    except AdbError as e:
        print(f"[失败] {e}")
        return 2
    print(f"[OK] adb: {adb_path}")
    adb = Adb(adb_path)
    try:
        serial = pick_device(adb, args.serial)
    except AdbError as e:
        print(f"[失败] {e}")
        devs = adb.devices()
        if devs:
            print("adb devices -l 输出:")
            for d in devs:
                print("   ", d["raw"])
        return 2
    print(f"[OK] 设备已连接: {serial}")
    dev = Adb(adb_path, serial)
    desc = describe_device(dev)
    print(f"[OK] 品牌/型号: {desc['brand']} {desc['model']}")
    print(f"[OK] Android {desc['android']} (SDK {desc['sdk']})"
          + (f" | ROM: {desc['rom']}" if desc["rom"] else ""))
    protect = protected_targets(dev)
    for label, key in (("桌面", "home"), ("最近任务", "recents"), ("输入法", "ime")):
        if protect.get(key):
            print(f"[OK] 当前{label}: {protect[key]}(清理时自动保护)")
    print(f"[建议] 清理列表: {desc['example']}")
    print("[下一步] 预演: python3 tools/phone.py apply "
          f"{desc['example']}/debloat.txt --dry-run")
    print("         设置级去广告: python3 tools/phone.py settings "
          f"{desc['example']}/settings.conf --dry-run")
    print("         摇一摇封杀:   python3 tools/phone.py shake status")
    return 0


def cmd_info(args) -> int:
    _, dev = _need_device(args)
    desc = describe_device(dev)
    protect = protected_targets(dev)
    print(f"序列号:   {dev.serial}")
    print(f"品牌:     {desc['brand']}")
    print(f"型号:     {desc['model']}"
          + (f"({desc['marketname']})" if desc.get("marketname") else ""))
    print(f"ROM:      {desc['rom'] or '未知'}")
    print(f"Android:  {desc['android']} (SDK {desc['sdk']})")
    print(f"Build:    {desc['display'] or '未知'}")
    print(f"桌面:     {protect.get('home') or '解析失败'}")
    print(f"最近任务: {protect.get('recents') or '解析失败'}")
    print(f"输入法:   {protect.get('ime') or '解析失败'}")
    print(f"推荐列表: {desc['example']}")
    return 0


def cmd_pair(args) -> int:
    adb = Adb()
    proc = adb.run("pair", args.ip_port, args.code)
    print(proc.stdout.strip() or proc.stderr.strip())
    return 0 if proc.returncode == 0 else 2


def cmd_connect(args) -> int:
    adb = Adb()
    proc = adb.run("connect", args.target)
    print(proc.stdout.strip() or proc.stderr.strip())
    return 0 if proc.returncode == 0 else 2


def cmd_disconnect(args) -> int:
    adb = Adb()
    proc = adb.run(*((["disconnect", args.target]) if args.target else ["disconnect"]))
    print(proc.stdout.strip() or proc.stderr.strip())
    return 0


def cmd_tcpip(args) -> int:
    _, dev = _need_device(args)
    proc = dev.run("tcpip", args.port)
    print(proc.stdout.strip() or proc.stderr.strip())
    print("提示: 现在可以运行 connect <手机IP> 进行无线连接(需手机与电脑同一 Wi-Fi)")
    return 0 if proc.returncode == 0 else 2


def cmd_shell(args) -> int:
    _, dev = _need_device(args)
    print(dev.shell(args.command))
    return 0


def cmd_packages(args) -> int:
    _, dev = _need_device(args)
    if args.disabled:
        out = dev.shell("pm list packages -d")
    elif args.uninstalled:
        out = dev.shell("pm list packages -u")
    else:
        out = dev.shell("pm list packages")
    print(out)
    return 0


def cmd_screenshot(args) -> int:
    _, dev = _need_device(args)
    name = args.name or f"shot-{now_ts()}.png"
    p = dev.screenshot(HOME_DIR / dev.serial / "shots" / name)
    print(f"截图已保存: {p}")
    return 0


def cmd_backup(args) -> int:
    _, dev = _need_device(args)
    d = backup_device(dev, label="manual")
    print(f"备份完成: {d}")
    return 0


def cmd_apply(args) -> int:
    _, dev = _need_device(args)
    entries = parse_list_file(args.list)
    print(f"列表 {args.list} 共 {len(entries)} 个条目")
    if not args.dry_run and not args.yes and not confirm(
            f"将对设备 {dev.serial} 执行 {len(entries)} 项操作, 继续? [y/N] "):
        print("已取消。可先加 --dry-run 预演。")
        return 1
    apply_list(dev, entries, list_file=args.list, dry_run=args.dry_run,
               do_backup=not args.no_backup, batch=args.batch,
               screenshot=args.screenshot)
    if not args.dry_run:
        print("")
        print("恢复命令: python3 tools/phone.py restore "
              f"{args.list}   (或 --all 全部恢复)")
        print("OTA 后检查: python3 tools/phone.py check "
              f"{args.list} --fix")
    return 0


def cmd_restore(args) -> int:
    _, dev = _need_device(args)
    state = load_state(dev.serial)
    if args.all:
        pkgs = list(state.get("packages", {}).keys())
        src = "state 记录"
    elif args.list:
        entries = parse_list_file(args.list)
        pkgs = [e["pkg"] for e in entries]
        src = args.list
    else:
        print("请指定列表文件或使用 --all")
        return 2
    extra = bool(state.get("settings") or state.get("shake"))
    if not pkgs and not extra:
        print(f"{src} 中没有需要恢复的内容。")
        return 0
    if not args.yes and not confirm(
            f"将恢复 {len(pkgs)} 个包"
            + ("及设置/传感器限制" if extra else "") + ", 继续? [y/N] "):
        print("已取消。")
        return 1
    restore_pkgs(dev, pkgs, state)
    return 0


def cmd_check(args) -> int:
    _, dev = _need_device(args)
    entries = parse_list_file(args.list)
    if args.fix and not args.yes and not confirm("将对变化项重新执行操作, 继续? [y/N] "):
        print("已取消。")
        return 1
    check_list(dev, entries, fix=args.fix)
    return 0


def cmd_audit(args) -> int:
    _, dev = _need_device(args)
    if args.write:
        write_audit_list(dev, args.write)
    else:
        audit_device(dev)
    return 0


def cmd_auto(args) -> int:
    """自动清单: 本机预装 × 互联网聚合知识库。"""
    _, dev = _need_device(args)
    try:
        meta, db = load_known_db(args.db)
    except (FileNotFoundError, ValueError) as e:
        print(f"[失败] {e}")
        return 2

    desc = describe_device(dev)
    print(f"设备: {desc['brand']} {desc['model']} | Android {desc['android']}"
          + (f" | ROM {desc['rom']}" if desc["rom"] else ""))
    print(f"知识库: {len(db)} 个包 (生成于 {meta.get('generated_at', '未知')})")
    print(f"力度: {args.tier} | 启发式: {'关' if args.no_heuristic else '开'} | "
          f"最少来源数: {args.min_sources}")

    res = auto_candidates(
        dev, db, tier=args.tier,
        include_third_party=args.include_third_party,
        include_heuristic=not args.no_heuristic,
        min_sources=args.min_sources, allow_caution=args.allow_caution,
        exclude_re=args.exclude)

    rows = res["rows"]
    if args.limit and args.limit > 0:
        rows = rows[:args.limit]

    print(f"本机预装 {res['installed']} 个, 命中可清理 {len(rows)} 个")
    for label, key in (("桌面", "home"), ("最近任务", "recents"), ("输入法", "ime")):
        if res["protect"].get(key):
            print(f"[保护] 当前{label}: {res['protect'][key]}")
    if res["blocked"]:
        print(f"[跳过] {len(res['blocked'])} 个被知识库标为 Unsafe(会破坏系统): "
              f"{', '.join(res['blocked'][:5])}"
              + (" ..." if len(res["blocked"]) > 5 else ""))
    if res["skipped_dep"]:
        print(f"[跳过] {len(res['skipped_dep'])} 个被其他组件依赖: "
              f"{', '.join(res['skipped_dep'][:5])}"
              + (" ..." if len(res["skipped_dep"]) > 5 else ""))
    if res["caution"]:
        print(f"[谨慎] {len(res['caution'])} 个涉及查找手机/支付/账号/云服务等, "
              "默认不动(确认不需要可加 --allow-caution):")
        for pkg, why in res["caution"][:8]:
            print(f"        {pkg}  — {why}")
        if len(res["caution"]) > 8:
            print(f"        ... 其余 {len(res['caution']) - 8} 个")

    if not rows:
        print("\n没有可自动清理的预装应用。")
        print("提示: 想更激进可加 --tier aggressive; 或先运行 "
              "python3 tools/harvest.py 更新知识库。")
        return 0

    cur = None
    for r in rows:
        if r["level"] != cur:
            cur = r["level"]
            n = sum(1 for x in rows if x["level"] == cur)
            print(f"\n== {cur} ({n}) ==")
        note = r["desc"].replace("\n", " ")[:64]
        src = f"{r['sources']}源" if r["sources"] else "启发式"
        print(f"  {r['action']:9s} {r['pkg']:44s} {r['partition']:12s} "
              f"{src:5s} {note}")

    out = Path(args.write) if args.write else (
        Path(HOME_DIR) / dev.serial / "auto-list.txt")
    saved = write_auto_list(rows, out, desc)
    print(f"\n清单已保存: {saved}")

    if not args.apply:
        print("这是预演(未改动手机)。确认无误后执行:")
        print(f"  python3 tools/phone.py auto --tier {args.tier} --apply")
        return 0

    if not args.yes and not confirm(f"将处理 {len(rows)} 个预装应用, 继续? [y/N] "):
        print("已取消。")
        return 1
    entries = [{"pkg": r["pkg"], "action": r["action"], "comment": r["desc"]}
               for r in rows]
    apply_list(dev, entries, list_file=str(saved), base=HOME_DIR)
    print("\n恢复: python3 tools/phone.py restore --all")
    return 0


def cmd_settings(args) -> int:
    _, dev = _need_device(args)
    entries = parse_settings_file(args.file)
    print(f"设置文件 {args.file} 共 {len(entries)} 项")
    apply_settings(dev, entries, dry_run=args.dry_run)
    if not args.dry_run:
        print("提示: 恢复原值: python3 tools/phone.py restore --all")
    return 0


def cmd_dns(args) -> int:
    _, dev = _need_device(args)
    if args.action == "on":
        dns_on(dev, args.host)
    elif args.action == "off":
        dns_off(dev)
    else:
        dns_status(dev)
    return 0


def cmd_shake(args) -> int:
    _, dev = _need_device(args)
    if args.action == "on":
        pkgs = phone_shake_list(args.list)
        if not args.yes and not confirm(
                f"将对已安装的候选 App(共 {len(pkgs)} 个)限制传感器, 继续? [y/N] "):
            print("已取消。")
            return 1
        shake_on(dev, pkgs)
        print("提示: 计步/AR/运动类 App 若异常, 运行: "
              "python3 tools/phone.py shake off <包名>")
    elif args.action == "off":
        if args.list and Path(args.list).exists():
            pkgs = phone_shake_list(args.list)
        elif args.list:
            pkgs = [args.list]
        else:
            pkgs = None
        shake_off(dev, pkgs)
    else:
        shake_status(dev)
    return 0


def phone_shake_list(path) -> list:
    """从清单文件读取包名(兼容注释与空行)。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"清单文件不存在: {p}")
    pkgs = []
    for raw in p.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)", line)
        if m:
            pkgs.append(m.group(1))
    return pkgs


def cmd_finish(args) -> int:
    adb, dev = _need_device(args)
    dev.shell("settings put global adb_enabled 0")
    print("[OK] 已尝试关闭 USB 调试(设置项 adb_enabled)")
    print("     如未生效, 请手动: 设置 → 系统 → 开发者选项 → 关闭“USB 调试”")
    wireless = [d for d in adb.devices() if d["transport"] == "wifi"]
    if wireless:
        adb.run("disconnect")
        print("[OK] 已断开无线调试连接")
    print("[提示] 无线调试建议保持关闭, 需要时再临时打开。")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "doctor": cmd_doctor, "info": cmd_info, "pair": cmd_pair,
        "connect": cmd_connect, "disconnect": cmd_disconnect,
        "tcpip": cmd_tcpip, "shell": cmd_shell, "packages": cmd_packages,
        "screenshot": cmd_screenshot, "backup": cmd_backup, "apply": cmd_apply,
        "restore": cmd_restore, "check": cmd_check, "audit": cmd_audit,
        "auto": cmd_auto,
        "settings": cmd_settings, "dns": cmd_dns, "shake": cmd_shake,
        "finish": cmd_finish,
    }
    try:
        return handlers[args.cmd](args)
    except AdbError as e:
        print(f"[错误] {e}")
        return 2
    except FileNotFoundError as e:
        print(f"[错误] {e}")
        return 2
    except ValueError as e:
        print(f"[错误] {e}")
        return 2
    except KeyboardInterrupt:
        print("\n已取消。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
