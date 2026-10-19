# Launch plan

Position Appy as an inspectable application workflow: find internships, avoid repeats, review forms, and connect replies to the right role. Lead with the offline demo. State the browser and account setup clearly.

## Before launch

- Have three people outside the project clone it and run the demo from the README. Ask each to attempt setup; fix the first point where they get stuck.
- Record a 30–45 second walkthrough using fictional profiles and a test tracker: discovery, a duplicate skipped, a reviewed form, a receipt, then a recruiting reply. Label staged scenes. Keep account tabs and real emails out of frame.
- Use `docs/assets/social-preview.png` as the GitHub social image. Keep the description and topics specific: job-search, internships, ai-agents, codex, notion, gmail, python, automation.
- Publish the initial release with working setup links and passing checks. Use issues for concrete work new contributors can reproduce.

## First month

| When | Action | What to publish |
| --- | --- | --- |
| Days 1–3 | Small pilot with peers and developer/job-search communities you already participate in | Demo link and a request for setup feedback |
| Days 4–5 | Launch on your own X and LinkedIn accounts | Short video, specific use case, repository link |
| Days 6–7 | Post to one relevant Reddit community if its rules allow project posts | Explain that you built it, show the workflow, ask one concrete question |
| Week 2 | Submit Show HN when eligible and available to answer comments | Runnable project, design tradeoffs, known setup requirements |
| Week 2 | Publish a technical article on DEV or your own blog | How complete tracker exports and Gmail cursors prevent duplicate work |
| Week 3 | Contact a few relevant newsletter writers or community maintainers | A short individual note with the demo and a reason it fits their readers |
| Week 4 | Publish fixes based on actual setup reports | Before/after behavior, contributor credits with permission, release notes |

Spread posts across days so you can answer questions and repair setup problems. Adapt each post to its audience. Check current rules before posting; do not paste the same announcement into many communities.

[Show HN](https://news.ycombinator.com/showhn.html) expects something people can try and prohibits asking friends for votes or comments. It also has [temporary restrictions for newer participants](https://news.ycombinator.com/showlim); check eligibility at launch. Reddit asks contributors to follow each community's rules and avoid repetitive promotion; read its [spam policy](https://support.reddithelp.com/hc/en-us/articles/360043504051-Spam) before choosing a subreddit.

## Draft posts

Edit these after the pilot. Add only results you measured and personal details you intend to make public.

### X

> I released Appy, my internship application workflow. It finds roles, skips ones already in Notion, and helps a local agent fill reviewed forms. An optional Gmail monitor tracks replies. Try the offline demo: https://github.com/Cole-Godfrey/appy

Use the video as the main attachment. A second post can show the skipped duplicate and explain the setup.

### LinkedIn

> I built Appy to keep job applications and recruiting replies connected.
>
> The workflow finds internships, checks what is already in a Notion tracker, and uses a local agent with Chrome and Simplify to help fill employer forms. The agent verifies a receipt before recording a submission. An optional Gmail monitor updates the right tracker row when replies arrive.
>
> I have made the project open source, with an offline demo and setup guide. You can inspect the scripts before connecting your own accounts.
>
> Repository: https://github.com/Cole-Godfrey/appy
>
> I would like feedback on setup: where does the guide first leave you unsure what to do?

### Reddit

Title: `I open sourced my internship application workflow with Notion tracking and Gmail follow-up`

> I built this for my own search and am sharing the code. Appy combines Python discovery scripts with instructions for a local browser agent. It checks a Notion tracker for duplicates, helps fill forms with Simplify, and records confirmed receipts. There is also an optional macOS Gmail monitor.
>
> You can run the offline demo without an API key. Live applications need your own browser/agent and service connections; the guide covers those separately.
>
> https://github.com/Cole-Godfrey/appy
>
> If you try it, which part of setup is least clear?

### Show HN

Title: `Show HN: Appy – an open-source internship application workflow`

> I built Appy for my own job search. It combines deterministic discovery and deduplication with a local agent that works through employer forms and records confirmed submissions in Notion.
>
> Discovery uses public internship feeds and Greenhouse/Ashby details, with optional TheirStack search. The optional macOS monitor uses Gmail Pub/Sub and durable history cursors, then asks a Codex agent to match replies to tracker rows.
>
> The offline demo uses the actual filters on fictional listings and needs only Python. Live setup needs several service connections. I would appreciate feedback on that setup and on cases where the deduplication misses a role.
>
> Code and setup: https://github.com/Cole-Godfrey/appy

### Newsletter / maintainer outreach

Subject: `Appy: an open source internship application workflow`

> Hi [name],
>
> Your [specific article or community thread] covers [relevant topic]. I built Appy, a local agent workflow for internship discovery, reviewed forms, and Notion tracking, with an optional Gmail reply monitor.
>
> The repo has a Python-only offline demo: https://github.com/Cole-Godfrey/appy
>
> It may fit a future roundup for readers working on [specific task]. Happy to answer technical questions if useful.

Personalize the bracketed fields. Send only to contacts whose work you have read; do not automate bulk outreach.

## What to measure

Once a week, record GitHub's available traffic/referrers, clones, new stars, setup reports, successful pilot setups, and outside contributions. Respect GitHub's retention window by recording aggregate figures regularly. Keep a private channel log with the post URL and date; do not track applicants.

Use those observations to choose the next action: fix repeated setup failures, expand a post that produced useful testers, or stop a channel that only produces low-quality traffic. There is no defensible star forecast before a pilot. Ask for a star once, after someone has found the project useful. Do not buy stars, trade votes, or invent adoption numbers.
