# AGENTS.md — CleanYourPhone 仓库地图(给编码代理)

参考 CleanYourTV / CleanYourAndroid / cleanyourphone(upfind) 三家组织方式。
核心约束: **无 root、不向手机安装软件、全部可逆、内置安全规则 + 动态保护**。

## 仓库地图

| 路径 | 内容 | 修改规则 |
| --- | --- | --- |
| `tools/phone.py` | 核心工具: adb 自动准备、列表/设置解析、安全规则、apply/restore/check/audit/settings/dns/shake/screenshot | 只允许标准库; 新增子命令需同步更新 `build_parser`/`main`/测试 |
| `tools/clean.sh` | 全流程编排(backup→debloat→settings→shake, 可分阶段) | 保持编排式实现, 逻辑一律放 phone.py |
| `tools/disable.sh` `restore.sh` `check.sh` | `phone.py` 的 bash 封装 | 保持转发式实现 |
| `tools/install-adb.sh` | 安装官方 Android 平台工具 | 覆盖 macOS/Linux/Windows |
| `tools/sync_uad.py` | 从 UAD-NG 同步品牌候选列表到 `examples/<品牌>/uad-recommended.txt` | 只生成候选文件, 禁止覆盖手工 `debloat.txt`; 必须过安全规则过滤 |
| `tests/test_phone.py` | 单元测试(FakeAdb 模拟设备) | 改 `phone.py` 行为必须同步测试 |
| `examples/<品牌>/debloat.txt` | 手工维护的清理列表 | 格式见下; 分 推荐/可选/谨慎(谨慎默认注释) |
| `examples/<品牌>/settings.conf` | 设置项(settings put) | 格式: `ns key value # 注释`; DNS 项默认注释 |
| `examples/<品牌>/README.md` | 手动关广告 + 优化设置 | 路径注明"设置顶部可搜索直达", 随版本可能变化 |
| `examples/shake_apps.txt` | 全品牌摇一摇封杀清单 | 只收常见第三方 App, 不收系统包 |
| `PROMPT.md` | 给 AI 助手的执行提示词 | 与 README 的工具用法保持一致 |

## 列表格式(debloat.txt)

```
包名  [uninstall|disable]  # 注释
```

- `uninstall`(默认): `pm uninstall --user 0`
- `disable`: `pm disable-user`
- `#` 开头为注释; 兼容 CRLF/UTF-8 BOM; 不存在的包由 `apply` 自动跳过, 不要为兼容删历史包名
- 分三区书写: 推荐 / 可选 / 谨慎(谨慎区默认整行注释, 用户自行取消注释)

## 硬性规则(不可违反)

1. `tools/phone.py` 只用 Python 标准库; 可用 `python3 -I` 隔离运行
2. 不得移除或弱化 `DENY_PATTERNS` / `PROTECTED_PACKAGES` / 动态保护
   (当前桌面 `resolve_home`、最近任务 `resolve_recents`、输入法 `current_ime`)
3. 不得添加"向手机安装 APK/替换 launcher"的能力——本项目明确不装软件
4. 不提供 `.bat`/`.ps1`: 仓库路径可能含中文, Windows 批处理会乱码;
   Windows 用户统一用 `python tools/phone.py`
5. `sync_uad.py` 只写 `uad-recommended.txt`(候选), 不覆盖 `debloat.txt`
6. 提交前运行: `python3 -I tests/test_phone.py`(全部通过)
7. 包名拿不准时: 写上并注释"部分版本存在", 由脚本按本机实际情况跳过

## 测试

```bash
python3 -I tests/test_phone.py
```

FakeAdb 在内存中模拟 adb, 覆盖: 列表/设置解析(BOM/CRLF)、安全拒绝、桌面/Recents/输入法
动态保护、卸载失败降级、分批、恢复(含设置与传感器还原)、OTA 后 check --fix、
settings 记录与还原、shake on/off、DNS 自愈与回退、审计分组。
