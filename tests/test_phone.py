#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CleanYourPhone 单元测试(使用 FakeAdb 模拟设备, 无需真机)。

运行: python3 -I tests/test_phone.py
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import phone  # noqa: E402


class FakeAdb(phone.Adb):
    """用内存数据结构模拟 adb 行为。"""

    def __init__(self, packages, disabled=(), home=None, extra=None,
                 refuse_disable=(), suspended=(), refuse_settings=False,
                 paths=None, third_party=()):
        self._packages = set(packages)
        self._disabled = set(disabled)
        self._suspended = set(suspended)
        self._refuse_disable = set(refuse_disable)
        self._refuse_settings = refuse_settings
        self._settings = {}
        self._home = home
        self._paths = dict(paths or {})
        self._third_party = set(third_party)
        self.calls = []
        self._extra = extra or {}
        self.serial = "FAKE123"

    def _path_of(self, pkg: str) -> str:
        if pkg in self._paths:
            return self._paths[pkg]
        tail = pkg.rsplit(".", 1)[-1].title()
        return f"/system/app/{tail}/{tail}.apk"

    def run(self, *args, timeout=120):
        self.calls.append(args)
        self._stderr = ""
        key = " ".join(str(a) for a in args)
        if key in self._extra:
            out = self._extra[key]
        elif args and args[0] == "shell":
            cmd = " ".join(args[1:])
            if cmd == "pm list packages":
                out = "\n".join(f"package:{p}" for p in sorted(self._packages))
            elif cmd == "pm list packages -s -f":
                out = "\n".join(
                    f"package:{self._path_of(p)}={p}"
                    for p in sorted(self._packages - self._third_party))
            elif cmd == "pm list packages -3 -f":
                out = "\n".join(
                    f"package:{self._path_of(p)}={p}"
                    for p in sorted(self._third_party))
            elif cmd == "pm list packages -d":
                out = "\n".join(f"package:{p}" for p in sorted(self._disabled))
            elif cmd == "dumpsys package":
                lines = []
                for p in sorted(self._packages | self._disabled):
                    lines.append(f"  Package [{p}] (1a2b3c):")
                    lines.append(
                        f"    User 0: ceDataInode=1 installed=true hidden=false "
                        f"suspended={'true' if p in self._suspended else 'false'} "
                        f"stopped=false notLaunched=false "
                        f"enabled={'3' if p in self._disabled else '0'} "
                        f"ofs=0 pdm=false instant=false virtual=false")
                out = "\n".join(lines)
            elif cmd.startswith("cmd package resolve-activity"):
                out = self._home or ""
            elif cmd.startswith("pm uninstall"):
                pkg = cmd.split()[-1]
                if pkg in self._packages:
                    self._packages.discard(pkg)
                    out = "Success"
                else:
                    out = "Failure [DELETE_FAILED_INTERNAL_ERROR]"
            elif cmd.startswith("pm disable-user"):
                pkg = cmd.split()[-1]
                if pkg in self._refuse_disable:
                    # ColorOS 乐划锁屏类: 静默拒绝, 退出码仍为 0
                    out = f"Package {pkg} new state: default"
                else:
                    self._disabled.add(pkg)
                    out = f"Package {pkg} new state: disabled-user"
            elif cmd.startswith("pm suspend"):
                pkg = cmd.split()[-1]
                self._suspended.add(pkg)
                out = f"Package {pkg} new suspended state: true"
            elif cmd.startswith("pm unsuspend"):
                pkg = cmd.split()[-1]
                self._suspended.discard(pkg)
                out = f"Package {pkg} new suspended state: false"
            elif cmd.startswith("pm enable"):
                pkg = cmd.split()[-1]
                self._disabled.discard(pkg)
                out = f"Package {pkg} new state: enabled"
            elif cmd.startswith("cmd package install-existing"):
                pkg = cmd.split()[-1]
                self._packages.add(pkg)
                out = f"Package {pkg} installed for user: 0"
            elif cmd.startswith("appops set"):
                out = ""  # 成功时无输出
            elif cmd.startswith("appops get"):
                out = "ignore"
            elif cmd.startswith("settings get"):
                parts = cmd.split()
                out = self._settings.get((parts[2], parts[3]), "null")
            elif cmd.startswith("settings put"):
                parts = cmd.split()
                if self._refuse_settings:
                    # 模拟 ColorOS 13: shell 无 WRITE_SETTINGS 权限, 写入被拒
                    self._stderr = (
                        "Exception occurred while executing 'put':\n"
                        "java.lang.SecurityException: com.android.shell was "
                        "not granted  this permission: "
                        "android.permission.WRITE_SETTINGS.")
                    out = ""
                else:
                    self._settings[(parts[2], parts[3])] = parts[4]
                    out = ""
            elif cmd.startswith("settings delete"):
                parts = cmd.split()
                self._settings.pop((parts[2], parts[3]), None)
                out = ""
            elif cmd.startswith("ping"):
                out = "PING www.google.com: 56 data bytes"
            else:
                out = ""
        else:
            out = ""
        return subprocess.CompletedProcess(
            args=["adb", *args], returncode=0, stdout=out,
            stderr=getattr(self, "_stderr", ""))


class ParseTest(unittest.TestCase):
    def test_parse_basic(self):
        entries = phone.parse_list(
            "# 注释\n\ncom.miui.player uninstall # 音乐\n"
            "com.miui.analytics disable # 统计\ncom.android.egg\n")
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0]["pkg"], "com.miui.player")
        self.assertEqual(entries[0]["action"], "uninstall")
        self.assertEqual(entries[0]["comment"], "音乐")
        self.assertEqual(entries[1]["action"], "disable")
        self.assertEqual(entries[2]["action"], "uninstall")  # 默认动作

    def test_parse_bad_line(self):
        with self.assertRaises(ValueError):
            phone.parse_list("这不是一个合法行")

    def test_parse_bom_and_crlf(self):
        text = "\ufeffcom.miui.player uninstall # 音乐\r\ncom.miui.video\r\n"
        entries = phone.parse_list(text)
        self.assertEqual([e["pkg"] for e in entries],
                         ["com.miui.player", "com.miui.video"])

    def test_parse_comment_only(self):
        self.assertEqual(phone.parse_list("# 只有注释\n\n"), [])

    def test_parse_settings(self):
        entries = phone.parse_settings(
            "# 注释\nglobal private_dns_mode hostname # DoT\n"
            "secure limit_ad_tracking 1\n")
        self.assertEqual(entries[0]["ns"], "global")
        self.assertEqual(entries[0]["key"], "private_dns_mode")
        self.assertEqual(entries[0]["value"], "hostname")
        self.assertEqual(entries[0]["comment"], "DoT")
        self.assertEqual(entries[1]["key"], "limit_ad_tracking")

    def test_parse_settings_bad(self):
        with self.assertRaises(ValueError):
            phone.parse_settings("bad_ns key value")


class DenyTest(unittest.TestCase):
    def test_core_packages_denied(self):
        for pkg in ["com.miui.home", "com.android.settings", "com.android.systemui",
                    "com.android.phone", "com.google.android.gms",
                    "com.android.providers.telephony", "com.miui.launcher",
                    "com.huawei.android.launcher", "com.sec.android.app.launcher",
                    "com.android.webview", "com.google.android.gsf",
                    "com.android.vending", "com.android.keychain"]:
            self.assertTrue(phone.is_denied(pkg), pkg)

    def test_removable_allowed(self):
        for pkg in ["com.miui.player", "com.miui.video", "com.android.egg",
                    "com.miui.analytics", "com.heytap.pictorial",
                    "com.android.browser", "com.miui.weather2",
                    "com.miui.securitycenter", "com.huawei.hwid"]:
            self.assertFalse(phone.is_denied(pkg), pkg)


class ProtectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_recents_and_ime_protected(self):
        dev = FakeAdb(
            packages={"com.example.myhome", "com.example.recentsp",
                      "com.example.ime", "com.miui.player"},
            home="com.example.myhome",
            extra={
                "shell dumpsys activity recents":
                    "mRecentsComponent=ComponentInfo{com.example.recentsp/"
                    "com.example.recentsp.RecentsActivity}",
                "shell settings get secure default_input_method":
                    "com.example.ime/.ImeService",
            })
        entries = phone.parse_list(
            "com.example.myhome uninstall\n"
            "com.example.recentsp uninstall\n"
            "com.example.ime uninstall\n"
            "com.miui.player uninstall\n")
        res = phone.apply_list(dev, entries, do_backup=False,
                               base=self.base, log=lambda *a: None)
        self.assertEqual(sorted(res["skipped_protected"]),
                         ["com.example.ime", "com.example.myhome",
                          "com.example.recentsp"])
        self.assertEqual(res["ok"], ["com.miui.player"])
        # 三个保护目标都还在设备上
        for pkg in ("com.example.myhome", "com.example.recentsp", "com.example.ime"):
            self.assertIn(pkg, dev._packages)


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_apply_rules(self):
        dev = FakeAdb(packages={
            "com.miui.home", "com.miui.player", "com.miui.video",
            "com.miui.analytics", "com.miui.home"})
        entries = phone.parse_list(
            "com.miui.player uninstall\n"
            "com.miui.analytics disable\n"
            "com.miui.home uninstall\n"          # 桌面, 应拒绝(命中安全规则)
            "com.android.settings disable\n"      # 安全规则, 应拒绝
            "com.absent.pkg uninstall\n")         # 不存在, 应跳过
        logs = []
        res = phone.apply_list(dev, entries, list_file="t.txt",
                               do_backup=False, base=self.base, log=logs.append)
        self.assertIn("com.miui.home", res["skipped_deny"])
        self.assertIn("com.android.settings", res["skipped_deny"])
        self.assertEqual(res["skipped_missing"], ["com.absent.pkg"])
        self.assertIn("com.miui.player", res["ok"])
        self.assertIn("com.miui.analytics", res["ok"])
        self.assertNotIn("com.miui.video", res["ok"])
        state = phone.load_state("FAKE123", self.base)
        self.assertEqual(state["packages"]["com.miui.player"]["action"], "uninstall")
        self.assertEqual(state["packages"]["com.miui.analytics"]["action"], "disable")

    def test_current_home_protected(self):
        # 第二道防线: 即使包名不在拒绝模式中, 只要是当前默认桌面就拒绝
        dev = FakeAdb(packages={"com.example.myhome", "com.miui.player"},
                      home="com.example.myhome")
        entries = phone.parse_list("com.example.myhome uninstall")
        res = phone.apply_list(dev, entries, do_backup=False,
                               base=self.base, log=lambda *a: None)
        self.assertEqual(res["skipped_protected"], ["com.example.myhome"])
        self.assertEqual(res["ok"], [])
        self.assertIn("com.example.myhome", dev._packages)

    def test_uninstall_fallback_to_disable(self):
        dev = FakeAdb(packages={"com.huawei.systemmanager"})
        dev._extra = {"shell pm uninstall --user 0 com.huawei.systemmanager":
                      "Failure [DELETE_FAILED_OPERATION_PENDING]"}
        entries = phone.parse_list("com.huawei.systemmanager uninstall")
        res = phone.apply_list(dev, entries, do_backup=False,
                               base=self.base, log=lambda *a: None)
        self.assertIn("com.huawei.systemmanager", res["ok"])
        state = phone.load_state("FAKE123", self.base)
        self.assertEqual(state["packages"]["com.huawei.systemmanager"]["action"],
                         "disable")

    def test_disable_refused_falls_back_to_suspend(self):
        """真机案例: ColorOS 乐划锁屏 pm disable-user 返回 default(静默拒绝),
        工具应自动改用 pm suspend 挂起。"""
        dev = FakeAdb(packages={"com.heytap.pictorial", "com.heytap.mcs"},
                      refuse_disable={"com.heytap.pictorial"})
        entries = phone.parse_list(
            "com.heytap.pictorial disable  # 乐划锁屏\n"
            "com.heytap.mcs disable  # 推送\n")
        logs = []
        res = phone.apply_list(dev, entries, do_backup=False,
                               base=self.base, log=logs.append)
        self.assertIn("com.heytap.pictorial", res["ok"])
        self.assertIn("com.heytap.mcs", res["ok"])
        self.assertEqual(res["fail"], [])
        self.assertIn("com.heytap.pictorial", dev._suspended)
        self.assertIn("com.heytap.mcs", dev._disabled)
        self.assertTrue(any("已挂起" in l for l in logs))
        state = phone.load_state("FAKE123", self.base)
        self.assertEqual(state["packages"]["com.heytap.pictorial"]["action"],
                         "suspend")
        # 恢复: 挂起 -> 取消挂起
        state = phone.load_state("FAKE123", self.base)
        r = phone.restore_pkgs(dev, ["com.heytap.pictorial"], state,
                               base=self.base, log=logs.append)
        self.assertEqual(r["ok"], ["com.heytap.pictorial"])
        self.assertNotIn("com.heytap.pictorial", dev._suspended)
        calls = [" ".join(c[1:]) for c in dev.calls]
        self.assertIn("pm unsuspend --user 0 com.heytap.pictorial", calls)

    def test_already_suspended_skipped(self):
        dev = FakeAdb(packages={"com.heytap.pictorial"},
                      suspended={"com.heytap.pictorial"},
                      refuse_disable={"com.heytap.pictorial"})
        entries = phone.parse_list("com.heytap.pictorial disable")
        res = phone.apply_list(dev, entries, do_backup=False,
                               base=self.base, log=lambda *a: None)
        self.assertEqual(res["already"], ["com.heytap.pictorial"])

    def test_dry_run_no_change(self):
        dev = FakeAdb(packages={"com.miui.player"})
        entries = phone.parse_list("com.miui.player uninstall")
        res = phone.apply_list(dev, entries, dry_run=True,
                               do_backup=False, base=self.base, log=lambda *a: None)
        self.assertIn("com.miui.player", res["ok"])
        self.assertIn("com.miui.player", dev._packages)  # 未真卸载
        state = phone.load_state("FAKE123", self.base)
        self.assertEqual(state["packages"], {})

    def test_batch_mode_processes_all(self):
        dev = FakeAdb(packages={"com.a.one", "com.a.two", "com.a.three",
                                "com.a.four", "com.a.five"})
        entries = phone.parse_list(
            "com.a.one uninstall\ncom.a.two uninstall\ncom.a.three uninstall\n"
            "com.a.four uninstall\ncom.a.five uninstall\n")
        res = phone.apply_list(dev, entries, do_backup=False, batch=2,
                               base=self.base, log=lambda *a: None)
        self.assertEqual(len(res["ok"]), 5)
        self.assertEqual(dev._packages, set())


class RestoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_apply_then_restore(self):
        dev = FakeAdb(packages={"com.miui.player", "com.miui.analytics"})
        entries = phone.parse_list(
            "com.miui.player uninstall\ncom.miui.analytics disable")
        phone.apply_list(dev, entries, do_backup=False, base=self.base,
                         log=lambda *a: None)
        self.assertNotIn("com.miui.player", dev._packages)
        self.assertIn("com.miui.analytics", dev._disabled)
        state = phone.load_state("FAKE123", self.base)
        res = phone.restore_pkgs(dev, ["com.miui.player", "com.miui.analytics"],
                                 state, base=self.base, log=lambda *a: None)
        self.assertEqual(res["fail"], [])
        self.assertIn("com.miui.player", dev._packages)
        self.assertNotIn("com.miui.analytics", dev._disabled)

    def test_restore_denied_skipped(self):
        dev = FakeAdb(packages={"com.miui.home"})
        state = phone.load_state("FAKE123", self.base)
        logs = []
        res = phone.restore_pkgs(dev, ["com.miui.home"], state,
                                 base=self.base, log=logs.append)
        self.assertEqual(res["ok"], [])
        self.assertTrue(any("安全规则" in m for m in logs))


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_check_and_fix(self):
        dev = FakeAdb(packages={"com.miui.player", "com.miui.video"})
        entries = phone.parse_list(
            "com.miui.player uninstall\ncom.miui.video uninstall")
        phone.apply_list(dev, entries, do_backup=False, base=self.base,
                         log=lambda *a: None)
        # 模拟 OTA 后厂商把应用改回
        dev._packages.add("com.miui.video")
        logs = []
        rows = phone.check_list(dev, entries, fix=False, base=self.base,
                                log=logs.append)
        changed = [r for r in rows if not r["ok"]]
        self.assertEqual([r["pkg"] for r in changed], ["com.miui.video"])
        # --fix 重新应用
        phone.check_list(dev, entries, fix=True, base=self.base,
                         log=lambda *a: None)
        self.assertNotIn("com.miui.video", dev._packages)

    def test_check_reports_suspend_and_downgrade(self):
        """真机场景: 乐划锁屏被挂起(disable 被拒)、浏览器卸载被拒降级为禁用,
        check 应把两者都识别为目标达成, 而不是误报"变化"。"""
        dev = FakeAdb(packages={"com.heytap.pictorial", "com.heytap.browser"},
                      refuse_disable={"com.heytap.pictorial"})
        dev._extra = {"shell pm uninstall --user 0 com.heytap.browser":
                      "Failure [DELETE_FAILED_INTERNAL_ERROR]"}
        entries = phone.parse_list(
            "com.heytap.pictorial disable  # 乐划锁屏\n"
            "com.heytap.browser uninstall  # 浏览器\n")
        phone.apply_list(dev, entries, do_backup=False, base=self.base,
                         log=lambda *a: None)
        rows = phone.check_list(dev, entries, fix=False, base=self.base,
                                log=lambda *a: None)
        by_pkg = {r["pkg"]: r for r in rows}
        self.assertTrue(by_pkg["com.heytap.pictorial"]["ok"])
        self.assertEqual(by_pkg["com.heytap.pictorial"]["current"], "已挂起")
        self.assertTrue(by_pkg["com.heytap.browser"]["ok"])
        self.assertEqual(by_pkg["com.heytap.browser"]["current"],
                         "已禁用(卸载降级)")
        # 挂起被系统恢复(OTA 类回潮) -> check 报变化, --fix 重新挂起
        dev._suspended.discard("com.heytap.pictorial")
        rows = phone.check_list(dev, entries, fix=False, base=self.base,
                                log=lambda *a: None)
        by_pkg = {r["pkg"]: r for r in rows}
        self.assertFalse(by_pkg["com.heytap.pictorial"]["ok"])
        phone.check_list(dev, entries, fix=True, base=self.base,
                         log=lambda *a: None)
        self.assertIn("com.heytap.pictorial", dev._suspended)


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_apply_and_revert(self):
        dev = FakeAdb(packages=set())
        entries = phone.parse_settings(
            "secure limit_ad_tracking 1 # 限制广告跟踪\n"
            "global private_dns_mode hostname\n")
        logs = []
        res = phone.apply_settings(dev, entries, base=self.base, log=logs.append)
        self.assertEqual(len(res["ok"]), 2)
        # 写入已回读校验生效
        self.assertEqual(dev._settings[("secure", "limit_ad_tracking")], "1")
        # 旧值(null)已记录
        state = phone.load_state("FAKE123", self.base)
        self.assertEqual(state["settings"]["secure:limit_ad_tracking"], "null")
        # restore --all 时还原(删除)
        phone.restore_pkgs(dev, [], state, base=self.base, log=logs.append)
        calls = [" ".join(c[1:]) for c in dev.calls]
        self.assertIn("settings delete secure limit_ad_tracking", calls)
        self.assertIn("settings delete global private_dns_mode", calls)
        self.assertEqual(state["settings"], {})

    def test_settings_write_refused_by_rom(self):
        """ColorOS 13 真机案例: shell 无 WRITE_SETTINGS 权限, put 静默失败。
        工具必须回读校验, 如实报告失败, 且不记录伪旧值。"""
        dev = FakeAdb(packages=set(), refuse_settings=True)
        entries = phone.parse_settings("secure limit_ad_tracking 1 # 限制广告跟踪")
        logs = []
        res = phone.apply_settings(dev, entries, base=self.base, log=logs.append)
        self.assertEqual(res["fail"], ["secure:limit_ad_tracking"])
        self.assertTrue(any("禁止 adb 写入" in l for l in logs))
        state = phone.load_state("FAKE123", self.base)
        self.assertNotIn("secure:limit_ad_tracking", state["settings"])


class ShakeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_shake_on_and_off(self):
        dev = FakeAdb(packages={"com.tencent.mm", "com.taobao.taobao"})
        res = phone.shake_on(dev, ["com.tencent.mm", "com.taobao.taobao",
                                   "com.absent.app"], base=self.base,
                             log=lambda *a: None)
        self.assertEqual(res["ok"], ["com.tencent.mm", "com.taobao.taobao"])
        self.assertEqual(res["missing"], ["com.absent.app"])
        state = phone.load_state("FAKE123", self.base)
        self.assertEqual(set(state["shake"]["com.tencent.mm"]), set(phone.SHAKE_OPS))
        calls = [" ".join(c[1:]) for c in dev.calls]
        self.assertIn("appops set com.tencent.mm BODY_SENSORS ignore", calls)
        # 还原
        phone.shake_off(dev, base=self.base, log=lambda *a: None)
        calls = [" ".join(c[1:]) for c in dev.calls]
        self.assertIn("appops set com.tencent.mm BODY_SENSORS default", calls)
        state = phone.load_state("FAKE123", self.base)  # 重新读取落盘状态
        self.assertEqual(state["shake"], {})

    def test_shake_unsupported_op_skipped(self):
        dev = FakeAdb(packages={"com.example.app"})
        dev._extra = {"shell appops set com.example.app READ_SENSORS ignore":
                      "Error: bad op"}
        res = phone.shake_on(dev, ["com.example.app"], base=self.base,
                             log=lambda *a: None)
        # BODY_SENSORS/ACTIVITY_RECOGNITION 成功, READ_SENSORS 被跳过
        self.assertEqual(res["ok"], ["com.example.app"])
        state = phone.load_state("FAKE123", self.base)
        self.assertNotIn("READ_SENSORS", state["shake"]["com.example.app"])

    def test_shake_list_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "shake.txt"
            f.write_text("# 注释\ncom.tencent.mm  # 微信\n\ncom.taobao.taobao\n",
                         encoding="utf-8")
            self.assertEqual(phone.phone_shake_list(f),
                             ["com.tencent.mm", "com.taobao.taobao"])


class DnsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_dns_on_ok(self):
        dev = FakeAdb(packages=set())
        with mock.patch.object(phone.time, "sleep", lambda *a: None):
            ok = phone.dns_on(dev, "dot.pub", base=self.base, log=lambda *a: None)
        self.assertTrue(ok)
        calls = [" ".join(c[1:]) for c in dev.calls]
        self.assertIn("settings put global private_dns_specifier dot.pub", calls)
        self.assertIn("settings put global private_dns_mode hostname", calls)

    def test_dns_on_auto_revert(self):
        dev = FakeAdb(packages=set())
        # ping 永远失败
        dev._extra = {"shell ping -c 1 -W 3 www.google.com": ""}
        with mock.patch.object(phone.time, "sleep", lambda *a: None):
            with self.assertRaises(phone.AdbError) as ctx:
                phone.dns_on(dev, "dns.adguard-dns.com", base=self.base,
                             log=lambda *a: None)
        self.assertIn("853", str(ctx.exception))
        calls = [" ".join(c[1:]) for c in dev.calls]
        self.assertIn("settings put global private_dns_mode opportunistic",
                      calls)
        self.assertIn("settings delete global private_dns_specifier", calls)

    def test_dns_bad_hostname(self):
        dev = FakeAdb(packages=set())
        with self.assertRaises(phone.AdbError):
            phone.dns_on(dev, "bad host!", base=self.base, log=lambda *a: None)


class AuditTest(unittest.TestCase):
    def test_audit_groups(self):
        dev = FakeAdb(packages={
            "com.miui.analytics", "com.heytap.pictorial",
            "com.miui.player", "com.vivo.browser"})
        found = phone.audit_device(dev, log=lambda *a: None)
        self.assertIn("com.miui.analytics", found.get("统计与遥测", []))
        self.assertIn("com.heytap.pictorial", found.get("广告与推广服务", []))
        self.assertIn("com.miui.player", found.get("内容推荐/资讯", []))

    def test_audit_write(self):
        dev = FakeAdb(packages={"com.miui.analytics"})
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "candidate.txt"
            phone.write_audit_list(dev, out, log=lambda *a: None)
            entries = phone.parse_list(out.read_text(encoding="utf-8"))
            self.assertTrue(any(e["pkg"] == "com.miui.analytics" for e in entries))


