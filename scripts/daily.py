#!/usr/bin/env python3
"""Report daily estimates from a Vertex runner's local spend ledger."""

import argparse
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
import shlex
import subprocess
import sys

def amount(mapping, key):
    value = mapping.get(key)
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("invalid amount in Vertex ledger")
    return value


def read_report(root, day):
    config = {}
    for line in (root / "vertex.env").read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip().startswith(("VERTEX_PROJECT", "VERTEX_TOTAL_BUDGET_USD")):
            config[key.strip()] = value.strip()
    ledger = json.loads((root / "runners/state/vertex-spend.json").read_text())
    accounts = ledger["accounts"]
    rows = []
    configured = set()
    for slot in range(1, 10):
        suffix = "" if slot == 1 else f"_{slot}"
        project = config.get("VERTEX_PROJECT" + suffix)
        if not project:
            continue
        configured.add(project)
        entry = accounts.get(project, {})
        daily = amount(entry.get("days", {}), day)
        used = amount(entry, "total_usd")
        limit = float(config.get("VERTEX_TOTAL_BUDGET_USD" + suffix, 0) or 0)
        if not math.isfinite(limit) or limit < 0:
            raise ValueError("invalid total limit in Vertex configuration")
        remaining = round(max(0, limit - (used or 0)), 6) if limit else None
        rows.append({
            "slot": slot, "day_usd": daily, "used_usd": used,
            "limit_usd": limit or None, "remaining_usd": remaining,
        })
    if not rows:
        raise ValueError("no configured Vertex accounts")
    return {
        "date": day,
        "daily_usd": amount(ledger["days"], day),
        "other_configs_usd": round(sum(
            amount(entry.get("days", {}), day) or 0
            for project, entry in accounts.items() if project not in configured
        ), 6),
        "configs": rows,
    }


def dollars(value, missing="无记账记录"):
    return missing if value is None else f"${value:,.4f}"


def print_report(report):
    print(f"Vertex 花费日报 · {report['date']} · 运行主机账本日")
    print(f"当日已记账合计：{dollars(report['daily_usd'])}")
    for row in report["configs"]:
        budget = dollars(row["remaining_usd"], "未设上限")
        used = dollars(row["used_usd"])
        print(f"配置 {row['slot']}：{dollars(row['day_usd'])}｜累计 {used}｜本地总预算余额 {budget}")
    if report["other_configs_usd"]:
        print(f"合计含已移除配置：{dollars(report['other_configs_usd'])}")
    print("金额为本地估算，Google 账单及赠金抵扣需另核。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, help="ledger date, default yesterday on the runner host")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--root", default="~/.agy-cli-manager", help="runner data directory on the target host")
    parser.add_argument("--ssh-target", help="SSH config alias or user@host for the runner host")
    args = parser.parse_args()

    if args.ssh_target:
        if args.ssh_target.startswith("-") or any(c.isspace() for c in args.ssh_target):
            parser.error("invalid SSH target")
        script = Path(__file__).resolve()
        flags = ["--root", args.root]
        if args.date:
            flags.extend(("--date", args.date.isoformat()))
        if args.json:
            flags.append("--json")
        source = script.read_text()
        remote_command = f"python3 - {shlex.join(flags)}"
        try:
            return subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", args.ssh_target, remote_command],
                input=source, text=True, timeout=45,
            ).returncode
        except (OSError, subprocess.TimeoutExpired):
            print("Vertex 花费未知，SSH 查询失败。", file=sys.stderr)
            return 1

    today = datetime.now().astimezone().date()
    day = args.date or today - timedelta(days=1)
    if day > today:
        parser.error("date cannot be later than the runner host's ledger date")
    try:
        report = read_report(Path(args.root).expanduser(), day.isoformat())
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
        print(f"Vertex 花费未知，无法读取账本或配置（{type(error).__name__}）。", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
