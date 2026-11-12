---
name: vertex-spend-monitor
description: 查询 Vertex runner 的每日估算花费及本地预算，按需设置每日监控报告。适用于 Google Cloud 赠金用量、Vertex 共享池花费日报和预算查询。
---

# Vertex 每日花费监控

## 查询

先按 README.md 核对数据格式和配置。需要 Python 3.10+，只用标准库。数据目录由使用者配置，凭据保存在运行主机。

在 runner 本机执行，默认查询主机时区的昨天。

```sh
python3 scripts/daily.py
python3 scripts/daily.py --root /path/to/runner-data --date YYYY-MM-DD --json
```

通过使用者已有的 SSH 配置查询远程主机。

```sh
python3 scripts/daily.py --ssh-target runner-alias
```

报告日期、各配置的当日估算、账本合计和本地总预算余额。共享池数字包含所有使用该配置的任务。缺记录时报告「无记账记录」，读取失败时报告「未知」并保留错误摘要。

金额来自 runner 按配置价格计算的账本，包含账本已计入的缓存费用。Google 官方入账金额、赠金抵扣及剩余赠金需要从 Cloud Billing 报告或已有账单导出核对。先确认来源和日期口径，再根据用户所需报告金额。

## 每日监控

用户要配置或生成监控方案时，将查询命令与报告模板交给其选择的调度器。若只是交付 Skill 或询问能力，完成交付。用户明确要求启动定时报告后，先查现有同类任务，复用或更新，按用户指定的时区、时间和交付位置配置。未指定时间时询问或提出默认值。

日报包含所查日期、美元总估算、各配置估算和本地预算余额。金额标明本地估算，缺数据及查询失败保留未知状态。脚本只输出结果，由调度器发送。具体命令及通用调度示例见 README.md。
