#!/usr/bin/env python3
"""Query official Google Cloud Billing exports in BigQuery."""

import argparse
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

API = "https://bigquery.googleapis.com/bigquery/v2"
MONEY = ("cost", "credits", "promotional_credits", "net")


def read_settings(path):
    settings = json.loads(path.read_text())
    project = settings["query_project"]
    table = settings["billing_table"]
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", project):
        raise ValueError("invalid query_project")
    if not re.fullmatch(r"[a-z][a-z0-9-]*\.[A-Za-z0-9_]+\.[A-Za-z0-9_-]+", table):
        raise ValueError("invalid billing_table")
    ZoneInfo(settings.get("timezone", "Asia/Taipei"))
    limit = settings.get("maximum_bytes_billed", 1_000_000_000)
    if type(limit) is not int or limit <= 0:
        raise ValueError("maximum_bytes_billed must be a positive integer")
    if settings.get("auth", "user") not in ("user", "adc"):
        raise ValueError("auth must be user or adc")
    return settings


def access_token(settings):
    command = ["gcloud", "auth"]
    if settings.get("auth") == "adc":
        command.append("application-default")
    command.append("print-access-token")
    environment = os.environ.copy()
    if settings.get("gcloud_config_dir"):
        environment["CLOUDSDK_CONFIG"] = str(Path(settings["gcloud_config_dir"]).expanduser())
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, env=environment)
    if result.returncode or not result.stdout.strip():
        raise RuntimeError("gcloud authentication failed; verify the selected local identity")
    return result.stdout.strip()


