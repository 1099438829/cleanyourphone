# examples — 各品牌清理列表索引

每个品牌目录包含以下文件:

| 文件 | 说明 |
| --- | --- |
| `debloat.txt` | 手工维护的清理列表(推荐/可选/谨慎三区) |
| `settings.conf` | 设置级去广告项(`settings put`, DNS 项默认注释) |
| `README.md` | 该品牌**手动关闭广告**的逐条设置路径 + 优化设置建议 |
| `uad-recommended.txt` | UAD-NG 自动生成的候选(`python3 -I tools/sync_uad.py` 同步, 需人工核对) |
| `device-inventory.md`(部分) | **真机实测记录**: 拉取的清单/设置键、ROM 限制、清理后状态 |
| `device-system-packages.txt`(部分) | 真机 `pm list packages -s -f` 原始输出 |

| 目录 | 适用品牌/ROM | 清理重点 |
| --- | --- | --- |
| [xiaomi-hyperos](xiaomi-hyperos/) | 小米/红米/POCO MIUI 12-14、HyperOS 1-2 | MSA、遥测、锁屏画报、负一屏、视频/音乐/浏览器 |
| [huawei-harmonyos](huawei-harmonyos/) | 华为 EMUI 10/11、HarmonyOS 2-4(NEXT 5.x 走 hdc) | 华为视频/音乐/搜索、玩机技巧、HMS 遥测 |
| [honor-magicos](honor-magicos/) | 荣耀 MagicOS 6/7/8/9 | 杂志锁屏、浏览器/视频/音乐、推送通道 |
| [oppo-coloros](oppo-coloros/) | OPPO ColorOS 7-15 | 乐划锁屏、锁屏杂志、欢太统计、浏览器 |
| [oneplus-coloros](oneplus-coloros/) | 一加国行 ColorOS/OxygenOS 11-15 | 禅定模式、游戏空间、图标包、乐划锁屏 |
| [realme-ui](realme-ui/) | realme 国行 realme UI 2-6 | realme 音乐/安全检测/睡眠胶囊 + ColorOS 共用项 |
| [vivo-originos](vivo-originos/) | vivo/iQOO OriginOS 1-5、Funtouch OS 10-14 | 锁屏画报、营销中心、负一屏、浏览器 |
| [samsung-oneui-cn](samsung-oneui-cn/) | 三星国行 One UI 5-8 | Samsung Free 负一屏资讯、McAfee 弹窗 |
| [meizu-flyme](meizu-flyme/) | 魅族 Flyme 8/9/10/11 | 魅族浏览器、视频 |
| [zte-nubia](zte-nubia/) | 中兴 Axon / 努比亚 Z / 红魔 MyOS 11-14 | 数据采集、快应用容器、努比亚浏览器/商店 |
| [moto-myiui](moto-myiui/) | 摩托罗拉 myui 4-6(联想旗下) | Moto App Box、发现气泡、演示模式、诊断上报 |
| [lenovo-zui](lenovo-zui/) | 联想 ZUI 14-16 / 拯救者 | 联想应用中心、浏览器、语音全家桶、主题覆盖层 |
| [transsion-hios](transsion-hios/) | 传音 Tecno/Infinix/itel HiOS·XOS 12-14 | Folax 语音、AI 壁纸、健康、售后 App、工程模式 |
| [universal](universal/) | 全品牌通用 | Android 广告服务、Google 组件、AOSP 彩蛋 |
| [shake_apps.txt](shake_apps.txt) | 全品牌摇一摇封杀清单 | 微信/淘宝/抖音等 22 款第三方 App |
| [freeze-recommended.txt](freeze-recommended.txt) | 全品牌可冻结预装清单(1848 个, safe/recommended/caution 三级) | 冻结=不可启动但不删除, 随时可解冻; 也可 `python3 tools/phone.py freeze --tier safe` 按本机过滤 |

> 不想手工挑? 用**自动清单**: `python3 tools/harvest.py` 抓取互联网知识库后,
> `python3 tools/phone.py auto` 会按**本机实际预装**自动生成清单(见根目录 README)。
>
> 不敢删只想让它闭嘴? 用**冻结清单**: `python3 tools/phone.py freeze --tier safe`
> (语义参考 Hail / FreezeYou, 解冻 `restore --all`)。

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

# 自动清单(按本机预装自动匹配)
python3 tools/harvest.py            # 更新互联网知识库
python3 tools/phone.py auto         # 预演
python3 tools/phone.py auto --apply # 执行
```

## 列表格式

```
包名  [uninstall|disable]  [[v>=13]]  # 注释
```

- `uninstall`(默认): `pm uninstall --user 0`, 对当前用户卸载系统应用, 可用 `install-existing` 恢复
- `disable`: `pm disable-user`, 禁用组件, 可用 `pm enable` 恢复
- **版本标注**(可选): `[v>=13]` `[v<12]` `[v=13.1]` `[v12-13]`, 写在行尾或注释里都行;
  与当前 ROM 版本不符的条目会被自动跳过
- 行首 `#` 为注释; 不同 ROM 包名有差异, 不存在的包会自动跳过
- 命中安全规则(桌面/电话/短信/系统 UI 等)或当前桌面/输入法/最近任务的包会被拒绝并提示

## 版本标注怎么用

同一个品牌的不同 ROM 版本, 包名和可卸载程度都不一样, 所以列表支持按版本分区:

```
com.heytap.pictorial   disable    [v>=12]  # ColorOS 12+ 是乐划锁屏
com.coloros.lockscreen.magazine disable [v<12]  # ColorOS 11 及以下是锁屏杂志
com.heytap.browser     uninstall  [v<12]   # 低版本可直接卸载
com.heytap.browser     disable    [v>=12]  # 高版本 ROM 拦截卸载, 直接禁用
```

- 版本号单位是**该 ROM 家族的版本**(ColorOS 13.1 / MagicOS 8.0 / OriginOS 4.0),
  小米会把 MIUI 与 HyperOS 两套编号拉平(MIUI 14=14, HyperOS 1=15, HyperOS 2=16)
- realme UI 会自动换算成 ColorOS 等效版本(realme UI 4.0 = ColorOS 13)
- 查看本机版本 + 某份清单的适用性:

```bash
python3 tools/phone.py rom
python3 tools/phone.py rom --list examples/oppo-coloros/debloat.txt
```

