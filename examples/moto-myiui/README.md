# 摩托罗拉 国行 (myui 4-6) — 手动关闭广告与优化设置

> 列表: [`debloat.txt`](debloat.txt) · 设置: [`settings.conf`](settings.conf)
> 适用: moto edge / moto g 系列国行(myui, 联想旗下, 接近原生 Android)

## 一、关闭广告与推荐(设置内操作)

1. **Moto App Box(应用推荐位)**
   桌面/文件夹里的「Moto」推荐 → 长按 → 卸载
   (或卸载 `com.motorola.brapps`)
2. **发现气泡(Discovery)**
   设置 → 搜索「发现」/「提示」→ 关闭; 或卸载 `com.motorola.discovery`
3. **个性化广告**
   设置 → 隐私 → 广告 → 关闭「个性化广告」
4. **Moto 通知(营销)**
   设置 → 通知 → Moto 通知 → 关闭
5. **浏览器/应用商店**: myui 国行预装联想应用中心与浏览器, 不需要可直接卸载

## 二、优化设置

1. **动画提速**: 设置 → 关于手机 → 连点「版本号」7 次 → 开发者选项 → 动画缩放 `0.5x`
2. **关闭系统更新自动下载**: 设置 → 系统 → 系统更新 → 关闭自动下载
3. **Moto 手势**: 设置 → 手势(Moto Actions) → 按需关闭甩腕开相机/翻转勿扰
4. **电池养护**: 设置 → 电池 → 电池养护 → 开启「限制充电至 80%」(长期插电适用)
5. **关闭使用情况上报**: 设置 → 隐私 → 使用情况和诊断 → 关闭

## 三、版本差异(重要)

| myui 版本 | 卸载行为 | 说明 |
| --- | --- | --- |
| myui 4 (Android 13) | `pm uninstall --user 0` 基本可用 | 直接卸载 |
| myui 5 (Android 14) | 基本可用 | 同上 |
| myui 6 (Android 15) | 少数系统组件卸载被拒 | 自动降级禁用 |

- myui 的版本号常不在独立属性里(只在 `ro.build.display.id` 或设置页显示),
  工具识别不到时会提示「未识别 ROM」, 此时可手动指定:
  `python3 tools/phone.py rom --version myui:5`

## 四、注意事项

- **保留** `com.motorola.actions`(Moto 手势)、`com.motorola.camera3`(相机)
- **保留** `com.motorola.batterycare`(电池养护), 删了「限充 80%」会失效
- 运营商相关包(`com.motorola.attvowifi` / `comcastext` 等)仅美版机型存在, 国行一般没有,
  列表中不存在的包会自动跳过
- myui 自带广告很少, 清理重点其实是「演示模式 / 诊断上报 / AI 服务」这类后台项
