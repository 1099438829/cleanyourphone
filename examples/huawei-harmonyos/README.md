# 华为 (EMUI 10/11, HarmonyOS 2-5) — 手动关闭广告与优化设置

## 一、关闭广告(设置内操作)

1. **限制广告跟踪(最重要)**
   设置 → 隐私 → **广告与隐私** → 打开"限制广告跟踪"
2. **杂志锁屏**(锁屏广告主要来源)
   设置 → 桌面和壁纸 → **杂志锁屏** → 关闭(建议同时清理已下载的锁屏图片)
3. **智慧搜索资讯/热搜**
   设置 → 智慧助手 → 智慧搜索 → 高级功能/设置 → 关闭"资讯""热搜""个性化推荐"
   (或卸载 `com.huawei.search`)
4. **玩机技巧/服务推荐**
   设置 → 智慧助手 → 关闭"智能推荐/个性化推荐"相关开关(或卸载 `com.huawei.tips`)
5. **浏览器资讯**(保留浏览器时)
   浏览器 → 我的 → 设置 → 关闭"资讯通知/个性化推荐"
6. **华为视频/音乐**: 卸载后广告入口随之消失(见 `debloat.txt`)
7. **应用市场推荐**: 应用市场 → 我的 → 设置 → 关闭"个性化推荐"

> 小技巧: 设置页顶部搜索"广告""推荐""杂志锁屏"通常能直达开关。

## 二、优化设置

1. **动画提速**: 设置 → 系统和更新 → 开发人员选项 → 三个动画缩放设为 `0.5x`
2. **关闭自动下载更新**: 设置 → 系统和更新 → 软件更新 → 右上角"设置" → 关闭"WiFi 下自动下载"
3. **关闭用户体验计划**: 设置 → 系统和更新 → 用户体验改进计划 → 关闭
4. **应用启动管理**: 设置 → 应用 → 应用启动管理 → 关闭不需要自启动的应用
5. **电池优化**: 设置 → 电池 → 更多电池设置 → 关闭"性能模式"(发热场景)
6. **负一屏(今天)**: 设置 → 桌面和壁纸 → 桌面设置 → 可关闭"智能助手/今天"

## 三、注意事项

- 华为对 `com.huawei.*` 系统应用保护较严: 卸不掉的会自动降级为禁用(`pm disable-user`), 效果相同
- **保留** `com.huawei.hicloud`(云服务)与查找设备, 手机丢失时靠它们定位
- **保留** `com.huawei.hwid`(华为账号): HMS 服务、应用市场都依赖它, 默认不卸
- `com.huawei.systemmanager`(手机管家)含广告但管权限, 默认不动; 想卸请自行权衡

## 四、版本差异(重要)

| 版本 | 调试通道 | 说明 |
| --- | --- | --- |
| EMUI 10/11 (Android 10) | adb | 卸载基本可用 |
| HarmonyOS 2 (Android 10-11) | adb | 开发者选项需打开「仅充电时允许 ADB 调试」 |
| HarmonyOS 3 (Android 12) | adb | 部分预装卸载后会自动恢复, 用 `check --fix` |
| HarmonyOS 4/4.2 (Android 12) | adb | 华为账号/云空间/钱包已列入谨慎名单 |
| **HarmonyOS NEXT 5.x** | **hdc** | 华为移除了 adb; 工具自动切 hdc 通道, 只能卸载(见下) |

- 版本识别: `python3 tools/phone.py rom`(NEXT 5.x 会提示改用 hdc)
- 想确认版本: 设置 → 关于手机 → 版本号; 或 `adb shell getprop hw_sc.build.platform.version`

### HarmonyOS NEXT 5.x: hdc 怎么用

1. **装 hdc**: 电脑上装 [DevEco Studio](https://developer.huawei.com/consumer/cn/deveco-studio/),
   命令行 hdc 在 `DevEco Studio/sdk/default/.../hdc`(macOS/Linux 下也可 `ln -s` 到 PATH)
2. **手机端**: 设置 → 系统 → 开发者选项 → 打开「HDC 调试」, 插线后手机点允许
3. **跑工具**(自动探测, 无需参数; 多通道时手动指定):
   ```bash
   python3 tools/phone.py doctor
   python3 tools/phone.py --hdc ~/DevEcoStudio/sdk/default/hms/hdc apply examples/huawei-harmonyos/debloat.txt --dry-run
   ```
4. **能力边界**(bm 工具决定):
   - 能: `bm uninstall -n <包名> -k` 卸载(保留数据), 恢复需按上文手动重装
   - 不能: 禁用/挂起(`pm disable-user`/`pm suspend` 不存在)、`settings put` 系统设置、
     `appops` 摇一摇封杀、区分预装分区 —— 这些请按本 README「一、关闭广告」手动操作
   - 清单里 `disable` 条目会明确报告"bm 不支持禁用", 想处理就把动作改成 `uninstall`