class AutoTest(unittest.TestCase):
    """自动清单: 本机预装 × 聚合知识库。"""

    def setUp(self):
        self.dev = FakeAdb(
            packages={"com.miui.player", "com.miui.video", "com.miui.home",
                      "com.android.settings", "com.miui.msa.global",
                      "com.miui.analytics", "com.miui.weather2",
                      "com.oplus.statistics.rom", "com.tencent.mm",
                      "com.miui.foo", "com.coloros.findmyphone",
                      "com.oplus.pay"},
            paths={"com.oplus.statistics.rom": "/my_heytap/app/Stat/Stat.apk",
                   "com.miui.player": "/system/app/Music/Music.apk"},
            third_party={"com.tencent.mm"},
            home="com.miui.home/.Launcher")
        self.db = {
            "com.miui.player": {"r": "Recommended", "d": "音乐", "s": ["uad-ng"]},
            "com.miui.video": {"r": "Advanced", "d": "视频", "s": ["uad-ng"]},
            "com.miui.msa.global": {"r": "Recommended", "d": "MSA 广告",
                                    "s": ["uad-ng", "gh:a/b"], "a": "disable"},
            "com.miui.weather2": {"r": "Expert", "d": "天气", "s": ["uad-ng"]},
            "com.miui.analytics": {"r": "Unsafe", "d": "统计(危险)",
                                   "s": ["uad-ng"]},
            "com.miui.home": {"r": "Recommended", "d": "桌面", "s": ["uad-ng"]},
            "com.android.settings": {"r": "Recommended", "d": "设置",
                                     "s": ["uad-ng"]},
            "com.tencent.mm": {"r": "Recommended", "d": "微信", "s": ["uad-ng"]},
            "com.miui.foo": {"r": "Recommended", "d": "被桌面依赖的服务",
                             "s": ["uad-ng"], "nb": ["com.miui.home"]},
            "com.coloros.findmyphone": {"r": "Recommended", "d": "查找手机",
                                        "s": ["uad-ng"]},
            "com.oplus.pay": {"r": "Recommended", "d": "OPPO 支付",
                              "s": ["uad-ng"]},
        }

    def _pkgs(self, res):
        return {r["pkg"] for r in res["rows"]}

    def test_standard_tier(self):
        res = phone.auto_candidates(self.dev, self.db, tier="standard",
                                    log=lambda *a: None)
        got = self._pkgs(res)
        self.assertIn("com.miui.player", got)          # Recommended
        self.assertIn("com.miui.video", got)           # Advanced
        self.assertIn("com.miui.msa.global", got)
        self.assertNotIn("com.miui.weather2", got)     # Expert, 需 aggressive
        self.assertNotIn("com.miui.analytics", got)    # Unsafe 永不处理
        self.assertNotIn("com.miui.home", got)         # 桌面(安全规则)
        self.assertNotIn("com.android.settings", got)  # 设置(安全规则)
        self.assertIn("com.miui.analytics", res["blocked"])
        # 动作: 服务型包用 disable
        msa = next(r for r in res["rows"] if r["pkg"] == "com.miui.msa.global")
        self.assertEqual(msa["action"], "disable")

    def test_aggressive_includes_expert_and_heuristic(self):
        res = phone.auto_candidates(self.dev, self.db, tier="aggressive",
                                    log=lambda *a: None)
        got = self._pkgs(res)
        self.assertIn("com.miui.weather2", got)
        # 知识库未收录但命中厂商广告/统计特征
        self.assertIn("com.oplus.statistics.rom", got)
        h = next(r for r in res["rows"] if r["pkg"] == "com.oplus.statistics.rom")
        self.assertEqual(h["level"], "Heuristic")
        self.assertEqual(h["partition"], "my_heytap")

    def test_standard_no_heuristic(self):
        res = phone.auto_candidates(self.dev, self.db, tier="standard",
                                    include_heuristic=False,
                                    log=lambda *a: None)
        self.assertNotIn("com.oplus.statistics.rom", self._pkgs(res))

    def test_third_party_excluded_by_default(self):
        res = phone.auto_candidates(self.dev, self.db, tier="aggressive",
                                    log=lambda *a: None)
        self.assertNotIn("com.tencent.mm", self._pkgs(res))
        res2 = phone.auto_candidates(self.dev, self.db, tier="aggressive",
                                     include_third_party=True,
                                     log=lambda *a: None)
        self.assertIn("com.tencent.mm", self._pkgs(res2))

    def test_dependency_guard(self):
        """被"保留包"依赖的候选应被剔除。"""
        res = phone.auto_candidates(self.dev, self.db, tier="standard",
                                    log=lambda *a: None)
        self.assertNotIn("com.miui.foo", self._pkgs(res))
        self.assertIn("com.miui.foo", res["skipped_dep"])

    def test_caution_blocked_by_default(self):
        """查找手机/支付这类删了丢功能的包, 默认只提示不处理。"""
        res = phone.auto_candidates(self.dev, self.db, tier="standard",
                                    log=lambda *a: None)
        got = self._pkgs(res)
        self.assertNotIn("com.coloros.findmyphone", got)
        self.assertNotIn("com.oplus.pay", got)
        caution = {p for p, _ in res["caution"]}
        self.assertIn("com.coloros.findmyphone", caution)
        self.assertIn("com.oplus.pay", caution)

    def test_caution_can_be_allowed(self):
        res = phone.auto_candidates(self.dev, self.db, tier="standard",
                                    allow_caution=True, log=lambda *a: None)
        got = self._pkgs(res)
        self.assertIn("com.coloros.findmyphone", got)
        self.assertIn("com.oplus.pay", got)
        fp = next(r for r in res["rows"] if r["pkg"] == "com.coloros.findmyphone")
        self.assertIn("谨慎", fp["desc"])

    def test_min_sources(self):
        res = phone.auto_candidates(self.dev, self.db, tier="standard",
                                    min_sources=2, log=lambda *a: None)
        got = self._pkgs(res)
        self.assertIn("com.miui.msa.global", got)      # 2 个来源
        self.assertNotIn("com.miui.player", got)       # 只有 1 个来源

    def test_exclude_regex(self):
        res = phone.auto_candidates(self.dev, self.db, tier="standard",
                                    exclude_re="player|video",
                                    log=lambda *a: None)
        got = self._pkgs(res)
        self.assertNotIn("com.miui.player", got)
        self.assertNotIn("com.miui.video", got)

    def test_write_auto_list(self):
        res = phone.auto_candidates(self.dev, self.db, tier="standard",
                                    log=lambda *a: None)
        with tempfile.TemporaryDirectory() as d:
            out = phone.write_auto_list(
                res["rows"], Path(d) / "auto.txt",
                {"brand": "Xiaomi", "model": "M2102K1C", "android": "14"})
            entries = phone.parse_list(out.read_text(encoding="utf-8"))
            pkgs = {e["pkg"] for e in entries}
            self.assertIn("com.miui.player", pkgs)
            msa = next(e for e in entries if e["pkg"] == "com.miui.msa.global")
            self.assertEqual(msa["action"], "disable")

    def test_load_known_db_missing(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                phone.load_known_db(Path(d) / "nope.json")


class HarvestParseTest(unittest.TestCase):
    """harvest.extract: 从社区列表/教程帖里提取包名。"""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        import harvest
        cls.h = harvest

    def test_list_format(self):
        text = ("# 注释\n"
                "com.miui.player uninstall  # 音乐\n"
                "com.miui.video disable\n"
                "adb shell pm uninstall --user 0 com.xiaomi.ab\n"
                "pm disable-user --user 0 com.miui.msa.global\n"
                "com.tencent.mm\n")
        r = self.h.extract(text, "list")
        self.assertEqual(r["com.miui.player"]["action"], "uninstall")
        self.assertEqual(r["com.miui.player"]["comment"], "音乐")
        self.assertEqual(r["com.miui.video"]["action"], "disable")
        self.assertIn("com.xiaomi.ab", r)
        self.assertEqual(r["com.miui.msa.global"]["action"], "disable")
        self.assertIn("com.tencent.mm", r)

    def test_post_mode_ignores_bare_names(self):
        text = ("执行 `adb shell pm uninstall --user 0 com.miui.analytics`。\n"
                "另外 com.miui.player 是音乐应用。\n")
        r = self.h.extract(text, "post")
        self.assertIn("com.miui.analytics", r)
        self.assertNotIn("com.miui.player", r)

    def test_safety_filter(self):
        self.assertFalse(self.h.is_safe("com.android.settings"))
        self.assertFalse(self.h.is_safe("com.miui.home"))
        self.assertFalse(self.h.is_safe("com.google.android.gms"))
        self.assertTrue(self.h.is_safe("com.miui.player"))

    def test_merge_keeps_most_conservative_level(self):
        db = {}
        self.h.merge(db, "com.miui.video", source="a", removal="Recommended")
        self.h.merge(db, "com.miui.video", source="b", removal="Expert")
        self.h.merge(db, "com.miui.video", source="c", removal="Recommended")
        self.assertEqual(db["com.miui.video"]["r"], "Expert")
        self.assertEqual(sorted(db["com.miui.video"]["s"]), ["a", "b", "c"])

    def test_merge_blocks_dangerous(self):
        db = {}
        self.h.merge(db, "com.miui.home", source="x", removal="Recommended")
        self.h.merge(db, "com.android.settings", source="x")
        self.assertEqual(db, {})

    def test_community_default_level(self):
        db = {}
        self.h.merge(db, "com.example.bloat", source="gh:a/b")
        self.assertEqual(db["com.example.bloat"]["r"], "Community")


class RomVersionTest(unittest.TestCase):
    """版本感知: ROM 家族/版本识别、列表版本标注、分版本动作策略。"""

    def _props(self, brand, **kv):
        lines = [f"[ro.product.brand]: [{brand}]"]
        lines += [f"[{k}]: [{v}]" for k, v in kv.items()]
        return {"shell getprop": "\n".join(lines)}

    def _dev(self, brand, pkgs=(), **kv):
        return FakeAdb(packages=pkgs, extra=self._props(brand, **kv))

    def test_parse_and_fmt_version(self):
        self.assertEqual(phone.parse_version("V13.1.0"), (13, 1, 0))
        self.assertEqual(phone.parse_version("OS2.0.1.0.VNBCNXM"), (2, 0, 1, 0))
        self.assertEqual(phone.parse_version("ColorOS 13.1"), (13, 1))
        self.assertEqual(phone.parse_version(""), ())
        self.assertEqual(phone.fmt_version((13, 1, 0)), "13.1")
        self.assertEqual(phone.fmt_version((14,)), "14")

    def test_detect_coloros_new_and_old(self):
        new = phone.detect_rom(self._dev(
            "OPPO", **{"ro.build.version.oplusrom": "V13.1.0",
                       "ro.build.version.oplusrom.display": "ColorOS 13.1"}))
        self.assertEqual(new["family"], "coloros")
        self.assertEqual(new["generation"], (13, 1))
        self.assertFalse(new["uninstall_ok"])
        self.assertFalse(new["legacy"])

        old = phone.detect_rom(self._dev(
            "OPPO", **{"ro.build.version.oplusrom": "V11.2"}))
        self.assertEqual(old["family"], "coloros")
        self.assertTrue(old["uninstall_ok"])
        self.assertTrue(old["legacy"])       # 低版本: 卸载不被拦截

    def test_detect_hyperos_and_miui_generation(self):
        hyper = phone.detect_rom(self._dev(
            "Xiaomi", **{"ro.mi.os.version.name": "OS2.0.1.0.VNBCNXM"}))
        self.assertEqual(hyper["family"], "xiaomi")
        self.assertEqual(hyper["edition"], "HyperOS")
        self.assertEqual(hyper["generation"][0], 16)   # HyperOS 2 -> 16
        miui = phone.detect_rom(self._dev(
            "Redmi", **{"ro.miui.ui.version.name": "V12.5.3.0.RKBCNXM"}))
        self.assertEqual(miui["edition"], "MIUI")
        self.assertEqual(miui["generation"][:2], (12, 5))
        self.assertTrue(miui["legacy"])

    def test_detect_harmonyos_next_unsupported(self):
        rom = phone.detect_rom(self._dev(
            "HUAWEI", **{"hw_sc.build.platform.version": "5.0.0"}))
        self.assertEqual(rom["family"], "harmonyos")
        self.assertIn("hdc", rom["unsupported"])
        emui = phone.detect_rom(self._dev(
            "HUAWEI", **{"ro.build.version.emui": "EmotionUI_12.0.0"}))
        self.assertIsNone(emui["unsupported"])     # EMUI 12 不该被当成 NEXT

    def test_detect_unknown_rom(self):
        rom = phone.detect_rom(self._dev("acme", **{"ro.build.version.release": "12"}))
        self.assertIsNone(rom["family"])
        self.assertEqual(rom["generation"], ())

    def test_rom_override(self):
        rom = phone.detect_rom(props={}, override="coloros:11.2")
        self.assertEqual(rom["family"], "coloros")
        self.assertEqual(rom["generation"], (11, 2))
        self.assertTrue(rom["legacy"])

    def test_parse_gates_and_filter(self):
        entries = phone.parse_list(
            "com.a uninstall [v>=13] # 新版本\n"
            "com.b uninstall [v<12] # 老版本\n"
            "com.c disable # 无标注\n"
            "com.d uninstall # 注释里 [v12-13]\n")
        self.assertEqual(entries[0]["gates"], [(">=", (13,))])
        self.assertEqual(entries[3]["gates"], [("range", (12,), (13,))])
        self.assertEqual(entries[2]["gates"], [])

        old = phone.detect_rom(props={"ro.product.brand": "OPPO",
                                      "ro.build.version.oplusrom": "V11.2"})
        kept, skipped = phone.filter_entries_by_rom(entries, old)
        self.assertEqual({e["pkg"] for e in kept}, {"com.b", "com.c"})
        self.assertEqual({e["pkg"] for e in skipped}, {"com.a", "com.d"})

    def test_filter_keeps_all_when_version_unknown(self):
        entries = phone.parse_list("com.a uninstall [v>=13]")
        kept, skipped = phone.filter_entries_by_rom(entries, {"generation": ()})
        self.assertEqual(len(kept), 1)
        self.assertEqual(skipped, [])

    def test_apply_skips_version_mismatch(self):
        dev = self._dev("OPPO", {"com.heytap.browser", "com.heytap.pictorial"},
                        **{"ro.build.version.oplusrom": "V13.1.0"})
        dev.serial = "FAKE-V"
        entries = phone.parse_list(
            "com.heytap.browser uninstall [v<12]\n"
            "com.heytap.pictorial disable [v>=12]")
        rom = phone.detect_rom(dev)
        res = phone.apply_list(dev, entries, rom=rom, do_backup=False,
                               log=lambda *a: None)
        self.assertEqual(res["ok"], ["com.heytap.pictorial"])
        self.assertEqual([e["pkg"] for e in res["skipped_version"]],
                         ["com.heytap.browser"])
        self.assertFalse(any("uninstall com.heytap.browser" in c[1]
                             for c in dev.calls if c[0] == "shell"))

    def test_prefer_disable_skips_uninstall_attempt(self):
        dev = self._dev("OPPO", {"com.heytap.browser"},
                        **{"ro.build.version.oplusrom": "V13.1.0"})
        dev.serial = "FAKE-P"
        rom = phone.detect_rom(dev)
        entries = phone.parse_list("com.heytap.browser uninstall")
        res = phone.apply_list(dev, entries, rom=rom, do_backup=False,
                               prefer_disable=True, log=lambda *a: None)
        self.assertEqual(res["ok"], ["com.heytap.browser"])
        self.assertFalse(any("pm uninstall" in c[1]
                             for c in dev.calls if c[0] == "shell"))

    def test_auto_legacy_uninstall_upgrades_content(self):
        db = {"com.coloros.video": {"r": "Recommended", "d": "视频",
                                    "s": ["uad-ng"], "a": "disable"}}
        old = self._dev("OPPO", {"com.coloros.video"},
                        **{"ro.build.version.oplusrom": "V11.2"})
        res = phone.auto_candidates(old, db, log=lambda *a: None)
        self.assertEqual(res["rows"][0]["action"], "uninstall")
        self.assertIn("[低版本直卸]", res["rows"][0]["desc"])

        new = self._dev("OPPO", {"com.coloros.video"},
                        **{"ro.build.version.oplusrom": "V13.1.0"})
        res2 = phone.auto_candidates(new, db, log=lambda *a: None)
        self.assertEqual(res2["rows"][0]["action"], "disable")

    def test_auto_version_override_skips_package(self):
        db = {"com.heytap.pictorial": {"r": "Recommended", "d": "乐划锁屏",
                                       "s": ["uad-ng"]}}
        old = self._dev("OPPO", {"com.heytap.pictorial"},
                        **{"ro.build.version.oplusrom": "V11.2"})
        res = phone.auto_candidates(old, db, log=lambda *a: None)
        self.assertEqual(res["rows"], [])
        self.assertEqual(res["skipped_version"][0][0], "com.heytap.pictorial")

    def test_rom_pkg_override_window(self):
        profiles = phone.load_rom_profiles()
        old = phone.detect_rom(props={"ro.product.brand": "OPPO",
                                      "ro.build.version.oplusrom": "V11.2"})
        new = phone.detect_rom(props={"ro.product.brand": "OPPO",
                                      "ro.build.version.oplusrom": "V13.1.0"})
        self.assertTrue(phone.rom_pkg_override(
            "com.coloros.lockscreen.magazine", old, profiles).get("action"))
        self.assertTrue(phone.rom_pkg_override(
            "com.coloros.lockscreen.magazine", new, profiles).get("skip"))
        self.assertEqual(phone.rom_pkg_override(
            "com.heytap.pictorial", new, profiles)["action"], "disable")

    def test_legacy_upgradable_scope(self):
        # 广告/遥测类可以升级为卸载; 基础设施服务仍然只禁用
        self.assertTrue(phone.legacy_upgradable("com.oplus.interconnectcollectkit"))
        self.assertTrue(phone.legacy_upgradable("com.coloros.video"))
        self.assertFalse(phone.legacy_upgradable("com.coloros.ocrservice"))
        self.assertFalse(phone.legacy_upgradable("com.heytap.mcs"))
        self.assertFalse(phone.legacy_upgradable("com.android.bookmarkprovider"))

    def test_rom_profiles_file_is_valid_json(self):
        profiles = phone.load_rom_profiles()
        self.assertIn("coloros", profiles["families"])
        for name, cfg in profiles["families"].items():
            self.assertTrue(cfg.get("label"), name)
            self.assertTrue(cfg.get("brands"), name)
        for pkg, ov in profiles["packages"].items():
            self.assertIn(ov["family"], profiles["families"], pkg)


class FreezeListParseTest(unittest.TestCase):
    def test_parse_freeze_action(self):
        entries = phone.parse_list(
            "# 冻结清单\ncom.miui.analytics freeze  # 统计\n"
            "com.heytap.pictorial freeze [v>=12]  # 乐划锁屏\n")
        self.assertEqual(entries[0]["action"], "freeze")
        self.assertEqual(entries[0]["pkg"], "com.miui.analytics")
        self.assertEqual(entries[1]["action"], "freeze")
        self.assertEqual(entries[1]["gates"], [(">=", (12,))])

    def test_parse_bad_action_rejected(self):
        with self.assertRaises(ValueError):
            phone.parse_list("com.miui.analytics nuke")


class FreezeApplyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_freeze_disables_and_force_stops(self):
        """冻结 = disable + force-stop, 记录 action=freeze。"""
        dev = FakeAdb(packages={"com.miui.analytics", "com.vivo.magazine"})
        entries = phone.parse_list(
            "com.miui.analytics freeze\ncom.vivo.magazine freeze")
        logs = []
        res = phone.apply_list(dev, entries, do_backup=False,
                               base=self.base, log=logs.append)
        self.assertEqual(sorted(res["ok"]),
                         ["com.miui.analytics", "com.vivo.magazine"])
        self.assertEqual(res["fail"], [])
        self.assertEqual(dev._disabled,
                         {"com.miui.analytics", "com.vivo.magazine"})
        self.assertEqual(dev._suspended, set())
        calls = [" ".join(c[1:]) for c in dev.calls]
        self.assertIn("am force-stop com.miui.analytics", calls)
        self.assertIn("am force-stop com.vivo.magazine", calls)
        self.assertTrue(any("已冻结" in l for l in logs))
        state = phone.load_state("FAKE123", self.base)
        self.assertEqual(state["packages"]["com.miui.analytics"]["action"],
                         "freeze")

    def test_freeze_refused_falls_back_to_suspend(self):
        """真机案例: ColorOS 乐划锁屏禁止禁用 -> 冻结自动降级为挂起。"""
        dev = FakeAdb(packages={"com.heytap.pictorial"},
                      refuse_disable={"com.heytap.pictorial"})
        entries = phone.parse_list("com.heytap.pictorial freeze")
        logs = []
        res = phone.apply_list(dev, entries, do_backup=False,
                               base=self.base, log=logs.append)
        self.assertEqual(res["ok"], ["com.heytap.pictorial"])
        self.assertIn("com.heytap.pictorial", dev._suspended)
        self.assertNotIn("com.heytap.pictorial", dev._disabled)
        state = phone.load_state("FAKE123", self.base)
        self.assertEqual(state["packages"]["com.heytap.pictorial"]["action"],
                         "suspend")

    def test_freeze_already_disabled_skipped(self):
        dev = FakeAdb(packages={"com.miui.analytics"},
                      disabled={"com.miui.analytics"})
        entries = phone.parse_list("com.miui.analytics freeze")
        res = phone.apply_list(dev, entries, do_backup=False,
                               base=self.base, log=lambda *a: None)
        self.assertEqual(res["already"], ["com.miui.analytics"])

    def test_freeze_then_restore(self):
        dev = FakeAdb(packages={"com.miui.analytics"})
        entries = phone.parse_list("com.miui.analytics freeze")
        phone.apply_list(dev, entries, do_backup=False, base=self.base,
                         log=lambda *a: None)
        state = phone.load_state("FAKE123", self.base)
        r = phone.restore_pkgs(dev, ["com.miui.analytics"], state,
                               base=self.base, log=lambda *a: None)
        self.assertEqual(r["ok"], ["com.miui.analytics"])
        self.assertNotIn("com.miui.analytics", dev._disabled)
        calls = [" ".join(c[1:]) for c in dev.calls]
        self.assertIn("pm enable --user 0 com.miui.analytics", calls)
        self.assertIn("pm unsuspend --user 0 com.miui.analytics", calls)
        self.assertEqual(state["packages"], {})

    def test_check_reports_frozen(self):
        dev = FakeAdb(packages={"com.miui.analytics"},
                      disabled={"com.miui.analytics"})
        entries = phone.parse_list("com.miui.analytics freeze")
        rows = phone.check_list(dev, entries, base=self.base,
                                log=lambda *a: None)
        self.assertTrue(rows[0]["ok"])
        self.assertEqual(rows[0]["current"], "已冻结")


class FreezeDbTest(unittest.TestCase):
    """rules/freeze-packages.json 与 tools/freeze-curated.tsv 的约束。"""

    @classmethod
    def setUpClass(cls):
        cls.meta, cls.db, cls.never = phone.load_freeze_db()

    def test_db_shape(self):
        self.assertGreaterEqual(len(self.db), 100)
        self.assertTrue(self.never)
        for pkg, rec in self.db.items():
            self.assertIn(rec["t"], phone.FREEZE_TIERS, pkg)
            self.assertTrue(rec.get("i"), pkg)
            self.assertTrue(rec.get("b"), pkg)
            self.assertIn("hail", rec.get("s") or [], pkg)

    def test_db_covers_brand_disable_entries(self):
        """品牌清单里每条 disable 都必须在冻结清单中(冻结是其可逆替代)。"""
        import re
        re_line = re.compile(
            r"^([A-Za-z][\w.]*)\s+disable\b")
        missing = []
        for path in sorted(Path(__file__).resolve().parent.parent.glob(
                "examples/*/debloat.txt")):
            for raw in path.read_text(encoding="utf-8").splitlines():
                s = raw.strip()
                if not s or s.startswith("#"):
                    continue
                m = re_line.match(s)
                if m and m.group(1) not in self.db:
                    missing.append(f"{path.parent.name}:{m.group(1)}")
        self.assertEqual(missing, [])

    def test_never_freeze_covers_core(self):
        for pkg in ("com.miui.home", "com.android.systemui", "com.android.phone",
                    "com.xiaomi.account", "com.google.android.gms"):
            self.assertTrue(any(p in pkg for p in self.never), pkg)

    def test_generated_list_is_applicable(self):
        path = (Path(__file__).resolve().parent.parent
                / "examples" / "freeze-recommended.txt")
        self.assertTrue(path.exists())
        entries = phone.parse_list(path.read_text(encoding="utf-8"), str(path))
        self.assertGreaterEqual(len(entries), 100)
        self.assertTrue(all(e["action"] == "freeze" for e in entries))


class FreezeCandidatesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.db = {
            "com.miui.analytics": {"t": "safe", "r": "统计", "i": "无感知",
                                   "b": ["xiaomi"]},
            "com.miui.player": {"t": "recommended", "r": "音乐", "i": "音乐不可用",
                                "b": ["xiaomi"]},
            "com.heytap.push": {"t": "caution", "r": "推送", "i": "收不到推送",
                                "b": ["oppo"]},
            "com.miui.home": {"t": "safe", "r": "桌面", "i": "不可用",
                              "b": ["xiaomi"]},
        }
        self.never = ["com.miui.home", "com.xiaomi.account"]
        self.dev = FakeAdb(
            packages={"com.miui.analytics", "com.miui.player", "com.heytap.push",
                      "com.miui.home", "com.android.settings", "com.tencent.mm",
                      "com.xiaomi.account"},
            home="com.miui.home/.Launcher")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, **kw):
        db = dict(self.db)
        db["never_freeze"] = {"patterns": self.never}
        with mock.patch.object(phone, "load_freeze_db",
                               return_value=({"total": 4}, db, self.never)):
            return phone.freeze_candidates(self.dev, db, **kw)

    def test_tier_safe_only(self):
        res = self._run(tier="safe")
        pkgs = {r["pkg"] for r in res["rows"]}
        self.assertEqual(pkgs, {"com.miui.analytics"})

    def test_tier_recommended(self):
        res = self._run(tier="recommended")
        pkgs = {r["pkg"] for r in res["rows"]}
        self.assertEqual(pkgs, {"com.miui.analytics", "com.miui.player"})

    def test_tier_all_includes_caution(self):
        res = self._run(tier="all")
        pkgs = {r["pkg"] for r in res["rows"]}
        self.assertEqual(pkgs, {"com.miui.analytics", "com.miui.player",
                                "com.heytap.push"})

    def test_brand_filter(self):
        res = self._run(tier="all", brands=["oppo"])
        self.assertEqual({r["pkg"] for r in res["rows"]}, {"com.heytap.push"})

    def test_core_and_never_freeze_skipped(self):
        res = self._run(tier="all")
        rows = {r["pkg"] for r in res["rows"]}
        self.assertNotIn("com.miui.home", rows)       # 当前桌面(动态保护)
        self.assertNotIn("com.xiaomi.account", rows)  # never_freeze 黑名单
        self.assertIn("com.xiaomi.account", res["skipped_never"])
        self.assertNotIn("com.android.settings", rows)  # DENY 规则

    def test_third_party_not_listed(self):
        res = self._run(tier="all")
        self.assertNotIn("com.tencent.mm", {r["pkg"] for r in res["rows"]})


