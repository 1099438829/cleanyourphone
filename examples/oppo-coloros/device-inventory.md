# 真机清单 — OPPO PEQM00 (Android 13 / ColorOS 13)

> 2026-10-23 通过 adb 拉取并分析, 用于回补 `debloat.txt` / `settings.conf`。
> 拉取命令(可复现):
>
> ```bash
> adb shell pm list packages -s -f   # 系统应用(含 APK 路径), 存为 device-system-packages.txt
> adb shell pm list packages -3 -f   # 第三方应用
> adb shell pm list packages -d      # 已禁用
> adb shell pm list packages -u      # 已对 user 0 卸载
> adb shell settings list global / secure / system   # 三类系统设置
> adb shell dumpsys role             # 默认应用角色
> ```

## 设备概况

| 项 | 值 |
| --- | --- |
| 品牌/型号 | OPPO PEQM00 |
| 系统 | Android 13 (SDK 33) / ColorOS 13 |
| 系统应用 | 310 个(其中 65 个命中安全规则, 属核心组件, 禁止操作) |
| 第三方应用 | 40 个 |
| 默认桌面(HOME 角色) | `com.android.launcher` |
| 默认浏览器(BROWSER 角色) | `com.heytap.browser` |
| 默认输入法 | `com.sohu.inputmethod.sogouoem`(搜狗 OEM 版) |

## 一、ROM 限制(实测, 重要)

1. **卸载受限**: 大部分 `com.heytap.*` 预装应用 `pm uninstall --user 0` 返回
   `DELETE_FAILED_INTERNAL_ERROR`, 需降级为禁用
2. **禁用受限**: `com.heytap.pictorial`(乐划锁屏)执行 `pm disable-user` 返回
   `new state: default`(静默拒绝, 退出码为 0), 需改用 `pm suspend --user 0` 挂起
3. **设置写入受限**: 该 ROM 禁止 adb shell 写入 `settings`
   (`SecurityException: com.android.shell was not granted this permission:
   android.permission.WRITE_SETTINGS`), 所有 `settings put` 静默失败;
   工具已改为写入后回读校验, 如实报告失败

## 二、设置里发现的广告/隐私相关键(真机实测)

发现于 `settings list system/secure/global`, 已整理进 `settings.conf`
(默认注释, 因该 ROM 禁止 adb 写入; 旧版本 ColorOS 可尝试):

| 键 | 现值 | 含义 |
| --- | --- | --- |
| `system keyguard_apk_show_pictorial` | 1 | 锁屏显示乐划锁屏画报 |
| `system oplus_customize_pictorial_apply` | 1 | 乐划锁屏画报应用 |
| `system oplus_customize_pictorial_auto_play` | 1 | 画报自动播放 |
| `system oplus_customize_cta_update_pictorial` | 1 | 锁屏画报内容更新 |
| `system oplus_customize_cta_user_experience` | 1 | 用户体验改进计划 |
| `system is_mcs_upload` | 1 | 欢太移动云(mcs)数据上传 |
| `secure operator_service_improve_plan` | 1 | 运营商服务改进计划 |
| `secure recommend_support` | 1 | 内容推荐总开关 |
| `secure app_recommend_channel` | 1 | 应用推荐渠道 |
| `secure sidebar_recommend_declaration` | 0 | 侧边栏推荐声明(已关) |
| `global filter_notification_track` | 1 | 通知追踪过滤(已开) |
| `global network_recommendations_enabled` | 0 | 网络推荐(已关) |
| `global bug_report` | 0 | Bug 报告(已关) |

## 三、清单里发现但原列表缺失的包(已回补)

| 包名 | APK 路径 | 处理 |
| --- | --- | --- |
| `com.oplus.statistics.rom` | 系统统计 | 推荐禁用 |
| `com.coloros.video` | 视频/信息流 | 推荐禁用 |
| `com.oplus.onetrace` | `/system_ext/app/OTrace` | 可选(遥测) |
| `com.oplus.crashbox` | `/system_ext/app/CrashBox` | 可选(遥测) |
| `com.oplus.interconnectcollectkit` | `/product/app/InterconnectCollectKit` | 可选(遥测) |
| `com.google.android.printservice.recommendation` | Google 打印推荐 | 可选(遥测) |
| `com.coloros.assistantscreen` | 智能助手负一屏 | 可选(关后负一屏不可用) |
| `com.oplus.customize.coreapp` | `/system_ext/priv-app/CustCoreApp` | 可选(个性化核心, 谨慎) |
| `com.mediatek.gnssdebugreport` | MTK 定位调试上报 | 可选 |
| `com.android.adservices.api` | Android 广告服务 API | 可选 |
| `com.coloros.childrenspace` | 儿童空间 | 可选卸载 |

## 四、清理后的设备状态(2026-10-23)

- 卸载(user 0): `com.heytap.speechassist`、`com.coloros.smartsidebar`、
  `com.oplus.logkit`、`com.coloros.childrenspace`
- 禁用: `com.heytap.mcs`、`com.heytap.yoli`、`com.heytap.themestore`、
  `com.heytap.music`、`com.heytap.reader`、`com.nearme.gamecenter`、
  `com.coloros.video`、`com.oplus.statistics.rom`、`com.android.adservices.api`、
  `com.mediatek.gnssdebugreport`
- 挂起(suspend): `com.heytap.pictorial`(乐划锁屏)、`com.heytap.browser`(浏览器)、
  `com.heytap.quicksearchbox`(全局搜索)
- 保护未动: 桌面 `com.android.launcher`、输入法 `com.sohu.inputmethod.sogouoem`

> 注意: 默认浏览器角色仍指向已挂起的 `com.heytap.browser`, 点击链接时
> 系统会弹"选择应用"; 如常用其他浏览器可在 设置 → 应用 → 默认应用 中改绑。
