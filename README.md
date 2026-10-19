# Appy

A local AI-agent workflow for internship applications. The agent finds new roles, skips ones already in your Notion tracker, fills applications with Simplify in Chrome, enters emailed verification codes from Gmail, and records each confirmed submission in Notion.

## Requirements

- A local agent with Chrome control and Notion and Gmail MCP connections, such as Codex
- Chrome with [Simplify Copilot](https://simplify.jobs/copilot), signed in with your profile
- A Notion tracker database with Company, Position, Status, Next Action, application date, URL, and Resume Used
- Python 3.10+ (no packages)
- Optional: a [TheirStack](https://theirstack.com) API key

## Setup

```sh
git clone https://github.com/Cole-Godfrey/appy.git
cd appy
cp templates/*.md .
cp .env.example .env
```

1. Fill in `INFORMATION.md` and put your resume in this folder.
2. Set `NOTION_TRACKER_ID` in `.env` to your tracker's data source (`collection://…`).
3. Review `APPLICATION_GUIDE.md`; its answer preferences and permissions are the agent's rules.

Your profile, questions, next steps, `.env`, and PDFs are Git-ignored.

## Use

Open this folder in your agent and prompt it, for example:

> Submit 10 internship applications for SWE, ML, or quant roles. Follow APPLICATION_GUIDE.md, read INFORMATION.md, use Simplify in your own Chrome tab group, retrieve emailed verification codes through Gmail MCP, and check/update the tracker through Notion MCP. Add jobs only after confirmed submission. Put questions in QUESTIONS.md.

The agent exports the tracker and runs discovery itself:

```sh
python3 discover_jobs.py --tracker tmp/tracker.json > tmp/jobs.json
```

Tests: `python3 -m unittest`

MIT licensed.
