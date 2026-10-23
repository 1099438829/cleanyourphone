# 贡献指南

感谢帮 CleanYourPhone 补充更多品牌/机型/ROM 的清理列表!

## 贡献一个列表

1. Fork 本仓库, 新建 `examples/<brand>-<rom>/`(如 `examples/xiaomi-hyperos/`)
2. 按格式写 `debloat.txt`:

   ```
   包名  [uninstall|disable]  # 中文注释(这个应用是干什么的、卸了会怎样)
   ```

   - 分三区: **推荐**(安全有效) / **可选**(按需) / **谨慎**(整行默认注释)
   - 广告与统计服务用 `disable`, 预装应用用 `uninstall`
   - 拿不准的包名: 写上并注明"部分版本存在", 脚本会自动跳过不存在的包
3. 写 `settings.conf`(命名空间 global/secure/system + 键名 + 值)与 `README.md`
   (手动关闭广告的设置路径 + 优化设置建议)
4. 在 `examples/README.md` 的索引表里加一行
5. 本地验证:

   ```bash
   python3 -I tests/test_phone.py                 # 单元测试
   python3 tools/phone.py apply examples/<你的目录>/debloat.txt --dry-run
   python3 -I tools/sync_uad.py                   # 可选: 对比 UAD-NG 候选, 补齐遗漏
   ```

6. PR 里请附上: 测试机型、ROM 版本、`python3 tools/phone.py info` 的输出

## 报告问题

- 某个包卸载后出现功能异常 → 开 issue, 说明机型/ROM/包名/现象, 我们会把它移到"谨慎区"或加保护
- 列表漏了某个广告源 → 开 issue 或直接 PR

## 不要做的事

- 不要添加 root/刷机/安装 APK 相关能力
- 不要绕过 `tools/phone.py` 的安全规则(见 AGENTS.md)
- 不要提交真实的个人设备信息(序列号等)
