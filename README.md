# CleanYourPhone — 清理你的国产手机

参考 [CleanYourTV](https://github.com/Gathin23/cleanyourtv)、
[CleanYourAndroid](https://github.com/Bhargi777/cleanyourandroid)、
[cleanyourphone](https://github.com/upfind/cleanyourphone) 三家思路, 为**国产手机**
(小米/红米/POCO、华为、荣耀、OPPO/一加/realme、vivo/iQOO、三星国行、魅族)打造的清理项目。

**无需 root、无需解锁、不在手机上安装任何软件、不替换桌面启动器, 全部操作可一键恢复。**

三层清理策略: **卸载预装应用** · **关闭广告与统计服务** · **设置级去广告 + 摇一摇封杀**。
(卸载/禁用被 ROM 拒绝时自动降级, 禁用被拒时自动挂起, 见下方"真机实测")

## 仓库地址

| 平台 | 地址 |
| --- | --- |
| GitHub | https://github.com/1099438829/cleanyourphone |
| Gitee(国内访问更快) | https://gitee.com/muziys/cleanyourphone |

```bash
git clone https://github.com/1099438829/cleanyourphone.git
# 或
git clone https://gitee.com/muziys/cleanyourphone.git
```

---

## 原理

手机都自带 ADB 调试桥。电脑通过 USB 数据线(或同一 Wi-Fi)连接手机后, 用 Android 标准命令完成清理:

| 操作 | 命令 | 恢复方式 |
| --- | --- | --- |
| 卸载预装应用(对当前用户) | `pm uninstall --user 0 <包名>` | `cmd package install-existing --user 0 <包名>` |
| 禁用广告/统计服务 | `pm disable-user <包名>` | `pm enable --user 0 <包名>` |
| 挂起(禁用被 ROM 拒绝时) | `pm suspend --user 0 <包名>` | `pm unsuspend --user 0 <包名>` |
| 关闭广告相关系统设置 | `settings put <ns> <key> <val>` | 还原旧值(restore --all 自动处理) |
| 封杀"摇一摇"跳转 | `appops set <包名> BODY_SENSORS ignore` 等 | `appops set <包名> <op> default` |

- APK 始终留在系统分区, 变的只是"对当前用户是否安装/启用", 所以**不会变砖、可完全恢复**
- 恢复出厂设置同样能恢复一切
- **本项目不替换桌面启动器**: 原厂桌面始终保留(同时被安全规则和保护名单双重拦截)

## 零门槛: adb 自动准备

电脑上**不需要提前安装任何东西**: 检测不到 adb 时, 脚本会自动从 Google 官方
直链下载免安装 platform-tools(约 10MB)到 `~/.cleanyourphone/platform-tools` 并直接使用,
无需配置环境变量。也支持手动安装:

```bash
bash tools/install-adb.sh        # 或 brew install android-platform-tools
```

## 前置条件(仅手机端)

1. 设置 → 关于手机 → 连点"版本号"7 次 → 返回 → 系统/更多设置 → **开发者选项** → 打开 **USB 调试**
2. 无线调试(Android 11+, 免数据线): 开发者选项 → 无线调试 → 配对码配对
   (`python3 tools/phone.py pair 192.168.x.x:端口 配对码`, 再 `connect 192.168.x.x:端口`)
3. 首次连接在手机上点"允许"USB 调试授权

## 快速开始

```bash
# 0. 自检(自动准备 adb、识别品牌、显示当前桌面/输入法/最近任务保护对象)
python3 tools/phone.py doctor

# 1. 预演: 只打印计划, 不动手机
python3 tools/phone.py apply examples/xiaomi-hyperos/debloat.txt --dry-run

# 2. 执行(自动先备份包列表与系统设置, 需输入 y 确认)
tools/disable.sh examples/xiaomi-hyperos/debloat.txt

# 3. 设置级去广告(关闭限制广告跟踪等, 旧值自动记录可还原)
python3 tools/phone.py settings examples/xiaomi-hyperos/settings.conf

# 4. 摇一摇封杀(微信/淘宝/抖音等 22 款 App, appops 限制传感器)
python3 tools/phone.py shake on

# 5. 可选: Private DNS 去广告(带自愈, 解析失败自动回退, 不会搞挂网络)
python3 tools/phone.py dns on dot.pub        # 国内; 国外可用 dns.adguard-dns.com

# 6. 恢复(包/设置/传感器限制一并还原)
tools/restore.sh --all
```

也可以一条命令跑全流程(每步确认): `tools/clean.sh`(支持 `--debloat/--settings/--shake/--dry-run`)。

Windows 用户: 把本仓库放在**不含中文的路径**下, 用 `python tools/phone.py ...` 代替 `.sh` 脚本。

## 支持品牌与列表

| 品牌/ROM | 列表目录 | 清理重点 |
| --- | --- | --- |
| 小米/红米/POCO MIUI、HyperOS | `examples/xiaomi-hyperos/` | MSA/遥测/锁屏画报、负一屏、视频/音乐/浏览器 |
| 华为 EMUI、HarmonyOS | `examples/huawei-harmonyos/` | 华为视频/音乐/搜索、玩机技巧、HMS 遥测 |
| 荣耀 MagicOS | `examples/honor-magicos/` | 杂志锁屏、浏览器/视频/音乐、推送通道 |
| OPPO/一加/realme ColorOS | `examples/oppo-coloros/` | 乐划锁屏、锁屏杂志、欢太统计、浏览器 |
| vivo/iQOO OriginOS | `examples/vivo-originos/` | 锁屏画报、营销中心、负一屏、浏览器 |
| 三星国行 One UI | `examples/samsung-oneui-cn/` | Samsung Free 负一屏资讯、McAfee 弹窗 |
| 魅族 Flyme | `examples/meizu-flyme/` | 魅族浏览器、视频 |
| 全品牌通用 | `examples/universal/` | Android 广告服务、Google 组件、AOSP 彩蛋 |

每个品牌目录含: `debloat.txt`(清理列表)、`settings.conf`(设置项)、
`README.md`(**手动关闭广告**的逐条设置路径 + 优化设置建议)、
`uad-recommended.txt`(UAD-NG 自动生成的候选, 运行 `python3 -I tools/sync_uad.py` 同步)。
部分目录含 `device-inventory.md` + `device-system-packages.txt`:
真机拉取的系统应用清单与实测结论(见下节)。

## 安全设计(来自 CleanYourAndroid 的护栏实践)

1. **硬性拒绝名单**: 桌面、电话、短信、系统 UI、设置、WebView、GMS、账号体系等
   (40+ 条正则 + 显式核心包清单), 写死在 `tools/phone.py`, 任何列表都无法绕过
2. **动态保护**: 每次执行前解析**当前默认桌面**、**最近任务提供者**(禁用它任务切换会失灵)、
   **当前输入法**(禁用它重启后无法输入 PIN), 三者永不触碰
3. **自动备份**: 每次执行前保存包列表、禁用列表、系统设置、getprop、dumpsys recents 到
   `~/.cleanyourphone/<序列号>/backup-时间戳/`
4. **状态记录**: 每个被处理的包/设置/传感器限制都记录到 `~/.cleanyourphone/<序列号>/state.json`
5. **降级策略**: `pm uninstall` 被 ROM 拒绝时自动降级为 `pm disable-user`;
   `pm disable-user` 被 ROM 静默拒绝时自动降级为 `pm suspend`(挂起, 无法启动)
6. **分批+截图**: `--batch N --screenshot` 每处理 N 个自动截图, 逐段验证不出事再继续
7. **DNS 自愈**: Private DNS 开启后自动探测解析, 失败(网络封锁 853 端口)立即回退, 手机网络不受影响
8. **确认与预演**: 非 `--dry-run` 执行前必须输入 y 确认; 管道/非交互环境默认拒绝

## 工具一览(tools/)

| 工具 | 作用 |
| --- | --- |
| `phone.py` | 核心工具(Python 标准库, 跨平台, 18 个子命令) |
| `clean.sh` | 全流程编排(备份→debloat→settings→shake, 可分阶段) |
| `disable.sh` / `restore.sh` / `check.sh` | 应用/恢复/检查列表 |
| `install-adb.sh` | 安装官方 Android 平台工具 |
| `sync_uad.py` | 从 UAD-NG 社区数据库同步品牌候选列表 |
| `../tests/test_phone.py` | 单元测试(模拟设备): `python3 -I tests/test_phone.py` |

## 真机实测(2026-10-23, OPPO PEQM00 / Android 13 / ColorOS 13)

完整记录见 [`examples/oppo-coloros/device-inventory.md`](examples/oppo-coloros/device-inventory.md),
原始系统应用清单见 [`examples/oppo-coloros/device-system-packages.txt`](examples/oppo-coloros/device-system-packages.txt)(310 个系统应用)。

| ROM 行为 | 现象 | 工具的处理 |
| --- | --- | --- |
| 卸载受限 | `com.heytap.*` 多数返回 `DELETE_FAILED_INTERNAL_ERROR` | 自动降级为禁用 |
| 禁用受限 | 乐划锁屏 `pm disable-user` 返回 `new state: default`(静默拒绝) | 自动改用 `pm suspend` 挂起 |
| 设置写入受限 | `settings put` 抛 `SecurityException: WRITE_SETTINGS` | 回读校验, 如实报告失败, 引导手动操作 |
| 包名差异 | 列表 23 条中 9 条该机型未安装 | 自动跳过, 不影响其他条目 |

清理后该机状态: 卸载 4 个、禁用 10 个、挂起 3 个(乐划锁屏/浏览器/全局搜索),
桌面与输入法未动。真机清单还发现了原列表缺失的 11 个遥测/广告包, 已回补
`examples/oppo-coloros/debloat.txt`, 并发现 12 个广告相关 settings 键(记入 settings.conf)。

## 常见问题(FAQ)

**Q: 会不会丢数据?**
不会。卸载的是系统预装应用(视频/音乐/浏览器这类), 不触碰你的照片、微信、联系人。

**Q: 卸载和"禁用"有什么区别?**
`uninstall --user 0` 让应用从当前用户消失(图标消失, 可恢复); `disable` 保留图标位置但停用组件。
广告服务类建议 `disable`, 预装应用类用 `uninstall`。

**Q: 怎么恢复?**
`tools/restore.sh --all`(包+设置+传感器限制一并还原), 或恢复出厂设置。

**Q: OTA 升级后失效了怎么办?**
`tools/check.sh <列表> --fix` 会检查哪些被厂商改回并重新应用。

**Q: 会不会变砖?**
不会。所有操作都是 Android 标准的用户级包管理, 可逆; 核心组件被安全规则硬性拦截。

**Q: 为什么有的包卸不掉?**
各 ROM 保护策略不同(华为/HarmonyOS、ColorOS 较严)。脚本会自动降级为禁用;
禁用也被拒时(如 OPPO 乐划锁屏)自动挂起, 效果相同。

**Q: `settings` 提示"该 ROM 禁止 adb 写入系统设置"?**
实测 ColorOS 13 等 ROM 禁止 adb shell 写入 settings(SecurityException),
这不是工具故障, 请按品牌 README 的手动开关操作。

**Q: 摇一摇封杀会影响 App 吗?**
只限制传感器(加速度计/陀螺仪)读取, 不影响 App 其他功能; 但计步器、AR、运动健康类
App 可能受影响, 可单独还原: `python3 tools/phone.py shake off <包名>`。

**Q: Private DNS 会让手机上不了网吗?**
不会。开启后会自动探测, 连续 6 次无法解析就自动回退"自动"模式(部分网络封锁 853 端口)。

**Q: 需要数据线吗?**
首次建议用数据线(最稳); 之后可用 Android 11+ 无线调试。

## 故障排除

| 现象 | 处理 |
| --- | --- |
| 提示未找到 adb | 脚本会自动下载; 失败请检查网络或运行 `bash tools/install-adb.sh` |
| `adb devices` 为空 | 换数据线/口; 确认手机已解锁并允许 USB 调试; 安装手机驱动 |
| 设备显示 `unauthorized` | 手机上撤销 USB 调试授权后重新允许 |
| 设备显示 `offline` | 插拔数据线, 或关闭再打开 USB 调试 |
| macOS 连不上无线设备 | 系统设置 → 隐私与安全性 → 本地网络 → 允许终端访问 |
| `Failure [DELETE_FAILED_...]` | 该 ROM 受保护, 脚本会自动降级为禁用; 仍失败则重启手机后重试 |
| `new state: default`(禁用被拒) | 该 ROM 静默拒绝禁用, 脚本会自动挂起; 属正常 |
| `SecurityException ... WRITE_SETTINGS` | 该 ROM 禁止 adb 写系统设置, 请按品牌 README 手动操作 |
| 截图失败/全黑 | 手机屏幕处于关闭状态, 唤醒后重试(不影响清理本身) |
| 卸载后桌面出现空白 | 恢复该项: `tools/restore.sh <列表>` |

## 已知限制(参考 CleanYourAndroid)

- **手势导航**: Android 10-12 部分 ROM 的手势导航依赖原厂桌面, 若原厂桌面被列入清理,
  建议保留(脚本默认不动桌面)
- **最近任务**: 由原厂桌面提供, 脚本会解析并保护它
- **工作资料(Work Profile)**: 不在处理范围
- 部分厂商封锁 ADB 卸载: 自动降级为禁用即可

## 用完请关闭调试

```bash
python3 tools/phone.py finish
```

## 目录结构

```
cleanyourphone/
├── README.md / PROMPT.md / AGENTS.md / CONTRIBUTING.md / LICENSE
├── tools/
│   ├── phone.py         核心工具(标准库, 跨平台)
│   ├── clean.sh         全流程编排(可分阶段)
│   ├── disable.sh       应用列表
│   ├── restore.sh       恢复
│   ├── check.sh         OTA 后检查
│   ├── install-adb.sh   安装 adb
│   └── sync_uad.py      同步 UAD-NG 候选列表
├── tests/test_phone.py  单元测试(模拟设备, 30 个用例)
└── examples/            各品牌列表 + settings.conf + 手动关广告/优化设置说明
    └── shake_apps.txt   全品牌摇一摇封杀清单(22 款 App)
    └── oppo-coloros/device-inventory.md  真机实测记录(OPPO PEQM00)
    └── oppo-coloros/device-system-packages.txt  真机系统应用清单(310 个)
```

## 致谢与许可

- 思路与组织方式参考 [CleanYourTV](https://github.com/Gathin23/cleanyourtv)(MIT)
- 安全护栏与分批截图实践参考 [CleanYourAndroid](https://github.com/Bhargi777/cleanyourandroid)(MIT)
- 零门槛 adb、UAD-NG 同步、设置级去广告与摇一摇封杀参考
  [cleanyourphone(upfind)](https://github.com/upfind/cleanyourphone)(MIT)
- 列表基于上述项目与社区 debloat 实践整理, MIT 许可, 详见 [LICENSE](LICENSE)
