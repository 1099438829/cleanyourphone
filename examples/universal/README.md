# 全品牌通用(Google 组件 / AOSP 内置) — 说明

本目录的 `debloat.txt` 适用于所有 Android 手机, 主要处理:

- `com.android.adservices` — Android 系统广告服务(隐私沙盒/共享广告 ID), 建议禁用
- 未使用的 Google 预装组件(Duo、Google TV、数字健康、ARCore 等)
- AOSP 内置小件(安卓彩蛋、AOSP 音乐/邮件、屏保等)

## 注意

- 国行机型大多**未预装 Google 组件**, 列表中不存在的包会自动跳过, 属正常现象
- 使用 Google 服务(Gmail/地图/YouTube)的用户, 请勿卸载 `com.google.android.gms`(脚本安全规则也会拒绝)
- `com.google.android.googlequicksearchbox`(Google 应用)卸载后, 桌面 Google 搜索栏会失效, 按需选择
- 建议先执行本列表, 再执行对应品牌的列表
