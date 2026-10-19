import contextlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import discover_jobs as jobs


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        Path("tmp").mkdir(exist_ok=True)
        key = patch.object(jobs, "theirstack_key", return_value="")
        key.start()
        self.addCleanup(key.stop)

    def test_duplicate_links_and_role_fallback(self):
        tracker = [{"company": "Acme, Inc.", "title": "Software Engineer Intern",
                    "application_url": "https://acme.com/careers?gh_jid=123"}]
        candidates = [
            {"company": "Acme Inc", "title": "SWE Intern", "url": "https://job-boards.greenhouse.io/acme/jobs/123?gh_src=a"},
            {"company": "Acme Inc", "title": "Software Engineering Internship - Summer 2027", "url": "https://example.com/456"},
            {"company": "Acme Inc", "title": "ML Intern", "url": "https://jobs.ashbyhq.com/acme/789/application?utm_source=test"},
            {"company": "Acme Inc", "title": "ML Intern", "url": "https://jobs.ashbyhq.com/acme/789/"},
        ]
        self.assertEqual(jobs.exclude_duplicates(candidates, tracker), [candidates[2]])
        self.assertNotEqual(jobs.url_key("https://example.com/jobs?id=1"), jobs.url_key("https://example.com/jobs?id=2"))
        self.assertEqual(jobs.greenhouse_link("https://boards.greenhouse.io/embed/job_app?for=acme&token=123"), ("acme", "123"))
        applied = [{"company": "Rivet", "title": "Intern, Software Engineering (Summer 2027)",
                    "application_url": "https://jobs.ashbyhq.com/rivet/789"}]
        renamed = [{"company": "Rivet Industries", "title": "Software Engineer Intern",
                    "url": "https://jobs.ashbyhq.com/rivet/789/application?embed=true"}]
        self.assertEqual(jobs.exclude_duplicates(renamed, applied), [])
        older = [{"company": "Acme", "title": "Software Intern Summer 2026"}]
        current = [{"company": "Acme", "title": "Software Intern Summer 2027", "url": "https://example.com/current"}]
        self.assertEqual(jobs.exclude_duplicates(current, older), current)
        tracked_source = [{"company": "Old name", "title": "Different title",
                           "reference_url": "https://example.com/source"}]
        from_search = [{"company": "Acme", "title": "Software Intern", "url": "https://acme.com/careers/1",
                        "reference_url": "https://example.com/source?utm_campaign=test"}]
        self.assertEqual(jobs.exclude_duplicates(from_search, tracked_source), [])
        employer = {key: value for key, value in from_search[0].items() if key != "reference_url"}
        self.assertEqual(jobs.exclude_duplicates([employer, *from_search], tracked_source), [])

    def test_term_activity_and_visibility(self):
        base = {"company_name": "Acme", "title": "Software Intern", "url": "https://example.com/job", "active": True}
        rows = [base, {**base, "active": False}, {**base, "is_visible": False},
                {**base, "terms": ["Summer 2026"]}, {**base, "terms": ["Winter 2027"]},
                {**base, "terms": ["Summer 2027"]}, {**base, "title": "Software Engineer 1"}]
        self.assertEqual(len(jobs.simplify_jobs(rows, 2027)), 2)
        self.assertFalse(jobs.target_term([], "Software Intern Summer '26", 2027))

    def test_cli_uses_the_requested_year_feed(self):
        with tempfile.TemporaryDirectory(dir="tmp") as directory:
            tracker = Path(directory) / "tracker.json"
            tracker.write_text("[]")
            with patch("sys.argv", ["discover_jobs.py", "--tracker", str(tracker), "--year", "2028", "--theirstack-limit", "0"]), \
                    patch.object(jobs, "fetch", return_value=[]) as fetch, \
                    contextlib.redirect_stdout(io.StringIO()):
                jobs.main()
            fetch.assert_called_once_with(jobs.SIMPLIFY.format(year=2028))

    def test_greenhouse_uses_publication_not_update(self):
        board = {"jobs": [{"id": 123, "title": "Software Intern Summer 2027",
                           "absolute_url": "https://example.com/job", "updated_at": "2026-10-05T00:00:00Z"}]}
        with patch.object(jobs, "fetch", side_effect=[board, {"first_published": "2026-01-01T01:00:00+01:00"}]):
            found, errors = jobs.greenhouse_jobs("acme", "Acme", 2027)
        self.assertEqual(errors, [])
        self.assertEqual(found[0]["posted"], jobs.timestamp("2026-01-01T00:00:00Z"))
        with patch.object(jobs, "fetch", side_effect=[board, OSError("unavailable")]):
            found, errors = jobs.greenhouse_jobs("acme", "Acme", 2027)
        self.assertEqual(found[0]["posted"], 0)
        self.assertTrue(errors)

    def test_ashby_filters_and_preserves_live_details(self):
        self.assertEqual(jobs.ashby_board("https://jobs.ashbyhq.com/Acme%20Inc/id/application"), "Acme Inc")
        self.assertIsNone(jobs.ashby_board("https://example.com/acme/id"))
        base = {"title": "Software Intern Summer 2027", "isListed": True,
                "jobUrl": "https://jobs.ashbyhq.com/acme/123", "location": "Seattle",
                "publishedAt": "2026-10-07T00:00:00Z", "descriptionPlain": "Undergraduate internship",
                "compensation": {"scrapeableCompensationSalarySummary": "$40/hr"},
                "secondaryLocations": [{"location": "Austin"}], "workplaceType": "Hybrid"}
        rows = [base, {**base, "isListed": False}, {**base, "title": "Software Intern Summer 2026"},
                {**base, "title": "Software Intern Winter 2027"},
                {**base, "title": "Software Engineer", "employmentType": "FullTime"},
                {**base, "title": "Sales Intern Summer 2027"},
                {**base, "title": "Engineering Intern Summer 2027", "department": "Software"},
                {**base, "title": "Software Engineer", "employmentType": "Intern"}]
        with patch.object(jobs, "fetch", return_value={"jobs": rows}) as fetch:
            found, errors = jobs.ashby_jobs("Acme Inc", "Acme", 2027)
        fetch.assert_called_once_with(jobs.ASHBY + "/Acme%20Inc?includeCompensation=true")
        self.assertEqual(errors, [])
        self.assertEqual(len(found), 3)
        self.assertEqual(found[0]["locations"], ["Seattle", "Austin"])
        self.assertEqual(found[0]["description"], base["descriptionPlain"])
        self.assertEqual(found[0]["compensation"], base["compensation"])
        self.assertEqual(found[0]["last_published_at"], base["publishedAt"])
        self.assertEqual(found[0]["posted"], 0)
        with patch.object(jobs, "fetch", side_effect=OSError("unavailable")):
            found, errors = jobs.ashby_jobs("acme", "Acme", 2027)
        self.assertEqual(found, [])
        self.assertEqual(len(errors), 1)

    def test_greenhouse_preloads_questions_and_rejects_stale_season(self):
        board = {"jobs": [{"id": 123, "title": "Software Intern", "absolute_url": "https://example.com/job", "location": {"name": "Remote"}}]}
        questions = [{"label": "Graduation year", "required": True, "fields": [{"values": [{"label": "2028", "value": 1}]}]}]
        detail = {"title": "Software Intern Summer 2027", "location": {"name": "London"},
                  "content": "&amp;lt;p&amp;gt;UK work authorization required&amp;lt;/p&amp;gt;",
                  "questions": questions, "pay_input_ranges": [{"min_cents": 5000}]}
        with patch.object(jobs, "fetch", side_effect=[board, detail]) as fetch:
            found, errors = jobs.greenhouse_jobs("acme", "Acme", 2027)
        self.assertEqual(fetch.call_args.args[0], jobs.GREENHOUSE + "/acme/jobs/123?questions=true&pay_transparency=true")
        self.assertEqual(errors, [])
        self.assertEqual(found[0]["title"], detail["title"])
        self.assertEqual(found[0]["locations"], ["London"])
        self.assertEqual(found[0]["description"], "UK work authorization required")
        self.assertEqual(found[0]["questions"], questions)
        self.assertEqual(found[0]["compensation"], detail["pay_input_ranges"])
        with patch.object(jobs, "fetch", side_effect=[board, {**detail, "title": "Software Intern Fall 2026"}]):
            self.assertEqual(jobs.greenhouse_jobs("acme", "Acme", 2027), ([], []))

    def test_cli_rejects_bad_tracker_before_polling(self):
        Path("tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir="tmp") as directory:
            tracker = Path(directory) / "tracker.json"
            tracker.write_text('{"has_more": true, "results": []}')
            with patch("sys.argv", ["discover_jobs.py", "--tracker", str(tracker)]), patch.object(jobs, "fetch") as fetch, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    jobs.main()
            self.assertEqual(error.exception.code, 1)
            fetch.assert_not_called()

    def test_cli_sorts_recent_old_unknown_and_reports_failures(self):
        now = datetime.now(timezone.utc).timestamp()
        base = {"company_name": "Acme", "title": "Software Intern", "active": True, "terms": ["Summer 2027"]}
        feed = [{**base, "url": "https://example.com/old", "date_posted": now - 1000000},
                {**base, "url": "https://example.com/new", "date_posted": now - 3600},
                {**base, "url": "https://job-boards.greenhouse.io/acme/jobs/123"}]
        with tempfile.TemporaryDirectory(dir="tmp") as directory:
            tracker = Path(directory) / "tracker.json"
            tracker.write_text("[]")
            output = io.StringIO()
            with patch("sys.argv", ["discover_jobs.py", "--tracker", str(tracker)]), patch.object(jobs, "fetch", side_effect=[feed, OSError("unavailable")]), contextlib.redirect_stdout(output):
                jobs.main()
        result = json.loads(output.getvalue())
        self.assertEqual([row["fresh"] for row in result["jobs"]], [True, False, False])
        self.assertIsNone(result["jobs"][-1]["posted_at"])
        self.assertTrue(result["warnings"])


class TheirStackTests(unittest.TestCase):
    def setUp(self):
        Path("tmp").mkdir(exist_ok=True)
        directory = tempfile.TemporaryDirectory(dir="tmp")
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.tracker = self.directory / "tracker.json"
        self.tracker.write_text("[]")

    def posting(self, **changes):
        return {"company": "Acme", "job_title": "Software Intern Summer 2027",
                "url": "https://example.com/job/1", "final_url": "https://acme.com/careers/1",
                "source_url": "https://example.com/job/1", "date_posted": "2026-10-10",
                "date_reposted": "2026-10-13", "discovered_at": "2026-10-13T12:00:00Z",
                "locations": [{"display_name": "Seattle, WA"}], "description": "Undergraduate internship",
                "salary_string": "$30–40/hr", "min_salary": 30, "salary_period": "hour", **changes}

    def cli(self, arguments=()):
        output = io.StringIO()
        with patch("sys.argv", ["discover_jobs.py", "--tracker", str(self.tracker), *arguments]), contextlib.redirect_stdout(output):
            jobs.main()
        return json.loads(output.getvalue())

    def test_key_env_precedence_and_safe_dotenv_loading(self):
        dotenv = self.directory / ".env"
        dotenv.write_text('APPLICATION_PASSWORD=private\nexport THEIRSTACK_API_KEY = "test-key" # comment\n')
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(jobs.theirstack_key(dotenv), "test-key")
            self.assertEqual(jobs.theirstack_key(self.directory / "absent"), "")
            dotenv.write_text("THEIRSTACK_API_KEY='$(do-not-execute)'\n")
            self.assertEqual(jobs.theirstack_key(dotenv), "$(do-not-execute)")
        with patch.dict(os.environ, {"THEIRSTACK_API_KEY": "environment-key"}):
            self.assertEqual(jobs.theirstack_key(dotenv), "environment-key")
        with patch.dict(os.environ, {"THEIRSTACK_API_KEY": ""}):
            self.assertEqual(jobs.theirstack_key(dotenv), "")

    def test_post_request_authentication_and_json(self):
        response = io.StringIO('{"data": [], "metadata": {}}')
        with patch.object(jobs, "urlopen", return_value=response) as open_url:
            self.assertEqual(jobs.theirstack_search({"limit": 1}, "test-key")["data"], [])
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, jobs.THEIRSTACK)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(json.loads(request.data), {"limit": 1})

    def test_company_aliases_and_matching(self):
        names = jobs.company_names("Acme Devices (ACME)") + ["Harbor"]
        self.assertEqual(names, ["Acme Devices (ACME)", "Acme Devices", "ACME", "Harbor"])
        self.assertTrue(jobs.company_matches("HARBOR", names))
        self.assertTrue(jobs.company_matches("ACME", names))
        self.assertFalse(jobs.company_matches("Something Else", names))

    def test_search_pagination_caps_raw_rows_and_sends_company_date_filters(self):
        pages = [{"data": [self.posting(url=f"https://example.com/{i}", final_url=None) for i in range(25)]},
                 {"data": [self.posting(final_url="https://acme.com/26")]}]
        with patch.object(jobs, "theirstack_search", side_effect=pages) as search:
            found, errors = jobs.theirstack_jobs("test-key", 2027, ["Acme"], "2026-10-01", "2026-10-13", limit=26, countries=["US", "CA"])
        self.assertEqual(len(found), 26)
        self.assertEqual([call.args[0]["offset"] for call in search.call_args_list], [0, 25])
        self.assertEqual([call.args[0]["limit"] for call in search.call_args_list], [25, 1])
        self.assertTrue(all(call.args[0]["job_country_code_or"] == ["US", "CA"] for call in search.call_args_list))
        payload = search.call_args_list[0].args[0]
        self.assertEqual(payload["company_name_case_insensitive_or"], ["Acme"])
        self.assertEqual(payload["posted_at_gte"], "2026-10-01")
        self.assertEqual(payload["posted_at_lte"], "2026-10-13")
        self.assertNotIn("posted_at_max_age_days", payload)
        self.assertFalse(payload["is_closed"])
        self.assertFalse(payload["include_total_results"])
        self.assertIn("cap reached", errors[0])

    def test_search_filters_and_preserves_original_publication_and_details(self):
        rows = [self.posting(), self.posting(closed_at="2026-10-12"), self.posting(has_blurred_data=True),
                self.posting(job_title="Software Intern Summer 2026"), self.posting(job_title="Software Intern Winter 2027"),
                self.posting(job_title="Sales Intern Summer 2027"), self.posting(job_title="Software Engineer"),
                self.posting(company="Other"), self.posting(final_url=None, url=None, source_url=None)]
        with patch.object(jobs, "theirstack_search", return_value={"data": rows}) as search:
            found, errors = jobs.theirstack_jobs("test-key", 2027, ["ACME"], max_age_days=90)
        self.assertEqual(errors, [])
        self.assertEqual(len(found), 1)
        self.assertEqual(search.call_args.args[0]["posted_at_max_age_days"], 90)
        self.assertEqual(found[0]["posted"], jobs.timestamp("2026-10-10"))
        self.assertEqual(found[0]["url"], "https://acme.com/careers/1")
        self.assertEqual(found[0]["reference_url"], "https://example.com/job/1")
        self.assertEqual(found[0]["locations"], ["Seattle, WA"])
        self.assertEqual(found[0]["description"], "Undergraduate internship")
        self.assertEqual(found[0]["compensation"]["salary_string"], "$30–40/hr")
        with patch.object(jobs, "theirstack_search", return_value={"data": [self.posting(job_title="Sales Intern")]}) as search:
            found, errors = jobs.theirstack_jobs("test-key", 2027, limit=1)
        self.assertEqual(found, [])
        self.assertEqual(search.call_count, 1)
        self.assertIn("cap reached", errors[0])

    def test_failures_are_warnings_and_do_not_expose_key(self):
        for error in [HTTPError(jobs.THEIRSTACK, code, "Failure", {}, None) for code in (401, 402, 429)]:
            with self.subTest(code=error.code), patch.object(jobs, "theirstack_search", side_effect=error):
                found, errors = jobs.theirstack_jobs("test-key", 2027)
            self.assertEqual(found, [])
            self.assertEqual(errors, [f"TheirStack: HTTP {error.code}"])
        with patch.object(jobs, "theirstack_search", side_effect=OSError("Failure test-key")):
            _, errors = jobs.theirstack_jobs("test-key", 2027)
        self.assertNotIn("test-key", str(errors))
        for response in [{}, {"data": {}}, {"data": [None]}, {"data": [], "metadata": "invalid"}]:
            with self.subTest(response=response), patch.object(jobs, "theirstack_search", return_value=response):
                found, errors = jobs.theirstack_jobs("test-key", 2027)
            self.assertEqual(found, [])
            self.assertTrue(errors)
        with patch.object(jobs, "theirstack_search", side_effect=[{"data": [self.posting()] * 25}, OSError("offline")]):
            found, errors = jobs.theirstack_jobs("test-key", 2027, limit=30)
        self.assertEqual(len(found), 25)
        self.assertIn("offline", errors[0])
        with patch.object(jobs, "theirstack_search", return_value={"data": [], "metadata": {"truncated_results": 5}}):
            _, errors = jobs.theirstack_jobs("test-key", 2027)
        self.assertIn("truncated results", errors[0])

    def test_cli_default_searches_recent_and_enriches_new_boards(self):
        row = self.posting(final_url="https://job-boards.greenhouse.io/acme/jobs/123")
        board = {"jobs": [{"id": 123, "title": row["job_title"], "absolute_url": row["final_url"]}]}
        detail = {"content": "<p>Live employer description</p>", "questions": [{"label": "Graduation"}]}
        with patch.object(jobs, "theirstack_key", return_value="test-key"), \
                patch.object(jobs, "theirstack_search", return_value={"data": [row]}) as search, \
                patch.object(jobs, "fetch", side_effect=[[], board, detail]):
            result = self.cli()
        self.assertEqual(len(result["jobs"]), 1)
        self.assertEqual(result["jobs"][0]["source"], "Greenhouse")
        self.assertEqual(result["jobs"][0]["description"], "Live employer description")
        self.assertEqual(result["jobs"][0]["posted_at"], "2026-10-10T00:00:00+00:00")
        self.assertEqual(result["jobs"][0]["reference_url"], row["source_url"])
        self.assertEqual(search.call_count, 1)
        self.assertEqual(search.call_args.args[0]["posted_at_max_age_days"], 3)
        self.assertEqual(result["warnings"], [])

    def test_cli_company_date_filters_apply_to_public_results_too(self):
        feed = [{"company_name": company, "title": "Software Intern", "active": True,
                 "url": f"https://example.com/{i}", "date_posted": posted}
                for i, (company, posted) in enumerate([
                    ("Acme", "2026-10-10T23:59:59Z"), ("Other", "2026-10-10"),
                    ("Acme", "2026-10-09"), ("Acme", None), ("Acme", "2026-10-11")])]
        with patch.object(jobs, "theirstack_key", return_value="test-key"), \
                patch.object(jobs, "theirstack_search", return_value={"data": []}) as search, \
                patch.object(jobs, "fetch", return_value=feed):
            result = self.cli(["--company", "ACME", "--posted-after", "2026-10-10", "--posted-before", "2026-10-10"])
        self.assertEqual(len(result["jobs"]), 1)
        self.assertEqual(result["jobs"][0]["url"], "https://example.com/0")
        self.assertEqual(search.call_count, 1)

    def test_cli_company_scope_and_disable_switch(self):
        with patch.object(jobs, "theirstack_key", return_value="test-key"), \
                patch.object(jobs, "theirstack_search", return_value={"data": [self.posting(company="ACME")]}) as search, \
                patch.object(jobs, "fetch", return_value=[]):
            result = self.cli(["--company", "ACME"])
        self.assertEqual([row["company"] for row in result["jobs"]], ["ACME"])
        self.assertEqual(search.call_count, 1)
        self.assertEqual(search.call_args.args[0]["posted_at_max_age_days"], 90)
        with patch.object(jobs, "theirstack_key") as key, \
                patch.object(jobs, "fetch", return_value=[]):
            self.assertEqual(self.cli(["--theirstack-limit", "0"])["warnings"], [])
        key.assert_not_called()

    def test_cli_country_filter_normalizes(self):
        with patch.object(jobs, "theirstack_key", return_value="test-key"), \
                patch.object(jobs, "theirstack_search", return_value={"data": []}) as search, \
                patch.object(jobs, "fetch", return_value=[]):
            self.cli(["--theirstack-country", "us", "--theirstack-country", "US"])
        self.assertEqual(search.call_count, 1)
        self.assertTrue(all(call.args[0]["job_country_code_or"] == ["US"] for call in search.call_args_list))

    def test_cli_simplify_failure_keeps_theirstack_results(self):
        with patch.object(jobs, "theirstack_key", return_value="test-key"), \
                patch.object(jobs, "theirstack_search", return_value={"data": [self.posting()]}), \
                patch.object(jobs, "fetch", side_effect=OSError("offline")):
            result = self.cli()
        self.assertEqual(len(result["jobs"]), 1)
        self.assertIn("Simplify: offline", result["warnings"])

    def test_cli_theirstack_failure_keeps_public_results(self):
        feed = [{"company_name": "Acme", "title": "Software Intern", "active": True,
                 "url": "https://example.com/job", "date_posted": "2026-10-10"}]
        with patch.object(jobs, "theirstack_key", return_value="test-key"), \
                patch.object(jobs, "theirstack_search", side_effect=HTTPError(jobs.THEIRSTACK, 402, "No credits", {}, None)), \
                patch.object(jobs, "fetch", return_value=feed):
            result = self.cli()
        self.assertEqual(len(result["jobs"]), 1)
        self.assertEqual(result["jobs"][0]["source"], "Simplify")
        self.assertEqual(result["warnings"], ["TheirStack: HTTP 402"])

    def test_unknown_dates_stay_unknown_despite_recent_discovery_or_repost(self):
        with patch.object(jobs, "theirstack_search", return_value={"data": [self.posting(date_posted=None)]}):
            found, errors = jobs.theirstack_jobs("test-key", 2027)
        self.assertEqual(errors, [])
        self.assertEqual(found[0]["posted"], 0)
        self.assertEqual(jobs.filter_jobs(found), found)
        self.assertEqual(jobs.filter_jobs(found, posted_after=jobs.iso_date("2026-10-01")), [])

    def test_cli_rejects_invalid_arguments_before_network(self):
        for arguments in [["--theirstack-limit", "-1"], ["--company", " "], ["--posted-after", "2026-02-30"],
                          ["--posted-after", "20261010"], ["--posted-after", "2026-10-11", "--posted-before", "2026-10-10"]]:
            with self.subTest(arguments=arguments), patch.object(jobs, "fetch") as fetch, \
                    patch.object(jobs, "theirstack_search") as search, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    self.cli(arguments)
            self.assertEqual(error.exception.code, 2)
            fetch.assert_not_called()
            search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
