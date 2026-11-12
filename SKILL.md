---
name: vertex-spend-monitor
description: 查询 Google Cloud 官方已入账的每日及本月费用、赠金抵扣和净费用，按需设置每日预算监控报告。适用于 Vertex、Google AI 和 Cloud 赠金的官方账单查询。
---

# Google Cloud 官方花费监控

## 查询准备

阅读 README.md 的配置和验证边界。数据源为 Cloud Billing 标准或详细使用费 BigQuery 导出。用户本地的 settings.local.json 指向已启用的导出表。运行主机通过 gcloud 已有身份认证，凭据留在本地。

先检查导出和 IAM 是否齐备。导出未启用、无数据或权限不足时报告官方金额未知，说明需要补齐的依赖。启用导出及建立资源按用户授权执行。

## 官方账单查询

需要 Python 3.10+ 和 gcloud。命令在技能目录执行。

```sh
python3 scripts/daily.py --settings settings.local.json --dry-run
python3 scripts/daily.py --settings settings.local.json
python3 scripts/daily.py --settings settings.local.json --date YYYY-MM-DD --json
```

默认查询所配时区的昨天，附上本月截至该日的已入账费用。按账单币种分开汇报费用、全部抵扣、其中促销赠金抵扣和净费用。净费用 = 费用 + 抵扣，抵扣通常为负数。按用量日期汇总，月计覆盖该月第一天至所查日期。

结果涵盖表内整个结算账号的服务和项目。查询具体 Vertex 项目时，从 daily_details 读取对应项目及服务的明细，并保留账号整体支出以支持预算检查。

报告币种、日期、时区及所查记录最近导出时间。无对应记录时金额未知。后续入账及调整可能改变金额。检查赠金剩余余额时另外读取官方赠金页。预算告警及余额以官方对应数据核对。

## 每日监控

用户要交付 Skill 或监控方案时提供命令和调度示例。用户明确要求启动定时报告后，先查现有同类任务，按其时区、时间及交付位置复用或设置。脚本输出查询结果，由用户选择的调度器发送。

日报包含官方来源、每日费用、抵扣、净费用、本月截至该日累计、币种、时区、导出时间和异常。缺数据或查询失败保留未知状态。因账单入账有延迟，执行硬性费用上限时另核服务侧配额和限额能力。