def request(token, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = Request(API + path, data=data, headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
    })
    try:
        with urlopen(req, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        # Keep returned messages and authentication headers out of reports.
        if error.code == 404:
            raise RuntimeError("Official billing table is unavailable; verify export startup, table name and location") from None
        raise RuntimeError(f"BigQuery HTTP {error.code}; check export, IAM and query limits") from None


def query_body(settings, day, dry_run=False):
    table = settings["billing_table"]
    # Sum credits within each record before grouping, preserving each cost once.
    query = f"""
SELECT
  CAST(DATE(usage_start_time, @timezone) AS STRING) AS day,
  currency,
  COALESCE(project.id, '(billing-account)') AS project,
  service.description AS service,
  CAST(SUM(CAST(cost AS NUMERIC)) AS STRING) AS cost,
  CAST(SUM(IFNULL((SELECT SUM(CAST(c.amount AS NUMERIC))
    FROM UNNEST(credits) c), 0)) AS STRING) AS credits,
  CAST(SUM(IFNULL((SELECT SUM(CAST(c.amount AS NUMERIC))
    FROM UNNEST(credits) c WHERE c.type = 'PROMOTION'), 0)) AS STRING) AS promotional_credits,
  CAST(MAX(export_time) AS STRING) AS latest_export_time
FROM `{table}`
WHERE usage_start_time >= TIMESTAMP(@start, @timezone)
  AND usage_start_time < TIMESTAMP(@end, @timezone)
GROUP BY day, currency, project, service
ORDER BY day, currency, project, service
"""
    values = [
        ("start", "DATE", day.replace(day=1).isoformat()),
        ("end", "DATE", (day + timedelta(days=1)).isoformat()),
        ("timezone", "STRING", settings.get("timezone", "Asia/Taipei")),
    ]
    body = {
        "query": query, "useLegacySql": False, "timeoutMs": 10000,
        "maximumBytesBilled": str(settings.get("maximum_bytes_billed", 1_000_000_000)),
        "parameterMode": "NAMED",
        "queryParameters": [
            {"name": name, "parameterType": {"type": kind}, "parameterValue": {"value": value}}
            for name, kind, value in values
        ],
    }
    if settings.get("location"):
        body["location"] = settings["location"]
    if dry_run:
        body["dryRun"] = True
    return body


def run_query(settings, day, token, dry_run=False):
    project = quote(settings["query_project"], safe="")
    response = request(token, f"/projects/{project}/queries", query_body(settings, day, dry_run))
    if dry_run:
        if response.get("errors"):
            raise RuntimeError("BigQuery dry run returned errors")
        return {"dry_run": True, "bytes_processed": response.get("totalBytesProcessed")}
    reference = response.get("jobReference", {})
    job = reference.get("jobId")
    location = reference.get("location", settings.get("location"))
    endpoint = f"/projects/{project}/queries/{quote(job, safe='')}" if job else None
    deadline = time.monotonic() + 90
    pages, schema = [], None
    while True:
        if response.get("errors"):
            raise RuntimeError("BigQuery job returned errors; inspect it with local credentials")
        if response.get("jobComplete"):
            schema = response.get("schema", schema)
            pages.extend(response.get("rows", []))
            page = response.get("pageToken")
            if not page:
                break
            params = {"pageToken": page, "maxResults": 10000}
        else:
            params = {"timeoutMs": 10000, "maxResults": 10000}
        if not endpoint or time.monotonic() >= deadline:
            raise RuntimeError("BigQuery query incomplete; official spend is unknown")
        if location:
            params["location"] = location
        response = request(token, endpoint + "?" + urlencode(params))
    fields = [field["name"] for field in (schema or {}).get("fields", [])]
    return [dict(zip(fields, [cell["v"] for cell in row["f"]])) for row in pages]


def totals(rows):
    result = {}
    for row in rows:
        currency = row["currency"]
        sums = result.setdefault(currency, {name: Decimal(0) for name in MONEY})
        for name in MONEY[:3]:
            sums[name] += Decimal(row[name])
        sums["net"] = sums["cost"] + sums["credits"]
    return {currency: {key: str(value) for key, value in values.items()}
            for currency, values in result.items()}


def report(rows, settings, day):
    daily = [row for row in rows if row["day"] == day.isoformat()]
    return {
        "source": "Google Cloud Billing BigQuery export",
        "date": day.isoformat(),
        "timezone": settings.get("timezone", "Asia/Taipei"),
        "month_through_date": totals(rows),
        "daily": totals(daily),
        "daily_status": "recorded" if daily else "no_exported_records",
        "latest_export_time_in_period": max(
            (row["latest_export_time"] for row in rows if row.get("latest_export_time")), default=None),
        "daily_details": daily,
    }


def print_report(result):
    print(f"Google 官方账单日报 · {result['date']} · {result['timezone']}")
    for title, key in (("当日已入账", "daily"), ("本月截至该日已入账", "month_through_date")):
        if not result[key]:
            print(f"{title}：未知，导出中无对应记录")
        for currency, values in result[key].items():
            print(f"{title} [{currency}] 费用 {values['cost']}，全部抵扣 {values['credits']}，"
                  f"其中促销赠金 {values['promotional_credits']}，净费用 {values['net']}")
    print(f"所查记录最近导出时间：{result['latest_export_time_in_period'] or '未知'}")
    print("官方账单导出可能滞后，后续入账及调整会改变结果。净费用为费用加抵扣。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, required=True, help="local JSON settings file")
    parser.add_argument("--date", type=date.fromisoformat, help="usage date, default yesterday")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="validate query without executing it")
    args = parser.parse_args()
    try:
        settings = read_settings(args.settings)
        today = datetime.now(ZoneInfo(settings.get("timezone", "Asia/Taipei"))).date()
        day = args.date or today - timedelta(days=1)
        if day > today:
            raise ValueError("date is in the future")
        data = run_query(settings, day, access_token(settings), args.dry_run)
        result = data if args.dry_run else report(data, settings, day)
        if args.json or args.dry_run:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print_report(result)
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, InvalidOperation,
            URLError, subprocess.SubprocessError) as error:
        # Error type alone avoids exposing identity, table paths or token output.
        print(f"官方花费未知（{type(error).__name__}）。核对账单导出、IAM、gcloud 登录和查询上限。", file=sys.stderr)
        if isinstance(error, RuntimeError):
            print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
