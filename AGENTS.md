# AGENTS.md — CleanYourPhone 仓库地图(给编码代理)

参考 CleanYourTV / CleanYourAndroid / cleanyourphone(upfind) 三家组织方式。
核心约束: **无 root、不向手机安装软件、全部可逆、内置安全规则 + 动态保护**。

## 仓库地图

| 路径 | 内容 | 修改规则 |
| --- | --- | --- |
| `tools/phone.py` | 核心工具: adb/hdc 自动准备、列表/设置解析、ROM 版本识别、安全规则、apply/restore/check/audit/settings/dns/shake/rom/freeze/screenshot、UI 引擎(ui)、App 内开关(adsw)、通知渠道(chan)、断网(cutnet)、快应用(quickapp) | 只允许标准库; 新增子命令需同步更新 `build_parser`/`main`/测试 |
| `tools/clean.sh` | 全流程编排(backup→debloat→settings→shake, 可分阶段) | 保持编排式实现, 逻辑一律放 phone.py |
| `tools/disable.sh` `restore.sh` `check.sh` | `phone.py` 的 bash 封装 | 保持转发式实现 |
| `tools/install-adb.sh` | 安装官方 Android 平台工具 | 覆盖 macOS/Linux/Windows |
| `tools/build_freeze_db.py` | 由品牌清单 + `tools/freeze-curated.tsv` + `rules/known-packages.json`(知识库, OEM+Recommended/Advanced 级, 关键词自动分级)生成 `rules/freeze-packages.json` 与 `examples/freeze-recommended.txt` | 分级表(freeze-curated.tsv)与 IMPACT_RULES 手改; 生成物不手改; 知识库来源必须过 phone.py 安全规则(DENY/谨慎名单/never_freeze/品牌过滤) |
| `tools/sync_uad.py` | 从 UAD-NG 同步品牌候选列表到 `examples/<品牌>/uad-recommended.txt` | 只生成候选文件, 禁止覆盖手工 `debloat.txt`; 必须过安全规则过滤 |
| `rules/known-packages.json` | 自动清单知识库(harvest.py 生成) | 由脚本生成, 不手改 |
| `rules/rom-profiles.json` | 版本规则库: 家族属性/版本说明/分版本动作覆盖/hdc 门槛 | 手改; 新增家族需带 `label/brands/props/priority`, 并在测试里覆盖识别 |
| `rules/freeze-packages.json` | 冻结清单: 1848 个 safe/recommended/caution 三级 + 影响 + never_freeze | 由 build_freeze_db.py 生成, 不手改 |
| `rules/ad-switches.json` | App 内广告开关路径: 声明式步骤(launch/tap/tap_any/switches/gesture...), 按 brands/roms/gate/models 匹配 | 手改; 每条必须带 `manual` 还原路径; 带 `models` 的只对实测机型生效, 不得为了"通用"去掉 models |
| `tests/test_phone.py` | 单元测试(FakeAdb/FakeHdc 模拟设备) | 改 `phone.py` 行为必须同步测试 |
| `examples/<品牌>/debloat.txt` | 手工维护的清理列表 | 格式见下; 分 推荐/可选/谨慎(谨慎默认注释); 版本相关条目加 `[v>=13]` 标注 |
| `examples/<品牌>/settings.conf` | 设置项(settings put) | 格式: `ns key value # 注释`; DNS 项默认注释 |
| `examples/<品牌>/README.md` | 手动关广告 + 优化设置 | 路径注明"设置顶部可搜索直达", 随版本可能变化; 需含"版本差异"小节 |
| `examples/shake_apps.txt` | 全品牌摇一摇封杀清单 | 只收常见第三方 App, 不收系统包 |
| `PROMPT.md` | 给 AI 助手的执行提示词 | 与 README 的工具用法保持一致 |

## 列表格式(debloat.txt)

```
包名  [uninstall|disable|freeze]  [[v>=13]]  # 注释
```

