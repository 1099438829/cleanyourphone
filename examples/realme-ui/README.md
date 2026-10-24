# realme 国行 (realme UI 2-6) — 手动关闭广告与优化设置

> 列表: [`debloat.txt`](debloat.txt) · 设置: [`settings.conf`](settings.conf)
> realme UI 是 ColorOS 分支, 广告开关与 OPPO 高度一致, 详细路径见
> [`../oppo-coloros/README.md`](../oppo-coloros/README.md)

## 一、关闭广告(设置内操作)

1. **乐划锁屏(锁屏广告)**: 设置 → 桌面与锁屏 → 乐划锁屏 → 关闭
2. **个性化广告**: 设置 → 权限与隐私 → 隐私 → 广告与隐私 → 关闭个性化推荐
3. **浏览器资讯**: 浏览器 → 我的 → 设置 → 关闭资讯推送
4. **应用商店推荐**: 应用商店 → 我的 → 设置 → 关闭个性化推荐
5. **realme Link / 社区推送**: 各自应用内设置 → 关闭通知与推荐

## 二、优化设置

1. 动画缩放 `0.5x`(开发者选项)
2. 关闭系统更新自动下载(设置 → 关于手机 → 右上角「···」)
3. 自启动管理: 设置 → 应用 → 自启动
4. 关闭用户体验计划: 设置顶部搜索「体验改进」

## 三、版本差异(重要)

realme UI 的编号和 ColorOS 不是一套, 工具会自动换算成「ColorOS 等效版本」:

| realme UI | 等效 ColorOS | Android | 卸载行为 |
| --- | --- | --- | --- |
| 2.0 | 11 | 11 | 基本可直接卸载 |
| 3.0 | 12 | 12 | 开始出现卸载被拒 |
| 4.0 | 13 | 13 | 大量系统应用只能禁用/挂起; adb 禁写 settings |
| 5.0 | 14 | 14 | 同上, 挂起可能被系统恢复 |
| 6.0 | 15 | 15 | 同上, 建议分批执行 |

所以 `debloat.txt` 里的 `[v<12]` / `[v>=12]` 是**按 ColorOS 等效版本**判断的:
realme UI 2.0 会命中 `[v<12]`(直接卸载), realme UI 4.0 会命中 `[v>=12]`(禁用)。

## 四、注意事项

- **保留** `com.realme.findphone.client2`(查找手机)、`com.heytap.cloud`(云服务)
- **保留** `com.heytap.usercenter`(账号中心)、`com.coloros.oshare`(互传)
- `com.realme.link` 是耳机/手表配套 App, 有 realme 生态设备就保留
