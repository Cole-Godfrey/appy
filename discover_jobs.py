#!/usr/bin/env python3
"""Discover internships through public feeds and TheirStack; exclude a Notion MCP export."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from html import unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shlex
import sys
from urllib.error import HTTPError
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen

SIMPLIFY = "https://raw.githubusercontent.com/SimplifyJobs/Summer{year}-Internships/dev/.github/scripts/listings.json"
GREENHOUSE = "https://boards-api.greenhouse.io/v1/boards"
ASHBY = "https://api.ashbyhq.com/posting-api/job-board"
THEIRSTACK = "https://api.theirstack.com/v1/jobs/search"
ROOT = Path(__file__).resolve().parent
INTERN = re.compile(r"\b(intern(?:ship)?s?|co[ -]?op|summer (?:analyst|associate))\b", re.I)
ROLE = re.compile(r"software|machine learning|\bML\b|\bAI\b|artificial intelligence|data|quant|developer|programmer|computer|firmware|embedded|security|product", re.I)


def fetch(url):
    request = Request(url, headers={"User-Agent": "internship-discovery/1.0"})
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def theirstack_key(path=ROOT / ".env"):
    """Read only the API key, without executing or exposing other .env entries."""
    if "THEIRSTACK_API_KEY" in os.environ:
        return os.environ["THEIRSTACK_API_KEY"].strip()
    if not path.exists():
        return ""
    for line in path.read_text().splitlines():
        name, separator, value = line.strip().removeprefix("export ").partition("=")
        if separator and name.strip() == "THEIRSTACK_API_KEY":
            parts = shlex.split(value, comments=True)
            if len(parts) > 1:
                raise ValueError("Invalid THEIRSTACK_API_KEY in .env")
            return parts[0] if parts else ""
    return ""


def company_names(name):
    names = [name.strip()]
    match = re.fullmatch(r"(.+?)\s+\(([^()]+)\)", name.strip())
    if match:
        names.extend(match.groups())
    return names


def company_matches(name, companies):
    return not companies or bool({text_key(alias) for alias in company_names(name)}
                                 & {text_key(company) for company in companies})


def theirstack_search(payload, api_key):
    request = Request(THEIRSTACK, data=json.dumps(payload).encode(), headers={
        "Authorization": "Bearer " + api_key, "Content-Type": "application/json",
        "User-Agent": "internship-discovery/1.0"}, method="POST")
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def theirstack_jobs(api_key, year, companies=(), posted_after=None, posted_before=None,
                   max_age_days=3, limit=50, countries=()):
    """Cap billable rows, including rows rejected by local eligibility filters."""
    filters = {"is_closed": False, "job_title_pattern_and": [INTERN.pattern, ROLE.pattern],
               "job_title_pattern_not": [r"\b(winter|spring|fall|autumn)\b"],
               "include_total_results": False}
    if companies:
        filters["company_name_case_insensitive_or"] = list(companies)
    if countries:
        filters["job_country_code_or"] = list(countries)
    if posted_after:
        filters["posted_at_gte"] = posted_after
    if posted_before:
        filters["posted_at_lte"] = posted_before
    if not posted_after and not posted_before:
        filters["posted_at_max_age_days"] = max_age_days
    jobs, errors, offset = [], [], 0
    while offset < limit:
        page_size = min(25, limit - offset)
        try:
            response = theirstack_search({**filters, "offset": offset, "limit": page_size}, api_key)
            if not isinstance(response, dict) or not isinstance(response.get("data"), list):
                raise ValueError("invalid search response")
            rows = response["data"]
            if len(rows) > page_size or any(not isinstance(row, dict) for row in rows):
                raise ValueError("invalid search page")
            metadata = response.get("metadata") or {}
            if not isinstance(metadata, dict):
                raise ValueError("invalid search metadata")
        except (OSError, ValueError) as error:
            message = f"HTTP {error.code}" if isinstance(error, HTTPError) else str(error).replace(api_key, "[redacted]")
            errors.append(f"TheirStack: {message}")
            break
        for row in rows:
            title = row.get("job_title") or ""
            company = row.get("company") or (row.get("company_object") or {}).get("name")
            url = row.get("final_url") or row.get("url") or row.get("source_url")
            if not (company and url and urlsplit(url).scheme in {"http", "https"}
                    and not row.get("closed_at") and not row.get("has_blurred_data")
                    and INTERN.search(title) and ROLE.search(title) and target_term([], title, year)
                    and company_matches(company, companies)):
                continue
            locations = [location.get("display_name") or location.get("name")
                         for location in row.get("locations") or [] if isinstance(location, dict)]
            jobs.append({"company": company, "title": title, "url": url,
                         "reference_url": row.get("source_url") or row.get("url"),
                         "locations": [location for location in locations if location]
                         or [row.get("long_location") or row.get("location") or ""],
                         "posted": timestamp(row.get("date_posted")), "source": "TheirStack",
                         "description": row.get("description") or "",
                         "compensation": {key: row[key] for key in (
                             "salary_string", "min_salary", "max_salary", "salary_currency", "salary_period",
                             "min_annual_salary_usd", "max_annual_salary_usd") if row.get(key) is not None}})
        if metadata.get("truncated_results"):
            errors.append("TheirStack: API reported truncated results; narrow the filters")
        offset += len(rows)
        if len(rows) < page_size:
            break
    if limit and offset >= limit:
        errors.append(f"TheirStack: result cap reached ({limit}); narrow filters or increase --theirstack-limit")
    return jobs, errors


def description_text(content):
    class Text(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

    parser = Text()
    parser.feed(unescape(unescape(content or "")))
    return " ".join(" ".join(parser.parts).split())


def timestamp(value):
    if not value:
        return 0
    try:
        if isinstance(value, (int, float)):
            return value
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (date if date.tzinfo else date.replace(tzinfo=timezone.utc)).timestamp()
    except (TypeError, ValueError):
        return 0


def greenhouse_link(url):
    parsed = urlsplit(url or "")
    if parsed.hostname not in {"boards.greenhouse.io", "job-boards.greenhouse.io"}:
        return None
    match = re.fullmatch(r"/([^/]+)/jobs/(\d+)/?", parsed.path)
    if match:
        return match.groups()
    query = dict(parse_qsl(parsed.query))
    if query.get("for") and query.get("token", "").isdigit():
        return query["for"], query["token"]
    return None


def ashby_board(url):
    parsed = urlsplit(url or "")
    if parsed.hostname != "jobs.ashbyhq.com":
        return None
    parts = parsed.path.strip("/").split("/")
    return unquote(parts[0]) if parts[0] else None


def url_key(url):
    if not url:
        return ""
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query))
    greenhouse = greenhouse_link(url)
    job_id = greenhouse[1] if greenhouse else query.get("gh_jid")
    if job_id:
        return "greenhouse:" + job_id
    if parsed.hostname == "jobs.ashbyhq.com":
        parts = unquote(parsed.path).strip("/").split("/")
        if len(parts) >= 2:
            return "ashby:" + "/".join(parts[:2]).casefold()
    query = [(k, v) for k, v in parse_qsl(parsed.query)
             if not k.lower().startswith("utm_") and k.lower() not in {"gh_src", "source", "src", "ref", "referral"}]
    path = re.sub(r"/(apply|application)/?$", "", parsed.path).rstrip("/")
    return (parsed.hostname or "").removeprefix("www.").lower() + path + ("?" + urlencode(sorted(query)) if query else "")


def text_key(value):
    return " ".join(re.findall(r"\w+", value.casefold()))


def role_key(row, year=2027):
    years = re.findall(r"\b20\d{2}\b|['’]\d{2}\b", row["title"])
    season = int(years[0].replace("'", "20").replace("’", "20")) if years else year
    title = re.sub(r"\b(summer|20\d{2})\b|['’]\d{2}\b", "", row["title"], flags=re.I)
    title = re.sub(r"\binternships?\b", "intern", title, flags=re.I)
    title = re.sub(r"\bengineering\b", "engineer", title, flags=re.I)
    return re.sub(r"\W+", "", row["company"].casefold()), text_key(title), season


def target_term(terms, title, year):
    known = [term for term in terms if term and term != "N/A"]
    if known:
        return f"Summer {year}" in known
    years = re.findall(r"\b20\d{2}\b|['’]\d{2}\b", title)
    years = [int(value.replace("'", "20").replace("’", "20")) for value in years]
    return (not years or year in years) and not re.search(r"\b(winter|spring|fall|autumn)\b", title, re.I)


def simplify_jobs(rows, year):
    return [{"company": row["company_name"], "title": row["title"],
             "url": row["url"], "locations": row.get("locations", []),
             "posted": timestamp(row.get("date_posted")), "source": "Simplify"}
            for row in rows if row.get("active") and row.get("is_visible", True)
            and row.get("url") and target_term(row.get("terms", []), row["title"], year)
            and INTERN.search(row["title"])
            and (ROLE.search(row["title"]) or ROLE.search(row.get("category", "")))]


def greenhouse_jobs(board, company, year):
    jobs, errors = [], []
    try:
        rows = fetch(f"{GREENHOUSE}/{board}/jobs")["jobs"]
    except (OSError, ValueError, KeyError) as error:
        return [], [f"Greenhouse {board}: {error}"]
    for row in rows:
        title = row["title"]
        if not (INTERN.search(title) and ROLE.search(title) and target_term([], title, year)):
            continue
        try:
            detail = fetch(f"{GREENHOUSE}/{board}/jobs/{row['id']}?questions=true&pay_transparency=true")
        except (OSError, ValueError) as error:
            errors.append(f"Greenhouse {board}/{row['id']}: {error}")
            detail = {}
        title = detail.get("title") or title
        if not (INTERN.search(title) and ROLE.search(title) and target_term([], title, year)):
            continue
        jobs.append({"company": detail.get("company_name") or company, "title": title,
                     "url": row["absolute_url"], "locations": [detail.get("location", row.get("location", {})).get("name", "")],
                     "posted": timestamp(detail.get("first_published")), "source": "Greenhouse",
                     "description": description_text(detail.get("content")),
                     "questions": detail.get("questions", []),
                     "demographic_questions": detail.get("demographic_questions"),
                     "compliance": detail.get("compliance", []),
                     "data_compliance": detail.get("data_compliance", []),
                     "compensation": detail.get("pay_input_ranges", [])})
    return jobs, errors


def ashby_jobs(board, company, year):
    try:
        rows = fetch(f"{ASHBY}/{quote(board, safe='')}?includeCompensation=true")["jobs"]
    except (OSError, ValueError, KeyError) as error:
        return [], [f"Ashby {board}: {error}"]
    jobs = []
    for row in rows:
        title = row.get("title", "")
        role = " ".join(row.get(key) or "" for key in ("title", "department", "team"))
        url = row.get("jobUrl") or row.get("applyUrl")
        if not (url and row.get("isListed", True)
                and (INTERN.search(title) or row.get("employmentType") == "Intern")
                and ROLE.search(role) and target_term([], title, year)):
            continue
        jobs.append({"company": company, "title": title, "url": url,
                     "locations": [row.get("location", "")] + [
                         location.get("location", "") for location in row.get("secondaryLocations", [])],
                     "posted": 0, "source": "Ashby",
                     "last_published_at": row.get("publishedAt"),
                     "description": row.get("descriptionPlain", ""),
                     "compensation": row.get("compensation"),
                     "workplace_type": row.get("workplaceType")})
    return jobs, []


def exclude_duplicates(jobs, tracker, year=2027):
    urls = {url_key(row.get(field)) for row in tracker
            for field in ("application_url", "reference_url") if row.get(field)}
    roles = {role_key(row, year) for row in tracker}
    related_urls = {}
    for job in jobs:
        related_urls.setdefault(url_key(job["url"]), set()).update(
            url_key(job.get(field)) for field in ("url", "reference_url") if job.get(field))
    seen, result = set(), []
    for job in jobs:
        keys = related_urls[url_key(job["url"])]
        if not keys & urls and role_key(job, year) not in roles and not keys & seen:
            seen.update(keys)
            result.append(job)
    return result


def iso_date(value):
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("use a valid YYYY-MM-DD date")


def filter_jobs(jobs, companies=(), posted_after=None, posted_before=None):
    start = timestamp(posted_after.isoformat()) if posted_after else None
    end = timestamp(posted_before.isoformat()) + 86400 if posted_before else None
    return [job for job in jobs if company_matches(job["company"], companies)
            and (start is None or job["posted"] and job["posted"] >= start)
            and (end is None or job["posted"] and job["posted"] < end)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracker", type=Path, required=True, help="Complete MCP JSON array: company, title, application_url, reference_url")
    parser.add_argument("--year", type=int, default=2027)
    parser.add_argument("--limit", type=int, default=50, help="0 returns all candidates")
    parser.add_argument("--company", action="append", default=[], help="Exact company name, case insensitive; repeatable")
    parser.add_argument("--posted-after", type=iso_date, help="Inclusive publication date, YYYY-MM-DD; excludes unknown dates")
    parser.add_argument("--posted-before", type=iso_date, help="Inclusive publication date, YYYY-MM-DD; excludes unknown dates")
    parser.add_argument("--theirstack-limit", type=int, default=50, help="Maximum billable rows per search; 0 disables TheirStack")
    parser.add_argument("--theirstack-country", action="append", default=[], help="TheirStack job country ISO2 code; repeatable (e.g. US)")
    args = parser.parse_args()
    if args.limit < 0 or args.theirstack_limit < 0:
        parser.error("limits must be nonnegative")
    if args.posted_after and args.posted_before and args.posted_after > args.posted_before:
        parser.error("--posted-after must not follow --posted-before")
    if any(not company.strip() for company in args.company):
        parser.error("--company must not be blank")
    if any(not re.fullmatch(r"[A-Za-z]{2}", country) for country in args.theirstack_country):
        parser.error("--theirstack-country must be a two-letter ISO country code")
    countries = list(dict.fromkeys(country.upper() for country in args.theirstack_country))
    try:
        tracker = json.loads(args.tracker.read_text())
        if not isinstance(tracker, list) or any(
            not isinstance(row, dict) or not all(isinstance(row.get(key), str) and row[key].strip()
                                               for key in ("company", "title")) for row in tracker
        ) or any(row.get(field) is not None and not isinstance(row[field], str)
                 for row in tracker for field in ("application_url", "reference_url")):
            raise ValueError("tracker must be a complete array with company and title strings")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Discovery failed: {error}\n")
    errors, theirstack = [], []
    companies = list(dict.fromkeys(alias for company in args.company for alias in company_names(company)))
    try:
        listings = simplify_jobs(fetch(SIMPLIFY.format(year=args.year)), args.year)
    except (OSError, ValueError, KeyError) as error:
        listings = []
        errors.append(f"Simplify: {error}")
    if args.theirstack_limit:
        try:
            api_key = theirstack_key()
        except (OSError, ValueError):
            api_key = ""
            errors.append("TheirStack: could not read THEIRSTACK_API_KEY")
        if api_key:
            # Company searches look back further than the general recent search.
            found, failed = theirstack_jobs(
                api_key, args.year, companies,
                args.posted_after.isoformat() if args.posted_after else None,
                args.posted_before.isoformat() if args.posted_before else None,
                max_age_days=90 if companies else 3, limit=args.theirstack_limit, countries=countries)
            theirstack.extend(found)
            errors.extend(failed)
        else:
            errors.append("TheirStack: THEIRSTACK_API_KEY is missing; using public feeds")
    boards, ashby_boards = {}, {}
    for row in listings + tracker + theirstack:
        if not company_matches(row["company"], companies):
            continue
        for field in ("url", "application_url", "reference_url"):
            link = greenhouse_link(row.get(field))
            if link:
                boards[link[0]] = row["company"]
            board = ashby_board(row.get(field))
            if board:
                ashby_boards[board] = row["company"]
    jobs = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        tasks = [(greenhouse_jobs, board, company) for board, company in boards.items()]
        tasks += [(ashby_jobs, board, company) for board, company in ashby_boards.items()]
        for found, failed in pool.map(lambda item: item[0](item[1], item[2], args.year), tasks):
            jobs.extend(found)
            errors.extend(failed)
    # Prefer employer details when both feeds contain the same job.
    dates = {url_key(job["url"]): job["posted"] for job in listings + theirstack if job["posted"]}
    references = {url_key(job["url"]): job["reference_url"] for job in theirstack if job["reference_url"]}
    for job in jobs:
        job["posted"] = job["posted"] or dates.get(url_key(job["url"]), 0)
        if url_key(job["url"]) in references:
            job["reference_url"] = references[url_key(job["url"])]
    jobs = filter_jobs(jobs + theirstack + listings, companies, args.posted_after, args.posted_before)
    jobs = exclude_duplicates(jobs, tracker, args.year)
    jobs.sort(key=lambda job: job["posted"], reverse=True)
    now = datetime.now(timezone.utc).timestamp()
    for job in jobs:
        posted = job.pop("posted")
        job["fresh"] = bool(posted and 0 <= now - posted <= 72 * 3600)
        job["posted_at"] = datetime.fromtimestamp(posted, timezone.utc).isoformat() if posted else None
    json.dump({"jobs": jobs[:args.limit] if args.limit else jobs, "warnings": errors}, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
