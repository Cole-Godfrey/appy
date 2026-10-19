# Discovery

```sh
python3 discover_jobs.py --tracker tmp/tracker.json --theirstack-limit 0
```

Public discovery uses the SimplifyJobs summer internship feed for `--year`, then enriches Greenhouse and Ashby boards found in the feed or tracker. It does not enumerate every employer board. A year's feed must exist upstream. Network access is required; failures appear in `warnings` while other sources continue.

The default year is 2027. Role matching covers software, ML/AI, data, quant, developer, security, firmware, embedded, and related technical internships. Other terms and full-time discovery need changes to the filters.

| Flag | Default | Meaning |
| --- | --- | --- |
| `--tracker PATH` | Required | Complete JSON array from Notion |
| `--year YEAR` | 2027 | Summer term and upstream feed |
| `--limit N` | 50 | Maximum output candidates; `0` returns all |
| `--company NAME` | None | Exact case-insensitive name; repeatable |
| `--career-fair` | Off | Restrict to local target company bullets, combined with `--company` |
| `--posted-after DATE` | None | Inclusive YYYY-MM-DD; excludes unknown dates |
| `--posted-before DATE` | None | Inclusive YYYY-MM-DD; excludes unknown dates |
| `--theirstack-limit N` | 50 | Billable rows per API search; `0` disables it |
| `--theirstack-country CODE` | None | Two-letter country filter for TheirStack only; repeatable |

```sh
python3 discover_jobs.py --tracker tmp/tracker.json --year 2027 \
  --company "Example Company" --theirstack-limit 0 --limit 0
```

Company aliases in parentheses are supported. Public results remain global even with `--theirstack-country US`; check location and work eligibility before applying.

## Optional TheirStack

Set `THEIRSTACK_API_KEY` in the environment or `.env`. Environment values take precedence. The key is sent only to TheirStack; API errors redact it.

```sh
python3 discover_jobs.py --tracker tmp/tracker.json \
  --theirstack-country US --theirstack-limit 25 --limit 0
```

Unrestricted discovery makes a general search over the last three days and, when your company list has entries, a second company search over 90 days. An explicit company filter uses one 90-day search. Date flags replace that lookback. A cap of 25 can therefore allow up to 50 billable rows across two searches, including rejected rows. `--limit` does not control API spending. See [TheirStack's API reference](https://theirstack.com/en/docs/api-reference/jobs/search_jobs_v1).

## Results

Output is `{ "jobs": [...], "warnings": [...] }`. Candidates have company, title, URL, locations, source, `posted_at`, and `fresh`; enriched sources may include descriptions, questions, and compensation.

Deduplication normalizes employer URLs, removes tracking parameters, and checks company/title/term as a fallback. It also compares source URLs. Review the shortlist: renamed roles and unusual URLs can still need a manual check.

`fresh` means the known publication time is within the last 72 hours. An unknown date stays eligible unless date filters are set. Ashby's last-publication timestamp does not establish original posting time; it is preserved separately. Neither a recent fetch nor an employer update makes a job fresh.
