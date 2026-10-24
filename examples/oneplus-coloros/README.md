# 一加 国行 (ColorOS / OxygenOS 12-15) — 手动关闭广告与优化设置

> 列表: [`debloat.txt`](debloat.txt) · 设置: [`settings.conf`](settings.conf)
> 一加国行 9RT 之后改用 ColorOS, 广告开关与 OPPO 一致, 详细路径见
> [`../oppo-coloros/README.md`](../oppo-coloros/README.md)

## 一、关闭广告(设置内操作)

1. **乐划锁屏**: 设置 → 桌面与锁屏 → 乐划锁屏 → 关闭
2. **个性化广告**: 设置 → 权限与隐私 → 隐私 → 广告与隐私 → 关闭
3. **浏览器资讯**: 浏览器 → 我的 → 设置 → 关闭资讯推送
4. **应用商店推荐**: 软件商店 → 我的 → 设置 → 关闭个性化推荐
5. **游戏空间推荐**: 游戏空间 → 设置 → 关闭推荐(或卸载 `com.oneplus.gamespace`)

## 二、优化设置

1. 动画缩放 `0.5x`(开发者选项)
2. 关闭系统更新自动下载(设置 → 关于手机 → 右上角「···」)
3. 自启动管理: 设置 → 应用 → 自启动
4. 禅定模式不用可卸载(`com.oneplus.brickmode`)

## 三、版本差异(重要)

| 版本 | 卸载行为 | 建议 |
| --- | --- | --- |
| ColorOS 11 / OxygenOS 11 (Android 11) | `pm uninstall --user 0` 基本可用 | 直接卸载 |
| ColorOS 12 (Android 12) | 系统应用卸载被拒开始增多 | 自动降级禁用 |
| ColorOS 13 (Android 13) | 大量被拒; adb 禁写 settings | 正常执行, 看失败项 |
| ColorOS 14/15 (Android 14/15) | 同上, 挂起可能被系统恢复 | `check --fix` 重新挂起 |

- 想少刷失败日志: 加 `--prefer-disable`, 该版本会拦截的包直接走禁用
- 版本识别: `python3 tools/phone.py rom`

## 四、注意事项

- **保留** `com.oneplus.camera`(相机)、`com.oneplus.gallery`(相册)、`com.oneplus.aod`(息屏显示)
- **保留** `com.oneplus.account`(一加账号)、`com.coloros.oshare`(互传)
- 图标包(`com.oneplus.iconpack.*`)可卸载, 只影响主题选择
