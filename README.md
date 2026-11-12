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

## 获取查询凭据

先安装 [Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install)。登录账号需要拥有上面的 BigQuery 数据读取和查询权限。以下两种登录方式任选一种，设置文件的 auth 字段须与所选方式对应。

### 使用 gcloud 用户登录

运行以下命令，在浏览器中选择有查询权限的 Google 账号并完成授权。

```sh
gcloud auth login
gcloud auth list
```

在 settings.local.json 中设置 "auth": "user"。脚本每次执行时向 gcloud 获取短期 access token，再调用 BigQuery。

### 使用 Application Default Credentials（ADC）

运行以下命令并完成浏览器授权。在授权页面允许访问 Google Cloud 的权限。

```sh
gcloud auth application-default login --scopes=https://www.googleapis.com/auth/cloud-platform,openid,https://www.googleapis.com/auth/userinfo.email
```

在 settings.local.json 中设置 "auth": "adc"。gcloud 会将 ADC 保存在本机配置目录，脚本通过 gcloud 换取短期 access token。若组织要求设置配额项目，可按其权限配置执行以下命令，替换项目占位值。

```sh
gcloud auth application-default set-quota-project YOUR_QUERY_PROJECT
```

命令运行主机没有可用浏览器时，可在登录命令后加 --no-launch-browser，按终端给出的链接完成登录，再在终端回填授权码。授权链接和授权码仅用于本次登录。

ADC 包含可换取 access token 的 refresh token，按私密文件管理。gcloud 用户登录和 ADC 分别保存身份，切换 gcloud 用户后应核对所选认证方式的身份。具体行为见 [Google 官方 ADC 设置说明](https://docs.cloud.google.com/docs/authentication/set-up-adc-local-dev-environment)。

### 使用独立认证目录

可以把认证资料放在仓库外的独立目录。以下示例使用 ADC。

```sh
export CLOUDSDK_CONFIG="$HOME/.config/cloud-billing-monitor"
mkdir -p "$CLOUDSDK_CONFIG"
chmod 700 "$CLOUDSDK_CONFIG"
gcloud auth application-default login --scopes=https://www.googleapis.com/auth/cloud-platform,openid,https://www.googleapis.com/auth/userinfo.email
```

在本地设置文件中加入 "gcloud_config_dir": "~/.config/cloud-billing-monitor"，并设置 "auth": "adc"。定时任务也会使用这个目录里的认证配置。

结束使用时，可以在相同 CLOUDSDK_CONFIG 环境下撤销所选认证。

```sh
# 撤销 ADC
gcloud auth application-default revoke
# 撤销 gcloud 用户登录
gcloud auth revoke
```

OAuth 凭据、refresh token、access token、授权码、服务账号密钥和本地认证目录均应保存在使用者自己的环境中。公开仓库只提供虚构配置示例。

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