class FakeHdc(phone.Hdc):
    """模拟 hdc 设备(HarmonyOS NEXT): bm 工具只能卸载, 没有 disable/suspend。"""

    def __init__(self, bundles=(), props=None):
        self._bundles = set(bundles)
        self._props = dict(props or {})
        self.calls = []
        self.serial = "HDC456"
        self.adb = "/fake/hdc"

    def run(self, *args, timeout=120):
        self.calls.append(args)
        cmd = " ".join(str(a) for a in args)
        out = ""
        if "bm dump -a" in cmd:
            out = "\n".join(sorted(self._bundles))
        elif "bm uninstall" in cmd:
            parts = cmd.split()
            pkg = parts[parts.index("-n") + 1]
            if pkg in self._bundles:
                self._bundles.discard(pkg)
                out = "uninstall bundle successfully."
            else:
                out = "error: bundle not found."
        elif "param get" in cmd:
            out = self._props.get(cmd.split()[-1], "")
        return subprocess.CompletedProcess(
            args=["hdc", *args], returncode=0, stdout=out, stderr="")


class HdcChannelTest(unittest.TestCase):
    """HarmonyOS NEXT 5.x: 无 adb, 走 hdc; bm 只能卸载。"""

    def setUp(self):
        self.dev = FakeHdc(bundles={
            "com.huawei.video", "com.huawei.music", "com.huawei.search",
            "com.huawei.hwid", "ohos.example.hello"})

    def test_is_hdc(self):
        self.assertTrue(phone.is_hdc(self.dev))
        self.assertFalse(phone.is_hdc(FakeAdb(packages={"com.a.b"})))

    def test_hdc_list_bundles(self):
        pkgs = phone.hdc_list_bundles(self.dev)
        self.assertEqual(pkgs, {"com.huawei.video", "com.huawei.music",
                                "com.huawei.search", "com.huawei.hwid",
                                "ohos.example.hello"})

    def test_hdc_uninstall_ok_and_missing(self):
        ok, out = phone.hdc_uninstall(self.dev, "com.huawei.video")
        self.assertTrue(ok, out)
        self.assertNotIn("com.huawei.video", self.dev._bundles)
        ok, out = phone.hdc_uninstall(self.dev, "com.huawei.absent")
        self.assertFalse(ok)

    def test_apply_hdc_uninstall_only(self):
        entries = phone.parse_list(
            "com.huawei.video uninstall # 华为视频\n"
            "com.huawei.search disable # 搜索\n"
            "com.huawei.music freeze # 音乐\n")
        logs = []
        with tempfile.TemporaryDirectory() as tmp:
            res = phone.apply_list(self.dev, entries, base=tmp, log=logs.append,
                                   do_backup=False)
        self.assertEqual(res["ok"], ["com.huawei.video"])
        self.assertEqual(sorted(res["skipped_unsupported"]),
                         ["com.huawei.music", "com.huawei.search"])
        joined = "\n".join(logs)
        self.assertIn("bm 工具没有禁用/冻结/挂起能力", joined)
        self.assertIn("[已卸载] com.huawei.video", joined)

    def test_apply_hdc_never_fails_pm(self):
        entries = phone.parse_list("com.huawei.video uninstall")
        with tempfile.TemporaryDirectory() as tmp:
            phone.apply_list(self.dev, entries, base=tmp, log=lambda *a: None,
                             do_backup=False)
        # hdc 通道绝不能出现 pm uninstall(那是 adb 的命令)
        self.assertFalse(any("pm uninstall" in " ".join(str(a) for a in c)
                             for c in self.dev.calls))
        self.assertTrue(any("bm uninstall" in " ".join(str(a) for a in c)
                            for c in self.dev.calls))

    def test_check_hdc_reports_unsupported(self):
        self.dev._bundles.discard("com.huawei.video")   # 先卸载掉
        entries = phone.parse_list(
            "com.huawei.video uninstall\ncom.huawei.search disable\n")
        with tempfile.TemporaryDirectory() as tmp:
            rows = phone.check_list(self.dev, entries, base=tmp,
                                    log=lambda *a: None)
        by_pkg = {r["pkg"]: r for r in rows}
        self.assertTrue(by_pkg["com.huawei.video"]["ok"])   # 已卸载
        self.assertFalse(by_pkg["com.huawei.search"]["ok"])
        self.assertIn("通道不支持", by_pkg["com.huawei.search"]["current"])

    def test_detect_harmonyos_next_hdc_required(self):
        props = {"const.product.brand": "HUAWEI",
                 "const.harmony.version": "5.0.0",
                 "const.ohos.apiversion": "12"}
        rom = phone.detect_rom(props=props)
        self.assertTrue(rom.get("hdc_required"))
        self.assertEqual(rom.get("family"), "harmonyos")
        self.assertIsNotNone(rom.get("unsupported"))  # 说明文字仍在(供 adb 通道拒绝)

    def test_unsupported_rom_hdc_channel_not_refused(self):
        rom = {"family": "harmonyos", "hdc_required": True,
               "unsupported": "HarmonyOS NEXT 只提供 hdc 调试"}
        out = []
        with mock.patch("builtins.print", out.append):
            refused = phone._unsupported_rom(rom, self.dev)   # hdc 设备
        self.assertFalse(refused)
        self.assertTrue(any("hdc 通道" in line for line in out))

    def test_unsupported_rom_adb_channel_refused(self):
        rom = {"family": "harmonyos", "hdc_required": True,
               "unsupported": "HarmonyOS NEXT 只提供 hdc 调试, 没有 adb"}
        out = []
        with mock.patch("builtins.print", out.append):
            refused = phone._unsupported_rom(rom, FakeAdb(packages={"com.a.b"}))
        self.assertTrue(refused)
        self.assertTrue(any("[不支持]" in line for line in out))

    def test_restore_hdc_reports_manual(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 造一个含"已卸载"记录的状态文件
            state = {"serial": self.dev.serial,
                     "packages": {"com.huawei.video": {"action": "uninstall",
                                                       "list": "t.txt"}}}
            d = phone.Path(tmp) / self.dev.serial
            d.mkdir(parents=True)
            (d / "state.json").write_text(json.dumps(state), encoding="utf-8")
            logs = []
            phone.restore_pkgs(self.dev, ["com.huawei.video"], state,
                               base=tmp, log=logs.append)
        joined = "\n".join(logs)
        self.assertIn("install-existing", joined)
        self.assertIn("手动重装", joined)

    def test_rom_policy_lines_hdc_channel(self):
        rom = {"family": "harmonyos", "display": "HarmonyOS NEXT 5.0",
               "hdc_required": True}
        lines = phone.rom_policy_lines(rom, channel="hdc")
        self.assertTrue(any("已切换到 hdc 通道" in l for l in lines))
        self.assertTrue(any("bm dump -a" in l for l in lines))


if __name__ == "__main__":
    unittest.main(verbosity=2)

