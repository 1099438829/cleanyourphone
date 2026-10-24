# 传音 Tecno / Infinix / itel 国行版 (HiOS / XOS 12-14) — 手动关闭广告与优化设置

> 列表: [`debloat.txt`](debloat.txt) · 设置: [`settings.conf`](settings.conf)
> 适用: Tecno Camon/Phantom、Infinix Note/Hot、itel 系列(HiOS/XOS, 传音旗下)

## 一、关闭广告与推送(设置内操作)

1. **Palm Store / 应用商店推荐**
   应用商店 → 我的 → 设置 → 关闭「个性化推荐 / 推送通知」
2. **Phoenix / 浏览器资讯**
   浏览器 → 菜单 → 设置 → 关闭「资讯推送 / 个性化内容」
3. **锁屏画报(Glance / 杂志锁屏)**
   设置 → 锁屏 → 关闭「锁屏画报 / Glance」
4. **广告标识**
   设置 → 隐私 → 广告 → 关闭「个性化广告」并重置广告 ID
5. **系统级推送**: 传音机型营销推送多来自 `com.transsion.*` 服务,
   列表中的 disable 项已覆盖大部分

## 二、优化设置

1. **动画提速**: 设置 → 关于手机 → 连点「版本号」7 次 → 开发者选项 → 动画缩放 `0.5x`
2. **关闭系统更新自动下载**: 设置 → 系统 → 系统更新 → 关闭自动下载
3. **自启动管理**: 设置 → 应用 → 自启动(或 手机管家 → 自启动)
4. **关闭用户体验计划**: 设置 → 系统 → 用户体验改进 → 关闭
5. **内存扩展(Virtual RAM)**: 设置 → 存储 → 内存扩展 → 不需要可关闭(小内存机型建议保留)

## 三、版本差异(重要)

| HiOS/XOS 版本 | 卸载行为 | 说明 |
| --- | --- | --- |
| HiOS 12 (Android 12) | `pm uninstall --user 0` 基本可用 | 直接卸载 |
| HiOS 13 (Android 13) | 基本可用 | 同上 |
| HiOS 14 (Android 14) | 部分预装卸载被拒 | 自动降级禁用 |

- 版本号一般在 `ro.build.display.id`(如 `HiOS13.0.0`), 工具会自动提取;
  识别不到时手动指定 `python3 tools/phone.py rom --version hios:13`

## 四、注意事项

- **保留** `com.transsion.datatransfer`(换机迁移)、`com.transsion.filemanagerx`(文件管理)
- **保留** `com.transsion.camera`(相机)、`com.transsion.childmode`(儿童模式)
- 传音机型广告较多, 建议 `--tier standard` 先预演:
  `python3 tools/phone.py auto --tier standard --dry-run`
- 部分机型预装合作 App 在 `/data/app`(可卸载的第三方), 需要 `--include-third-party` 才会纳入
