#!/usr/bin/env python3
"""List internships posted in the last few days, minus the ones you have already applied to."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

from discover_jobs import SIMPLIFY, exclude_duplicates, fetch, role_key, simplify_jobs

ROOT = Path(__file__).resolve().parent
FIELDS = {"software": "Software", "data": "AI and data", "quant": "Quant",
          "hardware": "Hardware", "product": "Product"}
ALIASES = {"swe": "software", "ai": "data", "ml": "data"}


def field_of(category):
    words = (category or "").casefold().replace("/", " ").split()
    first = words[0] if words else ""
    if first in {"ai", "data"}:
        return "data"
    if first.startswith("quant"):
        return "quant"
    return first if first in FIELDS else "other"


def field_name(value):
    key = ALIASES.get(value.casefold(), value.casefold())
    if key not in FIELDS:
        raise argparse.ArgumentTypeError("choose " + ", ".join(FIELDS))
    return key


def read_tracker(path):
    """A Notion export (JSON array) or a text file with one posting URL per line."""
    text = Path(path).read_text()
    try:
        rows = json.loads(text)
    except ValueError:
        return [{"company": "", "title": "", "application_url": line.strip()}
                for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("tracker JSON must be an array of rows")
    return [{"company": row.get("company") or "", "title": row.get("title") or "",
             "application_url": row.get("application_url"), "reference_url": row.get("reference_url")}
            for row in rows]


def shortlist(rows, tracker=(), year=2027, days=3, fields=(), where="", now=None):
    """Return (roles, skipped): recent roles newest first, and how many the tracker removed."""
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    categories = {row.get("url"): field_of(row.get("category")) for row in rows}
    places = [re.compile(r"\b" + re.escape(place.strip()) + r"\b", re.I) for place in where.split(",") if place.strip()]
    roles = [{**job, "field": categories.get(job["url"], "other")} for job in simplify_jobs(rows, year)
             if job["posted"] and now - job["posted"] <= days * 86400]
    roles = [job for job in roles if (not fields or job["field"] in fields)
             and (not places or any(place.search(location) for place in places for location in job["locations"]))]
    # The feed sometimes lists one role under two URLs; keep the newest.
    roles.sort(key=lambda job: job["posted"], reverse=True)
    seen, unique = set(), []
    for job in exclude_duplicates(roles, [], year):
        key = (role_key(job, year), tuple(sorted(job["locations"])))
        if key not in seen:
            seen.add(key)
            unique.append(job)
    kept = exclude_duplicates(unique, tracker, year)
    return kept, len(unique) - len(kept)


def ago(seconds):
    hours = max(0, int(seconds // 3600))
    if hours < 1:
        return "just now"
    return f"{hours}h ago" if hours < 48 else f"{hours // 24}d ago"


def report(roles, skipped, args, now, limit, style=lambda text, code: text):
    span = "today" if args.days == 1 else f"in the last {args.days} days"
    scope = ", ".join(FIELDS[key] for key in args.field) if args.field else "all technical fields"
    lines = [style(f"{len(roles)} internships posted {span}", "1"),
             f"Summer {args.year} · {scope}" + (f" · {args.where}" if args.where else ""), ""]
    if skipped:
        lines[1] += f" · {skipped} already applied, skipped"
    day = None
    for job in roles[:limit]:
        posted = datetime.fromtimestamp(job["posted"], timezone.utc).astimezone()
        label = f"{posted:%A, %b} {posted.day}"
        if label != day:
            lines += [style(label, "2"), ""]
            day = label
        place = "; ".join(job["locations"][:2]) + (f" +{len(job['locations']) - 2}" if len(job["locations"]) > 2 else "")
        lines += [f"  {style(job['company'], '1')}  {job['title']}",
                  "  " + style(f"{place or 'Location not listed'} · {ago(now - job['posted'])}", "2"),
                  "  " + job["url"], ""]
    if len(roles) > limit:
        lines.append(f"…and {len(roles) - limit} more. Add --limit 0 to see every role.\n")
    if not roles:
        lines.append("Nothing matches yet. Try a larger --days or fewer filters.\n")
    if not args.tracker:
        lines.append(style("Skip roles you've applied to: python3 shortlist.py --tracker applied.txt", "2"))
    lines.append(style("Let your agent apply with your review: docs/setup.md", "2"))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field", action="append", type=field_name, default=[],
                        help="software, data (AI/ML), quant, hardware or product; repeatable")
    parser.add_argument("--days", type=int, default=3, help="How far back to look (default 3)")
    parser.add_argument("--where", default="", help="Location text, comma-separated: \"New York, Remote\"")
    parser.add_argument("--tracker", type=Path, help="Roles to skip: a Notion JSON export or one URL per line")
    parser.add_argument("--year", type=int, default=2027, help="Summer term (default 2027)")
    parser.add_argument("--limit", type=int, default=20, help="Roles to print; 0 prints all (default 20)")
    parser.add_argument("--json", action="store_true", help="Print every matching role as JSON")
    parser.add_argument("--sample", action="store_true", help="Use the fictional listings in examples/, offline")
    args = parser.parse_args()
    if args.days < 1 or args.limit < 0:
        parser.error("--days must be at least 1 and --limit nonnegative")
    args.field = list(dict.fromkeys(args.field))
    try:
        tracker = read_tracker(args.tracker) if args.tracker else []
    except (OSError, ValueError) as error:
        parser.exit(1, f"Could not read --tracker: {error}\n")
    if args.sample:
        rows = json.loads((ROOT / "examples/listings.json").read_text())
        tracker = tracker or json.loads((ROOT / "examples/tracker.json").read_text())
        now = max(datetime.fromisoformat(row["date_posted"].replace("Z", "+00:00")).timestamp()
                  for row in rows) + 3600
    else:
        try:
            rows = fetch(SIMPLIFY.format(year=args.year))
        except (OSError, ValueError) as error:
            parser.exit(1, f"Could not reach the public internship feed: {error}\n"
                           "Check your connection, or run with --sample to try it offline.\n")
        now = datetime.now(timezone.utc).timestamp()
    roles, skipped = shortlist(rows, tracker, args.year, args.days, args.field, args.where, now)
    if args.json:
        json.dump({"generated_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                   "year": args.year, "days": args.days, "skipped": skipped, "sample": args.sample,
                   "roles": [{**{key: job[key] for key in ("company", "title", "url", "locations", "field")},
                              "posted_at": datetime.fromtimestamp(job["posted"], timezone.utc).isoformat()}
                             for job in roles]}, sys.stdout, indent=2)
        print()
        return
    color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
    style = (lambda text, code: f"\033[{code}m{text}\033[0m") if color else (lambda text, code: text)
    print(report(roles, skipped, args, now, args.limit or len(roles), style))


if __name__ == "__main__":
    main()
