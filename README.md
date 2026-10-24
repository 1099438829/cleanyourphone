# CleanYourPhone — 清理你的国产手机

参考 [CleanYourTV](https://github.com/Gathin23/cleanyourtv)、
[CleanYourAndroid](https://github.com/Bhargi777/cleanyourandroid)、
[cleanyourphone](https://github.com/upfind/cleanyourphone) 三家思路, 为**国产手机**
(小米/红米/POCO、华为、荣耀、OPPO/一加/realme、vivo/iQOO、三星国行、魅族、
中兴/努比亚/红魔、摩托罗拉、联想、传音)打造的清理项目。

**无需 root、无需解锁、不在手机上安装任何软件、不替换桌面启动器, 全部操作可一键恢复。**

三层清理策略: **卸载预装应用** · **关闭广告与统计服务** · **设置级去广告 + 摇一摇封杀**。
外加**自动清单**: 抓取互联网 debloat 知识库, 与本机预装求交集后一键清理(见"自动清单")。
**版本感知**: 同一品牌不同 ROM 版本, 包名和能否卸载都不一样 —— 工具会先识别
ColorOS 13.1 / HyperOS 2 / MagicOS 8 这类版本号, 再决定"直接卸载"还是"禁用/挂起"
(见"版本感知")。
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

> HarmonyOS NEXT 用的 hdc 不会自动下载(华为无公开直链): 装一个
> [DevEco Studio](https://developer.huawei.com/consumer/cn/deveco-studio/)
> 即可拿到命令行 hdc, 或用 `--hdc <路径>` 指过去。

## 前置条件(仅手机端)

1. 设置 → 关于手机 → 连点"版本号"7 次 → 返回 → 系统/更多设置 → **开发者选项** → 打开 **USB 调试**
2. 无线调试(Android 11+, 免数据线): 开发者选项 → 无线调试 → 配对码配对
   (`python3 tools/phone.py pair 192.168.x.x:端口 配对码`, 再 `connect 192.168.x.x:端口`)
3. 首次连接在手机上点"允许"USB 调试授权

## HarmonyOS NEXT(5.x 起): 没有 adb, 改用 hdc

HarmonyOS NEXT 5.0 开始华为**移除了 adb**, 调试走 **hdc**(HarmonyOS Debug Bridge)。
工具会自动探测: `adb` 连不上时若找到 hdc, 就切到 hdc 通道; 也可强制指定
`--hdc /path/to/hdc`。

```bash
# 自动探测(先 adb 后 hdc), 无需额外参数
python3 tools/phone.py doctor

# 手动指定 hdc 路径(DevEco Studio 自带: DevEco Studio/sdk/default/.../hdc)
python3 tools/phone.py --hdc ~/DevEcoStudio/sdk/default/hms/hdc packages
```

**NEXT 上的能力边界(bm 工具决定, 不是工具的锅)**:

| 操作 | adb 通道(EMUI/HarmonyOS 4 及以下) | hdc 通道(NEXT 5.x+) |
| --- | --- | --- |
| 卸载 | `pm uninstall --user 0` | `bm uninstall -n <包名> -k`(保留数据) |
| 禁用/挂起 | `pm disable-user` / `pm suspend` | **不支持**, 只能卸载 |
| 区分预装分区 | `pm list packages -s -f` | 不支持, 按包名清单匹配 |
| 恢复 | `pm install-existing` | 不支持, 需按品牌 README 手动重装 |
| 系统设置/摇一摇 | `settings put` / `appops set` | 不支持, 按 README 手动改 |

因此 HarmonyOS NEXT 上: 清单里写 `uninstall` 的条目正常执行; 写 `disable` 的条目
工具会明确报告"bm 不支持禁用"而不是静默失败。华为鸿蒙请配合
`examples/huawei-harmonyos/README.md` 里的手动开关使用。

## 快速开始

```bash
# 0. 自检(自动准备 adb、识别品牌与 ROM 版本、显示当前桌面/输入法/最近任务保护对象)
python3 tools/phone.py doctor

# 0.5 看 ROM 版本与该版本的清理策略(哪些能直卸、哪些只能禁用)
python3 tools/phone.py rom
python3 tools/phone.py rom --list examples/oppo-coloros/debloat.txt

# 1. 预演: 只打印计划, 不动手机
python3 tools/phone.py apply examples/xiaomi-hyperos/debloat.txt --dry-run

# 2. 执行(自动先备份包列表与系统设置, 需输入 y 确认)
tools/disable.sh examples/xiaomi-hyperos/debloat.txt

# 2.5 或者更保守: 只冻结不删除(参考 Hail / FreezeYou, 随时可解冻)
python3 tools/phone.py freeze --tier safe --apply

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

## 自动清单: 互联网知识库 × 本机预装

不想逐条挑列表? 让工具自己算: 先抓取互联网上公开的 debloat 知识, 再和**你手机里
实际装着的预装应用**求交集, 生成一份只属于这台手机的清单。

```bash
python3 tools/harvest.py                 # 1. 抓取聚合(1-5 分钟, 可重复跑更新)
python3 tools/phone.py auto              # 2. 预演: 看会动哪些, 不碰手机
python3 tools/phone.py auto --apply      # 3. 执行(自动备份 + 确认)
```

### 数据来源(全部公开, 只读, 不上传任何东西)

| 源 | 内容 | 规模 |
| --- | --- | --- |
| UAD-NG 结构化库 | Universal Android Debloater Next Generation, 带 Recommended / Advanced / Expert / Unsafe 分级与依赖关系 | 5381 条 |
| GitHub 代码搜索 | 用 `pm uninstall --user 0`、`debloat` 等关键词自动发现社区列表与教程帖 | 每轮 12-30 个文件 |
| 内置精选仓库 | CleanYourTV 等已知高质量列表 | 11 个文件 |
| Gitee 中文社区 | 搜索接口已改为 JS 渲染, 默认跳过; 可用 `--gitee-repo owner/repo` 手动指定 | 可选 |

多源同一包按**最保守**原则合并(任一源标 Unsafe 就保持 Unsafe); 命中本项目安全规则的包永不入库。
产出: `rules/known-packages.json`(结构化知识库)、`rules/ALL-BLOAT.txt`(人类可读全量清单)、
`rules/harvest-report.md`(抓取报告)。国内访问 GitHub 不稳时自动走 ghproxy / jsdelivr 镜像。

### 三档力度

| 力度 | 包含 | 适用 |
| --- | --- | --- |
| `--tier safe` | 仅 Recommended | 第一次用, 最保守 |
| `--tier standard`(默认) | Recommended + Advanced | 常规清理 |
| `--tier aggressive` | 再加 Expert + 启发式(厂商广告/遥测特征) | 想清得更彻底 |

### 自动清单的六道保险

1. 只处理**系统分区预装**(`pm list packages -s`), 用户自己装的应用默认不碰
   (`--include-third-party` 才会纳入 /data/app)
2. 命中安全规则(桌面/电话/短信/系统 UI/输入法/GMS)直接剔除
3. 知识库标 `Unsafe` 的永不处理
4. **依赖保护**: 依赖核心组件的、或被"要保留的包"依赖的, 一律跳过
5. **谨慎名单**: 查找手机、支付、密码本、云服务、厂商账号、系统更新、备份恢复、
   语音识别、无障碍、设备认证、当前默认浏览器 —— 默认只列出不处理。
   (UAD 常把这些标成"推荐", 删了会丢功能/丢数据; 确认不需要再加 `--allow-caution`)
6. 执行前照旧自动备份 + 状态记录, `restore --all` 一键还原

> 真机实测(OPPO ColorOS 13, 310 个系统应用, 5021 条知识库): `safe` 命中 84、
> `standard` 138、`aggressive` 182; 另有 27 个被标 Unsafe、15 个被谨慎名单拦下。

## 版本感知: 同一个品牌, 不同版本不一样

国产 ROM 的"能不能卸"高度依赖版本:

- **ColorOS 11 及以下**: `pm uninstall --user 0` 基本可用 → 清单里的 `uninstall` 直接执行
- **ColorOS 12 起**: 大量 `com.heytap.*` 返回 `DELETE_FAILED_INTERNAL_ERROR` → 只能禁用,
  禁用还被拒的(乐划锁屏)再挂起; 13 起连 `settings put` 都被禁(无 `WRITE_SETTINGS`)
- **MIUI 12-14 → HyperOS 1/2**: 前者多数可卸, 后者限制明显变多; 而且小米必须先开
  「USB 调试(安全设置)」, 否则卸载一律失败
- **HarmonyOS NEXT 5.x**: 已经**没有 adb** 了(改用 hdc + HAP), 本工具直接提示不支持

所以工具在动手前先识别版本:

```bash
$ python3 tools/phone.py rom
家族:   ColorOS(coloros)
版本:   ColorOS 13.1  原始值: ColorOS 13.1  来源: ro.build.version.oplusrom.display
可比序: 13.1  (列表里的 [v>=13] 就是和它比)
依据:   真机验证: OPPO PEQM00 / Android 13 / ColorOS 13.1
版本说明: ColorOS 13: 大量 com.heytap.* 返回 DELETE_FAILED_INTERNAL_ERROR, 自动降级禁用; ...
版本策略: ColorOS 13.1 起 ROM 会拦截大量系统应用卸载(...) → 卸载失败自动降级禁用,
          禁用被拒再挂起; 想少刷失败日志可加 --prefer-disable
```

### 能识别的 ROM 家族

| 家族 | 主要品牌 | 版本属性(按优先级) | 卸载被拦截的起始版本 |
| --- | --- | --- | --- |
| ColorOS / realme UI / OxygenOS | OPPO、一加、realme | `ro.build.version.oplusrom[.display]`、`ro.build.version.opporom`、`ro.build.version.realmeui` | 12.0(真机验证 13.1) |
| MIUI / HyperOS | 小米、红米、POCO、黑鲨 | `ro.mi.os.version.name`(HyperOS)、`ro.miui.ui.version.name`(MIUI) | HyperOS 1(可比序 15) |
| HarmonyOS / EMUI | 华为、老荣耀 | `hw_sc.build.platform.version`、`ro.build.version.emui` | NEXT 5.x 起改用 hdc(见下) |
| MagicOS | 荣耀 | `ro.build.version.magic` | 8.0 |
| OriginOS / Funtouch | vivo、iQOO | `ro.vivo.os.version`、`ro.build.version.funtouch` | 4.0 |
| One UI | 三星国行 | `ro.build.version.oneui`(60100 → 6.1) | 无 |
| Flyme | 魅族 | `ro.flyme.version` | 无 |
| MyOS | 中兴、努比亚、红魔 | `ro.build.display.id` 中的 `MyOS` 字样 | 无 |
| myui | 摩托罗拉 | `ro.build.display.id` 中的 `myui` 字样 | 无 |
| HiOS / XOS | 传音 Tecno/Infinix/itel | `ro.build.display.id` 中的 `HiOS`/`XOS` | 无 |
| ZUI | 联想、拯救者 | `ro.build.display.id` 中的 `ZUI` | 无 |

- 识别不出来的(或想模拟别的版本)可手动指定: `--rom-version coloros:13.1` / `rom --version hios:13`
- 规则表: [`rules/rom-profiles.json`](rules/rom-profiles.json)(家族属性、各版本说明、分版本动作覆盖)

### 低版本直接卸载, 高版本禁用优先

- **低版本**(低于该家族的卸载拦截门槛, 如 ColorOS 11、MIUI 12.5):
  `auto` 会把"内容/广告类且分级 Recommended"的条目从 `disable` **升级为 `uninstall`**,
  清单里标注为 `[低版本直卸]`。这类包不涉及系统服务, 卸载后 `install-existing` 可恢复。
- **高版本**(ColorOS 12+ / HyperOS 1+): 卸载失败自动降级禁用, 禁用被拒自动挂起。
  想跳过失败尝试、直接走禁用: `--prefer-disable`。
- 觉得升级太激进: `--no-legacy-uninstall` 关掉。

### 列表版本标注

一份清单可以同时写不同版本的规则, 版本不符的条目自动跳过:

```
com.heytap.pictorial            disable    [v>=12]  # ColorOS 12+ 是乐划锁屏
com.coloros.lockscreen.magazine disable    [v<12]   # ColorOS 11 及以下是锁屏杂志
com.heytap.browser              uninstall  [v<12]   # 低版本直接卸载
com.heytap.browser              disable    [v>=12]  # 高版本只能禁用
```

- 支持 `[v>=13]` `[v<12]` `[v=13.1]` `[v12-13]`, 写在行尾或注释里都行
- 小米把两套编号拉平: MIUI 14 = 14, HyperOS 1 = 15, HyperOS 2 = 16(所以 `[v>=15]` 就是 HyperOS 起)
- realme UI 自动换算: realme UI 2.0 = 11 / 3.0 = 12 / 4.0 = 13 / 5.0 = 14 / 6.0 = 15
- 查看某份清单在本机的适用性: `python3 tools/phone.py rom --list <清单>`


## 支持品牌与列表

| 品牌/ROM | 列表目录 | 清理重点 |
| --- | --- | --- |
| 小米/红米/POCO MIUI、HyperOS | `examples/xiaomi-hyperos/` | MSA/遥测/锁屏画报、负一屏、视频/音乐/浏览器 |
| 华为 EMUI、HarmonyOS 2-5(NEXT 走 hdc) | `examples/huawei-harmonyos/` | 华为视频/音乐/搜索、玩机技巧、HMS 遥测 |
| 荣耀 MagicOS 6-9 | `examples/honor-magicos/` | 杂志锁屏、浏览器/视频/音乐、推送通道 |
| OPPO ColorOS 7-15 | `examples/oppo-coloros/` | 乐划锁屏、锁屏杂志、欢太统计、浏览器 |
| 一加国行 ColorOS/OxygenOS | `examples/oneplus-coloros/` | 禅定模式、游戏空间、图标包、乐划锁屏 |
| realme 国行 realme UI 2-6 | `examples/realme-ui/` | realme 音乐/安全检测/睡眠胶囊 + ColorOS 共用项 |
| vivo/iQOO OriginOS、Funtouch | `examples/vivo-originos/` | 锁屏画报、营销中心、负一屏、浏览器 |
| 三星国行 One UI 5-8 | `examples/samsung-oneui-cn/` | Samsung Free 负一屏资讯、McAfee 弹窗 |
| 魅族 Flyme 8-11 | `examples/meizu-flyme/` | 魅族浏览器、视频 |
| 中兴/努比亚/红魔 MyOS | `examples/zte-nubia/` | 数据采集、快应用容器、努比亚浏览器/商店 |
| 摩托罗拉 myui | `examples/moto-myiui/` | Moto App Box、发现气泡、演示模式、诊断上报 |
| 联想 ZUI / 拯救者 | `examples/lenovo-zui/` | 联想应用中心、浏览器、语音全家桶、主题覆盖层 |
| 传音 Tecno/Infinix/itel HiOS·XOS | `examples/transsion-hios/` | Folax 语音、AI 壁纸、健康、售后 App、工程模式 |
| 全品牌通用 | `examples/universal/` | Android 广告服务、Google 组件、AOSP 彩蛋 |

每个品牌目录含: `debloat.txt`(清理列表)、`settings.conf`(设置项)、
`README.md`(**手动关闭广告**的逐条设置路径 + 优化设置建议)、
`uad-recommended.txt`(UAD-NG 自动生成的候选, 运行 `python3 -I tools/sync_uad.py` 同步)。
部分目录含 `device-inventory.md` + `device-system-packages.txt`:
真机拉取的系统应用清单与实测结论(见下节)。

## 冻结列表: 不删除, 只是让它闭嘴

参考 [Hail(雹)](https://github.com/aistra0528/Hail) 与
[FreezeYou(自冻)](https://github.com/FreezeYou/FreezeYou) 的冻结语义:
**冻结 = 应用无法启动, 但 APK 与数据都保留, 随时可以解冻**。
适合"这个预装我不想用, 但也不敢删"的场景, 也是高版本 ROM(卸载被拦截时)
唯一能彻底停掉它的手段。

| 模式 | 命令 | 效果 | 解冻 |
| --- | --- | --- | --- |
| `disable`(默认) | `pm disable-user --user 0 <包>` | 应用从桌面消失, 不可启动 | `pm enable` |
| `suspend`(兜底) | `pm suspend --user 0 <包>` | 图标变灰, 系统提示"已挂起" | `pm unsuspend` |
| `hide` | `pm hide --user 0 <包>` | 需要 root 或设备所有者, adb 做不到 | 本工具不使用 |

工具里的 `freeze` 动作 = `disable` + `am force-stop`, 禁用被 ROM 静默拒绝时
自动降级为 `suspend`(与 Hail 的降级路径一致), 解冻统一用
`pm enable` + `pm unsuspend` 双保险 —— Hail 的教训是**解冻必须覆盖实际生效的那个模式**。

```bash
# 1. 按冻结清单预演(只列清单, 不动手机)
python3 tools/phone.py freeze --tier safe

# 2. 执行(候选按本机实际安装过滤; 需输入 y 确认)
python3 tools/phone.py freeze --tier safe --apply

# 3. 更全一点: safe + recommended(推送通道/内容预装/负一屏等, 影响明确)
python3 tools/phone.py freeze --tier recommended --apply

# 4. 按品牌过滤 / 手动保存清单再执行
python3 tools/phone.py freeze --tier safe --brand xiaomi --write /tmp/xm-freeze.txt
python3 tools/phone.py apply /tmp/xm-freeze.txt

# 5. 解冻(冻结的包/卸载的包/改过的设置一起还原)
python3 tools/phone.py restore --all
```

三级分级(数据在 `rules/freeze-packages.json`, 每条都带"冻结后影响"说明):

| 分级 | 数量 | 含义 |
| --- | --- | --- |
| `safe` | 110 | 纯广告/统计/遥测/日志/工厂测试组件, 冻结后几乎无感知 |
| `recommended` | 1059 | 推送通道/内容预装/负一屏等, 影响明确可预期 |
| `caution` | 679 | 会关掉某个功能(浏览器/视频/人脸解锁/主题等), 冻结前先看影响 |

`examples/freeze-recommended.txt` 是整理好的成品清单, 可直接
`python3 tools/phone.py apply examples/freeze-recommended.txt`。
清单由 `tools/build_freeze_db.py` 从两个来源生成:

1. **14 个品牌 debloat 列表的 `disable` 条目**(即"这些包本来就是我们建议禁用的",
   人工分级), 手工分级表在 `tools/freeze-curated.tsv`
2. **互联网聚合知识库**(`rules/known-packages.json`, UAD-NG 等 5000+ 包): 取 OEM 预装 +
   Recommended/Advanced 级, 过与运行时一致的安全规则(DENY/谨慎名单/never_freeze/
   品牌过滤), 再按包名关键词自动分级; Advanced 级一律 caution

知识库自动分级的条目未经真机验证, 所以 `caution` 级务必先读"影响"列;
要改分级改 `freeze-curated.tsv`(品牌条目)或 `build_freeze_db.py` 的
`IMPACT_RULES`(知识库条目), 跑一次生成脚本即可。

**不要冻结的**: 桌面/电话/短信/账号/同步适配器/GMS 等核心组件,
见 `rules/freeze-packages.json` 的 `never_freeze` 段(与 `phone.py` 的
`DENY_PATTERNS`/`PROTECTED_PACKAGES` 保持同步); 每次执行前还会动态保护
**当前桌面、最近任务提供者、当前输入法**。

## 安全设计(来自 CleanYourAndroid 的护栏实践)

1. **硬性拒绝名单**: 桌面、电话、短信、系统 UI、设置、WebView、GMS、账号体系等
   (40+ 条正则 + 显式核心包清单), 写死在 `tools/phone.py`, 任何列表都无法绕过
2. **动态保护**: 每次执行前解析**当前默认桌面**、**最近任务提供者**(禁用它任务切换会失灵)、
   **当前输入法**(禁用它重启后无法输入 PIN), 三者永不触碰
3. **自动备份**: 每次执行前保存包列表、禁用列表、系统设置、getprop、dumpsys recents 到
   `~/.cleanyourphone/<序列号>/backup-时间戳/`
4. **状态记录**: 每个被处理的包/设置/传感器限制都记录到 `~/.cleanyourphone/<序列号>/state.json`
5. **降级策略**: `pm uninstall` 被 ROM 拒绝时自动降级为 `pm disable-user`;
   `pm disable-user` 被 ROM 静默拒绝时自动降级为 `pm suspend`(挂起, 无法启动);
   冻结(`freeze`)被拒时同样降级为挂起, 解冻统一 `pm enable` + `pm unsuspend` 双保险
6. **分批+截图**: `--batch N --screenshot` 每处理 N 个自动截图, 逐段验证不出事再继续
7. **DNS 自愈**: Private DNS 开启后自动探测解析, 失败(网络封锁 853 端口)立即回退, 手机网络不受影响
8. **确认与预演**: 非 `--dry-run` 执行前必须输入 y 确认; 管道/非交互环境默认拒绝
9. **谨慎名单**(自动清单): 查找手机/支付/密码本/云服务/账号/系统更新/备份/语音识别/
   无障碍/设备认证/默认浏览器, 默认只提示不处理 —— UAD 常把这些标成"推荐", 删了会丢功能
10. **版本门槛**(v2.2): 清单条目可带 `[v>=13]` 版本标注, 与当前 ROM 版本不符的直接跳过;
    HarmonyOS NEXT(5.x+)自动切 hdc 通道, bm 做不到的操作(禁用/挂起)明确报告不静默失败

## 工具一览(tools/)

| 工具 | 作用 |
| --- | --- |
| `phone.py` | 核心工具(Python 标准库, 跨平台, 21 个子命令) |
| `harvest.py` | 抓取聚合互联网 debloat 知识 -> `rules/known-packages.json` |
| `build_freeze_db.py` | 由品牌清单 + `tools/freeze-curated.tsv` + 知识库生成冻结清单 -> `rules/freeze-packages.json` |
| `clean.sh` | 全流程编排(备份→debloat→settings→shake, 可分阶段) |
| `disable.sh` / `restore.sh` / `check.sh` | 应用/恢复/检查列表 |
| `install-adb.sh` | 安装官方 Android 平台工具 |
| `sync_uad.py` | 从 UAD-NG 社区数据库同步品牌候选列表(轻量版, 只要品牌候选时用它) |
| `../rules/rom-profiles.json` | 版本规则库: 家族属性/版本说明/分版本动作覆盖 |
| `../rules/freeze-packages.json` | 冻结清单: 1848 个可冻结预装(safe 110 / recommended 1059 / caution 679)+ 影响 + never_freeze 黑名单 |
| `../tests/test_phone.py` | 单元测试(模拟设备, 93 个用例): `python3 -I tests/test_phone.py` |

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

**Q: 那"冻结"又是什么? 和禁用一样吗?**
`freeze` = `disable` + 强制停止, 语义上参考 Hail/FreezeYou: 应用不可启动、不进后台,
但 APK 与数据都保留, `pm enable` 即解冻。适合"不敢删但也不想用它"的预装;
高版本 ROM 卸载被拦截时, 冻结是唯一能彻底停掉它的手段。
禁用被 ROM 拒绝时会自动降级为 `pm suspend`(挂起)。详见上文"冻结列表"。

**Q: 怎么恢复?**
`tools/restore.sh --all`(包+设置+传感器限制一并还原), 或恢复出厂设置。
只解冻某几个包: `python3 tools/phone.py shell "pm enable --user 0 <包名>"`。

**Q: OTA 升级后失效了怎么办?**
`tools/check.sh <列表> --fix` 会检查哪些被厂商改回并重新应用。

**Q: `auto` 会不会删太多?**
默认 `--tier standard` 只处理 Recommended + Advanced, 且过六道保险(见上文)。
想先看看不动手就 `python3 tools/phone.py auto`; 觉得太激进就 `--tier safe`,
想更彻底用 `--tier aggressive`, 还能 `--exclude 'browser|music'` 排除。

**Q: 知识库多久更新一次?**
`python3 tools/harvest.py` 随时可重跑, 会重新抓取 UAD-NG 与社区列表;
`rules/harvest-report.md` 里有生成时间和每个源的记录数。

**Q: 会不会变砖?**
不会。所有操作都是 Android 标准的用户级包管理, 可逆; 核心组件被安全规则硬性拦截。

**Q: 为什么有的包卸不掉?**
各 ROM 保护策略不同(华为/HarmonyOS、ColorOS 较严)。脚本会自动降级为禁用;
禁用也被拒时(如 OPPO 乐划锁屏)自动挂起, 效果相同。

**Q: 我的手机是 ColorOS 11 / MIUI 12.5, 能用同一份列表吗?**
能。列表条目带 `[v<12]` / `[v>=12]` 标注, 工具识别到低版本会自动走"直接卸载"那一行,
高版本走"禁用"那一行; 版本不符的条目直接跳过。先跑 `python3 tools/phone.py rom --list <列表>`
看适用性。

**Q: 识别出的版本不对 / 识别不出来怎么办?**
可手动指定: `--rom-version coloros:13.1`(apply/auto/check 都支持)或
`python3 tools/phone.py rom --version hios:13`。中兴/摩托罗拉/传音/联想的版本号常只写在
`ro.build.display.id` 里, 识别不出时会提示"未识别 ROM", 此时按 Android 版本保守处理。

**Q: HarmonyOS NEXT 能用吗?**
可以, 但能力受限。NEXT(5.x)移除了 adb, 工具会自动切到 **hdc 通道**
(或 `--hdc <路径>` 指定 DevEco Studio 自带的 hdc), 卸载走 `bm uninstall`;
禁用/挂起/系统设置/摇一摇这些 bm 做不到的动作会明确报告"不支持", 需按
`examples/huawei-harmonyos/README.md` 手动操作。HarmonyOS 4.x 及以下走 adb, 全部功能可用。

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
│   ├── harvest.py       抓取聚合互联网 debloat 知识
│   ├── clean.sh         全流程编排(可分阶段)
│   ├── disable.sh       应用列表
│   ├── restore.sh       恢复
│   ├── check.sh         OTA 后检查
│   ├── install-adb.sh   安装 adb
│   └── sync_uad.py      同步 UAD-NG 候选列表
├── rules/               规则库
│   ├── known-packages.json   5009 个包的分级/描述/依赖/来源(harvest.py 生成)
│   ├── rom-profiles.json     版本规则: 11 个 ROM 家族 + 分版本动作覆盖
│   ├── freeze-packages.json  冻结清单: 1848 个可冻结预装 + 分级/影响 + never_freeze
│   ├── ALL-BLOAT.txt         人类可读全量清单(按厂商分组)
│   └── harvest-report.md     抓取报告(来源与失败原因)
├── tests/test_phone.py  单元测试(模拟设备, 93 个用例)
└── examples/            各品牌列表 + settings.conf + 手动关广告/优化设置说明
    ├── xiaomi-hyperos/ huawei-harmonyos/ honor-magicos/ oppo-coloros/
    ├── oneplus-coloros/ realme-ui/ vivo-originos/ samsung-oneui-cn/ meizu-flyme/
    ├── zte-nubia/ moto-myiui/ lenovo-zui/ transsion-hios/ universal/
    ├── freeze-recommended.txt  成品冻结清单(可直接 apply)
    ├── shake_apps.txt   全品牌摇一摇封杀清单(22 款 App)
    └── oppo-coloros/device-inventory.md  真机实测记录(OPPO PEQM00)
```

## 致谢与许可

- 思路与组织方式参考 [CleanYourTV](https://github.com/Gathin23/cleanyourtv)(MIT)
- 安全护栏与分批截图实践参考 [CleanYourAndroid](https://github.com/Bhargi777/cleanyourandroid)(MIT)
- 冻结语义(disable/hide/suspend 三态、解冻同模式、降级路径)参考
  [Hail(雹)](https://github.com/aistra0528/Hail)(GPL-3.0) 与
  [FreezeYou(自冻)](https://github.com/FreezeYou/FreezeYou)(GPL-3.0)
- 零门槛 adb、UAD-NG 同步、设置级去广告与摇一摇封杀参考
  [cleanyourphone(upfind)](https://github.com/upfind/cleanyourphone)(MIT)
- 列表基于上述项目与社区 debloat 实践整理, MIT 许可, 详见 [LICENSE](LICENSE)
