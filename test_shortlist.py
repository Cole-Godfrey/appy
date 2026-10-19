import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import shortlist

NOW = 1_800_000_000


def row(company, title, url, hours_ago, category="Software", locations=("Remote",)):
    return {"company_name": company, "title": title, "url": url, "category": category, "active": True,
            "terms": ["Summer 2027"], "locations": list(locations), "date_posted": NOW - hours_ago * 3600}


class ShortlistTests(unittest.TestCase):
    def test_window_fields_places_and_newest_first(self):
        rows = [row("Acme", "Software Intern", "https://example.com/1", 5),
                row("Acme", "Data Science Intern", "https://example.com/2", 2, "AI/ML/Data", ["Sunnyvale, CA"]),
                row("Bolt", "Quant Research Intern", "https://example.com/3", 30, "Quant", ["New York, NY"]),
                row("Old", "Software Intern", "https://example.com/4", 24 * 4)]
        roles, skipped = shortlist.shortlist(rows, now=NOW)
        self.assertEqual([job["url"][-1] for job in roles], ["2", "1", "3"])
        self.assertEqual(skipped, 0)
        self.assertEqual([job["field"] for job in roles], ["data", "software", "quant"])
        roles, _ = shortlist.shortlist(rows, fields=["quant", "data"], now=NOW)
        self.assertEqual(len(roles), 2)
        roles, _ = shortlist.shortlist(rows, where="NY", now=NOW)
        self.assertEqual([job["company"] for job in roles], ["Bolt"])
        self.assertEqual(len(shortlist.shortlist(rows, days=5, now=NOW)[0]), 4)

    def test_tracker_skips_applied_roles_and_feed_repeats(self):
        rows = [row("Acme", "Software Intern", "https://example.com/1?utm_source=x", 1),
                row("Acme", "Software Intern", "https://example.com/1-copy", 3),
                row("Bolt", "ML Intern", "https://example.com/2", 2, "AI/ML/Data")]
        roles, skipped = shortlist.shortlist(rows, [{"company": "", "title": "",
                                                     "application_url": "https://example.com/1"}], now=NOW)
        self.assertEqual([job["company"] for job in roles], ["Bolt"])
        self.assertEqual(skipped, 1)

    def test_tracker_accepts_json_export_or_url_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            text = Path(directory) / "applied.txt"
            text.write_text("# applied\nhttps://example.com/1\n\n")
            self.assertEqual(shortlist.read_tracker(text)[0]["application_url"], "https://example.com/1")
            export = Path(directory) / "tracker.json"
            export.write_text(json.dumps([{"company": "Acme", "title": "Intern", "application_url": None}]))
            self.assertEqual(shortlist.read_tracker(export)[0]["company"], "Acme")
            export.write_text("{}")
            with self.assertRaises(ValueError):
                shortlist.read_tracker(export)

    def test_field_names_and_aliases(self):
        self.assertEqual(shortlist.field_name("ML"), "data")
        self.assertEqual(shortlist.field_of("Data Science, AI & Machine Learning"), "data")
        self.assertEqual(shortlist.field_of("Quantitative Finance"), "quant")
        self.assertEqual(shortlist.field_of(None), "other")
        with self.assertRaises(argparse.ArgumentTypeError):
            shortlist.field_name("law")

    def run_cli(self, *args):
        output = io.StringIO()
        with patch.object(sys, "argv", ["shortlist.py", *args]), contextlib.redirect_stdout(output):
            shortlist.main()
        return output.getvalue()

    def test_sample_runs_offline(self):
        with patch.object(shortlist, "fetch", side_effect=AssertionError("network")):
            text = self.run_cli("--sample")
            data = json.loads(self.run_cli("--sample", "--json"))
        self.assertIn("2 internships posted in the last 3 days", text)
        self.assertIn("1 already applied, skipped", text)
        self.assertEqual([job["company"] for job in data["roles"]], ["Harbor Systems", "Juniper Research"])

    def test_live_feed_failure_explains_the_offline_option(self):
        error = io.StringIO()
        with patch.object(shortlist, "fetch", side_effect=OSError("offline")), \
                contextlib.redirect_stderr(error), self.assertRaises(SystemExit):
            self.run_cli()
        self.assertIn("--sample", error.getvalue())


if __name__ == "__main__":
    unittest.main()
