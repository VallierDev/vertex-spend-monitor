import importlib.util
import json
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/daily.py"
spec = importlib.util.spec_from_file_location("daily", SCRIPT)
daily = importlib.util.module_from_spec(spec)
spec.loader.exec_module(daily)


class OfficialBillingTests(unittest.TestCase):
    def setUp(self):
        self.settings = daily.read_settings(SCRIPT.parents[1] / "settings.example.json")
        self.day = date(2026, 1, 15)

    def row(self, day="2026-01-15", currency="USD", cost="1.25", credit="-1"):
        return {
            "day": day, "currency": currency, "project": "example-project",
            "service": "Vertex AI", "cost": cost, "credits": credit,
            "promotional_credits": credit, "latest_export_time": "2026-01-16 01:00:00 UTC",
        }

    def test_decimal_credits_and_currency_isolation(self):
        result = daily.report([
            self.row(cost="0.1", credit="-0.1"),
            self.row(cost="0.2", credit="0"),
            self.row(currency="EUR", cost="5", credit="-2"),
        ], self.settings, self.day)
        self.assertEqual(result["daily"]["USD"]["cost"], "0.3")
        self.assertEqual(result["daily"]["USD"]["net"], "0.2")
        self.assertEqual(result["daily"]["EUR"]["net"], "3")

    def test_unknown_day_keeps_month_amount(self):
        result = daily.report([self.row(day="2026-01-14")], self.settings, self.day)
        self.assertEqual(result["daily_status"], "no_exported_records")
        self.assertEqual(result["daily"], {})
        self.assertEqual(result["month_through_date"]["USD"]["cost"], "1.25")

    def test_empty_export_remains_unknown(self):
        result = daily.report([], self.settings, self.day)
        self.assertEqual(result["daily"], {})
        self.assertEqual(result["month_through_date"], {})
        self.assertIsNone(result["latest_export_time_in_period"])

    def test_query_bounds_and_no_credit_cross_join(self):
        query = daily.query_body(self.settings, self.day)
        parameters = {p["name"]: p["parameterValue"]["value"] for p in query["queryParameters"]}
        self.assertEqual(parameters["start"], "2026-01-01")
        self.assertEqual(parameters["end"], "2026-01-16")
        self.assertEqual(query["maximumBytesBilled"], "1000000000")
        self.assertIn("SELECT SUM(CAST(c.amount AS NUMERIC))", query["query"])
        self.assertNotIn("CROSS JOIN", query["query"])
        self.assertNotIn("token", json.dumps(query))

    def test_job_poll_and_pagination_keep_same_job(self):
        row = self.row()
        schema = {"fields": [{"name": key} for key in row]}
        encoded = {"f": [{"v": value} for value in row.values()]}
        responses = [
            {"jobComplete": False, "jobReference": {"jobId": "example-job", "location": "US"}},
            {"jobComplete": True, "schema": schema, "rows": [encoded], "pageToken": "next"},
            {"jobComplete": True, "rows": [encoded]},
        ]
        with patch.object(daily, "request", side_effect=responses) as api:
            result = daily.run_query(self.settings, self.day, "test-placeholder")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1], row)
        self.assertIn("/queries/example-job?", api.call_args_list[1].args[1])
        self.assertIn("pageToken=next", api.call_args_list[2].args[1])

    def test_job_error_is_unknown(self):
        with patch.object(daily, "request", return_value={"jobComplete": True, "errors": [{}]}):
            with self.assertRaises(RuntimeError):
                daily.run_query(self.settings, self.day, "test-placeholder")

    def test_dry_run(self):
        with patch.object(daily, "request", return_value={"totalBytesProcessed": "1234"}) as api:
            result = daily.run_query(self.settings, self.day, "test-placeholder", dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertTrue(api.call_args.args[2]["dryRun"])

    def test_isolated_auth_directory(self):
        settings = dict(self.settings, auth="adc", gcloud_config_dir="~/example-auth")
        with patch.object(daily.subprocess, "run") as process:
            process.return_value.returncode = 0
            process.return_value.stdout = "test-placeholder\n"
            self.assertEqual(daily.access_token(settings), "test-placeholder")
        self.assertEqual(process.call_args.kwargs["env"]["CLOUDSDK_CONFIG"],
                         str(Path.home() / "example-auth"))
        self.assertIn("application-default", process.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
