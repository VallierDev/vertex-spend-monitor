# Google Cloud Official Spend Monitor

一个 Skill，用于查询 Google Cloud 官方已入账费用和赠金抵扣，并按需交给调度器生成每日报告。支持 Google Cloud Billing 标准和详细使用费 BigQuery 导出。

## 数据与金额

查询源为 Google Cloud 写入 BigQuery 的 Cloud Billing 记录。报告包含每日费用和本月截至指定日期的累计金额，每种账单币种分别汇总。

| 字段 | 含义 |
| --- | --- |
| cost | 官方记录中的费用 |
| credits | 全部抵扣，通常为负数 |
| promotional_credits | 全部抵扣中 PROMOTION 类型的赠金抵扣 |
| net | cost + credits |
| latest_export_time_in_period | 所查记录最近一次导出时间 |

查询按配置时区的 usage_start_time 汇总，月计覆盖当月第一天至所查日期。后续调整可能影响历史日期。账期发票还需要按 invoice.month 及对应费用类型核对。

导出覆盖整个结算账号，包含所有服务及项目。daily_details 提供所查日期按项目、服务和币种分组的官方金额。预算监控应结合整个账号的费用。

金额均来自官方已入账数据。赠金剩余余额需要单独从官方赠金页核对。预算本身和实际扣款还须结合对应预算设置、付款及发票状态确认。

## 前置配置

1. 在 Cloud Billing → 账单导出，启用标准使用费用或详细使用费导出，选择 BigQuery 数据集。
2. 等待 Google 创建导出表并写入数据。初次启用的历史回填范围取决于数据集位置等条件，之后的数据会持续更新。
3. 给查询身份相应的数据读取和查询权限，例如数据集上的 BigQuery Data Viewer、查询项目的 BigQuery Job User。查询项目需要启用 BigQuery API。
4. 在运行主机安装 Python 3.10+ 和 gcloud，使用本人或组织指定的查询身份登录。
5. 将 settings.example.json 复制为 settings.local.json，替换查询项目、真实导出表、数据集位置和时区。

脚本使用 Python 标准库。auth=user 使用 gcloud auth print-access-token，auth=adc 使用 gcloud auth application-default print-access-token。gcloud 配置、OAuth 文件和本地设置由使用者自行保管。

需要使用独立登录目录时，在本地设置中加入 gcloud_config_dir，填写对应的 gcloud 配置目录。脚本仅对子进程设置 CLOUDSDK_CONFIG，查询身份按该目录中的登录配置选择。

maximum_bytes_billed 为单次查询的扫描计费上限，默认 1 GB。BigQuery 查询可能产生费用，超过上限的查询失败。根据表规模配置相应上限。

官方说明见 [启用账单导出](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-setup)、[导出表结构](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage) 和 [费用与抵扣查询示例](https://docs.cloud.google.com/billing/docs/how-to/bq-examples)。

## 安装与使用

将仓库安装到支持 SKILL.md 的客户端技能目录，例如 ~/.codex/skills/vertex-spend-monitor。命令在安装目录中执行。

```sh
cp settings.example.json settings.local.json
# 编辑 settings.local.json，填写自己的项目与官方导出表
python3 scripts/daily.py --settings settings.local.json --dry-run
python3 scripts/daily.py --settings settings.local.json
python3 scripts/daily.py --settings settings.local.json --date 2026-01-15 --json
```

默认查询指定时区的昨天。查询先提交一次作业，再读取同一作业的结果，包括分页。认证、导出或查询失败时返回非零退出码并报告未知。当天无记录时保留无记录状态。

## 每日监控

Skill 和脚本可交给 Codex 自动化、cron 或其他调度器。由使用者选择报告时间、时区和发送渠道。

以下 cron 示例在调度主机时间每天 10:00 查询所配时区的昨天，并保存报告。路径替换为实际安装路径。调度主机必须可执行 gcloud 且已有认证。

```cron
0 10 * * * /usr/bin/python3 /path/to/vertex-spend-monitor/scripts/daily.py --settings /path/to/settings.local.json > /path/to/cloud-billing-daily.txt 2>&1
```

调度提示词示例。

> 运行 vertex-spend-monitor 的 scripts/daily.py --settings settings.local.json，报告 Google Cloud 官方已入账的每日费用、全部抵扣、其中促销赠金和净费用，以及本月截至该日的累计金额。保留币种、时区、导出时间。读取失败或无数据时报告未知及原因，检查是否有超出预算的已入账费用。

Cloud Billing 数据可能延迟。每日已入账金额会随新数据及调整变化。Google Cloud Budget 告警通常也有延迟，硬性费用上限需要另核具体服务的控制能力。

## 发布与凭据

所有示例项目及表名均为虚构占位值。本地设置和认证文件留在使用者机器，.gitignore 覆盖常见本地配置、凭据及报告。发布前检查提交内容及 Git 历史。

本版已改用官方账单导出接口。金额聚合、分页与失败处理通过离线测试。真实查询依赖使用者启用导出并配置授权，尚未在本仓库绑定任何真实账单表。
