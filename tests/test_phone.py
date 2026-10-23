#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CleanYourPhone 单元测试(使用 FakeAdb 模拟设备, 无需真机)。

运行: python3 -I tests/test_phone.py
"""
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
                 refuse_disable=(), suspended=(), refuse_settings=False):
        self._packages = set(packages)
        self._disabled = set(disabled)
        self._suspended = set(suspended)
        self._refuse_disable = set(refuse_disable)
        self._refuse_settings = refuse_settings
        self._settings = {}
        self._home = home
        self.calls = []
        self._extra = extra or {}
        self.serial = "FAKE123"

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