- `uninstall`(默认): `pm uninstall --user 0`(adb) / `bm uninstall -n`(hdc)
- `disable`: `pm disable-user`, 被 ROM 静默拒绝时自动降级 `pm suspend`
- `freeze`: disable + force-stop, 效果等同禁用但强调"随时可解冻"(语义参考 Hail)
- 版本标注(可选): `[v>=13]` `[v<12]` `[v=13.1]` `[v12-13]`; 版本不符的条目由 `apply`/`check` 自动跳过。
  版本单位是该 ROM 家族自己的版本; 小米把 MIUI/HyperOS 拉平(MIUI 14=14, HyperOS 1=15),
  realme UI 换算成 ColorOS 等效版本(realme UI 4.0=13)
- `#` 开头为注释; 兼容 CRLF/UTF-8 BOM; 不存在的包由 `apply` 自动跳过, 不要为兼容删历史包名
- 分三区书写: 推荐 / 可选 / 谨慎(谨慎区默认整行注释, 用户自行取消注释)

## 双通道: adb 与 hdc

- HarmonyOS NEXT 5.x+ 没有 adb, 工具自动探测 `hdc`(或 `--hdc <路径>` 强制指定)
- hdc 通道(华为 DevEco Studio 自带)只能卸载(`bm uninstall -n`), **没有** disable/suspend/
  settings/appops; 遇到这类动作要明确报告"不支持", 不静默失败
- 冻结(`freeze`)在 hdc 通道同样不可用, 需引导用户改用 uninstall + 手动设置
- UI 自动化(`ui`/`adsw`)与 `chan`/`cutnet`/`quickapp` 同样只走 adb; hdc 通道要拒绝并说明

## UI 自动化(ui / adsw)

- 只用系统自带 `uiautomator dump` + `input tap`, **不得引入 uiautomator2 或任何第三方包**
  (不用无障碍服务, 才不会跟 GKD/自动记账抢读屏)
- 点击前必须过 `UI_RISKY_WORDS`: 不点"同意/允许/支付/删除/安装/恢复出厂"类控件,
  除非用户显式 `--allow-risky`
- `switches` 步骤只动 `off` 点名的开关, `keep` 里的一律保留; 找不到入口就跳过, 不猜位置
- `adsw` 规则是**数据不是代码**: 不得在 JSON 里放可执行表达式, 新步骤类型要在
  `_adsw_step` 里显式实现并补测试
- App 内开关属手动态, `restore` 不负责还原; 每条规则必须写 `manual` 手动路径

## 硬性规则(不可违反)

1. `tools/phone.py` 只用 Python 标准库; 可用 `python3 -I` 隔离运行
2. 不得移除或弱化 `DENY_PATTERNS` / `PROTECTED_PACKAGES` / 动态保护
   (当前桌面 `resolve_home`、最近任务 `resolve_recents`、输入法 `current_ime`)
3. 不得添加"向手机安装 APK/替换 launcher"的能力——本项目明确不装软件
4. 不提供 `.bat`/`.ps1`: 仓库路径可能含中文, Windows 批处理会乱码;
   Windows 用户统一用 `python tools/phone.py`
5. `sync_uad.py` 只写 `uad-recommended.txt`(候选), 不覆盖 `debloat.txt`
6. 提交前运行: `python3 -I tests/test_phone.py`(全部通过)
7. 包名拿不准时: 写上并注释"部分版本存在", 由脚本按本机实际情况跳过

## 测试

```bash
python3 -I tests/test_phone.py
```

FakeAdb 在内存中模拟 adb, 覆盖: 列表/设置解析(BOM/CRLF)、安全拒绝、桌面/Recents/输入法
动态保护、卸载失败降级、分批、恢复(含设置与传感器还原)、OTA 后 check --fix、
settings 记录与还原、shake on/off、DNS 自愈与回退、审计分组、ROM 版本识别与
版本门槛、hdc 通道(HarmonyOS NEXT: bm 卸载/不支持禁用)、冻结分级与 never_freeze。

FakeUi 在内存中模拟手机界面(点带 goto 的控件切页, 点开关翻转状态), 覆盖:
控件树解析、同行标题识别、精确匹配优先、敏感词拒绝、点击导航、读屏失败重试、
adsw 只关点名开关、keep 保留、dry-run 不落地、可选步骤跳过、缺失入口报错、
规则库 schema 校验、通知渠道解析与营销分类、快应用识别与禁用、断网按 uid 执行。
