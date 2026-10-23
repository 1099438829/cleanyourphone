# OPPO / 一加 / realme 国行 (ColorOS 11-15 / realme UI) — 手动关闭广告与优化设置

## 一、关闭广告(设置内操作)

1. **乐划锁屏(锁屏广告, 头号来源)**
   设置 → 桌面与锁屏 → **乐划锁屏** → 关闭
   (或直接禁用/卸载 `com.heytap.pictorial`, 见 `debloat.txt`)
2. **个性化广告推荐**
   设置 → 权限与隐私 → 隐私 → **广告与隐私/广告推荐** → 关闭"个性化广告推荐"
   (部分版本路径为: 设置 → 隐私 → 广告; 也可在设置顶部搜索"广告"直达)
3. **浏览器资讯**(保留浏览器时)
   浏览器 → 我的 → 设置 → 关闭"资讯推送/个性化推荐"
4. **软件商店推荐**: 软件商店 → 我的 → 设置 → 关闭"个性化推荐/推送"
5. **全局搜索推荐**: 设置 → 便捷工具/搜索 → 关闭"热门搜索/资讯"(或卸载 `com.heytap.quicksearchbox`)
6. **游戏中心/游戏空间**: 各自应用内设置 → 关闭推荐与推送

## 二、优化设置

1. **动画提速**: 设置 → 关于手机 → 版本信息 → 连点版本号 7 次打开开发者选项 → 三个动画缩放设为 `0.5x`
2. **关闭自动更新**: 设置 → 关于手机 → 右上角"···" → 关闭"自动下载/夜间自动更新"
3. **关闭体验改进计划**: 设置顶部搜索"体验改进计划" → 关闭
4. **自启动管理**: 设置 → 权限与隐私 → 自启动管理(或 设置 → 应用 → 应用管理 → 自启动) → 按需关闭
5. **电池**: 设置 → 电池 → 高性能模式 → 按需开启
6. **智能侧边栏/悬浮球**: 不用可在 设置 → 便捷工具 里关闭(或卸载 `com.coloros.smartsidebar`)

## 三、注意事项

- 老机型使用 `com.nearme.*` 旧包名, 列表中不存在的包会自动跳过, 属正常
- **保留** `com.heytap.usercenter`(账号中心)与 `com.heytap.cloud`(云服务/查找手机)
- **保留** `com.coloros.oshare`(互传): 换机传输依赖它
- realme UI 国行同样适用本列表; 一加国行(ColorOS 内核)同样适用

## 四、真机测试记录(OPPO PEQM00, Android 13 / ColorOS 13)

- **卸载受限**: 大部分 `com.heytap.*` 预装应用执行 `pm uninstall --user 0` 会返回
  `DELETE_FAILED_INTERNAL_ERROR`(ROM 保护), 工具会自动**降级为禁用**, 属正常现象
- **乐划锁屏禁用受限**: `com.heytap.pictorial` 执行 `pm disable-user` 会返回
  `new state: default`(静默拒绝, 退出码仍为 0), 工具会自动改用
  `pm suspend --user 0` **挂起**(应用无法启动, 效果等同禁用); 挂起状态可能被系统恢复,
  可用 `check --fix` 重新挂起
- **真机命中/缺失情况**(18 条列表): 命中 12 条, 6 条该机型未安装
  (`com.coloros.lockscreen.magazine` / `com.nearme.statistics` / `com.heytap.habit.analysis` /
  `com.coloros.gamespace` / `com.heytap.push` / `com.heytap.dictation`)
- **审计补充**: `audit` 在该机发现列表外候选 `com.oplus.statistics.rom`、`com.coloros.video`、
  `com.coloros.childrenspace`、`com.mediatek.gnssdebugreport`、`com.android.adservices.api`,
  已补入本列表
- 该机输入法为搜狗 OEM 版(`com.sohu.inputmethod.sogouoem`), 清理时被自动保护, 不受影响
