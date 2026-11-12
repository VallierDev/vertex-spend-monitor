# Vertex Spend Monitor

一个可安装的 Skill，用于查询 Vertex runner 的每日估算花费、本地预算余额，并按使用者要求接入每日调度。

## 安装

需要 Python 3.10 或更新版本。将仓库下载或克隆到支持 SKILL.md 的客户端技能目录，例如 Codex 的 ~/.codex/skills/vertex-spend-monitor。脚本只使用 Python 标准库。SSH 模式还需要本机 ssh 和远端 python3。

## 数据来源

此工具读取已有 Vertex runner 的两个文件，配置由使用者自行准备。

- vertex.env，提供各配置的项目和总预算
- runners/state/vertex-spend.json，提供日花费、累计花费和项目明细

这是特定 runner 账本格式的查询器。Google 官方费用可通过 Cloud Billing 报告及 BigQuery 账单导出核对。账本可能按配置价格保守估算，赠金抵扣、现金扣款、税费及其他 GCP 资源费用需分别核实。

官方资料见 [Cloud Billing 报告](https://docs.cloud.google.com/billing/docs/reports) 和 [账单导出](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery)。

## 使用

默认数据目录为运行主机的 ~/.agy-cli-manager，默认查主机时区的昨天。查询时区应与写账本进程一致。

```sh
python3 scripts/daily.py
python3 scripts/daily.py --date 2026-01-15
python3 scripts/daily.py --root /path/to/runner-data --date 2026-01-15 --json
python3 scripts/daily.py --ssh-target runner-alias --json
```

SSH 使用已有 ~/.ssh/config 别名或 user@host，以 BatchMode 连接。私钥、端口等放在使用者的 SSH 配置中。查询代码经标准输入执行，输出只包含配置编号和金额。

### 配置格式

示例均为虚构值。

```dotenv
VERTEX_PROJECT=example-project-one
VERTEX_TOTAL_BUDGET_USD=25
VERTEX_PROJECT_2=example-project-two
VERTEX_TOTAL_BUDGET_USD_2=50
```

最多读取 9 个配置，第一个无数字后缀，第二个起使用 _2 至 _9。预算为 0 或省略时表示未设总上限。

```json
{
  "total_usd": 2.5,
  "days": {"2026-01-15": 1.25},
  "accounts": {
    "example-project-one": {
      "total_usd": 2.5,
      "days": {"2026-01-15": 1.25}
    }
  }
}
```

项目名用于在本机匹配账本，报告只显示配置编号。缺少日期记录时输出「无记账记录」。文件缺失、损坏或 SSH 失败时返回非零退出码，日报应报告金额未知。

本地总预算余额按配置上限减去账本累计用量计算。尚无项目记录时显示完整本地预算，赠金余额需另行核对。共享池明细覆盖所有使用对应配置的调用。脚本只读现有文件。

## 每日调度

Skill 和查询脚本可交给 Codex 自动化、cron 或其他调度器。安装仓库后，由使用者选择报告时间、时区和发送渠道。

以下 cron 示例每天在调度主机时间 10:00 查询昨日数据，并把报告写入本机文件。路径需要替换成实际安装路径，发送步骤由使用者的调度器完成。

```cron
0 10 * * * /usr/bin/python3 /path/to/vertex-spend-monitor/scripts/daily.py --ssh-target runner-alias > /path/to/vertex-daily.txt 2>&1
```

给 AI 调度器的提示词示例。

> 运行 vertex-spend-monitor 的 scripts/daily.py --ssh-target runner-alias，报告输出日期的 Vertex 估算总花费、各配置当日估算和本地预算余额。标明美元及账本日期。缺记录时保留无记录状态，读取失败时报告未知及错误摘要。说明 Google 官方账单与赠金抵扣需另核。

## 凭据管理

配置、账本、SSH 私钥、OAuth 文件及本地报告存放在使用者自己的运行环境。仓库内 .gitignore 覆盖常见本地配置及凭据文件。发布前还需检查实际待提交内容和 Git 历史。
