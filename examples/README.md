# examples — 各品牌清理列表索引

每个品牌目录包含四个文件:

| 文件 | 说明 |
| --- | --- |
| `debloat.txt` | 手工维护的清理列表(推荐/可选/谨慎三区) |
| `settings.conf` | 设置级去广告项(`settings put`, DNS 项默认注释) |
| `README.md` | 该品牌**手动关闭广告**的逐条设置路径 + 优化设置建议 |
| `uad-recommended.txt` | UAD-NG 自动生成的候选(`python3 -I tools/sync_uad.py` 同步, 需人工核对) |

| 目录 | 适用品牌/ROM | 清理重点 |
| --- | --- | --- |
| [xiaomi-hyperos](xiaomi-hyperos/) | 小米/红米/POCO MIUI 12-14、HyperOS 1-2 | MSA、遥测、锁屏画报、负一屏、视频/音乐/浏览器 |
| [huawei-harmonyos](huawei-harmonyos/) | 华为 EMUI 10/11、HarmonyOS 2-5 | 华为视频/音乐/搜索、玩机技巧、HMS 遥测 |
| [honor-magicos](honor-magicos/) | 荣耀 MagicOS 7/8/9 | 杂志锁屏、浏览器/视频/音乐、推送通道 |
| [oppo-coloros](oppo-coloros/) | OPPO/一加/realme ColorOS 11-15、realme UI | 乐划锁屏、锁屏杂志、欢太统计、浏览器 |
| [vivo-originos](vivo-originos/) | vivo/iQOO OriginOS 1-4、Funtouch OS 10-13 | 锁屏画报、营销中心、负一屏、浏览器 |
| [samsung-oneui-cn](samsung-oneui-cn/) | 三星国行 One UI 5-8 | Samsung Free 负一屏资讯、McAfee 弹窗 |
| [meizu-flyme](meizu-flyme/) | 魅族 Flyme 9/10/AI | 魅族浏览器、视频 |
| [universal](universal/) | 全品牌通用 | Android 广告服务、Google 组件、AOSP 彩蛋 |
| [shake_apps.txt](shake_apps.txt) | 全品牌摇一摇封杀清单 | 微信/淘宝/抖音等 22 款第三方 App |

## 使用

```bash
# 预演(不执行)
python3 tools/phone.py apply examples/xiaomi-hyperos/debloat.txt --dry-run

# 执行(自动先备份)
tools/disable.sh examples/xiaomi-hyperos/debloat.txt

# 分批执行 + 每批截图验证(第一次清理推荐)
python3 tools/phone.py apply examples/xiaomi-hyperos/debloat.txt --batch 5 --screenshot

# 设置级去广告
python3 tools/phone.py settings examples/xiaomi-hyperos/settings.conf

# 摇一摇封杀 / Private DNS
python3 tools/phone.py shake on
python3 tools/phone.py dns on dot.pub

# 恢复 / OTA 后检查
tools/restore.sh --all
tools/check.sh examples/xiaomi-hyperos/debloat.txt --fix
```

## 列表格式

```
包名  [uninstall|disable]  # 注释
```

- `uninstall`(默认): `pm uninstall --user 0`, 对当前用户卸载系统应用, 可用 `install-existing` 恢复
- `disable`: `pm disable-user`, 禁用组件, 可用 `pm enable` 恢复
- 行首 `#` 为注释; 不同 ROM 包名有差异, 不存在的包会自动跳过
- 命中安全规则(桌面/电话/短信/系统 UI 等)或当前桌面/输入法/最近任务的包会被拒绝并提示
