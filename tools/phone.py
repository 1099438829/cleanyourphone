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
  rom [--list 文件]               识别 ROM 家族/版本, 说明该版本的卸载策略与清单适用性
  settings <settings.conf> [--dry-run]   写入系统设置(关闭广告/限制追踪)
  dns on [主机名] | off | status   Private DNS 去广告(带自愈: 解析失败自动关闭)
  shake on|off|status [清单]       封杀第三方 App "摇一摇"开屏广告(appops)
  chan scan|open|app|verify       营销通知渠道: 只读扫描 + 深链跳转手动关
  cutnet on|off|status [包名...]  给挂起的广告/统计包断网(防被系统拉起)
  ui dump|find|tap|switch|wait|open|back|home
                                  界面自动化: 读屏/找控件/点开关(纯 adb, 不装软件)
  adsw list|run|verify|explore    App 内广告开关: 按规则库自动拨(可预演)
  quickapp check|off              检测/关闭快应用(广告跳转的免安装小程序)
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
import xml.etree.ElementTree as ET
from pathlib import Path

VERSION = "2.4.0"
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
# 行格式: <包名> [uninstall|disable|freeze] [[v>=13]] [# 注释]
#   - 行首 # 为注释, 空行忽略; 兼容 CRLF 与 UTF-8 BOM
#   - 动作缺省为 uninstall
#   - freeze = 冻结: pm disable-user + 强制停止, 应用不可启动但数据/APK 保留,
#     pm enable 即恢复; 禁用被拒时自动降级 pm suspend(参考 Hail 的冻结语义)
#   - 版本标注可写在行尾或注释里: [v>=13] [v<12] [v=13.1] [v12-13]
#     版本不符的条目在 apply/check 时自动跳过(见 rom-profiles.json)
# ---------------------------------------------------------------------------
LIST_LINE_RE = re.compile(
    r"^(?P<pkg>[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)"   # 包名
    r"(?:\s+(?P<action>uninstall|disable|freeze))?"           # 可选动作
    r"(?:\s+(?P<gate>(?:\[[^\]]*\]\s*)+))?"                   # 可选版本标注
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
        comment = (m.group("comment") or "").strip()
        gates = parse_gates(m.group("gate") or "") + parse_gates(comment)
        entries.append({
            "pkg": m.group("pkg"),
            "action": m.group("action") or "uninstall",
            "comment": strip_gates(comment),
            "gates": gates,
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

    transport = "adb"

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


# ---------------------------------------------------------------------------
# hdc(HarmonyOS Debug Bridge)通道
#   HarmonyOS NEXT 5.x 起只提供 hdc, 没有 adb; 包管理换成 bm 工具:
#     hdc shell bm dump -a           列出所有已安装 bundle
#     hdc shell bm uninstall -n 包名  卸载(可加 -k 保留数据)
#     hdc shell bm clean -d -n 包名   清数据
#   注意: bm 没有 pm 的 disable/suspend 能力, 也拿不到安装分区,
#   因此 HarmonyOS NEXT 上"禁用/挂起/区分预装"都做不到, 只能卸载。
# ---------------------------------------------------------------------------
HDC_BIN_NAMES = ("hdc", "hdc_std", "hdc.exe", "hdc_std.exe")
HDC_HINT = (
    "未找到 hdc 工具。HarmonyOS NEXT(5.x)只能通过 hdc 调试:\n"
    "  方式一: 安装 DevEco Studio, hdc 在其 sdk/default/openharmony/toolchains/ 下\n"
    "          或安装「命令行工具」: https://device.harmonyos.com/cn/docs/apiref/"
    "harmonyos-guides/ide-commandline-get\n"
    "  方式二: 已有 hdc 时用环境变量指定: HDC=/path/to/hdc python3 tools/phone.py ..."
)


def _hdc_candidates() -> list:
    paths = []
    home = Path.home()
    if platform.system() == "Darwin":
        paths += [
            home / "command-line-tools/sdk/default/toolchains",
            home / "Library/Huawei/Sdk/toolchains",
            Path("/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains"),
            Path("/Applications/DevEco-Studio.app/Contents/sdk/hms/toolchains"),
            Path("/Applications/DevEco Studio.app/Contents/sdk/default/openharmony/toolchains"),
        ]
    elif platform.system() == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData/Local")))
        paths += [
            home / "command-line-tools/sdk/default/toolchains",
            local / "Huawei/Sdk/toolchains",
            Path("C:/DevEco Studio/sdk/default/openharmony/toolchains"),
            Path("D:/DevEco Studio/sdk/default/openharmony/toolchains"),
        ]
    else:
        paths += [
            home / "command-line-tools/sdk/default/toolchains",
            Path("/opt/command-line-tools/sdk/default/toolchains"),
            Path("/usr/local/command-line-tools/sdk/default/toolchains"),
        ]
    return paths


def ensure_hdc(verbose=True) -> str:
    """返回可用的 hdc 路径(不自动下载: 工具包较大且版本相关, 引导安装)。"""
    cand = os.environ.get("HDC")
    if cand and Path(cand).exists():
        return str(cand)
    found = None
    for name in HDC_BIN_NAMES:
        found = shutil.which(name)
        if found:
            return found
    for d in _hdc_candidates():
        for name in HDC_BIN_NAMES:
            p = d / name
            try:
                if p.is_file():
                    return str(p)
            except OSError:
                continue
    raise AdbError(HDC_HINT)


class Hdc:
    """hdc 的轻量封装, 接口与 Adb 对齐(transport="hdc")。"""

    transport = "hdc"

    def __init__(self, hdc_path=None, serial=None):
        self.adb = hdc_path or ensure_hdc()
        self.serial = serial

    def _cmd(self, *args):
        cmd = [self.adb]
        if self.serial:
            cmd += ["-t", self.serial]
        return cmd + [str(a) for a in args]

    def run(self, *args, timeout=120):
        return subprocess.run(
            self._cmd(*args), capture_output=True, text=True, timeout=timeout
        )

    def shell(self, command, timeout=120) -> str:
        proc = self.run("shell", command, timeout=timeout)
        return proc.stdout.strip().replace("\r", "")

    def shell_all(self, command, timeout=120) -> str:
        proc = self.run("shell", command, timeout=timeout)
        return (proc.stdout + proc.stderr).strip().replace("\r", "")

    def screenshot(self, path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = "/data/local/tmp/cyp_shot.png"
        out = self.shell(f"snapshot_display -f {tmp}")
        if "fail" in out.lower() and "success" not in out.lower():
            raise AdbError(f"截图失败: {out or '无输出'}(屏幕可能关闭, 请唤醒后重试)")
        proc = self.run("file", "recv", tmp, str(p), timeout=60)
        if not p.is_file() or p.stat().st_size == 0:
            raise AdbError(f"截图保存失败: {proc.stderr.strip() or '无输出'}")
        self.shell(f"rm -f {tmp}")
        return p

    def devices(self) -> list:
        try:
            proc = self.run("list", "targets")
        except Exception:
            return []
        out = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            low = line.lower()
            # hdc 没有设备时会打印 "[Fail]Not match target founded..." 之类的
            # 提示, 不能当成序列号(否则后续会拿报错文本去查 ROM)
            if low.startswith("[") or "fail" in low or "error" in low:
                continue
            if low.startswith("empty") or low.startswith("no target"):
                continue
            parts = line.split()
            serial = parts[0]
            if len(serial) < 6 or not re.match(r"^[\w.:\-]+$", serial):
                continue
            state = "device"
            if len(parts) > 2:
                st = parts[2].lower()
                if st not in ("connected", "device", "ready", "online"):
                    continue
            out.append({"serial": serial, "state": state,
                        "transport": "wifi" if ":" in serial else "usb",
                        "raw": line})
        return out


def is_hdc(dev) -> bool:
    return getattr(dev, "transport", "adb") == "hdc"


def hdc_list_bundles(dev) -> set:
    """`hdc shell bm dump -a` 解析出所有已安装 bundle 名。"""
    out = dev.shell("bm dump -a")
    pkgs = set()
    for line in out.splitlines():
        name = line.strip()
        if not name or " " in name or not name.startswith(("com.", "cn.", "org.",
                                                           "net.", "io.", "android.",
                                                           "ohos.")):
            continue
        pkgs.add(name)
    return pkgs


def hdc_uninstall(dev, pkg: str) -> tuple:
    """卸载 bundle(保留数据)。返回 (是否成功, 输出)。"""
    out = dev.shell(f"bm uninstall -n {pkg} -k")
    low = out.lower()
    ok = ("uninstall bundle successfully" in low or "successfully" in low
          or low.startswith("success"))
    return ok, out


def hdc_clean_data(dev, pkg: str) -> tuple:
    out = dev.shell(f"bm clean -d -n {pkg}")
    return "successfully" in out.lower(), out


def pick_any_device(serial=None):
    """自动选择通道: 先 adb, 再 hdc。返回 (adb_or_none, dev)。"""
    problems = []
    try:
        adb_path = ensure_adb(verbose=False)
        adb = Adb(adb_path)
        devs = [d for d in adb.devices() if d["state"] == "device"]
        if devs:
            return adb, Adb(adb_path, pick_device(adb, serial))
    except AdbError as e:
        problems.append(f"adb: {e}")
    except Exception as e:  # adb 存在但执行异常
        problems.append(f"adb: {e}")
    try:
        hdc = Hdc()
        devs = hdc.devices()
        if devs:
            if len(devs) > 1 and not serial:
                raise AdbError(
                    "检测到多台 HarmonyOS 设备, 请用 --serial 指定: "
                    + ", ".join(d["serial"] for d in devs))
            target = serial or devs[0]["serial"]
            return None, Hdc(hdc.adb, target)
    except AdbError as e:
        problems.append(f"hdc: {e}")
    except Exception as e:
        problems.append(f"hdc: {e}")
    detail = " | ".join(problems) if problems else "没有已连接的设备"
    raise AdbError(
        f"没有可用设备(adb 与 hdc 都没找到在线设备)。{detail}\n"
        "Android 手机: 打开 USB 调试; HarmonyOS NEXT: 安装 hdc 并开启调试模式")


def _need_device(args):
    """需要设备的命令统一入口: adb 优先, HarmonyOS NEXT 走 hdc。"""
    serial = getattr(args, "serial", None)
    forced = getattr(args, "hdc", None)
    if forced:
        hdc = Hdc(forced)
        devs = hdc.devices()
        if not devs:
            raise AdbError("指定了 --hdc 但没有找到 HarmonyOS 设备"
                           "(请在手机上开启调试模式并信任此电脑)")
        if len(devs) > 1 and not serial:
            raise AdbError("检测到多台 HarmonyOS 设备, 请用 --serial 指定")
        return None, Hdc(forced, serial or devs[0]["serial"])
    return pick_any_device(serial)


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
    "ro.product.marketname", "ro.product.manufacturer",
    "ro.build.version.release", "ro.build.version.sdk", "ro.build.display.id",
    "ro.miui.ui.version.name", "ro.miui.ui.version.code",   # 小米 MIUI
    "ro.mi.os.version.name", "ro.mi.os.version.code",       # 小米 HyperOS(澎湃)
    "ro.build.version.emui",          # 华为 EMUI
    "hw_sc.build.platform.version",   # 华为 HarmonyOS
    "ro.build.version.opporom", "ro.build.version.oplusrom",  # OPPO ColorOS
    "ro.build.version.oplusrom.display",
    "ro.vivo.os.version", "ro.vivo.os.name", "ro.vivo.rom.version",  # vivo
    "ro.build.version.magic", "ro.build.version.hihonor",  # 荣耀 MagicOS
    "ro.build.version.oneui",         # 三星 One UI
    "ro.flyme.version",               # 魅族 Flyme
]

BRAND_TO_EXAMPLE = {
    "xiaomi": "examples/xiaomi-hyperos",
    "redmi": "examples/xiaomi-hyperos",
    "poco": "examples/xiaomi-hyperos",
    "blackshark": "examples/xiaomi-hyperos",
    "huawei": "examples/huawei-harmonyos",
    "honor": "examples/honor-magicos",
    "hihonor": "examples/honor-magicos",
    "oppo": "examples/oppo-coloros",
    "oneplus": "examples/oneplus-coloros",
    "realme": "examples/realme-ui",
    "vivo": "examples/vivo-originos",
    "iqoo": "examples/vivo-originos",
    "samsung": "examples/samsung-oneui-cn",
    "meizu": "examples/meizu-flyme",
    "zte": "examples/zte-nubia",
    "nubia": "examples/zte-nubia",
    "redmagic": "examples/zte-nubia",
    "motorola": "examples/moto-myiui",
    "moto": "examples/moto-myiui",
    "lenovo": "examples/lenovo-zui",
    "tecno": "examples/transsion-hios",
    "infinix": "examples/transsion-hios",
    "itel": "examples/transsion-hios",
    "transsion": "examples/transsion-hios",
}


# ---------------------------------------------------------------------------
# ROM 家族与版本识别(版本感知)
#
#   同一品牌不同 ROM 版本, 可卸载范围与「卸载是否被 ROM 拦截」完全不同:
#     ColorOS 11 及以下 → pm uninstall --user 0 基本可用, 直接卸载
#     ColorOS 12 起     → 大量 com.heytap.* 返回 DELETE_FAILED_INTERNAL_ERROR,
#                         只能降级禁用/挂起(真机 ColorOS 13.1 已验证)
#   规则表: rules/rom-profiles.json(家族属性/版本说明/分版本动作覆盖)
# ---------------------------------------------------------------------------
ROM_PROFILE_FILE = (Path(__file__).resolve().parent.parent
                    / "rules" / "rom-profiles.json")
_ROM_PROFILES_CACHE: dict = {}


def load_rom_profiles(path=None) -> dict:
    """读取版本规则库; 文件缺失时返回空表(工具仍可用, 只是不做版本判断)。"""
    p = Path(path) if path else ROM_PROFILE_FILE
    key = str(p)
    if key in _ROM_PROFILES_CACHE:
        return _ROM_PROFILES_CACHE[key]
    data = {"families": {}, "packages": {}}
    try:
        if p.exists():
            loaded = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data["families"] = loaded.get("families") or {}
                data["packages"] = loaded.get("packages") or {}
                data["meta"] = loaded.get("meta") or {}
    except (ValueError, OSError):
        pass
    _ROM_PROFILES_CACHE[key] = data
    return data


_VERSION_NUM_RE = re.compile(r"(\d+(?:\.\d+)*)")


def parse_version(text) -> tuple:
    """把 "V13.1.0" / "OS2.0.1.0.VNBCNXM" / "13.1" 解析成 (13,1,0)。"""
    if not text:
        return ()
    m = _VERSION_NUM_RE.search(str(text))
    if not m:
        return ()
    try:
        return tuple(int(x) for x in m.group(1).split(".") if x != "")
    except ValueError:
        return ()


def fmt_version(vt: tuple) -> str:
    """(13,1,0) -> "13.1"(去掉尾部 0, 至少保留两位)。"""
    parts = list(vt or ())
    while len(parts) > 2 and parts[-1] == 0:
        parts.pop()
    return ".".join(str(x) for x in parts)


def _ver_lt(a: tuple, b: tuple) -> bool:
    n = max(len(a), len(b))
    return (tuple(a) + (0,) * (n - len(a))) < (tuple(b) + (0,) * (n - len(b)))


def _ver_eq(a: tuple, b: tuple) -> bool:
    n = max(len(a), len(b))
    return (tuple(a) + (0,) * (n - len(a))) == (tuple(b) + (0,) * (n - len(b)))


def read_all_props(dev: Adb) -> dict:
    """一次 `getprop` 取全量属性 -> {键: 值}。失败返回 {}。

    hdc 通道(HarmonyOS NEXT)没有 getprop, 改用 `param get` 取系统参数。
    """
    if is_hdc(dev):
        return _read_all_params(dev)
    try:
        out = dev.shell("getprop")
    except Exception:
        return {}
    props = {}
    for line in out.splitlines():
        m = re.match(r"^\[([^\]]+)\]:\s*\[(.*)\]\s*$", line.strip())
        if m:
            props[m.group(1)] = m.group(2).strip()
    return props


PARAM_LINE_RE = re.compile(r"^([A-Za-z0-9_.\-]+)\s*[:=]\s*(.*)$")


def _read_all_params(dev) -> dict:
    """`hdc shell param get` 全量参数 -> {名: 值}。"""
    try:
        out = dev.shell("param get")
    except Exception:
        out = ""
    props = {}
    for line in out.splitlines():
        m = PARAM_LINE_RE.match(line.strip())
        if m:
            props[m.group(1)] = m.group(2).strip()
    if not props:  # 兜底: 逐个取关键参数
        for key in ("const.ohos.version", "const.harmony.version",
                    "const.product.software.model", "const.ohos.apiversion",
                    "hw_sc.build.platform.version",
                    "const.product.brand", "const.product.model",
                    "const.product.manufacturer", "const.product.name"):
            try:
                v = dev.shell(f"param get {key}")
            except Exception:
                v = ""
            if v and "fail" not in v.lower():
                props[key] = v.strip()
    return props


def _norm_brand(props: dict) -> str:
    for key in ("ro.product.brand", "const.product.brand",
                "ro.product.manufacturer", "const.product.manufacturer",
                "ro.product.name", "const.product.name"):
        v = (props.get(key) or "").strip().lower()
        if v:
            return v.split()[0]
    return ""


def _family_candidates(brand: str, families: dict) -> list:
    """按品牌命中优先、priority 次之排序; 未命中的家族排在最后做兜底识别。"""
    hit = [k for k, c in families.items()
           if brand and brand in [b.lower() for b in c.get("brands") or []]]
    rest = [k for k in families if k not in hit]
    key = lambda k: families[k].get("priority", 5)  # noqa: E731
    return sorted(hit, key=key) + sorted(rest, key=key)


def _family_version(cfg: dict, props: dict):
    """从属性里取该家族的版本 -> (原始值, 版本元组, 属性名, edition) 或 None。"""
    for key in cfg.get("props") or []:
        if key == "ro.build.display.id":
            # 构建号(TP1A.220905.001 / U1TQS34.36-33-3)里的数字不是 ROM 版本,
            # 这类信息只走下面的"家族名 + 版本号"扫描
            continue
        raw = (props.get(key) or "").strip()
        if not raw or raw.lower() in ("unknown", "null", "0"):
            continue
        vt = parse_version(raw)
        if not vt:
            continue
        edition = None
        ep = cfg.get("edition_props") or {}
        if key in ep:
            edition = ep[key]
        elif key == cfg.get("edition_prop"):
            edition = cfg.get("edition_label") or "HyperOS"
        elif key == "ro.miui.ui.version.name":
            edition = "MIUI"
        return raw, vt, key, edition
    # 兜底: 扫描全部属性值里的家族名(MyOS / myui / HiOS / ZUI 等无稳定专有属性)
    pats = [re.compile(p, re.I) for p in cfg.get("name_patterns") or []]
    for key, raw in props.items():
        if not raw:
            continue
        for pat in pats:
            m = pat.search(raw)
            if not m:
                continue
            vt = parse_version(raw[m.end():m.end() + 24])
            if vt:
                return raw, vt, key, None
    return None


def _generation(cfg: dict, vt: tuple, edition) -> tuple:
    """把各家族自己的版本号换算成可跨版本比较的 generation。"""
    if not vt:
        return ()
    if cfg.get("scale") == "oneui":
        code = vt[0]
        return (code // 10000, (code // 100) % 100, code % 100)
    gmap = (cfg.get("generation_map") or {}).get(edition or "") or {}
    major = str(vt[0])
    if major in gmap:
        base = int(gmap[major])
        return (base,) + tuple(vt[1:])
    return vt


def _build_rom(family, cfg, raw, vt, edition, source, brand, android,
               confidence="prop") -> dict:
    gen = _generation(cfg, vt, edition)
    blocked = cfg.get("uninstall_blocked_from")
    legacy_below = cfg.get("legacy_uninstall_below")
    uninstall_ok, legacy = True, False
    if blocked and gen:
        uninstall_ok = _ver_lt(gen, parse_version(blocked))
        if legacy_below:
            legacy = _ver_lt(gen, parse_version(legacy_below))
    unsupported = None
    hdc_required = False
    if cfg.get("hdc_from") and gen and not _ver_lt(
            gen, parse_version(cfg["hdc_from"])):
        # 只有"原生鸿蒙/OHOS"版本才走 hdc; EMUI 12 / MagicOS 8 这类基于
        # Android 的版本号(12/8)远大于 5, 但 adb 完全可用, 不能误判
        hdc_props = cfg.get("hdc_props") or []
        hdc_native = bool(hdc_props) and (
            source in hdc_props
            or (edition or "") in ("HarmonyOS", "HarmonyOS NEXT", "OHOS"))
        if hdc_native:
            hdc_required = True
            unsupported = cfg.get("hdc_note") or "该版本只提供 hdc 调试, 没有 adb"
    if cfg.get("unsupported_from") and gen and not _ver_lt(
            gen, parse_version(cfg["unsupported_from"])):
        eds = cfg.get("unsupported_editions")
        if not eds or edition in eds:
            unsupported = cfg.get("unsupported_reason") or "该版本不再支持 adb 调试"
    label = cfg.get("label") or family
    shown = edition or label
    if cfg.get("scale") == "oneui":
        # One UI 的属性是版本代码(60100), 展示用换算后的 6.1
        shown, vt_show = label, gen
    else:
        vt_show = vt
    versions = cfg.get("versions") or {}
    major = str((vt or (0,))[0])
    note = versions.get(major) or ""
    if not note:
        # 取不高于当前版本的最大一条说明
        best = None
        for k, v in versions.items():
            try:
                kn = int(k)
            except ValueError:
                continue
            if kn <= int(major) and (best is None or kn > best[0]):
                best = (kn, v)
        note = best[1] if best else ""
    return {
        "family": family,
        "label": label,
        "edition": edition,
        "display": f"{shown} {fmt_version(vt_show)}".strip(),
        "version": fmt_version(vt_show),
        "generation": gen,
        "raw": raw,
        "source": source,
        "brand": brand,
        "android": android,
        "note": note,
        "notes": cfg.get("notes") or [],
        "legacy": legacy,
        "uninstall_ok": uninstall_ok,
        "uninstall_blocked_from": blocked,
        "protected_namespaces": cfg.get("protected_namespaces") or [],
        "unsupported": unsupported,
        "hdc_required": hdc_required,
        "confidence": confidence,
        "verified": cfg.get("verified") or "",
    }


def detect_rom(dev: Adb = None, props: dict = None, override: str = None,
               profiles: dict = None, channel: str = None) -> dict:
    """识别 ROM 家族与版本。override 形如 "13.1" 或 "coloros:13.1"(手动指定)。"""
    profiles = profiles or load_rom_profiles()
    families = profiles.get("families") or {}
    if props is None:
        props = read_all_props(dev) if dev is not None else {}
    if channel is None:
        channel = "hdc" if is_hdc(dev) else "adb"
    brand = _norm_brand(props)
    android = (props.get("ro.build.version.release")
               or props.get("const.ohos.apiversion") or "").strip()

    rom = None
    if override:
        fam, sep, ver = str(override).partition(":")
        if not sep:
            ver, fam = fam, ""
        fam = fam.strip().lower()
        if fam and fam in families:
            vt = parse_version(ver)
            rom = _build_rom(fam, families[fam], ver, vt, None, "手动指定",
                             brand, android, confidence="override")
        elif ver:
            # 只给了版本号: 沿用品牌识别出的家族
            for cand in _family_candidates(brand, families):
                if _family_version(families[cand], props):
                    vt = parse_version(ver)
                    rom = _build_rom(cand, families[cand], ver, vt, None,
                                     "手动指定", brand, android,
                                     confidence="override")
                    break

    if rom is None:
        for fam in _family_candidates(brand, families):
            got = _family_version(families[fam], props)
            if not got:
                continue
            raw, vt, source, edition = got
            conf = "display-id" if families[fam].get("confidence") == "display-id" else "prop"
            rom = _build_rom(fam, families[fam], raw, vt, edition, source,
                             brand, android, confidence=conf)
            break

    if rom is None:
        rom = {
            "family": None, "label": "未识别 ROM", "edition": None,
            "display": "", "version": "", "generation": (),
            "raw": (props.get("ro.build.display.id") or "").strip(),
            "source": "", "brand": brand, "android": android,
            "note": "", "notes": [], "legacy": False, "uninstall_ok": True,
            "uninstall_blocked_from": None, "protected_namespaces": [],
            "unsupported": None, "confidence": "unknown", "verified": "",
        }
    rom["channel"] = channel
    return rom


def rom_policy_lines(rom: dict, channel: str = None) -> list:
    """该 ROM 版本下的清理策略说明(给 CLI 打印)。"""
    if not rom or not rom.get("family"):
        return ["版本策略: 未识别 ROM 家族, 只按 Android 版本与包名安全规则处理"
                "(可加 --rom-version coloros:13.1 手动指定)"]
    if channel is None:
        channel = rom.get("channel") or "adb"
    out = []
    if rom.get("hdc_required"):
        out.append(f"版本策略: {rom['display']} 只提供 hdc 调试(HarmonyOS Debug Bridge), "
                   f"已{'切换到 hdc 通道' if channel == 'hdc' else '无法用 adb 连接'}")
        out.append("          包管理用 bm: bm dump -a 列 bundle / bm uninstall -n 卸载; "
                   "没有 disable/suspend, 也拿不到安装分区, 系统预装通常卸不掉")
    if rom.get("legacy"):
        out.append(f"版本策略: {rom['display']} 低于卸载拦截门槛"
                   f"(>= {rom.get('uninstall_blocked_from')}), "
                   "pm uninstall --user 0 通常可用 → 清单里的 uninstall 条目直接卸载")
    elif rom.get("uninstall_ok") is False:
        out.append(f"版本策略: {rom['display']} 起 ROM 会拦截大量系统应用卸载"
                   "(DELETE_FAILED_INTERNAL_ERROR) → 卸载失败自动降级禁用, "
                   "禁用被拒再挂起; 想少刷失败日志可加 --prefer-disable")
    else:
        out.append(f"版本策略: {rom['display']} 未记录卸载拦截, 按普通流程执行")
    if rom.get("unsupported") and not rom.get("hdc_required"):
        out.append(f"[不支持] {rom['unsupported']}")
    return out


# ---------------------------------------------------------------------------
# 列表里的版本标注: [v>=13] [v<12] [v=13.1] [v12-13]
#   - 写在行尾或注释里都行: com.x.y uninstall [v>=13] # 说明
#   - 版本比较用 ROM 的 generation(见 rom-profiles.json 的 generation_note)
# ---------------------------------------------------------------------------
GATE_RE = re.compile(
    r"\[\s*v\s*(?:(>=|<=|!=|>|<|=)\s*)?(\d+(?:\.\d+)*)"
    r"(?:\s*-\s*(\d+(?:\.\d+)*))?\s*\]", re.I)


def parse_gates(text: str) -> list:
    gates = []
    for m in GATE_RE.finditer(text or ""):
        op, lo, hi = m.group(1), parse_version(m.group(2)), m.group(3)
        if hi:
            gates.append(("range", lo, parse_version(hi)))
        elif op:
            gates.append((op, lo))
        else:
            gates.append((">=", lo))
    return gates


def strip_gates(text: str) -> str:
    return re.sub(r"\s+", " ", GATE_RE.sub(" ", text or "")).strip()


def fmt_gates(gates: list) -> str:
    """[(">=", (13,))] -> "[v>=13]"。"""
    out = []
    for g in gates or []:
        if g[0] == "range":
            out.append(f"[v{fmt_version(g[1])}-{fmt_version(g[2])}]")
        else:
            out.append(f"[v{g[0]}{fmt_version(g[1])}]")
    return " ".join(out)


def gate_pass(gates: list, gen: tuple) -> bool:
    for g in gates:
        if g[0] == "range":
            if _ver_lt(gen, g[1]) or _ver_lt(g[2], gen):
                return False
            continue
        op, v = g[0], g[1]
        if op == ">=" and _ver_lt(gen, v):
            return False
        if op == ">" and (not _ver_lt(v, gen) or _ver_eq(gen, v)):
            return False
        if op == "<=" and _ver_lt(v, gen):
            return False
        if op == "<" and not _ver_lt(gen, v):
            return False
        if op == "=" and not _ver_eq(gen, v):
            return False
        if op == "!=" and _ver_eq(gen, v):
            return False
    return True


def filter_entries_by_rom(entries: list, rom: dict) -> tuple:
    """按 ROM 版本过滤条目 -> (适用, 因版本不符跳过)。版本未知时不拦截。"""
    gen = (rom or {}).get("generation") or ()
    if not gen:
        return list(entries), []
    kept, skipped = [], []
    for e in entries:
        gates = e.get("gates") or []
        (kept if not gates or gate_pass(gates, gen) else skipped).append(e)
    return kept, skipped


def rom_pkg_override(pkg: str, rom: dict, profiles: dict = None):
    """版本专属动作覆盖 -> {"action":..., "note":...} 或 {"skip": True, "note":...} 或 None。"""
    profiles = profiles or load_rom_profiles()
    ov = (profiles.get("packages") or {}).get(pkg)
    if not ov:
        return None
    fam = ov.get("family")
    if fam and rom and rom.get("family") and fam != rom["family"]:
        return None
    gen = (rom or {}).get("generation") or ()
    if gen:
        if ov.get("vmin") and _ver_lt(gen, parse_version(ov["vmin"])):
            return {"skip": True, "note": ov.get("note") or ""}
        if ov.get("vmax") and _ver_lt(parse_version(ov["vmax"]), gen):
            return {"skip": True, "note": ov.get("note") or ""}
    return ov


def get_props(dev: Adb, all_props: dict = None) -> dict:
    """取 INFO_PROPS 里的属性。优先用一次 `getprop` 全量输出(快), 失败再逐个取。"""
    all_props = read_all_props(dev) if all_props is None else all_props
    if all_props:
        return {k: all_props.get(k, "") for k in INFO_PROPS}
    props = {}
    for key in INFO_PROPS:
        try:
            if is_hdc(dev):
                props[key] = dev.shell(f"param get {key}")
            else:
                props[key] = dev.shell(f"getprop {key}")
        except Exception:
            props[key] = ""
    return props


def describe_device(dev: Adb) -> dict:
    all_props = read_all_props(dev)
    props = get_props(dev, all_props)
    brand = (props.get("ro.product.brand") or props.get("const.product.brand")
             or "").strip()
    model = (props.get("ro.product.model") or props.get("const.product.model")
             or "").strip()
    rom_info = detect_rom(dev, props=all_props or props)
    example = BRAND_TO_EXAMPLE.get(brand.lower(), "examples/universal")
    return {
        "brand": brand, "model": model, "rom": rom_info.get("display") or "",
        "rom_info": rom_info,
        "marketname": props.get("ro.product.marketname", ""),
        "android": props.get("ro.build.version.release", "")
                   or props.get("const.ohos.apiversion", ""),
        "sdk": props.get("ro.build.version.sdk", ""),
        "display": props.get("ro.build.display.id", "")
                   or props.get("const.product.software.model", ""),
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
    """本次运行的动态保护目标: 桌面 / Recents / 输入法。

    hdc 通道(HarmonyOS NEXT)没有 pm resolve-activity / settings 命令,
    动态保护拿不到, 只能依赖静态安全规则 + 人工确认。
    """
    if is_hdc(dev):
        return {"home": None, "recents": None, "ime": None}
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
    """当前用户已安装的包。hdc 通道用 `bm dump -a` 列 bundle。"""
    if is_hdc(dev):
        return hdc_list_bundles(dev)
    return _parse_pm_list(dev.shell("pm list packages"))


def list_disabled(dev: Adb) -> set:
    """已被禁用的包。HarmonyOS NEXT 没有 disable 概念, 恒为空。"""
    if is_hdc(dev):
        return set()
    return _parse_pm_list(dev.shell("pm list packages -d"))


def list_suspended(dev: Adb) -> set:
    """已被挂起(pm suspend)的包; 部分 ROM(如 ColorOS 乐划锁屏)禁止
    pm disable-user, 但允许 suspend, 挂起后应用无法启动, 效果等同禁用。"""
    if is_hdc(dev):
        return set()
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
    if is_hdc(dev):
        # HarmonyOS NEXT: 没有 pm list/settings/getprop, 用 bm dump -a 备份
        (d / "bundles.txt").write_text(
            dev.shell("bm dump -a") + "\n", encoding="utf-8")
        (d / "packages.txt").write_text(
            dev.shell("bm dump -a") + "\n", encoding="utf-8")
        manifest = {
            "serial": dev.serial, "label": label, "channel": "hdc",
            "ts": dt.datetime.now().isoformat(timespec="seconds"),
            "device": {k: v for k, v in get_props(dev).items() if v},
            "home": None, "recents": None, "ime": None,
        }
        (d / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return d
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
        "channel": "adb",
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
               base=HOME_DIR, log=print, rom: dict = None,
               prefer_disable: bool = False, force_feature: bool = False) -> dict:
    """应用清理列表。返回分类结果字典。

    规则:
      * 命中 DENY 规则/显式核心包清单 -> 拒绝
      * 当前默认桌面 / Recents 提供者 / 当前输入法 -> 拒绝(动态保护)
      * 设备上不存在的包 -> 跳过(不同 ROM 包名有差异, 属正常)
      * 条目带 [v>=13] 之类版本标注且与当前 ROM 版本不符 -> 跳过
      * 命中"功能必留"(下拉搜索/负一屏/商店/推送层) -> 跳过;
        用户显式写在列表里并加 --force-feature 时放行(尊重显式意图)
      * uninstall 失败(ROM 限制) -> 自动降级为 disable
      * prefer_disable=True 且该版本 ROM 会拦截卸载 -> 直接禁用, 不试卸载
      * batch>0 时按批次处理, 每批之后截图(需 --screenshot), 方便逐段验证
    """
    installed = list_packages(dev)
    disabled = list_disabled(dev)
    suspended = list_suspended(dev)
    protect = protected_targets(dev)
    protected = {p for p in protect.values() if p}
    if rom is None:
        rom = detect_rom(dev)
    entries, skipped_version = filter_entries_by_rom(entries, rom)
    if skipped_version:
        log(f"[版本] {rom.get('display') or '未知 ROM'}: 跳过 {len(skipped_version)} 条"
            "标注了其他 ROM 版本的条目"
            f"({', '.join(e['pkg'] for e in skipped_version[:3])}"
            + (" ..." if len(skipped_version) > 3 else "") + ")")
    for line in rom_policy_lines(rom, channel=getattr(dev, "transport", "adb")):
        log(f"[ROM] {line}")
    if protect.get("ime"):
        log(f"[保护] 当前输入法: {protect['ime']}(禁用后重启将无法解锁, 已加入保护)")
    if protect.get("recents") and protect["recents"] != protect.get("home"):
        log(f"[保护] 最近任务提供者: {protect['recents']}(禁用它会导致任务切换失灵)")
    if protect.get("home"):
        log(f"[保护] 当前默认桌面: {protect['home']}")

    state = load_state(dev.serial, base)
    result = {"ok": [], "skipped_deny": [], "skipped_missing": [],
              "skipped_protected": [], "skipped_feature": [],
              "skipped_version": skipped_version,
              "skipped_unsupported": [], "already": [], "fail": []}

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
        keep_why = feature_keep_reason(pkg)
        if keep_why:
            if not force_feature:
                result["skipped_feature"].append(pkg)
                log(f"[保留] {pkg} 是{keep_why}, 不卸载/不禁用/不冻结"
                    "(确认要处理请加 --force-feature)")
                return
            log(f"[放行] {pkg} 是{keep_why}, 但列表显式指定且带 --force-feature, 继续处理"
                "(相关功能可能失效)")
        if pkg in protected:
            result["skipped_protected"].append(pkg)
            log(f"[保护] {pkg} 是桌面/最近任务/输入法, 已跳过")
            return
        if pkg not in installed:
            result["skipped_missing"].append(pkg)
            log(f"[跳过] {pkg} 未在本机安装(可能该机型/版本无此应用)")
            return
        if action in ("disable", "freeze") and (pkg in disabled or pkg in suspended):
            result["already"].append(pkg)
            log(f"[跳过] {pkg} 已处于禁用/挂起状态")
            return
        if dry_run:
            result["ok"].append(pkg)
            log(f"[预演] {action:9s} {pkg}  # {e['comment']}")
            return
        if is_hdc(dev):
            # HarmonyOS NEXT: 包管理只有 bm 工具, 没有 disable/suspend
            if action != "uninstall":
                result["skipped_unsupported"].append(pkg)
                log(f"[不支持] {pkg}: HarmonyOS NEXT 的 bm 工具没有禁用/冻结/挂起能力, "
                    "只能卸载(把列表里的 disable/freeze 改成 uninstall 再试)")
                return
            ok, out = hdc_uninstall(dev, pkg)
            if ok:
                record_pkg(state, pkg, "uninstall", list_file, base)
                result["ok"].append(pkg)
                log(f"[已卸载] {pkg}  # {e['comment']}")
            else:
                result["fail"].append(pkg)
                log(f"[失败] {pkg}: {out.strip() or '无输出'}"
                    "(系统 bundle 可能不允许卸载)")
            return
        if action == "uninstall":
            if (prefer_disable and rom.get("uninstall_ok") is False
                    and any(pkg.startswith(ns) for ns in
                            rom.get("protected_namespaces") or [])):
                log(f"[版本] {pkg} 在 {rom['display']} 上会被 ROM 拦截卸载, "
                    "直接改为禁用")
                action = "disable"
            else:
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
            if action == "freeze":
                # 冻结 = 禁用 + 强制停止(参考 Hail: 冻结后应用不得在后台运行)
                dev.shell(f"am force-stop {pkg}")
            record_pkg(state, pkg, action, list_file, base)
            result["ok"].append(pkg)
            if action == "freeze":
                log(f"[已冻结] {pkg}(不可启动, 数据保留; pm enable 可恢复)  # {e['comment']}")
            else:
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
        f"版本不符跳过 {len(result['skipped_version'])} | "
        f"已处于目标状态 {len(result['already'])} | 安全拒绝 "
        f"{len(result['skipped_deny']) + len(result['skipped_protected'])} | "
        f"功能必留跳过 {len(result['skipped_feature'])} | "
        f"通道不支持 {len(result['skipped_unsupported'])} | "
        f"失败 {len(result['fail'])}")
    if result["fail"]:
        log("失败项通常是因为该 ROM 受保护, 可尝试重启后重试或在列表中改为 disable/freeze。")
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
            if is_hdc(dev):
                log(f"[未恢复] {pkg}: HarmonyOS NEXT 没有 install-existing, "
                    "已卸载的 bundle 需在应用市场手动重装")
                result["fail"].append(pkg)
                continue
            out = dev.shell(f"cmd package install-existing --user 0 {pkg}")
            if "installed for user" in out.lower():
                log(f"[已恢复] {pkg}")
                result["ok"].append(pkg)
                state.get("packages", {}).pop(pkg, None)
            else:
                log(f"[未恢复] {pkg}: {out.strip() or '无输出'}")
                result["fail"].append(pkg)
        elif action in ("freeze", "suspend"):
            # 冻结/挂起都用 enable + unsuspend 双保险解冻
            # (Hail 的教训: 解冻必须覆盖实际生效的那个模式)
            dev.shell(f"pm unsuspend --user 0 {pkg}")
            dev.shell(f"pm enable --user 0 {pkg}")
            log(f"[已解冻] {pkg}(取消挂起/禁用)")
            result["ok"].append(pkg)
            state.get("packages", {}).pop(pkg, None)
        else:
            out = dev.shell(f"pm enable --user 0 {pkg}")
            log(f"[已恢复] {pkg}" + (f" ({out.strip()})" if out.strip() else ""))
            result["ok"].append(pkg)
            state.get("packages", {}).pop(pkg, None)
    if revert_extra:
        if is_hdc(dev):
            log("[提示] HarmonyOS NEXT 没有 settings/appops 命令, "
                "设置与传感器限制需按 README 手动改回")
        else:
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
               base=HOME_DIR, log=print, rom: dict = None) -> list:
    """对比列表与设备实际状态; fix=True 时把"回潮"项重新应用。"""
    if rom is None:
        rom = detect_rom(dev)
    entries, skipped_version = filter_entries_by_rom(entries, rom)
    if skipped_version:
        log(f"[版本] {rom.get('display') or '未知 ROM'}: 跳过 {len(skipped_version)} 条"
            "标注了其他 ROM 版本的条目")
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
    hdc_mode = is_hdc(dev)
    for e in entries:
        pkg, action = e["pkg"], e["action"]
        if is_denied(pkg) or pkg in protected:
            continue
        actual = state.get("packages", {}).get(pkg, {}).get("action", "")
        if pkg not in installed and action == "uninstall":
            cur, ok = "已卸载", True
        elif hdc_mode and action != "uninstall":
            cur, ok = "通道不支持(只能卸载)", False
        elif pkg in suspended:
            cur, ok = ("已挂起" if action != "uninstall" else "已挂起(卸载降级)"), True
        elif action in ("disable", "freeze"):
            ok = pkg in disabled
            cur = ("已冻结" if action == "freeze" else "已禁用") if ok else "仍启用"
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
                       do_backup=False, base=base, log=log, rom=rom)
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
# UI 自动化: 读屏 -> 找入口 -> 拨开关
#
#   思路来自 android-ad-cleaner(MIT 许可), 实现换成纯标准库:
#   用系统自带 uiautomator dump 取控件树, 自己解析 XML, 用 input tap 点击。
#   所以电脑端零依赖(不装 uiautomator2), 手机端不装任何东西,
#   也不占用无障碍服务(不跟 GKD / 自动记账抢读屏)。
#
#   为什么需要它: pm uninstall/disable/suspend 只能处理"包", 而系统广告开关、
#   搜索热搜、商店推广位、浏览器信息流都在 App 内部, 只能点界面关。
# ---------------------------------------------------------------------------
UI_DUMP_FILE = "/sdcard/window_dump.xml"
UI_DUMP_ALT = "/data/local/tmp/window_dump.xml"
UI_KEYCODES = {"back": 4, "home": 3, "enter": 66, "menu": 82, "power": 26,
               "wakeup": 224, "appswitch": 187, "delete": 67}

# 默认拒绝点击的敏感词: 工具不替机主同意协议、不买东西、不删数据
UI_RISKY_WORDS = ("同意", "允许", "授权", "安装", "购买", "支付", "付款",
                  "删除", "卸载", "格式化", "恢复出厂", "清除数据", "注销账号",
                  "agree", "allow", "install", "buy", "pay", "delete",
                  "uninstall", "erase", "factory reset")

UI_LAUNCH_ALIASES = {
    "settings": "am start -f 0x10008000 -a android.settings.SETTINGS",
    "apps": "am start -a android.settings.APPLICATION_SETTINGS",
    "notify": "am start -a android.settings.NOTIFICATION_SETTINGS",
    "wifi": "am start -a android.settings.WIFI_SETTINGS",
    "display": "am start -a android.settings.DISPLAY_SETTINGS",
    "privacy": "am start -a android.settings.PRIVACY_SETTINGS",
}
_UI_SCREEN_CACHE: dict = {}


class UiError(RuntimeError):
    """读屏或点击失败(界面没打开、控件找不到、屏幕锁着)。"""


def _ui_bounds(raw):
    """'[12,34][56,78]' -> (12, 34, 56, 78); 解析不了返回 None。"""
    m = re.match(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", raw or "")
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


class UiNode:
    """界面上的一个控件, 字段与 uiautomator dump 的 XML 属性对应。"""

    __slots__ = ("text", "rid", "cls", "pkg", "desc", "bounds", "clickable",
                 "checkable", "checked", "has_checked", "enabled",
                 "scrollable", "selected", "children", "parent")

    def __init__(self, attr: dict, parent=None):
        self.text = (attr.get("text") or "").strip()
        self.rid = attr.get("resource-id") or ""
        self.cls = attr.get("class") or ""
        self.pkg = attr.get("package") or ""
        self.desc = (attr.get("content-desc") or "").strip()
        self.bounds = _ui_bounds(attr.get("bounds"))
        self.clickable = attr.get("clickable") == "true"
        self.checkable = attr.get("checkable") == "true"
        self.has_checked = attr.get("checked") is not None
        self.checked = attr.get("checked") == "true"
        self.enabled = attr.get("enabled", "true") == "true"
        self.scrollable = attr.get("scrollable") == "true"
        self.selected = attr.get("selected") == "true"
        self.children = []
        self.parent = parent
        if parent is not None:
            parent.children.append(self)

    @property
    def label(self) -> str:
        return self.text or self.desc

    @property
    def center(self) -> tuple:
        if not self.bounds:
            return (0, 0)
        x1, y1, x2, y2 = self.bounds
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    @property
    def area(self) -> int:
        if not self.bounds:
            return 0
        x1, y1, x2, y2 = self.bounds
        return max(0, x2 - x1) * max(0, y2 - y1)

    @property
    def is_switch(self) -> bool:
        if self.checkable:
            return True
        low = self.cls.lower()
        return any(k in low for k in ("switch", "checkbox", "togglebutton",
                                      "checkedtextview"))

    def keys(self) -> str:
        return " ".join(x for x in (self.text, self.desc, self.rid, self.cls) if x)

    def __repr__(self) -> str:
        mark = ""
        if self.is_switch:
            mark = " [开]" if self.checked else (" [关]" if self.has_checked else " [?]")
        return f"<{self.label or self.rid or self.cls}{mark} @{self.center}>"


def _xml_attrs(raw: str) -> dict:
    """把 `<node a="1" b="2">` 里的属性抠成 dict(含实体反转义)。"""
    out = {}
    for m in re.finditer(r'([\w:.-]+)="([^"]*)"', raw):
        v = m.group(2)
        if "&" in v:
            v = (v.replace("&quot;", '"').replace("&apos;", "'")
                  .replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&"))
        out[m.group(1)] = v
    return out


def parse_ui_xml(xml: str) -> list:
    """解析 uiautomator dump 的 XML, 返回全部控件(先序, 带父子关系)。"""
    xml = (xml or "").strip()
    if not xml:
        return []
    start = xml.find("<hierarchy")
    if start < 0:
        start = xml.find("<?xml")
    if start > 0:
        xml = xml[start:]
    nodes: list = []

    def walk(el, parent):
        node = UiNode(el.attrib, parent)
        nodes.append(node)
        for child in el:
            if child.tag == "node":
                walk(child, node)

    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        # 页面很大时 dump 可能被截断; 退化成宽松正则(丢父子关系但能找控件)
        for m in re.finditer(r"<node\s([^>]*?)/?>", xml):
            nodes.append(UiNode(_xml_attrs(m.group(1))))
        return nodes
    if root.tag == "hierarchy":
        for child in root:
            if child.tag == "node":
                walk(child, None)
    else:
        walk(root, None)
    return nodes


def ui_dump_xml(dev: Adb, retries: int = 3) -> str:
    """抓当前界面的控件树(XML 文本)。"""
    errs = []
    for attempt in range(max(1, retries)):
        for path in (UI_DUMP_FILE, UI_DUMP_ALT):
            out = dev.shell_all(f"uiautomator dump {path}")
            low = out.lower()
            if "error" in low and "dumped" not in low:
                errs.append(out.strip()[:100])
                continue
            xml = dev.shell(f"cat {path}")
            if "<hierarchy" in xml or "<node" in xml:
                return xml
            errs.append((xml or out).strip()[:100])
        if attempt + 1 < retries:
            time.sleep(0.8)
    raise UiError(
        "读屏失败: 取不到界面控件树"
        + (f"({errs[-1]})" if errs and errs[-1] else "")
        + "\n  排查: 1) 手机已解锁且停在目标页面 "
          "2) 等页面加载完再试(动画未结束会报 could not get idle state) "
          "3) 企业管控或读屏类 App 占用 uiautomator 时会被拒")


def ui_nodes(dev: Adb, retries: int = 3) -> list:
    return parse_ui_xml(ui_dump_xml(dev, retries))


def ui_find(nodes: list, needle: str, exact: bool = False,
            visible_only: bool = True) -> list:
    """按文本/描述/资源 id 查控件, 返回按匹配强度排序的结果。"""
    needle = (needle or "").strip()
    if not needle:
        return []
    low = needle.lower()
    scored = []
    for n in nodes:
        if visible_only and (not n.enabled or n.area <= 0):
            continue
        text, desc = n.text.lower(), n.desc.lower()
        rid = n.rid.lower().rsplit("/", 1)[-1]
        score = 0
        if exact:
            if text == low or desc == low:
                score = 100
            elif rid == low:
                score = 90
        else:
            if text == low:
                score = 100
            elif text and low in text:
                score = 80
            elif desc == low:
                score = 70
            elif desc and low in desc:
                score = 60
            elif rid and low in rid:
                score = 40
        if score:
            scored.append((score, n))
    scored.sort(key=lambda x: -x[0])
    return [n for _, n in scored]


def ui_tap_node(dev: Adb, node: UiNode, log=print, allow_risky: bool = False,
                label_hint: str = "") -> tuple:
    """点控件; 控件本身不可点时点它最近的可点祖先。返回坐标。

    label_hint: 日志里显示的名字(开关自身的 text 常为空, 由调用方传入标题)。
    """
    target = node
    while target is not None and not target.clickable:
        target = target.parent
    if target is None:
        target = node
    x, y = target.center
    if x <= 0 and y <= 0:
        raise UiError(f"控件「{node.label or node.rid}」没有可点击区域")
    if not allow_risky:
        keys = target.keys().lower()
        hit = next((w for w in UI_RISKY_WORDS if w in keys), None)
        if hit:
            raise UiError(f"拒绝点击含敏感词「{hit}」的控件 "
                          f"「{target.label or target.rid}」(确认要点头加 --allow-risky)")
    dev.shell(f"input tap {x} {y}")
    shown = label_hint or target.label or target.rid or target.cls
    log(f"    点击「{shown}」 ({x},{y})")
    return x, y


def ui_screen(dev: Adb) -> tuple:
    """屏幕分辨率(缓存)。"""
    key = getattr(dev, "serial", "") or ""
    if key in _UI_SCREEN_CACHE:
        return _UI_SCREEN_CACHE[key]
    m = re.search(r"(\d+)x(\d+)", dev.shell("wm size"))
    size = (int(m.group(1)), int(m.group(2))) if m else (1080, 2400)
    _UI_SCREEN_CACHE[key] = size
    return size


def ui_scroll(dev: Adb, forward: bool = True, times: int = 1, log=None) -> None:
    """翻页。forward=True 表示看下面的内容(手指上滑)。"""
    w, h = ui_screen(dev)
    for _ in range(max(1, times)):
        x = w // 2
        y1, y2 = ((int(h * 0.75), int(h * 0.35)) if forward
                  else (int(h * 0.35), int(h * 0.75)))
        dev.shell(f"input swipe {x} {y1} {x} {y2} 300")
        time.sleep(0.7)


def ui_key(dev: Adb, name) -> None:
    dev.shell(f"input keyevent {UI_KEYCODES.get(name, name)}")
    time.sleep(0.5)


def ui_focus(dev: Adb) -> str:
    """当前前台组件(包名/类名); 拿不到返回空串。"""
    for cmd in ("dumpsys activity activities | grep -m1 mResumedActivity",
                "dumpsys window | grep -m1 mCurrentFocus"):
        m = re.search(r"([A-Za-z][\w.]*)/([\w.$]+)", dev.shell(cmd))
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    return ""


def ui_locked(dev: Adb) -> bool:
    """屏幕是否锁着(锁屏时点界面没有意义)。"""
    out = dev.shell("dumpsys window | grep -m1 -i showinglockscreen")
    if "showinglockscreen=true" in out.replace(" ", "").lower():
        return True
    out = dev.shell("dumpsys window policy | grep -m1 -i showing=")
    return "showing=true" in out.replace(" ", "").lower()


def ui_launcher_activity(dev: Adb, pkg: str) -> str:
    """App 的启动 Activity(用于 am start, 比 monkey 更可靠)。"""
    out = dev.shell(f"cmd package resolve-activity --brief "
                    f"-c android.intent.category.LAUNCHER {pkg}")
    for raw in reversed(out.splitlines()):
        line = raw.strip()
        if "/" in line and " " not in line:
            return line
    return ""


def ui_launch(dev: Adb, app: str, activity: str = "", wait: float = 1.6,
              log=print) -> str:
    """打开 App 或系统设置页。返回前台组件名(可能为空)。"""
    if app in UI_LAUNCH_ALIASES:
        dev.shell(UI_LAUNCH_ALIASES[app])
    elif activity:
        comp = activity if "/" in activity else f"{app}/{activity}"
        dev.shell(f"am start -n {comp}")
    else:
        comp = ui_launcher_activity(dev, app)
        if comp:
            dev.shell(f"am start -n {comp}")
        else:
            dev.shell(f"monkey -p {app} -c android.intent.category.LAUNCHER 1")
    time.sleep(wait)
    focus = ui_focus(dev)
    log(f"    打开 {activity or app}"
        + (f" -> {focus.split('/')[-1]}" if focus else " (前台未知)"))
    return focus


def ui_wait(dev: Adb, needle: str, timeout: float = 8.0,
            exact: bool = False) -> bool:
    """等界面上出现某文本。"""
    deadline = time.time() + max(0.5, timeout)
    while time.time() < deadline:
        try:
            if ui_find(ui_nodes(dev, retries=1), needle, exact=exact):
                return True
        except UiError:
            pass
        time.sleep(0.8)
    return False


def ui_switch_state(node: UiNode):
    """开关状态: True/False, 读不到返回 None(自绘开关常见)。"""
    if node.has_checked:
        return node.checked
    return None


def ui_switch_title(node: UiNode, nodes: list) -> str:
    """开关的标题。开关自己没文本时, 取同一行左侧离它最近的文本。"""
    if node.label:
        return node.label
    if not node.bounds:
        return ""
    y1, y2 = node.bounds[1], node.bounds[3]
    best = None
    for n in nodes:
        if n is node or not n.label or not n.bounds or n.area <= 0:
            continue
        cy = (n.bounds[1] + n.bounds[3]) // 2
        if not (y1 - 12 <= cy <= y2 + 12):
            continue          # 不在同一行
        if n.bounds[0] >= node.bounds[2]:
            continue          # 在开关右边, 是副标题/按钮
        if best is None or n.bounds[2] > best.bounds[2]:
            best = n
    return best.label if best else ""


def ui_switch_entries(nodes: list) -> list:
    """页面上的全部开关: [(标题, 节点, 状态)]。"""
    out = []
    for n in nodes:
        if not n.is_switch or n.area <= 0:
            continue
        out.append((ui_switch_title(n, nodes), n, ui_switch_state(n)))
    return out


def ui_describe(nodes: list, limit: int = 60, only_switch: bool = False) -> list:
    """把界面控件整理成可读行(给 explore / dump 用)。"""
    lines = []
    seen = set()
    for n in nodes:
        if n.area <= 0 or not n.enabled:
            continue
        if only_switch and not n.is_switch:
            continue
        if only_switch:
            label = ui_switch_title(n, nodes)
        else:
            label = n.label or (n.rid.rsplit("/", 1)[-1] if n.rid else "")
            if not label and not n.clickable:
                continue
        if not label:
            continue
        key = (label, n.bounds)
        if key in seen:
            continue
        seen.add(key)
        if n.is_switch:
            state = "开" if n.checked else ("关" if n.has_checked else "?")
            mark = f"[{state}] "
        else:
            mark = "[可点] " if n.clickable else ""
        lines.append(f"{mark}{label}  @{n.center[0]},{n.center[1]}")
        if len(lines) >= limit:
            break
    return lines


# ---------------------------------------------------------------------------
# App 内广告开关: 声明式 recipe
#
#   android-ad-cleaner 的做法是"每机型一个 recipe.py"(可执行 Python)。
#   这里改成 rules/ad-switches.json 里的声明式步骤, 理由:
#     * 不执行任意代码, 规则可以被审阅、被 diff
#     * 一条规则能按 品牌/ROM 家族/版本 自动挑选, 不用为每个小版本写脚本
#     * 每步都能 --dry-run 预演
#   步骤类型(do): launch / tap / tap_any / wait / back / key / scroll /
#                 switches / confirm / dismiss
# ---------------------------------------------------------------------------
ADSW_RULE_FILE = (Path(__file__).resolve().parent.parent
                  / "rules" / "ad-switches.json")
_ADSW_CACHE: dict = {}

# 弹窗按钮词表: 只点"取消/暂不"这一侧, 不替机主同意
ADSW_DISMISS_WORDS = ("取消", "以后再说", "暂不", "暂不开启", "跳过", "我知道了",
                      "不同意", "禁止", "关闭", "残忍拒绝", "下次再说")
ADSW_CONFIRM_WORDS = ("确定", "确认", "开启", "同意并继续", "OK", "好")


def load_adsw(path=None) -> dict:
    """读取 App 内开关规则库; 文件缺失时返回空表。"""
    p = Path(path) if path else ADSW_RULE_FILE
    key = str(p)
    if key in _ADSW_CACHE:
        return _ADSW_CACHE[key]
    data = {"targets": [], "meta": {}}
    if p.exists():
        try:
            loaded = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data["targets"] = [t for t in (loaded.get("targets") or [])
                                   if isinstance(t, dict) and t.get("id")]
                data["meta"] = loaded.get("meta") or {}
        except ValueError as e:
            raise ValueError(f"{p} 不是合法 JSON: {e}")
    _ADSW_CACHE[key] = data
    return data


def adsw_match(targets: list, brand: str = "", family: str = "",
               gen: tuple = (), ids=None, model: str = "",
               strict_model: bool = True) -> list:
    """挑出适用于本机的条目(品牌/ROM 家族/版本/型号都对得上才返回)。

    带 models 的条目是"机型专属路径"(实测机型), 型号对不上就不套用:
    别的机型照搬路径去点, 可能点到完全不同的开关, 比不点更危险。
    """
    want = {i.lower() for i in (ids or [])}
    out = []
    for t in targets:
        if want and t["id"].lower() not in want:
            continue
        brands = [b.lower() for b in (t.get("brands") or [])]
        if brands:
            if not brand or not any(b in brand.lower() for b in brands):
                continue
        roms = [r.lower() for r in (t.get("roms") or [])]
        if roms:
            if not family or family.lower() not in roms:
                continue
        gate = t.get("gate")
        if gate and gen:
            # 规则库里写 ">=15" 就行, 也兼容列表文件的 "[v>=15]" 写法
            expr = gate.strip()
            if not expr.startswith("["):
                expr = f"[v{expr}]"
            if not gate_pass(parse_gates(expr), gen):
                continue
        models = [m.upper() for m in (t.get("models") or [])]
        if models and strict_model and not want:
            if not model:
                continue
            if not any(m in model.upper() for m in models):
                continue
        out.append(t)
    return out


def _adsw_tap(dev: Adb, text: str, step: dict, dry_run: bool, log,
              allow_risky: bool, scrolls=None) -> bool:
    exact = bool(step.get("exact", True))
    if scrolls is None:
        scrolls = int(step.get("scroll", 0) or 0)
    hits = ui_find(ui_nodes(dev), text, exact=exact)
    for _ in range(max(0, scrolls)):
        if hits:
            break
        ui_scroll(dev, True)
        hits = ui_find(ui_nodes(dev), text, exact=exact)
    if not hits:
        raise UiError(f"界面上找不到「{text}」")
    if dry_run:
        log(f"    [预演] 点击「{text}」")
        return True
    ui_tap_node(dev, hits[0], log=log, allow_risky=allow_risky)
    time.sleep(float(step.get("settle", 0.8)))
    return True


def _adsw_switches(dev: Adb, step: dict, dry_run: bool, log,
                   allow_risky: bool, max_screens: int) -> bool:
    """把页面上指定的开关全部关掉, 并回读确认。"""
    off = [s for s in (step.get("off") or []) if s]
    keep = [s for s in (step.get("keep") or []) if s]
    page = step.get("page") or ""
    all_on_page = bool(step.get("all"))
    if not off and not all_on_page:
        raise UiError("switches 步骤需要 off 列表(或 all=true)")
    targets = [s.lower() for s in off]
    keeps = [s.lower() for s in keep]
    changed, unknown, already, seen = [], [], [], []
    tag = f"[{page}] " if page else ""

    for screen in range(max(1, max_screens)):
        entries = ui_switch_entries(ui_nodes(dev))
        for title, node, state in entries:
            low = (title or "").lower()
            if not low:
                continue
            if keeps and any(k in low for k in keeps):
                continue
            if not all_on_page and not any(t in low for t in targets):
                continue
            if title not in seen:
                seen.append(title)
            if state is False:
                already.append(title)
                continue
            if dry_run:
                mark = "开" if state else ("关" if state is False else "读不到")
                log(f"    [预读] 「{title}」当前{mark}")
                if state is not False:
                    changed.append(title)
                continue
            try:
                ui_tap_node(dev, node, log=log, allow_risky=allow_risky,
                            label_hint=title)
            except UiError as e:
                log(f"    [跳过] 「{title}」: {e}")
                continue
            if state is None:
                unknown.append(title)
            else:
                changed.append(title)
            time.sleep(0.5)
        if dry_run:
            break
        found_all = bool(targets) and all(
            any(t in s.lower() for s in seen) for t in targets)
        if found_all or not entries or screen + 1 >= max_screens:
            break
        ui_scroll(dev, True)

    missing = [t for t in off
               if not any(t.lower() in s.lower() for s in seen)
               and not any(k in t.lower() for k in keeps)]
    if changed or already or missing:
        log(f"    {tag}关闭 {len(changed)} 项"
            + (f", 本就关着 {len(already)} 项" if already else "")
            + (f", 本页没有 {'/'.join(missing)}" if missing else ""))
    if changed and not dry_run:
        time.sleep(0.6)
        still_on = []
        for title, _node, state in ui_switch_entries(ui_nodes(dev)):
            if state is True and title in changed:
                still_on.append(title)
        if still_on:
            log(f"    [注意] 回读发现仍开着: {'/'.join(still_on)}"
                "(可能被 ROM 强制打开, 或需要再点一次)")
            return False
        if unknown:
            log(f"    [提示] 这些开关读不到状态, 已点过, 请人工扫一眼: "
                f"{'/'.join(unknown)}")
    return True


def _adsw_popup(dev: Adb, words, dry_run: bool, log, allow_risky: bool) -> bool:
    """点弹窗按钮(只在当前页面上找, 不翻页不深挖)。"""
    hits = []
    nodes = ui_nodes(dev)
    for w in words:
        hits.extend(ui_find(nodes, w, exact=True))
    if not hits:
        return False
    if dry_run:
        log(f"    [预演] 点弹窗「{hits[0].label}」")
        return True
    ui_tap_node(dev, hits[0], log=log, allow_risky=allow_risky)
    time.sleep(0.6)
    return True


def _adsw_step(dev: Adb, step: dict, dry_run: bool, log,
               allow_risky: bool, max_screens: int) -> bool:
    kind = (step.get("do") or "").lower()
    if kind == "launch":
        app = step.get("app") or ""
        if dry_run:
            log(f"    [预演] 打开 {step.get('activity') or app}")
            return True
        ui_launch(dev, app, step.get("activity") or "",
                  wait=float(step.get("wait", 1.6)), log=log)
        return True
    if kind == "tap":
        return _adsw_tap(dev, step.get("text") or "", step, dry_run, log,
                         allow_risky)
    if kind == "tap_any":
        texts = [t for t in (step.get("texts") or []) if t]
        if dry_run:
            log(f"    [预演] 点其中之一: {' / '.join(texts)}")
            return True
        last = None
        for t in texts:
            try:
                if _adsw_tap(dev, t, step, dry_run, log, allow_risky):
                    return True
            except UiError as e:
                last = e
        raise UiError(f"入口都没找到: {' / '.join(texts)}"
                      + (f"({last})" if last else ""))
    if kind == "wait":
        if dry_run:
            log(f"    [预演] 等「{step.get('text')}」出现")
            return True
        ok = ui_wait(dev, step.get("text") or "",
                     timeout=float(step.get("timeout", 8)))
        if not ok:
            raise UiError(f"等不到「{step.get('text')}」")
        return True
    if kind == "back":
        n = int(step.get("n", 1) or 1)
        if not dry_run:
            for _ in range(n):
                ui_key(dev, "back")
        log(f"    返回 {n} 次")
        return True
    if kind == "key":
        name = step.get("name") or "back"
        if not dry_run:
            ui_key(dev, name)
        log(f"    按键 {name}")
        return True
    if kind == "scroll":
        if not dry_run:
            ui_scroll(dev, bool(step.get("forward", True)),
                      int(step.get("times", 1) or 1))
        log(f"    翻页 {step.get('times', 1)} 次")
        return True
    if kind == "gesture":
        preset = (step.get("preset") or "").lower()
        w, h = ui_screen(dev)
        paths = {
            "pull_down": (w // 2, int(h * 0.30), w // 2, int(h * 0.70)),
            "pull_down_short": (w // 2, int(h * 0.15), w // 2, int(h * 0.55)),
            "swipe_right": (w // 7, h // 2, w * 6 // 7, h // 2),
            "swipe_left": (w * 6 // 7, h // 2, w // 7, h // 2),
        }
        if preset not in paths:
            raise UiError(f"不认识的 gesture 预设: {preset or '(空)'}")
        x1, y1, x2, y2 = paths[preset]
        if not dry_run:
            dev.shell(f"input swipe {x1} {y1} {x2} {y2} 280")
            time.sleep(float(step.get("settle", 1.2)))
        log(f"    手势 {preset}")
        return True
    if kind == "switches":
        return _adsw_switches(dev, step, dry_run, log, allow_risky, max_screens)
    if kind == "confirm":
        return _adsw_popup(dev, ADSW_CONFIRM_WORDS, dry_run, log, allow_risky)
    if kind == "dismiss":
        return _adsw_popup(dev, ADSW_DISMISS_WORDS, dry_run, log, allow_risky)
    raise UiError(f"不认识的步骤类型: {kind or '(空)'}")


def adsw_run(dev: Adb, target: dict, dry_run: bool = False, log=print,
             allow_risky: bool = False, max_screens: int = 3) -> dict:
    """执行一条 recipe, 返回结果字典。"""
    tid = target.get("id", "?")
    label = target.get("label") or tid
    res = {"id": tid, "label": label, "ok": False, "done": [],
           "failed": [], "skipped": []}
    if not dry_run and ui_locked(dev):
        res["failed"].append("手机锁屏")
        log(f"[{label}] 手机锁屏了, 请先解锁")
        return res
    log(f"[{label}]" + (f"  (来源: {target['source']})" if target.get("source") else ""))
    for idx, step in enumerate(target.get("steps") or [], 1):
        kind = (step.get("do") or "?").lower()
        optional = bool(step.get("optional"))
        try:
            ok = _adsw_step(dev, step, dry_run, log, allow_risky, max_screens)
        except UiError as e:
            if optional:
                res["skipped"].append(f"{kind}: {e}")
                log(f"    [跳过] 可选步骤 {kind}: {e}")
                continue
            res["failed"].append(f"{kind}: {e}")
            log(f"    [失败] 第 {idx} 步 {kind}: {e}")
            return res
        if not ok:
            msg = f"{kind} 未完全生效"
            if optional:
                res["skipped"].append(msg)
                log(f"    [跳过] {msg}")
                continue
            res["failed"].append(msg)
            log(f"    [失败] 第 {idx} 步 {msg}")
            return res
        res["done"].append(kind)
    res["ok"] = not res["failed"]
    return res


def adsw_explore(dev: Adb, log=print, save=None, only_switch: bool = True) -> dict:
    """探路: 列出当前页面的开关/可点项, 并生成可粘贴的 JSON 步骤。"""
    nodes = ui_nodes(dev)
    focus = ui_focus(dev)
    log(f"当前页面: {focus or '未知'}")
    switches = ui_switch_entries(nodes)
    if switches:
        log(f"开关 {len(switches)} 个:")
        for title, node, state in switches:
            mark = "开" if state else ("关" if state is False else "?")
            log(f"  [{mark}] {title or '(无标题)'}  @{node.center[0]},{node.center[1]}")
    else:
        log("这一页没有识别到开关(可能是入口页, 请手动点进目标页后再跑一次)。")
    clicks = [n for n in nodes if n.clickable and n.area > 0 and n.label]
    if clicks:
        log(f"可点项 {len(clicks)} 个"
            + ("" if only_switch else ""))
        for n in clicks[:40]:
            log(f"  · {n.label}")
    snippet = {
        "do": "switches",
        "off": [t for t, _n, _s in switches if t],
        "page": (focus.split("/")[-1] if focus else ""),
    }
    if save:
        p = Path(save)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(snippet, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
        log(f"步骤片段已写入 {p}(粘到 rules/ad-switches.json 的 steps 里)")
    return {"focus": focus, "switches": switches, "snippet": snippet}


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
        if is_denied(pkg):
            continue
        if feature_keep_reason(pkg):
            continue          # 下拉搜索/负一屏/应用商店/推送传输层: 只提示不动它
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
                       "crashbox", "diagnos", "experience", "collect", "tracker",
                       "tracking", "reporter")),
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
    (r"usercenter|(^|\.)accounts?($|\.)|(^|\.)auth", "厂商账号(删了会退出登录)"),
    (r"softsim|esim", "虚拟 SIM"),
    (r"(^|\.)ota($|\.)|updater|softwareupdate", "系统更新"),
    (r"backup|restore", "备份恢复"),
    (r"speechsuite|iflytek", "语音识别(语音输入/语音助手依赖)"),
    (r"accessibility", "无障碍服务"),
    (r"remoteprovisioner|attestation", "设备认证(部分银行/支付 App 会校验)"),
    (r"childrenspace|parental", "儿童/家长模式"),
)
CAUTION_RE = [(re.compile(p, re.I), why) for p, why in CAUTION_RULES]


# ---------------------------------------------------------------------------
# 功能必留包: 不是核心系统组件, 但承载用户真实功能, 一律不卸载/不禁用/不冻结。
# 来源: android-ad-cleaner(rddmwmddr) 的硬规则与真机实测(2026-10)——
#   * 下拉搜索 com.heytap.quicksearchbox: 挂了桌面下滑搜索没了
#   * 负一屏 com.coloros.assistantscreen: 挂了负一屏没了
#   * 各品牌应用商店: 挂了不能装应用/更新
#   * 推送传输层 com.heytap.mcs / com.coloros.mcs: 挂了第三方 App 收不到推送
# 与 DENY_PATTERNS(核心系统组件)分开: 这里给的是"功能保留"原因。
# ---------------------------------------------------------------------------
FEATURE_KEEP_RULES = [
    (r"(^|\.)quicksearchbox($|\.)", "下拉搜索(挂了桌面下滑搜索没了)"),
    (r"(^|\.)assistantscreen($|\.)", "负一屏/速览(挂了负一屏没了)"),
    (r"(^|\.)appmarket($|\.)", "应用市场(装应用/更新入口)"),
    (r"(^|\.)appstore($|\.)", "应用商店(装应用/更新入口)"),
    (r"(^|\.)market($|\.)", "应用商店(装应用/更新入口)"),
    (r"(^|\.)mcs($|\.)", "推送传输层(挂了第三方 App 收不到推送)"),
]
FEATURE_KEEP_RE = [(re.compile(p, re.I), why) for p, why in FEATURE_KEEP_RULES]


def feature_keep_reason(pkg: str):
    """包名是否命中"功能必留"规则(下拉搜索/负一屏/应用商店/推送传输层)。"""
    for r, why in FEATURE_KEEP_RE:
        if r.search(pkg):
            return why
    return None


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

    hdc 通道(HarmonyOS NEXT): bm 拿不到安装分区, 只能列出全部已安装 bundle,
    路径为空; 此时无法区分预装/自装, auto 会额外提示需人工核对。
    """
    if is_hdc(dev):
        return {pkg: "" for pkg in sorted(hdc_list_bundles(dev))}
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


# ---------------------------------------------------------------------------
# 冻结清单(可冻结预装) — rules/freeze-packages.json
#
# 冻结语义参考 Hail(aistra0528/Hail) 与 FreezeYou(FreezeYou/FreezeYou):
#   freeze = 应用不可启动但不删除(数据/APK 保留), pm enable 即解冻
#   三态: disable(默认) / suspend(禁用被拒时兜底) / hide(需 root, 本工具不用)
# 生成/维护: python3 tools/build_freeze_db.py
# ---------------------------------------------------------------------------
FREEZE_DB_FILE = (Path(__file__).resolve().parent.parent
                  / "rules" / "freeze-packages.json")
FREEZE_TIERS = ("safe", "recommended", "caution")


def load_freeze_db(path=None) -> tuple:
    """读取可冻结清单, 返回 (meta, packages, never_freeze_patterns)。"""
    p = Path(path) if path else FREEZE_DB_FILE
    if not p.exists():
        raise FileNotFoundError(
            f"冻结清单不存在: {p}\n"
            "请先运行: python3 tools/build_freeze_db.py")
    data = json.loads(p.read_text(encoding="utf-8"))
    pkgs = data.get("packages") or {}
    if not isinstance(pkgs, dict) or not pkgs:
        raise ValueError(f"冻结清单格式异常或为空: {p}")
    never = data.get("never_freeze") or {}
    return data.get("meta") or {}, pkgs, never.get("patterns") or []


def freeze_candidates(dev: Adb, db: dict, tier: str = "safe",
                      brands=None, rom: dict = None, log=print,
                      never=None) -> dict:
    """本机预装 ∩ 冻结清单, 按分级过滤。

    tier: safe=只列几乎无感知的 / recommended=safe+推荐 / all=含 caution
    never: never_freeze 包名/片段列表(默认从 db["never_freeze"] 取)
    安全护栏(与 apply 一致): DENY 规则/显式核心清单/never_freeze/当前桌面等
    """
    if tier not in ("safe", "recommended", "all"):
        raise ValueError(f"tier 必须是 safe/recommended/all, 收到 {tier!r}")
    want = FREEZE_TIERS[:FREEZE_TIERS.index(tier) + 1] if tier != "all" \
        else FREEZE_TIERS
    # db 既可以是 packages 字典(load_freeze_db 的第二个返回值), 也可以是
    # 整个 freeze-packages.json(自动取其中的 packages/never_freeze);
    # 也兼容 db 上直接挂 never_freeze 键的用法
    if "packages" in db and isinstance(db.get("packages"), dict):
        if never is None:
            nf = db.get("never_freeze") or {}
            never = nf.get("patterns") if isinstance(nf, dict) else nf
        db = db["packages"]
    if never is None:
        nf = db.get("never_freeze") or {}
        never = nf.get("patterns") if isinstance(nf, dict) else nf
    never = [p for p in (never or []) if p]
    installed = preinstalled_packages(dev)
    protect = protected_targets(dev)
    prot = {p for p in protect.values() if p}
    rom = rom if rom is not None else detect_rom(dev)
    brands = {b.lower() for b in (brands or [])}
    rows, skipped = [], []
    skipped_feature = []
    for pkg in sorted(installed):
        if is_denied(pkg) or pkg in prot:
            continue
        keep_why = feature_keep_reason(pkg)
        if keep_why:
            skipped_feature.append((pkg, keep_why))
            continue
        if any(p and p in pkg for p in never):
            skipped.append(pkg)
            continue
        rec = db.get(pkg)
        if not rec or rec.get("t") not in want:
            continue
        if brands and not (brands & {b.lower() for b in rec.get("b") or []}):
            continue
        rows.append({
            "pkg": pkg, "tier": rec.get("t"), "action": "freeze",
            "reason": rec.get("r") or "", "impact": rec.get("i") or "",
            "brands": rec.get("b") or [], "gates": list(rec.get("v") or []),
            "path": installed[pkg],
        })
    kept, skipped_ver = filter_entries_by_rom(
        [{"pkg": r["pkg"], "action": "freeze", "gates": r["gates"],
          "comment": r["impact"]} for r in rows], rom)
    keep_pkgs = {e["pkg"] for e in kept}
    rows = [r for r in rows if r["pkg"] in keep_pkgs]
    order = {"safe": 0, "recommended": 1, "caution": 2}
    rows.sort(key=lambda r: (order.get(r["tier"], 9), r["pkg"]))
    return {"rows": rows, "installed": len(installed),
            "skipped_never": skipped, "skipped_version":
            [e["pkg"] for e in skipped_ver], "tier": tier, "rom": rom,
            "skipped_feature": skipped_feature,
            "protect": protect, "protected_hit": sorted(set(installed) & prot)}


def write_freeze_list(rows: list, path, desc: dict) -> Path:
    rom = desc.get("rom_info") or {}
    lines = [
        f"# CleanYourPhone 冻结清单 — {desc.get('brand','')} {desc.get('model','')}",
        f"# 生成时间: {now_ts()}  Android {desc.get('android','')} "
        f"{('ROM ' + desc['rom']) if desc.get('rom') else ''}",
        "# 冻结 = 应用不可启动但不删除, 数据保留; 解冻: python3 tools/phone.py restore --all",
        "# 语义参考 Hail(aistra0528/Hail) / FreezeYou(FreezeYou/FreezeYou)",
    ]
    if rom.get("display"):
        lines.append(f"# ROM 版本: {rom['display']}"
                     + (f"({rom.get('source')})" if rom.get("source") else ""))
    lines.append("")
    cur = None
    for r in rows:
        if r["tier"] != cur:
            cur = r["tier"]
            lines.append(f"# ---------- {cur} ----------")
        note = (r["impact"] or r["reason"]).replace("\n", " ")[:90]
        lines.append(f"{r['pkg']} freeze  # {note}".rstrip())
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


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


# 内容/广告类预装(不含系统服务): 低版本 ROM 上卸载不被拦截时可直接卸载
CONTENT_HINTS = (
    "browser", "video", "music", "reader", "news", "feed", "store", "shop",
    "mall", "gamecenter", "gamespace", "gamemanager", "theme", "searchbox",
    "pictorial", "magazine", "novel", "podcast", "shortvideo",
)

# 低版本"直接卸载"时仍然只禁用的基础设施类(卸了会影响别的功能)
LEGACY_KEEP_DISABLE = (
    "provider", "framework", "core", "overlay", "rro", "webview", "inputmethod",
    "keyguard", "launcher", "settings", "push", "mcs", "notification", "account",
    "cloud", "backup", "sync", "telecom", "telephony", "bluetooth", "nfc",
    "permission", "installer", "media", "audio", "camera",
)


def content_hit(pkg: str) -> bool:
    low = pkg.lower()
    return any(h in low for h in CONTENT_HINTS)


def legacy_upgradable(pkg: str) -> bool:
    """低版本 ROM 上把"禁用"升级为"卸载"是否合适。

    只针对"广告/统计/内容"这一类(命中启发式或内容关键词), 且不碰基础设施
    (provider/framework/ocr/scene/health 这类服务继续只禁用)。
    """
    if not pkg.startswith(VENDOR_NS):
        return False
    low = pkg.lower()
    if any(k in low for k in LEGACY_KEEP_DISABLE):
        return False
    return content_hit(pkg) or heuristic_hit(pkg) is not None


def auto_candidates(dev: Adb, db: dict, tier: str = "standard",
                    include_third_party: bool = False,
                    include_heuristic: bool = True,
                    min_sources: int = 1, allow_caution: bool = False,
                    exclude_re: str = "", log=print, rom: dict = None,
                    legacy_uninstall: bool = True,
                    profiles: dict = None) -> dict:
    """生成自动候选: 本机预装 ∩ 知识库(按分级) + 启发式补充。

    安全护栏(与 apply 一致, 但更严):
      * 命中 DENY 规则/显式核心清单 -> 剔除
      * 当前桌面/最近任务/输入法/默认浏览器 -> 剔除
      * 知识库标 Unsafe -> 剔除
      * 依赖核心组件、或被核心组件依赖 -> 剔除
      * 命中谨慎名单(查找手机/支付/账号/云服务/系统更新等) -> 默认只提示
    版本感知:
      * rom-profiles.json 的 packages 覆盖: 版本不符 -> 跳过, 指定动作 -> 覆盖
      * 低版本 ROM(卸载未被拦截)时, 内容/广告类 Recommended 条目直接改为卸载
    """
    levels = TIER_LEVELS.get(tier, TIER_LEVELS["standard"])
    installed = preinstalled_packages(dev, include_third_party)
    protect = protected_targets(dev)
    prot = {p for p in protect.values() if p}
    browser = resolve_default_browser(dev)
    if rom is None:
        rom = detect_rom(dev)
    profiles = profiles or load_rom_profiles()

    ex = re.compile(exclude_re) if exclude_re else None
    rows, blocked, skipped_dep, caution, skipped_version = [], [], [], [], []
    skipped_feature = []
    for pkg, path in sorted(installed.items()):
        if is_denied(pkg) or pkg in prot:
            continue
        keep_why = feature_keep_reason(pkg)
        if keep_why:
            skipped_feature.append((pkg, keep_why))
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
        # 版本专属规则: 动作覆盖 / 版本不符跳过
        ov = rom_pkg_override(pkg, rom, profiles)
        if ov and ov.get("skip"):
            skipped_version.append((pkg, ov.get("note") or "该 ROM 版本不适用"))
            continue
        if ov:
            if ov.get("action"):
                cand["action"] = ov["action"]
            if ov.get("note"):
                cand["desc"] = f"{cand['desc']} | [版本] {ov['note']}"
        # 低版本 ROM: 卸载不被拦截, 厂商广告/统计类直接卸载(不再只禁用)
        if (legacy_uninstall and rom.get("legacy")
                and cand["action"] == "disable" and cand["level"] == "Recommended"
                and not why and legacy_upgradable(pkg)):
            cand["action"] = "uninstall"
            cand["desc"] = f"{cand['desc']} | [低版本直卸]".strip()
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
        "protect": protect, "browser": browser, "rom": rom,
        "skipped_version": skipped_version,
        "skipped_feature": skipped_feature,
        "protected_hit": sorted(set(installed) & prot),
    }


def write_auto_list(rows: list, path, desc: dict) -> Path:
    rom = desc.get("rom_info") or {}
    lines = [
        f"# CleanYourPhone 自动生成清单 — {desc.get('brand','')} {desc.get('model','')}",
        f"# 生成时间: {now_ts()}  Android {desc.get('android','')} "
        f"{('ROM ' + desc['rom']) if desc.get('rom') else ''}",
        "# 来源: rules/known-packages.json (UAD-NG + GitHub/Gitee 社区共识)"
        " + rules/rom-profiles.json (版本规则)",
        "# 恢复: python3 tools/phone.py restore --all",
    ]
    if rom.get("display"):
        lines.append(f"# ROM 版本: {rom['display']}"
                     + (f"({rom.get('source')})" if rom.get("source") else "")
                     + f" | 卸载拦截: {'是' if rom.get('uninstall_ok') is False else '否'}")
    if rom.get("note"):
        lines.append(f"# 版本说明: {rom['note']}")
    lines.append("")
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
# ---------------------------------------------------------------------------
# 营销通知渠道: 只读扫描 + 深链跳转手动关
#
#   第三方没法直接关掉别的 App 的通知渠道(那是 App 自己的权限),
#   所以这里的定位是: 帮你找出"哪些渠道是营销类且还开着", 然后逐个跳到
#   系统渠道设置页让你点一下。清单可保存, OTA 之后可以 verify 复查。
#
#   渠道状态读取依赖 `dumpsys notification --noredact` 的输出格式,
#   各 ROM 差异很大; 解析不到时会明确提示改用 `chan app <包名>` 手动关,
#   不假装成功。
# ---------------------------------------------------------------------------
CHAN_MARKETING_WORDS = (
    "推荐", "活动", "优惠", "促销", "福利", "广告", "营销", "资讯", "热点",
    "热搜", "直播", "秒杀", "券", "红包", "任务", "签到", "抽奖", "会员",
    "推广", "新品", "上新", "精选", "话题", "游戏", "小说", "短视频",
    "promo", "marketing", "recommend", "advert", "campaign", "offer",
)
# 这些渠道名里带上面的词也要保留(订单/物流/安全类属于功能通知)
CHAN_KEEP_WORDS = (
    "订单", "物流", "快递", "发货", "支付", "退款", "安全", "验证", "登录",
    "更新", "升级", "下载", "提醒", "闹钟", "日程", "审批", "工单", "告警",
    "order", "ship", "delivery", "pay", "security", "verify", "update",
)
CHANNEL_TOKENS_RE = re.compile(
    r"NotificationChannel\{[^}]*?id='?([^,}']+)'?[^}]*?"
    r"(?:mImportance|importance)=(\d+)", re.I)
CHANNEL_NAME_RE = re.compile(r"name='([^']*)'")


def _pkg_from_line(line: str) -> str:
    """从 dumpsys 的任意一行里抠出包名。"""
    for pat in (r"pkg=([\w.]+)", r"Package \[([\w.]+)\]", r"^\s*([a-z][\w.]*\.[\w.]+):",
                r"packageName=([\w.]+)"):
        m = re.search(pat, line)
        if m:
            return m.group(1)
    return ""


def parse_notification_channels(text: str) -> list:
    """从 dumpsys notification 输出里解析通知渠道。

    返回 [{'pkg','id','name','importance','on'}]。
    importance: 0=NONE(已关), 1=MIN, 2=LOW, 3=DEFAULT, 4=HIGH, 5=MAX
    """
    rows = []
    pkg = ""
    for line in (text or "").splitlines():
        found = _pkg_from_line(line)
        if found:
            pkg = found
        for m in CHANNEL_TOKENS_RE.finditer(line):
            cid = (m.group(1) or "").strip()
            try:
                imp = int(m.group(2))
            except (TypeError, ValueError):
                imp = 3
            if not cid or cid in ("null", "mId"):
                continue
            nm = CHANNEL_NAME_RE.search(line)
            name = (nm.group(1).strip() if nm else "") or cid
            rows.append({"pkg": pkg, "id": cid, "name": name,
                         "importance": imp, "on": imp > 0})
    # 去重(同一渠道可能在多处出现)
    seen, out = set(), []
    for r in rows:
        key = (r["pkg"], r["id"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def is_marketing_channel(name: str) -> bool:
    low = (name or "").lower()
    if any(k in low for k in CHAN_KEEP_WORDS):
        return False
    return any(k in low for k in CHAN_MARKETING_WORDS)


def chan_scan(dev: Adb, only_marketing: bool = True, log=print) -> list:
    """扫描通知渠道(只读)。解析不到会抛 ValueError 提示改用手动方式。"""
    text = dev.shell_all("dumpsys notification --noredact", timeout=60)
    if "NotificationChannel" not in text and "mChannelId" not in text:
        raise ValueError(
            "这台 ROM 的 dumpsys notification 没有暴露渠道信息(常见于部分国产 ROM)。\n"
            "  改用: python3 tools/phone.py chan app <包名>  逐个 App 跳到通知设置页手动关\n"
            "  或:   python3 tools/phone.py ui tap 通知管理  自己点进去")
    rows = parse_notification_channels(text)
    if only_marketing:
        rows = [r for r in rows if is_marketing_channel(r["name"])]
    return rows


def write_chan_list(rows: list, path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 包名\t渠道id\t渠道名\t状态\t关闭方法",
             "# 用 phone.py chan open 本文件 逐个跳转; chan verify 复查",
             ]
    for r in rows:
        lines.append(f"{r['pkg']}\t{r['id']}\t{r['name']}\t"
                     f"{'开' if r['on'] else '关'}\t手动")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def chan_open_intent(pkg: str, channel_id: str = "") -> str:
    """跳转系统渠道/App 通知设置页的标准 action。"""
    if channel_id:
        return ("am start -a android.settings.CHANNEL_NOTIFICATION_SETTINGS "
                f"-e android.provider.extra.APP_PACKAGE {pkg} "
                f"-e android.provider.extra.CHANNEL_ID {channel_id}")
    return ("am start -a android.settings.APP_NOTIFICATION_SETTINGS "
            f"-e android.provider.extra.APP_PACKAGE {pkg}")


def chan_open(dev: Adb, rows: list, log=print, wait: float = 2.0) -> int:
    """逐个跳到渠道设置页, 由用户手动关。返回打开成功数。"""
    opened = 0
    for i, r in enumerate(rows, 1):
        log(f"\n[{i}/{len(rows)}] {r['pkg']} 渠道「{r['name']}」"
            f"({r['id']}) {'开着' if r['on'] else '已关'}")
        out = dev.shell_all(chan_open_intent(r["pkg"], r["id"]))
        if "Error" in out or "Exception" in out:
            log(f"  跳转失败: {out.strip()[:100]}")
            log(f"  改用 App 通知页: {chan_open_intent(r['pkg'])}")
            out = dev.shell_all(chan_open_intent(r["pkg"]))
        if "Error" in out:
            log("  该 ROM 不支持深链跳转, 请手动进入: 设置 > 通知 > 对应 App")
            continue
        opened += 1
        time.sleep(wait)
        log("  已跳到设置页, 请在手机上把该渠道关掉, 然后回来继续")
        if sys.stdin.isatty():
            try:
                input("  按回车继续(输入 s 跳过剩余): ").strip()
            except EOFError:
                pass
    return opened


def chan_verify(dev: Adb, rows: list, log=print) -> dict:
    """复查清单里的渠道还有几个开着。"""
    try:
        now = chan_scan(dev, only_marketing=False, log=log)
    except ValueError as e:
        log(f"[提示] {e}")
        return {"ok": [], "still_on": [], "unknown": rows}
    index = {(r["pkg"], r["id"]): r for r in now}
    ok, still_on, unknown = [], [], []
    for r in rows:
        cur = index.get((r["pkg"], r["id"]))
        if cur is None:
            unknown.append(r)
        elif cur["on"]:
            still_on.append(r)
        else:
            ok.append(r)
    log(f"复查 {len(rows)} 个渠道: 已关 {len(ok)} | 仍开着 {len(still_on)} | "
        f"查不到 {len(unknown)}")
    for r in still_on:
        log(f"  仍开着: {r['pkg']} 「{r['name']}」({r['id']})")
    for r in unknown:
        log(f"  查不到: {r['pkg']} 「{r['name']}」({r['id']})(App 可能已卸载或改了渠道)")
    return {"ok": ok, "still_on": still_on, "unknown": unknown}


def read_chan_list(path) -> list:
    rows = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        rows.append({"pkg": parts[0].strip(), "id": parts[1].strip(),
                     "name": (parts[2].strip() if len(parts) > 2 else parts[1]),
                     "on": (parts[3].strip() == "开") if len(parts) > 3 else True,
                     "importance": 3})
    return rows


# ---------------------------------------------------------------------------
# 挂起包的断网(数据节省程序白名单): 防止被系统/推送拉起
#   只对已被 disable/suspend 的包用, 普通 App 断网会影响正常使用。
# ---------------------------------------------------------------------------
def pkg_uid(dev: Adb, pkg: str):
    out = dev.shell(f"dumpsys package {pkg}")
    m = re.search(r"userId=(\d+)", out)
    return int(m.group(1)) if m else None


def cutnet_set(dev: Adb, pkgs: list, on: bool, log=print) -> dict:
    """给包断网(on=True)或恢复(on=False)。按 uid 走 netpolicy。"""
    res = {"ok": [], "fail": [], "skipped": []}
    verb = "add" if on else "remove"
    for pkg in pkgs:
        uid = pkg_uid(dev, pkg)
        if uid is None:
            res["fail"].append(pkg)
            log(f"[失败] {pkg}: 拿不到 uid(App 可能不存在)")
            continue
        out = dev.shell_all(f"cmd netpolicy {verb} restrict-background {uid}")
        low = out.lower()
        if "error" in low or "unknown" in low or "exception" in low:
            res["fail"].append(pkg)
            log(f"[失败] {pkg}(uid {uid}): {out.strip()[:80] or '无输出'}"
                "(该 ROM 可能没有 cmd netpolicy)")
            continue
        res["ok"].append(pkg)
        log(f"[{'已断网' if on else '已恢复'}] {pkg}(uid {uid})")
    return res


def cutnet_status(dev: Adb, pkgs: list, log=print) -> list:
    out = dev.shell_all("cmd netpolicy list restrict-background")
    if not out.strip() or "Unknown" in out:
        log("[提示] 该 ROM 不支持 cmd netpolicy list, 无法查询断网状态")
        return []
    uids = {str(pkg_uid(dev, p)): p for p in pkgs} if pkgs else {}
    rows = []
    for line in out.splitlines():
        m = re.search(r"uid[=:]?\s*(\d+)", line, re.I)
        if not m:
            continue
        uid = m.group(1)
        pkg = uids.get(uid, "")
        rows.append({"uid": uid, "pkg": pkg})
        log(f"  已断网: uid {uid}" + (f" ({pkg})" if pkg else ""))
    if not rows:
        log("  当前没有被限制后台网络的 uid")
    return rows


# ---------------------------------------------------------------------------
# 快应用: 广告里一点就跳进去的"免安装小程序"
#   关闭方式就是禁用它的框架包(可逆), 不需要额外机制。
# ---------------------------------------------------------------------------
QUICKAPP_PACKAGES = {
    "com.miui.hybrid": "小米/红米 快应用框架",
    "com.miui.hybrid.accessory": "小米 快应用辅助服务",
    "com.nearme.instant.platform": "OPPO/一加/realme 快应用",
    "com.oppo.instant.platform": "OPPO 快应用(旧)",
    "com.coloros.instant.platform": "ColorOS 快应用(旧)",
    "com.vivo.hybrid": "vivo 快应用",
    "com.vivo.instantapp": "vivo 快应用(旧)",
    "com.huawei.fastapp": "华为 快应用",
    "com.hihonor.fastapp": "荣耀 快应用",
    "com.huawei.hms.quickapp": "华为 快应用服务",
    "com.samsung.android.quickapp": "三星 快应用",
}
QUICKAPP_KEYWORDS = ("quickapp", "fastapp", "instant.platform", "hybrid",
                     "instantapp")


def quickapp_find(dev: Adb) -> list:
    """找出本机安装的快应用框架。返回 [(包名, 说明, 是否已禁用)]。"""
    installed = list_packages(dev)
    disabled = list_disabled(dev)
    rows = []
    for pkg in sorted(installed):
        why = QUICKAPP_PACKAGES.get(pkg)
        if not why:
            low = pkg.lower()
            if not any(k in low for k in QUICKAPP_KEYWORDS):
                continue
            why = "疑似快应用框架(按关键词命中)"
        rows.append((pkg, why, pkg in disabled))
    return rows


def quickapp_disable(dev: Adb, pkgs: list, log=print, dry_run: bool = False,
                     base=HOME_DIR) -> dict:
    """禁用快应用框架(走 apply_list, 复用安全规则与 state 记录, 可 restore)。"""
    if not pkgs:
        return {"ok": [], "fail": []}
    entries = [{"pkg": p, "action": "disable", "comment": "快应用框架",
                "gates": []} for p in pkgs]
    return apply_list(dev, entries, list_file="<quickapp>", dry_run=dry_run,
                      do_backup=not dry_run, base=base, log=log)


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
    ap.add_argument("--hdc", metavar="路径",
                    help="强制走 hdc 通道(HarmonyOS NEXT), 值为 hdc 可执行文件路径; "
                         "也可用环境变量 HDC=/path/to/hdc")
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
    p.add_argument("list", help="列表文件, 如 examples/xiaomi-hyperos/debloat.txt; "
                                "动作可为 uninstall / disable / freeze")
    p.add_argument("--dry-run", action="store_true", help="只预演不执行")
    p.add_argument("--yes", "-y", action="store_true", help="跳过确认")
    p.add_argument("--no-backup", action="store_true", help="跳过自动备份(不建议)")
    p.add_argument("--batch", type=int, default=0, metavar="N",
                   help="每批处理 N 个(0=一次性全部), 配合 --screenshot 逐批验证")
    p.add_argument("--screenshot", action="store_true",
                   help="每批处理后自动截图到 ~/.cleanyourphone/<序列号>/shots/")
    p.add_argument("--rom-version", metavar="版本",
                   help="手动指定 ROM 版本(如 13.1 或 coloros:13.1), 用于版本标注过滤")
    p.add_argument("--prefer-disable", action="store_true",
                   help="该版本 ROM 会拦截卸载时直接禁用, 不再尝试卸载(少刷失败日志)")
    p.add_argument("--force-feature", action="store_true",
                   help="放行「功能必留」项(下拉搜索/负一屏/商店/推送层)。"
                        "列表里显式写了这些包时用, 相关功能会失效")

    p = sub.add_parser("restore", help="恢复(包/设置/传感器限制)")
    p.add_argument("list", nargs="?", help="列表文件; 与 --all 二选一")
    p.add_argument("--all", action="store_true", help="恢复 state 记录中的所有包")
    p.add_argument("--yes", "-y", action="store_true", help="跳过确认")

    p = sub.add_parser("check", help="检查列表状态(OTA 后用)")
    p.add_argument("list", help="列表文件")
    p.add_argument("--fix", action="store_true", help="把状态变化的项重新应用")
    p.add_argument("--yes", "-y", action="store_true", help="修复时跳过确认")
    p.add_argument("--rom-version", metavar="版本",
                   help="手动指定 ROM 版本(如 13.1 或 coloros:13.1)")

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
    p.add_argument("--rom-version", metavar="版本",
                   help="手动指定 ROM 版本(如 13.1 或 coloros:13.1)")
    p.add_argument("--no-legacy-uninstall", action="store_true",
                   help="低版本 ROM 上也不把内容类预装从「禁用」升级为「卸载」")

    p = sub.add_parser("freeze", help="按冻结清单冻结预装应用(可恢复, 不删除)")
    p.add_argument("--tier", default="safe",
                   choices=["safe", "recommended", "all"],
                   help="safe=几乎无感知(默认) / recommended=含推荐项 / all=含 caution")
    p.add_argument("--brand", action="append", default=[], metavar="品牌",
                   help="只处理指定品牌(可多次): xiaomi/oppo/vivo/huawei/honor/"
                        "samsung/zte/moto/lenovo/transsion")
    p.add_argument("--db", metavar="文件",
                   help="指定冻结清单(默认 rules/freeze-packages.json)")
    p.add_argument("--write", metavar="文件", help="清单保存路径")
    p.add_argument("--apply", action="store_true",
                   help="真正执行冻结(默认只列清单, 不动手机)")
    p.add_argument("--dry-run", action="store_true", help="预演(与 --apply 连用)")
    p.add_argument("--yes", "-y", action="store_true", help="执行时跳过确认")
    p.add_argument("--limit", type=int, default=0, metavar="N",
                   help="最多列出/处理 N 项(0=不限)")
    p.add_argument("--rom-version", metavar="版本",
                   help="手动指定 ROM 版本(如 13.1 或 coloros:13.1)")

    p = sub.add_parser("rom", help="识别 ROM 家族/版本, 查看该版本的清理策略")
    p.add_argument("--list", metavar="文件",
                   help="检查某个清理列表在本机版本下的适用性")
    p.add_argument("--version", "--rom-version", dest="version", metavar="版本",
                   help="手动指定版本(如 13.1 或 coloros:13.1), 可离线使用")
    p.add_argument("--profiles", metavar="文件",
                   help="指定版本规则库(默认 rules/rom-profiles.json)")

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

    p = sub.add_parser("chan", help="营销通知渠道: 只读扫描 + 深链跳转手动关")
    p.add_argument("action", choices=["scan", "open", "app", "verify"],
                   help="scan=扫描候选(只读) / open=逐个跳到渠道页手动关 / "
                        "app=跳到 App 通知管理页 / verify=复查清单里还剩几个开着的")
    p.add_argument("target", nargs="?", default="",
                   help="scan: 保存路径(可选) / open,verify: 清单文件 "
                        "(包名<TAB>渠道id<TAB>说明) / app: 包名")
    p.add_argument("--save", metavar="文件", default="",
                   help="scan 时把候选清单写到该文件(默认只打印)")
    p.add_argument("--all", action="store_true",
                   help="scan 时连服务类渠道一起列(默认按营销关键词过滤)")

    p = sub.add_parser("cutnet", help="给挂起的广告/统计包断网(防被系统拉起)")
    p.add_argument("action", choices=["on", "off", "status"])
    p.add_argument("pkgs", nargs="*", metavar="包名",
                   help="要断网/恢复的包名; status 时省略则检查支持性")
    p.add_argument("--yes", "-y", action="store_true", help="跳过确认")

    p = sub.add_parser("ui", help="界面自动化: 读屏/找控件/点开关(纯 adb, 不装软件)")
    p.add_argument("action", choices=["dump", "find", "tap", "switch", "wait",
                                      "open", "back", "home"])
    p.add_argument("target", nargs="?", default="",
                   help="dump 时忽略; find/tap 是文本; switch 是开关标题; "
                        "open 是包名")
    p.add_argument("state", nargs="?", default="toggle",
                   choices=["on", "off", "toggle"], help="switch 的目标状态")
    p.add_argument("--exact", action="store_true", help="文本必须完全一致")
    p.add_argument("--index", type=int, default=0, help="多个匹配时取第几个(从 0 开始)")
    p.add_argument("--switch", action="store_true", help="dump 时只列开关")
    p.add_argument("--limit", type=int, default=60, help="最多列多少行")
    p.add_argument("--timeout", type=float, default=10, help="wait 的超时秒数")
    p.add_argument("--activity", help="open 时指定 Activity")
    p.add_argument("--save", help="dump 时把控件树 XML 保存到该文件")
    p.add_argument("--allow-risky", action="store_true",
                   help="允许点含敏感词的控件(同意/支付/删除等)")
    p.add_argument("--yes", "-y", action="store_true", help="跳过确认")

    p = sub.add_parser("adsw", help="App 内广告开关: 按规则库自动拨(可预演)")
    p.add_argument("action", choices=["list", "run", "verify", "explore"])
    p.add_argument("ids", nargs="*", help="只处理指定条目 id(省略=本机全部适用条目)")
    p.add_argument("--dry-run", action="store_true", help="只预演不点击")
    p.add_argument("--yes", "-y", action="store_true", help="跳过确认")
    p.add_argument("--rules", help="指定规则库(默认 rules/ad-switches.json)")
    p.add_argument("--max-screens", type=int, default=3,
                   help="每个页面最多翻几屏找开关(默认 3)")
    p.add_argument("--allow-risky", action="store_true",
                   help="允许点含敏感词的控件")
    p.add_argument("--all", action="store_true",
                   help="list 时列出全部条目, 不按品牌/版本过滤")
    p.add_argument("--any-model", action="store_true",
                   help="忽略机型限制, 强制套用带 models 的条目(可能点到别的开关)")
    p.add_argument("--save", help="explore 时把步骤片段保存到该文件")

    p = sub.add_parser("quickapp", help="检测/关闭快应用(广告跳转的免安装小程序)")
    p.add_argument("action", choices=["check", "off"])
    p.add_argument("--dry-run", action="store_true", help="只预演不执行")
    p.add_argument("--yes", "-y", action="store_true", help="跳过确认")

    sub.add_parser("finish", help="收尾: 关闭 USB 调试并断开无线连接")
    return ap


def cmd_doctor(args) -> int:
    dev = None
    adb_path = None
    try:
        adb_path = ensure_adb(verbose=False)
    except AdbError:
        adb_path = None
    if adb_path:
        adb = Adb(adb_path)
        try:
            serial = pick_device(adb, args.serial)
            dev = Adb(adb_path, serial)
            print(f"[OK] adb: {adb_path}")
            print(f"[OK] 设备已连接: {serial}")
        except AdbError as e:
            print(f"[提示] adb: {e}")
    if dev is None and not getattr(args, "serial", None):
        # 没有 Android 设备时尝试 hdc(HarmonyOS NEXT)
        try:
            _, dev = pick_any_device(None)
            print(f"[OK] hdc: {dev.adb}")
            print(f"[OK] HarmonyOS 设备已连接: {dev.serial}")
        except AdbError as e:
            print(f"[提示] hdc: {e}")
    if dev is None:
        if not adb_path:
            print("[失败] 没有找到 adb, 也没有找到 hdc。")
            print("       Android 手机请安装 adb; HarmonyOS NEXT 请安装 hdc(见华为 README)。")
        else:
            print("[失败] 没有已连接的设备。Android 打开 USB 调试; "
                  "HarmonyOS NEXT 安装 hdc 并开启调试模式。")
        return 2
    desc = describe_device(dev)
    print(f"[OK] 品牌/型号: {desc['brand']} {desc['model']}")
    print(f"[OK] Android {desc['android']} (SDK {desc['sdk']})"
          + (f" | ROM: {desc['rom']}" if desc["rom"] else ""))
    rom = desc.get("rom_info") or {}
    if rom.get("family"):
        print(f"[OK] ROM 版本: {rom['display']}(识别自 {rom.get('source') or '?'}"
              f", 可信度 {rom.get('confidence')})")
        for line in rom_policy_lines(
                rom, channel=getattr(dev, "transport", "adb")):
            print(f"[版本] {line}")
    else:
        print("[提示] 未识别 ROM 家族, 只按 Android 版本与包名安全规则处理")
    protect = protected_targets(dev)
    for label, key in (("桌面", "home"), ("最近任务", "recents"), ("输入法", "ime")):
        if protect.get(key):
            print(f"[OK] 当前{label}: {protect[key]}(清理时自动保护)")
    if is_hdc(dev):
        print("[提示] HarmonyOS NEXT: 只能卸载(bm uninstall), 不支持禁用/挂起, "
              "恢复需在应用市场手动重装")
        print("[下一步] 预演: python3 tools/phone.py apply "
              f"{desc['example']}/debloat.txt --dry-run --hdc {dev.adb}")
    else:
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
    rom = desc.get("rom_info") or {}
    print(f"序列号:   {dev.serial}")
    print(f"通道:     {'hdc(HarmonyOS NEXT)' if is_hdc(dev) else 'adb'}")
    print(f"品牌:     {desc['brand']}")
    print(f"型号:     {desc['model']}"
          + (f"({desc['marketname']})" if desc.get("marketname") else ""))
    print(f"ROM:      {desc['rom'] or '未知'}")
    if rom.get("family"):
        print(f"版本识别: {rom.get('raw')} -> {rom['display']}"
              f"({rom.get('source') or '?'}, generation "
              f"{'.'.join(str(x) for x in rom.get('generation') or ()) or '?'})")
        if rom.get("note"):
            print(f"版本说明: {rom['note']}")
        for line in rom_policy_lines(
                rom, channel=getattr(dev, "transport", "adb")):
            print(f"版本策略: {line}")
    print(f"Android:  {desc['android']} (SDK {desc['sdk']})")
    print(f"Build:    {desc['display'] or '未知'}")
    print(f"桌面:     {protect.get('home') or '解析失败'}")
    print(f"最近任务: {protect.get('recents') or '解析失败'}")
    print(f"输入法:   {protect.get('ime') or '解析失败'}")
    print(f"推荐列表: {desc['example']}")
    return 0


def cmd_rom(args) -> int:
    """识别 ROM 家族/版本, 说明该版本的清理策略与清单适用性。"""
    profiles = load_rom_profiles(args.profiles)
    if args.version and not args.serial:
        # 允许纯离线: 只给版本号, 不连设备
        rom = detect_rom(props={}, override=args.version, profiles=profiles)
        print(f"手动指定: {rom.get('display') or args.version}")
    else:
        _, dev = _need_device(args)
        desc = describe_device(dev)
        rom = detect_rom(dev, override=args.version, profiles=profiles)
        print(f"设备:   {desc['brand']} {desc['model']} | Android {desc['android']}")
        print(f"Build:  {desc['display'] or '未知'}")
        if rom.get("family"):
            print(f"家族:   {rom['label']}({rom['family']})")
            print(f"版本:   {rom['display']}"
                  f"  原始值: {rom.get('raw') or '?'}"
                  f"  来源: {rom.get('source') or '?'}")
            print(f"可比序: {'.'.join(str(x) for x in rom.get('generation') or ()) or '?'}"
                  "  (列表里的 [v>=13] 就是和它比)")
            if rom.get("verified"):
                print(f"依据:   {rom['verified']}")
        else:
            print("家族:   未识别(可加 --version coloros:13.1 手动指定)")
    if rom.get("note"):
        print(f"版本说明: {rom['note']}")
    for line in rom_policy_lines(rom):
        print(line)

    # 清单适用性检查
    if args.list:
        entries = parse_list_file(args.list)
        kept, skipped = filter_entries_by_rom(entries, rom)
        gated = [e for e in entries if e.get("gates")]
        print("")
        print(f"清单 {args.list}: 共 {len(entries)} 条, "
              f"其中带版本标注 {len(gated)} 条")
        print(f"  适用 {len(kept)} 条 | 版本不符 {len(skipped)} 条")
        for e in skipped:
            note = f"  # {e['comment']}" if e.get("comment") else ""
            print(f"    [跳过] {e['pkg']}  {fmt_gates(e['gates'])}{note}")
        if not gated:
            print("  提示: 该清单没有版本标注, 在任何版本上都会全部执行; "
                  "跨版本使用时建议给条目加 [v>=13] / [v<12]")
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


def _unsupported_rom(rom: dict, dev=None) -> bool:
    """该 ROM 版本不支持清理时给出说明并返回 True。

    HarmonyOS NEXT(5.x)走 hdc 通道时不算"不支持": bm 工具仍可卸载,
    只是没有禁用/挂起能力, 由 apply 阶段逐条如实报告。
    """
    if rom and rom.get("unsupported"):
        if dev is not None and rom.get("hdc_required") and is_hdc(dev):
            print("[提示] HarmonyOS NEXT: 当前为 hdc 通道, 只能卸载, 不支持禁用/挂起。")
            return False
        print(f"[不支持] {rom['unsupported']}")
        return True
    return False


def cmd_apply(args) -> int:
    _, dev = _need_device(args)
    entries = parse_list_file(args.list)
    rom = detect_rom(dev, override=getattr(args, "rom_version", None))
    print(f"ROM: {rom.get('display') or '未识别'}")
    if _unsupported_rom(rom, dev):
        return 2
    kept, skipped = filter_entries_by_rom(entries, rom)
    print(f"列表 {args.list} 共 {len(entries)} 个条目"
          + (f", 其中 {len(skipped)} 条标注的 ROM 版本与本机不符, 将跳过"
             if skipped else ""))
    if not kept:
        print("没有适用于当前 ROM 版本的条目。")
        return 0
    if not args.dry_run and not args.yes and not confirm(
            f"将对设备 {dev.serial} 执行 {len(kept)} 项操作, 继续? [y/N] "):
        print("已取消。可先加 --dry-run 预演。")
        return 1
    apply_list(dev, kept, list_file=args.list, dry_run=args.dry_run,
               do_backup=not args.no_backup, batch=args.batch,
               screenshot=args.screenshot, rom=rom,
               prefer_disable=args.prefer_disable,
               force_feature=args.force_feature)
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
    rom = detect_rom(dev, override=getattr(args, "rom_version", None))
    print(f"ROM: {rom.get('display') or '未识别'}")
    if _unsupported_rom(rom, dev):
        return 2
    if args.fix and not args.yes and not confirm("将对变化项重新执行操作, 继续? [y/N] "):
        print("已取消。")
        return 1
    check_list(dev, entries, fix=args.fix, rom=rom)
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
    rom = detect_rom(dev, override=getattr(args, "rom_version", None))
    print(f"设备: {desc['brand']} {desc['model']} | Android {desc['android']}"
          + (f" | ROM {desc['rom']}" if desc["rom"] else ""))
    if _unsupported_rom(rom, dev):
        return 2
    for line in rom_policy_lines(rom, channel=getattr(dev, "transport", "adb")):
        print(f"[ROM] {line}")
    print(f"知识库: {len(db)} 个包 (生成于 {meta.get('generated_at', '未知')})")
    print(f"力度: {args.tier} | 启发式: {'关' if args.no_heuristic else '开'} | "
          f"最少来源数: {args.min_sources}")

    res = auto_candidates(
        dev, db, tier=args.tier,
        include_third_party=args.include_third_party,
        include_heuristic=not args.no_heuristic,
        min_sources=args.min_sources, allow_caution=args.allow_caution,
        exclude_re=args.exclude, rom=rom,
        legacy_uninstall=not args.no_legacy_uninstall)

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
    if res.get("skipped_feature"):
        print(f"[保留] {len(res['skipped_feature'])} 个功能必留(下拉搜索/负一屏/"
              f"应用商店/推送传输层):")
        for pkg, why in res["skipped_feature"][:6]:
            print(f"        {pkg}  — {why}")
        if len(res["skipped_feature"]) > 6:
            print(f"        ... 共 {len(res['skipped_feature'])} 个")
    if res.get("skipped_version"):
        print(f"[版本] {len(res['skipped_version'])} 个因 ROM 版本不符跳过:")
        for pkg, note in res["skipped_version"][:6]:
            print(f"        {pkg}  — {note}")
        if len(res["skipped_version"]) > 6:
            print(f"        ... 其余 {len(res['skipped_version']) - 6} 个")
    legacy_up = sum(1 for r in rows if "[低版本直卸]" in (r.get("desc") or ""))
    if legacy_up:
        print(f"[低版本] {legacy_up} 个内容/广告类预装已按「直接卸载」处理"
              f"({rom.get('display')} 未拦截卸载)")
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
    apply_list(dev, entries, list_file=str(saved), base=HOME_DIR, rom=rom)
    print("\n恢复: python3 tools/phone.py restore --all")
    return 0


def cmd_freeze(args) -> int:
    """冻结清单: 本机预装 ∩ rules/freeze-packages.json(可恢复, 不删除)。"""
    _, dev = _need_device(args)
    try:
        meta, db, _never = load_freeze_db(args.db)
    except (FileNotFoundError, ValueError) as e:
        print(f"[失败] {e}")
        return 2

    desc = describe_device(dev)
    rom = detect_rom(dev, override=getattr(args, "rom_version", None))
    print(f"设备: {desc['brand']} {desc['model']} | Android {desc['android']}"
          + (f" | ROM {desc['rom']}" if desc["rom"] else ""))
    if _unsupported_rom(rom, dev):
        return 2
    for line in rom_policy_lines(rom, channel=getattr(dev, "transport", "adb")):
        print(f"[ROM] {line}")
    print(f"冻结清单: {len(db)} 个包 (生成于 {meta.get('generated_at', '未知')})")
    print(f"分级: {args.tier}"
          + (f" | 品牌过滤: {','.join(args.brand)}" if args.brand else ""))
    print("冻结 = 应用不可启动但不删除, 数据保留; 解冻: "
          "python3 tools/phone.py restore --all")

    res = freeze_candidates(dev, db, tier=args.tier,
                            brands=args.brand, rom=rom, never=_never)
    rows = res["rows"]
    if args.limit and args.limit > 0:
        rows = rows[:args.limit]

    print(f"\n本机预装 {res['installed']} 个, 命中可冻结 {len(rows)} 个")
    for label, key in (("桌面", "home"), ("最近任务", "recents"), ("输入法", "ime")):
        if res["protect"].get(key):
            print(f"[保护] 当前{label}: {res['protect'][key]}")
    if res["skipped_never"]:
        print(f"[跳过] {len(res['skipped_never'])} 个命中 never_freeze 黑名单: "
              f"{', '.join(res['skipped_never'][:5])}"
              + (" ..." if len(res["skipped_never"]) > 5 else ""))
    if res.get("skipped_feature"):
        print(f"[保留] {len(res['skipped_feature'])} 个功能必留(下拉搜索/负一屏/"
              f"应用商店/推送传输层):")
        for pkg, why in res["skipped_feature"][:6]:
            print(f"        {pkg}  — {why}")
        if len(res["skipped_feature"]) > 6:
            print(f"        ... 共 {len(res['skipped_feature'])} 个")
    if res["skipped_version"]:
        print(f"[版本] {len(res['skipped_version'])} 个因 ROM 版本不符跳过: "
              f"{', '.join(res['skipped_version'][:5])}")

    if not rows:
        print("\n本机没有可冻结的预装应用(可能已全部处理过, 或不在清单内)。")
        return 0

    cur = None
    for r in rows:
        if r["tier"] != cur:
            cur = r["tier"]
            n = sum(1 for x in rows if x["tier"] == cur)
            print(f"\n== {cur} ({n}) ==")
        print(f"  freeze    {r['pkg']:44s} {r['impact'][:60]}")

    out = Path(args.write) if args.write else (
        Path(HOME_DIR) / dev.serial / "freeze-list.txt")
    saved = write_freeze_list(rows, out, desc)
    print(f"\n清单已保存: {saved}")

    if not args.apply:
        print("这是预演(未改动手机)。确认无误后执行:")
        print(f"  python3 tools/phone.py freeze --tier {args.tier} --apply")
        return 0
    if args.dry_run:
        print("[预演模式] 不会真正冻结。")
    if not args.yes and not args.dry_run and not confirm(
            f"将冻结 {len(rows)} 个预装应用(可恢复), 继续? [y/N] "):
        print("已取消。")
        return 1
    entries = [{"pkg": r["pkg"], "action": "freeze", "comment": r["impact"]}
               for r in rows]
    apply_list(dev, entries, list_file=str(saved), base=HOME_DIR, rom=rom,
               dry_run=args.dry_run)
    if not args.dry_run:
        print("\n解冻: python3 tools/phone.py restore --all")
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


def cmd_ui(args) -> int:
    _, dev = _need_device(args)
    act = args.action
    if act == "dump":
        nodes = ui_nodes(dev)
        print(f"当前页面: {ui_focus(dev) or '未知'}")
        lines = ui_describe(nodes, limit=args.limit, only_switch=args.switch)
        for line in lines:
            print("  " + line)
        if not lines:
            print("  (没解析到控件; 换一页再试, 或用 --switch 只看开关)")
        if args.save:
            p = Path(args.save)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(ui_dump_xml(dev), encoding="utf-8")
            print(f"控件树 XML 已保存: {p}")
        return 0

    if act == "find":
        hits = ui_find(ui_nodes(dev), args.target, exact=args.exact)
        if not hits:
            print(f"找不到「{args.target}」")
            return 1
        for n in hits[:args.limit]:
            print(f"  {n}  可点={n.clickable} 可勾选={n.is_switch}")
        return 0

    if act == "tap":
        nodes = ui_nodes(dev)
        hits = ui_find(nodes, args.target, exact=args.exact)
        if not hits:
            print(f"找不到「{args.target}」。先用 ui dump 看页面上有什么。")
            return 1
        node = hits[min(args.index, len(hits) - 1)]
        if not args.yes and not confirm(f"点击「{node.label or node.rid}」? [y/N] "):
            print("已取消。")
            return 1
        ui_tap_node(dev, node, allow_risky=args.allow_risky)
        return 0

    if act == "switch":
        entries = ui_switch_entries(ui_nodes(dev))
        needle = args.target.lower()
        hit = [e for e in entries if needle in (e[0] or "").lower()]
        if not hit:
            print(f"页面上没有标题含「{args.target}」的开关。")
            print("用 ui dump --switch 看看这一页有哪些开关。")
            return 1
        title, node, state = hit[0]
        cur = "开" if state else ("关" if state is False else "读不到")
        print(f"开关「{title}」当前: {cur}")
        want = args.state
        need = (want == "off" and state is not False) or \
               (want == "on" and state is not True) or want == "toggle"
        if not need:
            print("已经是目标状态, 没有动它。")
            return 0
        if not args.yes and not confirm(f"点击开关「{title}」? [y/N] "):
            print("已取消。")
            return 1
        ui_tap_node(dev, node, allow_risky=args.allow_risky, label_hint=title)
        time.sleep(0.6)
        after = [s for t, _n, s in ui_switch_entries(ui_nodes(dev)) if t == title]
        if after:
            s = after[0]
            print(f"现在: {'开' if s else ('关' if s is False else '读不到(请人工确认)')}")
        return 0

    if act == "wait":
        ok = ui_wait(dev, args.target, timeout=args.timeout, exact=args.exact)
        print(f"{'已出现' if ok else '等不到'}: {args.target}")
        return 0 if ok else 1

    if act == "open":
        focus = ui_launch(dev, args.target, args.activity or "")
        if not focus:
            print("已发出启动命令, 但读不到前台组件(可能被系统拦截)")
        return 0

    if act in ("back", "home"):
        ui_key(dev, act)
        print(f"已按 {act}")
        return 0
    return 2


def cmd_adsw(args) -> int:
    _, dev = _need_device(args)
    if args.action == "explore":
        adsw_explore(dev, save=args.save)
        return 0

    db = load_adsw(args.rules)
    if not db["targets"]:
        print(f"规则库是空的或不存在: {args.rules or ADSW_RULE_FILE}")
        return 2

    rom = detect_rom(dev)
    desc = describe_device(dev)
    brand = rom.get("brand") or desc.get("brand") or ""
    family = rom.get("family") or ""
    gen = rom.get("generation") or ()
    model = desc.get("model") or ""
    if args.action == "list" and args.all:
        targets = db["targets"]
    else:
        targets = adsw_match(db["targets"], brand=brand, family=family, gen=gen,
                             ids=args.ids, model=model,
                             strict_model=not args.any_model)
    if not targets:
        print(f"没有匹配 {brand or '未知品牌'} / {family or '未知 ROM'} "
              f"{rom.get('display') or ''} {model} 的条目。")
        print("机型专属路径不能跨机型套用(可能点到别的开关)。可以:")
        print("  · adsw list --all        看全部条目")
        print("  · adsw run <id> --any-model  强制跑某条(自担风险)")
        print("  · adsw explore           自己探路, 把路径补进 rules/ad-switches.json")
        return 1

    if args.action == "list":
        print(f"本机: {brand} / {family or '未知'} {rom.get('display') or ''}"
              f" | 适用条目 {len(targets)} 条")
        for t in targets:
            mark = "已实测" if t.get("verified") else "待验证"
            print(f"\n· {t['id']}  [{mark}]")
            print(f"   {t.get('label') or ''}")
            if t.get("manual"):
                print(f"   手动路径: {t['manual']}")
            if t.get("source"):
                print(f"   来源: {t['source']}")
            print(f"   步骤 {len(t.get('steps') or [])} 步")
        print("\n执行: python3 tools/phone.py adsw run [条目id ...] --dry-run 先预演")
        return 0

    if args.action == "verify":
        print("复查模式: 只读, 会按步骤导航到各页面读开关状态, 不点击。")
        bad = 0
        for t in targets:
            res = adsw_run(dev, t, dry_run=True, log=print,
                           max_screens=args.max_screens)
            if not res["ok"]:
                bad += 1
            print("")
        print(f"复查完成: {len(targets)} 条, 有 {bad} 条没走通")
        return 0 if not bad else 1

    # run
    if not args.yes and not args.dry_run:
        print(f"将对 {len(targets)} 条目标自动点击界面(约 {len(targets)} 个 App)。")
        print("手机请保持解锁、停在桌面, 期间不要手动操作。")
        if not confirm("继续? [y/N] "):
            print("已取消。可先加 --dry-run 预演。")
            return 1
    ok_n, fail_n = 0, 0
    for t in targets:
        res = adsw_run(dev, t, dry_run=args.dry_run, log=print,
                       allow_risky=args.allow_risky,
                       max_screens=args.max_screens)
        if res["ok"]:
            ok_n += 1
            print(f"  完成: 走了 {len(res['done'])} 步"
                  + (f", 跳过 {len(res['skipped'])} 步" if res["skipped"] else ""))
        else:
            fail_n += 1
            print(f"  未完成: {'; '.join(res['failed'])}")
        print("")
    print(f"合计: 完成 {ok_n} 条 | 未完成 {fail_n} 条"
          + ("(预演, 未改动手机)" if args.dry_run else ""))
    if not args.dry_run and ok_n:
        print("\nApp 内开关属于「手动态」, restore 不会自动还原; "
              "要还原请按各条目 manual 路径把开关打开。")
    return 0 if not fail_n else 1


def cmd_chan(args) -> int:
    _, dev = _need_device(args)
    if args.action == "scan":
        rows = chan_scan(dev, only_marketing=not args.all)
        if not rows:
            print("没有扫到营销类渠道。加 --all 可以看全部渠道。")
            return 0
        print(f"营销类渠道 {len(rows)} 个(只读扫描, 没动手机):")
        for r in rows:
            print(f"  [{'开' if r['on'] else '关'}] {r['pkg']}"
                  f"  {r['name']}  ({r['id']})")
        target = args.save or args.target
        if target:
            p = write_chan_list(rows, target)
            print(f"\n清单已保存: {p}")
            print(f"逐个关闭: python3 tools/phone.py chan open {p}")
        else:
            print("\n加 --save 文件名 可保存清单, 再用 chan open 逐个跳转关闭")
        return 0

    if args.action == "open":
        if not args.target:
            print("请指定清单文件: chan open <清单.tsv>")
            return 2
        rows = read_chan_list(args.target)
        if not rows:
            print("清单是空的。")
            return 2
        print(f"将逐个跳到系统渠道设置页, 共 {len(rows)} 个, 请在手机上关掉。")
        chan_open(dev, rows)
        print(f"\n关完复查: python3 tools/phone.py chan verify {args.target}")
        return 0

    if args.action == "app":
        if not args.target:
            print("请指定包名: chan app <包名>")
            return 2
        out = dev.shell_all(chan_open_intent(args.target))
        print(out.strip() or f"已跳转 {args.target} 的通知设置页")
        return 0

    if args.action == "verify":
        if not args.target:
            print("请指定清单文件: chan verify <清单.tsv>")
            return 2
        res = chan_verify(dev, read_chan_list(args.target))
        return 0 if not res["still_on"] else 1
    return 2


def cmd_cutnet(args) -> int:
    _, dev = _need_device(args)
    if args.action == "status":
        cutnet_status(dev, args.pkgs)
        return 0
    if not args.pkgs:
        print("请给出包名(一般是被 freeze/suspend 的广告/统计包): "
              "cutnet on com.xxx")
        return 2
    on = args.action == "on"
    if on and not args.yes and not confirm(
            f"限制 {len(args.pkgs)} 个包的后台网络? [y/N] "):
        print("已取消。")
        return 1
    res = cutnet_set(dev, args.pkgs, on)
    return 0 if not res["fail"] else 1


def cmd_quickapp(args) -> int:
    _, dev = _need_device(args)
    rows = quickapp_find(dev)
    if not rows:
        print("本机没有快应用框架(或已被清理)。")
        return 0
    print(f"找到 {len(rows)} 个快应用相关包:")
    for pkg, why, dis in rows:
        print(f"  [{'已禁用' if dis else '启用中'}] {pkg}  # {why}")
    if args.action == "check":
        print("\n关闭: python3 tools/phone.py quickapp off")
        return 0
    todo = [p for p, _w, d in rows if not d]
    if not todo:
        print("全部已禁用, 无需操作。")
        return 0
    if not args.yes and not confirm(
            f"禁用 {len(todo)} 个快应用框架? 之后广告里不会再跳进快应用, "
            "restore 可恢复 [y/N] "):
        print("已取消。")
        return 1
    res = quickapp_disable(dev, todo, dry_run=args.dry_run)
    print(f"\n完成: 成功 {len(res['ok'])} | 失败 {len(res['fail'])}")
    print("恢复: python3 tools/phone.py restore --all")
    return 0 if not res["fail"] else 1


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
        "auto": cmd_auto, "rom": cmd_rom, "freeze": cmd_freeze,
        "settings": cmd_settings, "dns": cmd_dns, "shake": cmd_shake,
        "ui": cmd_ui, "adsw": cmd_adsw, "chan": cmd_chan,
        "cutnet": cmd_cutnet, "quickapp": cmd_quickapp,
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
